"""Opt-in live check: real resolve -> inline first frame, without saving history."""
import argparse
import json
import os
import sys
import time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("source")
parser.add_argument("--output", default=".tmp/preview-ux")
args = parser.parse_args()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication
from PySide6.QtMultimedia import QMediaPlayer
from clipharbor.gui import Window, STYLE
from clipharbor.store import Store

output = (root / args.output).resolve()
output.mkdir(parents=True, exist_ok=True)
app = QApplication([])
for font in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/segoeui.ttf"):
    QFontDatabase.addApplicationFont(font)
app.setStyle("Fusion")
app.setStyleSheet(STYLE)
app.setFont(QFont("Microsoft YaHei UI", 10))
window = Window(Store(output / "data"))
window.resize(1180, 890)
window.show()
window.link_input.setPlainText(args.source)
start = time.perf_counter()
metrics = {}
window.resolve(False)
window.worker.log.connect(lambda message: print(f"{time.perf_counter()-start:.2f}s {message}", flush=True))
deadline = start + 65
while time.perf_counter() < deadline:
    app.processEvents()
    if window.info and "resolve_seconds" not in metrics:
        metrics["resolve_seconds"] = round(time.perf_counter()-start, 3)
        metrics["id"] = window.info.video_id
        metrics["formats"] = len(window.info.formats)
    if window.inline_preview.media.loaded_frame:
        metrics["first_frame_seconds"] = round(time.perf_counter()-start, 3)
        break
    if not window.busy() and window.info is None:
        raise RuntimeError(window.detail.text())
    time.sleep(.01)
media = window.inline_preview.media
assert media.loaded_frame, "No decoded frame reached the inline preview"
assert media.player.playbackState() == QMediaPlayer.PlaybackState.PausedState
metrics["initial_state"] = "first frame paused; click to play"
assert not window.viewers, "Resolving must not open a separate player"
assert window.download_button.isEnabled(), "Preview must not block saving"
assert not window.store.records(), "Preview must not add library history"
metrics["save_enabled"] = True
metrics["extra_windows"] = 0
metrics["history_added"] = 0
window.grab().save(str(output / "inline-preview.png"))
media.toggle()
deadline = time.perf_counter()+8
while time.perf_counter() < deadline and media.player.position() < 300:
    app.processEvents()
    time.sleep(.02)
assert media.player.position() >= 300
metrics["playback"] = "decoded and advanced"
media.player.pause()
media.show_settings()
app.processEvents()
media.settings_panel.grab().save(str(output / "playback-settings.png"))
media.settings_panel.hide()
window.close()
deadline = time.perf_counter()+12
while window.isVisible() and time.perf_counter() < deadline:
    app.processEvents()
    time.sleep(.02)
assert not window.isVisible(), "Window failed to close cleanly"
(output / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
print(json.dumps(metrics, ensure_ascii=False), flush=True)
