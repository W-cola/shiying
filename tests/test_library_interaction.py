import copy
import os
import time
from pathlib import Path
from threading import Event

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QTextCursor
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from clipharbor.gui import Window, STYLE
from clipharbor.library import library_entries
from clipharbor.media import run_ffmpeg
from clipharbor.speech import TranscriptStore
from clipharbor.speech_gui import TranscriptEdit, TranscriptWorkspace, point_time, qposition
from clipharbor.store import Store


@pytest.fixture(scope="module")
def qt():
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(STYLE)
    yield app


def document(store, path=""):
    doc = store.create("原视频文案")
    doc.update(state="done", duration=8., local_path=str(path), segments=[{
        "text": "你好世界。", "original": "你好世界。", "start": 1., "end": 6., "words": [
            {"from": 0, "to": 2, "start": 1.2, "end": 2.}, {"from": 2, "to": 4, "start": 3.2, "end": 5.}]}])
    store.save(doc)
    return doc


def test_content_library_attaches_drafts_searches_body_and_retains_orphans(tmp_path):
    path = tmp_path/"source.mp4"
    record = {"id": "media", "title": "原视频", "kind": "video", "path": str(path), "time": "2026-10-23T08:00:00+08:00"}
    store = TranscriptStore(tmp_path/"data")
    original = document(store, path)
    draft = store.create("新稿")
    draft.update(local_path=str(store.folder(original["id"])/"audio.m4a"), segments=original["segments"])
    before = copy.deepcopy([record, original, draft])
    rows = library_entries([record], [draft, original], query="世界", has_text=True)
    assert len(rows) == 1 and rows[0]["id"] == "media"
    assert set(rows[0]["_doc_ids"]) == {original["id"], draft["id"]}
    assert [record, original, draft] == before
    assert not library_entries([record], [draft, original], kind="images")
    # Removing the media record must still leave readable transcripts in the library.
    orphan = library_entries([], [draft, original], kind="video", has_text=True)
    assert len(orphan) == 1 and len(orphan[0]["_doc_ids"]) == 2


def test_point_seek_uses_token_time_old_span_and_utf16(tmp_path):
    doc = document(TranscriptStore(tmp_path))
    assert point_time(doc, 2) == 3.2
    assert point_time(doc, 4) == 3.2  # Punctuation uses the nearest actual token.
    assert point_time(doc, 5) is None
    doc["segments"][0]["words"] = []
    assert point_time(doc, 2) == 1.
    doc["segments"][0]["text"] = "😀你好"
    doc["segments"][0]["words"] = [{"from": 1, "to": 3, "start": 2.5, "end": 4.}]
    assert point_time(doc, qposition("😀你好", 1)) == 2.5
    doc["edited_text"] = "修改后的文字"
    assert point_time(doc, 2) is None


def text_point(editor, position):
    cursor = editor.textCursor()
    cursor.setPosition(position)
    return editor.cursorRect(cursor).center()+QPoint(2, 0)


def test_real_text_click_drag_blank_and_edit_mode(qt):
    editor = TranscriptEdit()
    editor.setReadOnly(True)
    editor.setPlainText("你好世界。\n这是下一段。")
    editor.resize(420, 220)
    editor.show()
    qt.processEvents()
    points = []
    editor.pointSelected.connect(points.append)
    QTest.mouseClick(editor.viewport(), Qt.MouseButton.LeftButton, pos=text_point(editor, 2))
    assert points == [2]
    QTest.mouseClick(editor.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(390, 20))
    QTest.mouseClick(editor.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(20, 190))
    assert points == [2]
    QTest.mousePress(editor.viewport(), Qt.MouseButton.LeftButton, pos=text_point(editor, 0))
    QTest.mouseMove(editor.viewport(), text_point(editor, 4))
    QTest.mouseRelease(editor.viewport(), Qt.MouseButton.LeftButton, pos=text_point(editor, 4))
    assert editor.textCursor().hasSelection() and points == [2]
    QTest.mouseDClick(editor.viewport(), Qt.MouseButton.LeftButton, pos=text_point(editor, 1))
    assert points == [2]
    editor.setReadOnly(False)
    QTest.mouseClick(editor.viewport(), Qt.MouseButton.LeftButton, pos=text_point(editor, 2))
    assert points == [2]
    editor.close()


def spin(qt, predicate, seconds=5):
    until = time.monotonic()+seconds
    while not predicate() and time.monotonic() < until:
        qt.processEvents()
        time.sleep(.02)
    assert predicate()


def test_click_then_play_real_audio_seek_during_play_and_drag_selection(qt, tmp_path):
    workspace = TranscriptWorkspace(tmp_path)
    doc = document(workspace.store)
    audio = workspace.store.folder(doc["id"])/"audio.m4a"
    run_ffmpeg(["-f", "lavfi", "-i", "sine=frequency=440", "-t", "8", "-c:a", "aac", audio], Event())
    workspace.show_document(doc)
    workspace.resize(1050, 750)
    workspace.show()
    spin(qt, lambda: workspace.player.duration() > 7000)
    QTest.mouseClick(workspace.editor.viewport(), Qt.MouseButton.LeftButton, pos=text_point(workspace.editor, 2))
    assert workspace.player.position() == 3200 and workspace.play.text() == "从此处播放"
    assert workspace.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState
    workspace.play.click()
    spin(qt, lambda: workspace.player.position() > 3350)
    assert workspace.player.position() < 4500
    QTest.mouseClick(workspace.editor.viewport(), Qt.MouseButton.LeftButton, pos=text_point(workspace.editor, 0))
    assert 1200 <= workspace.player.position() < 2000
    assert workspace.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
    workspace.player.pause()
    cursor = workspace.editor.textCursor()
    cursor.setPosition(2)
    cursor.setPosition(4, QTextCursor.MoveMode.KeepAnchor)
    workspace.editor.setTextCursor(cursor)
    workspace.play.click()
    assert workspace.stop_at == 5000
    spin(qt, lambda: workspace.player.playbackState() == QMediaPlayer.PlaybackState.PausedState, 4)
    assert workspace.player.position() == 5000
    workspace.shutdown()
    workspace.close()


def test_unified_library_filters_fulltext_and_reader_back(qt, tmp_path):
    store = Store(tmp_path/"data")
    path = tmp_path/"video.mp4"
    path.write_bytes(b"fixture")
    from clipharbor.models import VideoInfo
    store.add_history(VideoInfo("", "", "id", "原视频"), path)
    window = Window(store)
    doc = document(window.speech.store, path)
    window.refresh_history()
    window.switch_page(1)
    window.history_has_text.click()
    window.history_search.setText("世界")
    assert window.history.rowCount() == 1
    window.history.selectRow(0)
    assert window.library_buttons[1].isEnabled()
    window.library_buttons[1].click()
    assert window.stack.currentWidget() is window.speech and window.nav_history.isChecked()
    window.speech.back_button.click()
    assert window.stack.currentIndex() == 1 and window.history_search.text() == "世界"
    window.history_kind.group.button(2).click()
    assert window.history.rowCount() == 0 and not window.library_buttons[1].isEnabled()
    window.close()
