import os
import struct
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from clipharbor.gui import STYLE
from clipharbor.icons import ICON_SIZES, app_icon
from clipharbor.widgets import ComboBox


def test_windows_icon_has_small_bitmaps_and_large_png_frames():
    app = QApplication.instance() or QApplication([])
    data = (Path(__file__).resolve().parent.parent / "assets" / "app.ico").read_bytes()
    reserved, kind, count = struct.unpack_from("<HHH", data)
    assert (reserved, kind, count) == (0, 1, len(ICON_SIZES))
    icon = QIcon(str(Path(__file__).resolve().parent.parent / "assets" / "app.ico"))
    assert not app_icon().isNull()
    for n, size in enumerate(ICON_SIZES):
        width, height, _, _, planes, depth, length, offset = struct.unpack_from("<BBBBHHII", data, 6+n*16)
        assert (width or 256, height or 256) == (size, size)
        assert (planes, depth) == (1, 32) and offset+length <= len(data)
        assert data[offset:offset+4] == (b"\x89PNG" if size >= 128 else b"(\x00\x00\x00")
        assert icon.pixmap(size, size).width() == size


def test_custom_picker_retains_selection_data_and_keyboard_support():
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    picker = ComboBox()
    for title, value in (("高清", "1080p"), ("流畅", "720p"), ("省空间", "480p")):
        picker.addItem(title, value)
    picker.resize(280, 42)
    picker.show()
    app.processEvents()
    picker.showPopup()
    app.processEvents()
    view = picker.view()
    target = picker.model().index(1, 0)
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=view.visualRect(target).center())
    app.processEvents()
    assert picker.currentData() == "720p"
    picker.setFocus()
    QTest.keyClick(picker, Qt.Key.Key_Down)
    assert picker.currentData() == "480p"
    picker.showPopup()
    app.processEvents()
    QTest.keyClick(picker.view(), Qt.Key.Key_Escape)
    assert picker.currentData() == "480p"
    picker.close()
