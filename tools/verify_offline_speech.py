"""Verify real local ASR, pause/resume and Qt replay with a supplied speech WAV.

Run with --models <directory with the three manifest files> --audio <speech.wav>.
Media, transcripts and reports stay under .tmp; no network is allowed in inference.
"""
import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path
from threading import Event

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
from clipharbor.media import run_ffmpeg
from clipharbor.models import Cancelled
from clipharbor.speech import LocalSpeech, TranscriptStore, document_text
from clipharbor.speech_models import SpeechModels


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", required=True, type=Path)
    parser.add_argument("--audio", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=root/".tmp/offline-speech")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    data = output/"data"
    models = SpeechModels(data)
    models.root.mkdir(parents=True, exist_ok=True)
    for item in models.files:
        if not models.verify(models.root/item["name"], item, Event()):
            assert models.verify(args.models/item["name"], item, Event()), item["name"]
            shutil.copy2(args.models/item["name"], models.root/item["name"])
    import requests
    original_request = requests.sessions.Session.request
    def no_network(*a, **kw):
        raise AssertionError("Local speech unexpectedly attempted a network request")
    requests.sessions.Session.request = no_network
    store = TranscriptStore(data)
    started = time.perf_counter()
    doc = store.create("中文原声 · 离线验证")
    result = LocalSpeech(store, Event()).run(doc, local_path=args.audio)
    assert result["state"] == "done" and document_text(result)
    assert any(p.get("words") for p in result["segments"])
    normal_seconds = time.perf_counter()-started
    repeated = output/"repeated.wav"
    run_ffmpeg(["-stream_loop", "3", "-i", args.audio, "-ac", "1", "-ar", "16000", repeated], Event())
    paused = store.create("暂停与检查点验证")
    cancel = Event()
    def stop_after_phrase(update):
        if update["segments"]:
            cancel.set()
    try:
        LocalSpeech(store, cancel, updated=stop_after_phrase).run(paused, local_path=repeated)
        raise AssertionError("Cancellation did not pause")
    except Cancelled:
        pass
    paused = store.read(paused["id"])
    assert paused["state"] == "paused" and 0 < paused["resume"] < paused["duration"]
    first = dict(paused["segments"][0])
    resumed = LocalSpeech(store, Event()).run(paused)
    assert resumed["state"] == "done" and resumed["segments"][0] == first
    assert len(resumed["segments"]) > 1
    assert all(b["start"] >= a["end"]-.001 for a, b in zip(resumed["segments"], resumed["segments"][1:]))
    silence = output/"silence.wav"
    run_ffmpeg(["-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", "2", silence], Event())
    quiet = LocalSpeech(store, Event()).run(store.create("无声验证"), local_path=silence)
    assert quiet["state"] == "unclear" and not document_text(quiet)
    quiet = LocalSpeech(store, Event()).run(quiet, force=True)
    assert quiet["state"] == "unclear" and not document_text(quiet)
    from PySide6.QtWidgets import QApplication
    from PySide6.QtMultimedia import QMediaPlayer
    from clipharbor.gui import Window, STYLE
    from clipharbor.store import Store
    from clipharbor.windows import diagnose_window
    from clipharbor.speech_gui import selection_range
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = Window(Store(data))
    window.switch_page(2)
    workspace = window.speech
    workspace.show_document(result)
    workspace.refresh()
    window.show()
    deadline = time.monotonic()+5
    while not workspace.player.duration() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.02)
    assert workspace.player.duration() > 0
    workspace.toggle_play()
    deadline = time.monotonic()+5
    while workspace.player.position() < 200 and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.02)
    assert workspace.player.position() >= 200 and workspace.player.error() == QMediaPlayer.Error.NoError
    workspace.player.pause()
    bounds = selection_range(result, 0, 2)
    assert bounds and bounds[1] > bounds[0]
    workspace.stop_at = int(bounds[1]*1000)
    workspace.player.setPosition(workspace.stop_at-100)
    workspace.player.play()
    deadline = time.monotonic()+3
    while workspace.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.02)
    assert workspace.player.playbackState() == QMediaPlayer.PlaybackState.PausedState
    assert abs(workspace.player.position()-int(bounds[1]*1000)) < 80
    # Exercise the real GUI worker/signals as well as the backend directly.
    before_history = window.store.records()
    assert workspace.start_local(args.audio, "本地导入 · 后台识别验证")
    deadline = time.monotonic()+30
    while workspace.worker and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.02)
    assert workspace.worker is None and workspace.current["state"] == "done"
    assert document_text(workspace.current)
    assert window.store.records() == before_history
    app.processEvents()
    window.grab().save(str(output/"原声文案.png"))
    report = {"ok": True, "network_blocked": True, "local_sample_seconds": result["duration"],
              "recognition_seconds": normal_seconds, "text": document_text(result), "word_timestamps": True,
              "pause_resume": True, "silent_audio_rejected": True, "real_audio_replay": True,
              "selection_boundary_stop": True, "gui_background_import": True,
              "window_identity": diagnose_window(window)}
    assert workspace.start_local(repeated, "关闭时暂停验证")
    window.close()
    deadline = time.monotonic()+30
    while (workspace.worker or window.isVisible()) and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.02)
    assert workspace.worker is None and not window.isVisible()
    report["graceful_worker_shutdown"] = True
    requests.sessions.Session.request = original_request
    (output/"report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
