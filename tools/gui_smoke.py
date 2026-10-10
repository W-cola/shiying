"""Render the actual Qt widgets and verify state transitions without a desktop."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase, QFont
from PySide6.QtCore import QTimer
from clipharbor.gui import Window, STYLE
from clipharbor.models import VideoInfo, VideoFormat
from clipharbor.store import Store

app = QApplication([])
app.setStyle("Fusion")
for font in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/segoeui.ttf"):
    QFontDatabase.addApplicationFont(font)
app.setFont(QFont("Microsoft YaHei", 10))
app.setStyleSheet(STYLE)
window = Window(Store(Path(".tmp/gui-test-data")))
window.resize(1120, 1040)
window.show()
app.processEvents()
window.link_input.setPlainText("https://v.douyin.com/78nnhuQHT8k/")
window.operation = "resolve"
info = VideoInfo("https://v.douyin.com/78nnhuQHT8k/", "https://www.douyin.com/video/7693840282563565674",
                 "7693840282563565674", "抖音视频 7693840282563565674", "口罩哥研报60秒", 83.734,
                 platform="抖音", formats=[VideoFormat("0", "播放画质 · 854×480")])
window.completed(info)
assert window.info.video_id == info.video_id
assert window.formats.count() == 1
assert "口罩哥" in window.video_meta.text()
window.download_button.setEnabled(True)
window.formats.setEnabled(True)
window.source_button.setEnabled(True)
sample = next(Path("downloads").glob("*.mp4"), None)
if sample:
    window.operation = "download"
    window.completed(sample.resolve())
    assert window.progress_bar.value() == 100
    assert window.history.rowCount() >= 1
app.processEvents()
window.grab().save(".tmp/app-preview.png")
window.switch_page(1)
assert window.stack.currentIndex() == 1
window.switch_page(0)
window.link_input.setPlainText("新的链接")
assert window.info is None
assert not window.download_button.isEnabled()
window.resolve(False)
def finish():
    if window.worker:
        QTimer.singleShot(30, finish)
        return
    assert "未完成" in window.status.text()
    assert window.resolve_button.isEnabled()
    print("GUI smoke passed; fonts:", len(QFontDatabase.families()))
    app.quit()
QTimer.singleShot(30, finish)
QTimer.singleShot(10000, app.quit)
app.exec()
