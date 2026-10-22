import hashlib
import json
import os
import zipfile
from pathlib import Path
from threading import Event

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtCore import QUrl
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication, QMessageBox

from clipharbor.models import AppError, Cancelled, VideoInfo, VideoFormat
from clipharbor.speech import TranscriptStore, document_text, text_ranges, word_timings
from clipharbor.speech_models import SpeechModels
from clipharbor.speech_gui import TranscriptWorkspace, selection_range
from clipharbor.gui import Window
from clipharbor.store import Store


def fake_models(tmp_path):
    models = SpeechModels(tmp_path/"data")
    content = b"validated model content"
    models.files = [{"name": "model.int8.onnx", "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest(), "url": "https://example.org/model"}]
    models.root.mkdir(parents=True)
    return models, content


def test_model_integrity_and_cancel(tmp_path):
    models, content = fake_models(tmp_path)
    target = models.root/"model.int8.onnx"
    target.write_bytes(content)
    models.validate(Event())
    target.write_bytes(b"X"+content[1:])
    assert models.ready()  # Size alone never authorizes inference.
    with pytest.raises(AppError):
        models.validate(Event())
    cancel = Event()
    cancel.set()
    with pytest.raises(Cancelled):
        models.verify(target, models.files[0], cancel)


def test_offline_zip_rejects_tampering_paths_preserves_previous(tmp_path):
    models, content = fake_models(tmp_path)
    target = models.root/"model.int8.onnx"
    target.write_bytes(content)
    archive = tmp_path/"pack.zip"
    for name, payload in (("../model.int8.onnx", content), ("model.int8.onnx", b"X"+content[1:])):
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr(name, payload)
        with pytest.raises(AppError):
            models.import_zip(archive, Event())
        assert target.read_bytes() == content
    target.unlink()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("model.int8.onnx", content)
    models.import_zip(archive, Event())
    models.validate(Event())


def test_download_resumes_and_validates_hash(tmp_path, monkeypatch):
    models, content = fake_models(tmp_path)
    partial = models.root/"model.int8.onnx.part"
    partial.write_bytes(content[:6])
    requests = []
    class Response:
        status_code = 206
        headers = {"Content-Range": f"bytes 6-{len(content)-1}/{len(content)}"}
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def raise_for_status(self): pass
        def iter_content(self, size): yield content[6:]
    def request(url, **kwargs):
        requests.append(kwargs)
        return Response()
    monkeypatch.setattr("clipharbor.speech_models.requests.get", request)
    models.download(models.files[0], Event(), lambda n: None)
    assert requests[0]["headers"]["Range"] == "bytes=6-"
    assert not partial.exists()
    models.validate(Event())


def example_document(store):
    doc = store.create("测试原声", "", "本地文件")
    doc.update(state="done", duration=8, segments=[{"start": 1., "end": 4., "text": "你好世界。", "original": "你好世界。",
        "words": [{"from": 0, "to": 2, "start": 1.2, "end": 2.}, {"from": 2, "to": 4, "start": 2.6, "end": 3.7}]}])
    store.save(doc)
    return doc


def test_transcript_edits_search_and_independent_delete(tmp_path):
    original = tmp_path/"original.mp4"
    original.write_bytes(b"original media")
    store = TranscriptStore(tmp_path/"data")
    doc = example_document(store)
    assert store.rows("世界")[0]["id"] == doc["id"]
    assert document_text(store.edit(doc["id"], "修改的文稿")) == "修改的文稿"
    assert not text_ranges(store.read(doc["id"]))
    assert document_text(store.restore_original(doc["id"])) == "你好世界。"
    assert not store.rows("修改的文稿")
    with pytest.raises(AppError):
        store.delete("../outside")
    store.delete(doc["id"])
    assert original.is_file() and not store.rows()


def test_real_word_times_and_selection_boundaries(tmp_path):
    store = TranscriptStore(tmp_path)
    doc = example_document(store)
    assert selection_range(doc, 2, 4) == (2.6, 3.7)
    assert selection_range(doc, 0, 2) == (1.2, 2.)
    assert selection_range(doc, 0, 0) is None
    doc["edited_text"] = "任意修改"
    assert selection_range(doc, 0, 2) is None
    words = word_timings("你好。", ["<|zh|>", "你", "好", "。"], [0, .3, 1.5, 2.1], [], 4., 7.)
    assert words[0]["start"] == 4.3 and words[1]["start"] == 5.5
    assert word_timings("你好", ["你"], [], [], 0, 3) == []


@pytest.fixture(scope="module")
def qt():
    yield QApplication.instance() or QApplication([])


def test_workspace_edit_copy_recovery_and_play_boundary(qt, tmp_path, monkeypatch):
    workspace = TranscriptWorkspace(tmp_path)
    doc = example_document(workspace.store)
    workspace.show_document(doc)
    workspace.refresh()
    workspace.search.setText("世界")
    assert workspace.library.count() == 1
    workspace.copy_text()
    assert QApplication.clipboard().text() == "你好世界。"
    workspace.toggle_edit()
    workspace.editor.setPlainText("手动校对的正文")
    workspace.save_edit()
    assert workspace.store.read(doc["id"])["edited_text"] == "手动校对的正文"
    workspace.restore_original()
    assert workspace.editor.toPlainText() == "你好世界。"
    workspace.stop_at = 2700
    workspace.position_changed(2800)
    assert workspace.stop_at is None
    workspace.current["state"] = "working"
    workspace.show_document(workspace.current)
    assert workspace.current["state"] == "paused" and workspace.run_button.isEnabled()
    workspace.shutdown()


def test_desktop_has_video_saved_media_and_local_import_entries(qt, tmp_path, monkeypatch):
    window = Window(Store(tmp_path/"data"))
    window.nav_history.click()
    assert window.stack.currentIndex() == 1
    assert window.library_import.isEnabled()
    called = []
    monkeypatch.setattr(window.speech, "start_online", lambda info, fmt: called.append(info.title))
    info = VideoInfo("https://example.org/v", "https://example.org/v", "id", "视频文案", formats=[VideoFormat("main", "原画")])
    window.info = info
    window.formats.clear()
    window.formats.addItem("原画")
    window.transcribe_video()
    assert called == ["视频文案"]
    window.close()
