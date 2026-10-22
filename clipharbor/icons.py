"""Vector application identity and Windows icon export."""
import struct
from pathlib import Path

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QRectF
from PySide6.QtGui import QIcon, QImage, QPainter, QColor
from PySide6.QtSvg import QSvgRenderer

from . import _resources  # noqa: F401 -- registers packaged Qt resources

ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def app_icon():
    from PySide6.QtGui import QPixmap
    icon = QIcon()
    for size in ICON_SIZES:
        icon.addPixmap(QPixmap.fromImage(render_icon(size)))
    return icon


def glyph(name, color="#335b46"):
    """Small stroke icons share a consistent weight at every display scale."""
    paths = {
        "play": '<path d="m9 5 11 7-11 7z" fill="currentColor" stroke="none"/>',
        "pause": '<path d="M8 5v14M16 5v14" stroke-width="3.5"/>',
        "volume": '<path d="M11 5 6 9H3v6h3l5 4zM15 8a6 6 0 0 1 0 8M18 5a10 10 0 0 1 0 14"/>',
        "muted": '<path d="M11 5 6 9H3v6h3l5 4zM16 9l6 6m0-6-6 6"/>',
        "expand": '<path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/>',
        "collapse": '<path d="M3 8h5V3m8 0v5h5M8 21v-5H3m18 0h-5v5"/>',
        "more": '<circle cx="5" cy="12" r="1.3" fill="currentColor"/><circle cx="12" cy="12" r="1.3" fill="currentColor"/><circle cx="19" cy="12" r="1.3" fill="currentColor"/>',
        "close": '<path d="m6 6 12 12M18 6 6 18"/>',
        "rotate": '<path d="M3 9a9 9 0 1 1 1 9M3 3v6h6"/>',
        "folder": '<path d="M3 6h7l2 3h9v11H3zM3 6V4h7l2 2h7v3"/>',
        "chevron": '<path d="m8 4 8 8-8 8"/>',
        "download": '<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',
    }
    body = paths.get(name, paths["more"])
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" color="{color}" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    icon = QIcon()
    from PySide6.QtGui import QPixmap
    for size in (24, 48, 72):
        pix = QPixmap(size, size)
        pix.fill(QColor(0, 0, 0, 0))
        painter = QPainter(pix)
        renderer.render(painter)
        painter.end()
        icon.addPixmap(pix)
    return icon


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
