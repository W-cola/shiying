"""Render the actual desktop widgets for visual review without downloading media."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication, QCheckBox, QDialog, QHBoxLayout, QLabel, QSlider, QVBoxLayout
from clipharbor.gui import Window, STYLE
from clipharbor.icons import app_icon
from clipharbor.models import VideoFormat, VideoInfo
from clipharbor.store import Store
from clipharbor.widgets import ComboBox

output = root / ".tmp" / "style-review"
output.mkdir(parents=True, exist_ok=True)
app = QApplication([])
for font in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/segoeui.ttf"):
    QFontDatabase.addApplicationFont(font)
app.setStyle("Fusion")
app.setStyleSheet(STYLE)
app.setFont(QFont("Microsoft YaHei UI", 10))
app.setWindowIcon(app_icon())
window = Window(Store(output / "data"))
window.resize(1120, 1030)
window.show()
window.operation = "resolve"
window.completed(VideoInfo("", "", "preview", "把喜欢的内容，留在自己手里", "拾影", 128, platform="B站",
    formats=[VideoFormat(str(i), name) for i, name in enumerate(("1080P · 高清画质", "720P · 流畅画质", "480P · 节省空间"))]))
for widget in (window.formats, window.preview_button, window.audio_button, window.source_button, window.download_button):
    widget.setEnabled(True)
app.processEvents()
window.grab().save(str(output / "main.png"))
window.formats.showPopup()
app.processEvents()
window.formats.view().window().grab().save(str(output / "picker.png"))
window.formats.hidePopup()

dialog = QDialog()
dialog.resize(760, 250)
box = QVBoxLayout(dialog)
box.setContentsMargins(24, 20, 24, 20)
box.addWidget(QLabel("播放器与筛选控件"))
row = QHBoxLayout()
for values in (("全部片段", "视频", "图文", "音频"), ("0.5×", "0.75×", "1×", "1.25×", "1.5×", "2×")):
    picker = ComboBox()
    picker.addItems(values)
    row.addWidget(picker)
check = QCheckBox("循环播放")
check.setChecked(True)
row.addWidget(check)
row.addWidget(QCheckBox("自动整理"))
box.addLayout(row)
for title, value in (("播放进度", 38), ("音量", 80), ("画面亮度", 50)):
    row = QHBoxLayout()
    row.addWidget(QLabel(title))
    slider = QSlider(Qt.Orientation.Horizontal)
    slider.setValue(value)
    row.addWidget(slider, 1)
    box.addLayout(row)
dialog.show()
app.processEvents()
dialog.grab().save(str(output / "controls.png"))
dialog.close()
window.close()
print(output)
