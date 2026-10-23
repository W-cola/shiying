import copy
import os
import shutil
import time
from pathlib import Path
from threading import Event

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QApplication, QMessageBox

from clipharbor.gui import Window, STYLE
from clipharbor.library import library_entries, available_forms
from clipharbor.media import run_ffmpeg
from clipharbor.models import VideoInfo, SavedMedia
from clipharbor.player import PlayerDialog
from clipharbor.speech import TranscriptStore
from clipharbor.store import Store


@pytest.fixture(scope="module")
def qt():
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(STYLE)
    yield app


@pytest.fixture(scope="module")
def media(tmp_path_factory):
    folder = tmp_path_factory.mktemp("forms-media")
    video, audio = folder/"source.mp4", folder/"source.m4a"
    run_ffmpeg(["-f", "lavfi", "-i", "testsrc2=s=160x90:r=15", "-f", "lavfi", "-i", "sine=frequency=440", "-t", "3", "-c:v", "libx264", "-c:a", "aac", video], Event())
    run_ffmpeg(["-i", video, "-vn", "-c:a", "copy", audio], Event())
    return video, audio


def add_document(store, source, audio):
    doc = store.create("同一内容的文案")
    doc.update(local_path=str(source), state="done", duration=3,
               segments=[{"text": "可以回听的正文", "original": "可以回听的正文", "start": 0, "end": 3}])
    store.save(doc)
    shutil.copy2(audio, store.folder(doc["id"])/"audio.m4a")
    return doc


def test_group_video_audio_and_transcript_preserves_all_records(tmp_path, media):
    video, audio = media
    store = Store(tmp_path/"data")
    info = VideoInfo("https://example.org/item/1", "", "1", "一个内容")
    store.add_history(info, video)
    store.add_history(info, SavedMedia(audio, [audio], "audio"))
    transcripts = TranscriptStore(store.root)
    doc = add_document(transcripts, video, audio)
    records = store.records()
    before = copy.deepcopy(records)
    rows = library_entries(records, [doc])
    assert len(rows) == 1 and rows[0]["kind"] == "video" and len(rows[0]["_records"]) == 2
    forms = available_forms(rows[0], {doc["id"]: doc}, transcripts.root)
    assert all(len(forms[kind]) == 1 for kind in ("video", "audio", "text"))
    assert forms["audio"][0]["path"] == str(audio)  # Prefer saved audio over its replay copy.
    assert records == before
    assert library_entries(records[1:], [doc])[0]["id"] == rows[0]["id"]
    assert len(library_entries(records, [doc], kind="audio")) == 1


def test_replay_cache_survives_missing_video_and_origin_link(tmp_path, media):
    video, audio = media
    deleted = tmp_path/"removed.mp4"
    transcripts = TranscriptStore(tmp_path/"data")
    doc = add_document(transcripts, deleted, audio)
    record = {"id": "audio", "kind": "audio", "path": str(audio), "origin_path": str(deleted), "title": "声音", "time": ""}
    row = library_entries([record], [doc])[0]
    assert row["_doc_ids"] == [doc["id"]]
    orphan = library_entries([], [doc])[0]
    forms = available_forms(orphan, {doc["id"]: doc}, transcripts.root)
    assert not forms["video"] and forms["audio"][0]["cached"] and forms["text"]


def test_new_draft_cache_is_audio_and_recovers_local_video(tmp_path, media):
    video, audio = media
    transcripts = TranscriptStore(tmp_path/"data")
    cache = tmp_path/"older-replay.m4a"
    shutil.copy2(audio, cache)
    doc = add_document(transcripts, cache, audio)
    doc.update(origin=str(video), media_kind="video")
    entry = library_entries([], [doc])[0]
    forms = available_forms(entry, {doc["id"]: doc}, transcripts.root)
    assert len(forms["video"]) == 1 and Path(forms["video"][0]["path"]) == video
    assert len(forms["audio"]) == 1 and Path(forms["audio"][0]["path"]) == cache
    doc["origin"] = str(tmp_path/"missing.mp4")
    forms = available_forms(library_entries([], [doc])[0], {doc["id"]: doc}, transcripts.root)
    assert not forms["video"] and forms["audio"] and forms["text"]


def test_inline_forms_and_has_text_filter_keep_video_default(qt, tmp_path, media, monkeypatch):
    video, audio = media
    store = Store(tmp_path/"data")
    store.add_history(VideoInfo("https://example.org/item", "", "1", "视频内容"), video)
    window = Window(store)
    doc = add_document(window.speech.store, video, audio)
    window.refresh_history()
    window.switch_page(1)
    window.history_has_text.click()
    window.history.selectRow(0)
    entry = window.selected_entry()
    shown = []
    monkeypatch.setattr(window, "show_viewer", lambda result, *args: shown.append(result))
    assert all((entry["id"], kind) in window.library_form_buttons for kind in ("video", "audio", "text"))
    window.open_history(0, 0)
    assert shown[-1].kind == "video" and window.stack.currentIndex() == 1
    window.library_form_buttons[(entry["id"], "audio")].click()
    assert shown[-1].kind == "audio" and Path(shown[-1].path).name == "audio.m4a"
    window.library_form_buttons[(entry["id"], "text")].click()
    assert window.speech.current["id"] == doc["id"] and window.stack.currentIndex() == 2
    window.speech.back_button.click()
    window.history_kind.setCurrentIndex(3)
    assert window.history.rowCount() == 1  # Audio replay is a form of this same content.
    window.close()


def test_context_menu_targets_clicked_row_and_versions(qt, tmp_path, media, monkeypatch):
    video, audio = media
    store = Store(tmp_path/"data")
    same = VideoInfo("https://example.org/one", "", "one", "第一条")
    store.add_history(same, video)
    second_version = tmp_path/"version-2.mp4"
    shutil.copy2(video, second_version)
    store.add_history(same, second_version)
    store.add_history(VideoInfo("https://example.org/two", "", "two", "第二条"), audio)
    window = Window(store)
    doc = add_document(window.speech.store, video, audio)
    window.refresh_history()
    window.switch_page(1)
    window.show()
    qt.processEvents()
    row = next(i for i in range(window.history.rowCount()) if window.history.item(i, 0).data(256)["title"] == "第一条")
    window.history.selectRow(1-row)
    window.library_context_menu(window.history.visualItemRect(window.history.item(row, 0)).center())
    assert window.selected_entry()["title"] == "第一条"
    shown = []
    monkeypatch.setattr(window, "show_viewer", lambda result, *args: shown.append(result))
    versions = next(a.menu() for a in window.library_menu.actions() if a.menu() and a.text().startswith("看视频"))
    versions.actions()[0].trigger()
    assert Path(shown[-1].path) == second_version
    window.library_menu.close()
    menu = window.build_library_menu(window.selected_entry())
    next(a for a in menu.actions() if a.text() == "听原声").trigger()
    assert shown[-1].kind == "audio"
    next(a for a in menu.actions() if a.text() == "读文案").trigger()
    assert window.speech.current["id"] == doc["id"]
    menu.close()
    window.close()


def test_audio_view_plays_without_video_only_controls(qt, media):
    audio = media[1]
    dialog = PlayerDialog(SavedMedia(audio, [audio], "audio"), "原声验证")
    dialog.audio.setMuted(True)
    dialog.show()
    deadline = time.monotonic()+5
    while dialog.player.position() < 150 and time.monotonic() < deadline:
        qt.processEvents()
        time.sleep(.02)
    assert dialog.player.position() >= 150 and dialog.player.error() == QMediaPlayer.Error.NoError
    assert dialog.surface.property("audio") and not dialog.media.fullscreen.isVisible()
    assert not dialog.rotate.isVisible() and dialog.height() < 400
    dialog.media.hide_controls()
    assert dialog.media.controls.isVisible()
    dialog.close()
    qt.processEvents()


def test_delete_only_selected_form_keeps_video_transcript_and_replay(qt, tmp_path, media, monkeypatch):
    video, audio = tmp_path/"saved.mp4", tmp_path/"saved.m4a"
    shutil.copy2(media[0], video)
    shutil.copy2(media[1], audio)
    store = Store(tmp_path/"data")
    info = VideoInfo("https://example.org/one", "", "1", "同一内容")
    store.add_history(info, video)
    store.add_history(info, SavedMedia(audio, [audio], "audio"))
    window = Window(store)
    doc = add_document(window.speech.store, video, audio)
    window.refresh_history()
    window.history.selectRow(0)
    entry = window.selected_entry()
    menu = window.build_library_menu(entry)
    deletions = next(a.menu() for a in menu.actions() if a.menu() and a.text().startswith("删除"))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **kw: QMessageBox.StandardButton.Yes)
    next(a for a in deletions.actions() if a.text() == audio.name).trigger()
    assert not audio.exists() and video.is_file()
    assert window.speech.store.read(doc["id"])["segments"]
    assert (window.speech.store.folder(doc["id"])/"audio.m4a").is_file()
    assert len(store.records()) == 1 and window.history.rowCount() == 1
    menu.close()
    window.close()
