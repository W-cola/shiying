"""Shared desktop pickers: consistent popup rows, selection and keyboard support."""
from PySide6.QtCore import Qt, QSize, QRectF, QEvent, QPoint, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QFont, QFontMetrics
from PySide6.QtWidgets import (QComboBox, QListView, QFrame, QStyledItemDelegate, QStyle,
    QVBoxLayout, QGraphicsDropShadowEffect, QPlainTextEdit, QWidget, QHBoxLayout, QPushButton, QButtonGroup)


class LibraryTitleDelegate(QStyledItemDelegate):
    """One elided title and one quieter metadata line, regardless of pasted newlines."""
    def paint(self, painter, option, index):
        painter.save()
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        painter.fillRect(option.rect, QColor("#e0f1e6" if selected else "#ffffff"))
        title_font = QFont(option.font)
        title_font.setWeight(QFont.Weight.DemiBold)
        meta_font = QFont(option.font)
        if meta_font.pixelSize() > 0:
            meta_font.setPixelSize(max(11, meta_font.pixelSize()-1))
        else:
            meta_font.setPointSizeF(max(8, meta_font.pointSizeF()-1))
        first, second = QFontMetrics(title_font), QFontMetrics(meta_font)
        rect = option.rect.adjusted(12, 0, -12, 0)
        top = rect.top()+(rect.height()-first.height()-second.height()-5)//2
        painter.setFont(title_font)
        painter.setPen(QColor("#244f39"))
        title = " ".join(str(index.data() or "").split())
        painter.drawText(QRectF(rect.left(), top, rect.width(), first.height()), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         first.elidedText(title, Qt.TextElideMode.ElideRight, rect.width()))
        painter.setFont(meta_font)
        painter.setPen(QColor("#789080"))
        painter.drawText(QRectF(rect.left(), top+first.height()+5, rect.width(), second.height()), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         second.elidedText(str(index.data(Qt.ItemDataRole.UserRole+1) or ""), Qt.TextElideMode.ElideRight, rect.width()))
        painter.restore()


class FilterBar(QWidget):
    currentIndexChanged = Signal(int)

    def __init__(self, items, parent=None):
        super().__init__(parent)
        self.items = items
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        box = QHBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(4)
        for index, (title, value) in enumerate(items):
            button = QPushButton(title)
            button.setObjectName("filterChip")
            button.setCheckable(True)
            self.group.addButton(button, index)
            box.addWidget(button)
        self.group.button(0).setChecked(True)
        self.group.idClicked.connect(self.currentIndexChanged)

    def currentData(self):
        return self.items[self.group.checkedId()][1]

    def setCurrentIndex(self, index):
        if index != self.group.checkedId():
            self.group.button(index).setChecked(True)
            self.currentIndexChanged.emit(index)


class ShareInput(QPlainTextEdit):
    submitted = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.composing = False

    def inputMethodEvent(self, event):
        self.composing = bool(event.preeditString())
        super().inputMethodEvent(event)

    def keyPressEvent(self, event):
        if (not self.composing and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            self.submitted.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class PickerDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        return QSize(size.width() + 44, max(38, size.height() + 16))

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        current = index.row() == self.parent().currentIndex()
        rect = QRectF(option.rect).adjusted(2, 1, -2, -1)
        painter.setPen(Qt.PenStyle.NoPen)
        if selected or current:
            painter.setBrush(QColor("#E8F3EB" if selected else "#F2F7F3"))
            painter.drawRoundedRect(rect, 7, 7)
        painter.setPen(QColor("#1D6544" if current else "#31533F"))
        font = option.font
        font.setBold(current)
        painter.setFont(font)
        text_rect = option.rect.adjusted(13, 0, -35, 0)
        text = option.fontMetrics.elidedText(str(index.data() or ""), Qt.TextElideMode.ElideRight, text_rect.width())
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
        if current:
            painter.setPen(QPen(QColor("#278357"), 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            x, y = option.rect.right() - 20, option.rect.center().y()
            painter.drawLine(x - 4, y, x - 1, y + 3)
            painter.drawLine(x - 1, y + 3, x + 5, y - 3)
        painter.restore()


class PickerPopup(QFrame):
    hidden = Signal()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.hidden.emit()


class ComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.popup = PickerPopup(self, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
        self.popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.popup.setObjectName("pickerPopup")
        outer = QVBoxLayout(self.popup)
        outer.setContentsMargins(10, 8, 10, 12)
        card = QFrame()
        card.setObjectName("pickerCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(6, 6, 6, 6)
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(17, 52, 34, 35))
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)
        view = QListView(card)
        view.setObjectName("pickerList")
        view.setFrameShape(QFrame.Shape.NoFrame)
        view.setUniformItemSizes(True)
        view.setSpacing(2)
        view.setMouseTracking(True)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        view.setModel(self.model())
        view.setItemDelegate(PickerDelegate(self))
        view.installEventFilter(self)
        view.clicked.connect(lambda index: self.choose(index.row()))
        layout.addWidget(view)
        self.popup_view = view
        self.popup.hidden.connect(lambda: QComboBox.hidePopup(self))
        self.setMaxVisibleItems(8)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def showPopup(self):
        if not self.count():
            return
        self.popup_view.setModel(self.model())
        index = self.model().index(self.currentIndex(), self.modelColumn(), self.rootModelIndex())
        self.popup_view.setCurrentIndex(index)
        rows = min(self.count(), self.maxVisibleItems())
        height = rows * 42 + 36
        screen = self.screen().availableGeometry()
        width = min(max(150, self.width()) + 20, screen.width() - 16)
        height = min(height, screen.height() - 24)
        below = self.mapToGlobal(QPoint(-10, self.height()-1))
        x = max(screen.left()+8, min(below.x(), screen.right()-width-8))
        y = below.y() if below.y()+height <= screen.bottom()-8 else self.mapToGlobal(QPoint(0, 0)).y()-height+1
        y = max(screen.top()+8, y)
        self.popup.resize(width, height)
        self.popup.move(x, y)
        self.popup.show()
        self.popup_view.scrollTo(index)
        self.popup_view.setFocus(Qt.FocusReason.PopupFocusReason)

    def hidePopup(self):
        self.popup.hide()
        super().hidePopup()

    def view(self):
        return self.popup_view

    def choose(self, row):
        if row < 0 or row >= self.count():
            return
        self.setCurrentIndex(row)
        self.hidePopup()
        self.setFocus(Qt.FocusReason.PopupFocusReason)
        self.activated.emit(row)
        self.textActivated.emit(self.itemText(row))

    def eventFilter(self, watched, event):
        if watched is self.popup_view and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.choose(self.popup_view.currentIndex().row())
                return True
            if event.key() == Qt.Key.Key_Escape:
                self.hidePopup()
                self.setFocus(Qt.FocusReason.PopupFocusReason)
                return True
        return super().eventFilter(watched, event)
