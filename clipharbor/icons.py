"""Vector application identity and Windows icon export."""
import struct
from pathlib import Path

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QRectF
from PySide6.QtGui import QIcon, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

from . import _resources  # noqa: F401 -- registers packaged Qt resources

ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def app_icon():
    return QIcon(":/shiying/app.svg")


def render_icon(size):
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(":/shiying/app.svg").render(painter, QRectF(0, 0, size, size))
    painter.end()
    return image


def png_bytes(image):
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, "PNG"):
        raise RuntimeError("图标 PNG 导出失败。")
    return bytes(data)


def dib_bytes(image):
    """32-bit BGRA DIB plus legacy AND mask, for reliable small shell icons."""
    image = image.convertToFormat(QImage.Format.Format_ARGB32)
    size, stride = image.width(), image.bytesPerLine()
    pixels = bytes(image.constBits())
    rows = [pixels[y*stride:y*stride+size*4] for y in range(size-1, -1, -1)]
    mask_stride = ((size + 31) // 32) * 4
    mask = bytearray(mask_stride * size)
    for row, data in enumerate(rows):
        for x in range(size):
            if data[x*4+3] == 0:
                mask[row*mask_stride+x//8] |= 128 >> (x % 8)
    bitmap = b"".join(rows)
    header = struct.pack("<IiiHHIIiiII", 40, size, size*2, 1, 32, 0, len(bitmap), 0, 0, 0, 0)
    return header + bitmap + bytes(mask)


def export_icons(folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    render_icon(512).save(str(folder / "app.png"))
    chunks, entries = [], []
    offset = 6 + 16 * len(ICON_SIZES)
    for size in ICON_SIZES:
        image = render_icon(size)
        data = dib_bytes(image) if size < 128 else png_bytes(image)
        entries.append(struct.pack("<BBBBHHII", size if size < 256 else 0, size if size < 256 else 0,
                                   0, 0, 1, 32, len(data), offset))
        chunks.append(data)
        offset += len(data)
    (folder / "app.ico").write_bytes(struct.pack("<HHH", 0, 1, len(entries)) + b"".join(entries) + b"".join(chunks))
