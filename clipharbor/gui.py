import sys
from datetime import datetime
from pathlib import Path
from threading import Event

from PySide6.QtCore import Qt, QThread, Signal, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QApplication, QComboBox, QFileDialog, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
    QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QHeaderView, QScrollArea)

from .engine import Engine, safe_message
from .models import AppError, Cancelled, human_duration, human_size
from .store import Store

STYLE = """
* { font-family: 'Microsoft YaHei UI', 'Microsoft YaHei', sans-serif; font-size: 14px; }
QMainWindow, QWidget#main { background: #f4f7f5; color: #173b2f; }
QFrame#sidebar { background: #132d24; }
QLabel { color: #173b2f; background: transparent; }
QLabel#logo { color: #effbf2; font-size: 30px; font-weight: 700; }
QLabel#sideCaption { color: #98b0a2; font-size: 12px; }
QLabel#headline { font-size: 27px; font-weight: 700; }
QLabel#muted { color: #708378; font-size: 13px; }
QLabel#eyebrow { color: #359768; font-weight: 600; font-size: 11px; }
QLabel#number { color: #198359; font-size: 34px; font-weight: 700; }
QLabel#section { font-size: 17px; font-weight: 600; }
QLabel#videoTitle { font-size: 17px; font-weight: 600; }
QLabel#badge { background: #e6f2e9; border-radius: 12px; color: #347550; padding: 6px 12px; font-size: 12px; }
QLabel#art { background: #e9f5ee; color: #238757; border-radius: 12px; font-size: 35px; }
QFrame#panel { background: white; border: 1px solid #e2eae5; border-radius: 15px; }
QPushButton { background: white; color: #35604b; border: 1px solid #d6e2d9; border-radius: 8px; padding: 10px 17px; font-weight: 600; }
QPushButton:hover { background: #eff7f1; border-color: #9ec7ab; }
QPushButton:pressed { background: #d9ebde; }
QPushButton:disabled { color: #a2b1a7; background: #f3f5f3; border-color: #e5ebe6; }
QPushButton#primary { background: #218956; color: white; border: none; }
QPushButton#primary:hover { background: #176d42; }
QPushButton#primary:disabled { background: #a4c5b1; color: #f3f6f4; }
QPushButton#nav { color: #b2c6bb; background: transparent; border: none; text-align: left; padding: 13px 16px; }
QPushButton#nav:checked { color: #e3f7e6; background: #274a37; }
QPushButton#nav:hover { background: #203f31; }
QPlainTextEdit, QLineEdit, QComboBox { background: #fafcfb; color: #284c3a; border: 1px solid #dce7de; border-radius: 8px; padding: 10px; selection-background-color: #c4e3d0; }
QPlainTextEdit:focus, QLineEdit:focus { border: 1px solid #55a477; }
QComboBox { min-height: 20px; }
QComboBox QAbstractItemView { background: white; selection-background-color: #d5eddd; color: #244832; }
QProgressBar { border: none; border-radius: 4px; background: #eaf0eb; max-height: 8px; min-height: 8px; }
QProgressBar::chunk { background: #2e9b65; border-radius: 4px; }
QTableWidget { border: none; background: white; gridline-color: #eff2ef; color: #2d4b39; selection-background-color: #e0f1e6; selection-color: #173b2f; }
QHeaderView::section { background: #f7faf8; color: #728176; border: none; border-bottom: 1px solid #e6eee8; padding: 12px; text-align: left; }
QPlainTextEdit#logs { font-family: 'Cascadia Code', 'Microsoft YaHei UI'; font-size: 12px; background: #f7faf8; color: #63806d; }
QScrollBar:vertical { background: #f1f5f2; width: 8px; }
QScrollBar::handle:vertical { background: #cad7cd; min-height: 20px; border-radius: 4px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


def label(text, name="", wrap=False):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    if name:
        widget.setObjectName(name)
    if name == "badge":
        widget.setFixedHeight(30)
    widget.setWordWrap(wrap)
    return widget


def app_icon():
    pix = QPixmap(128, 128)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#218956"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(0, 0, 128, 128, 29, 29)
    painter.setBrush(QColor("#eefbf1"))
    from PySide6.QtGui import QPolygonF
    from PySide6.QtCore import QPointF
    painter.drawPolygon(QPolygonF([QPointF(48, 33), QPointF(48, 95), QPointF(94, 64)]))
    painter.end()
    return QIcon(pix)


class Worker(QThread):
    log = Signal(str)
    progress = Signal(dict)
    result = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, data_dir, action, args):
        super().__init__()
        self.data_dir, self.action, self.args = data_dir, action, args
        self.cancel_event = Event()

    def run(self):
        try:
            engine = Engine(self.data_dir, self.log.emit, self.progress.emit, self.cancel_event)
            value = getattr(engine, self.action)(*self.args)
            self.result.emit(value)
        except Cancelled:
            self.cancelled.emit()
        except Exception as error:
            self.failed.emit(str(error) if isinstance(error, AppError) else "操作未完成：" + safe_message(error))


class Window(QMainWindow):
    def __init__(self, store=None):
        super().__init__()
        self.store = store or Store()
        self.info = None
        self.worker = None
        self.last_path = None
        self.operation = ""
        self.closing = False
        self.setWindowTitle("拾影 · 视频下载工具")
        self.setWindowIcon(app_icon())
        self.resize(1120, 920)
        self.setMinimumSize(960, 790)
        root = QWidget()
        root.setObjectName("main")
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(185)
        sidebar = QVBoxLayout(side)
        sidebar.setContentsMargins(20, 34, 20, 26)
        logo_row = QHBoxLayout()
        logo_mark = QLabel()
        logo_mark.setPixmap(app_icon().pixmap(32, 32))
        logo_row.addWidget(logo_mark)
        logo_row.addWidget(label("拾影", "logo"), 1)
        sidebar.addLayout(logo_row)
        sidebar.addWidget(label("让灵感，留在本地", "sideCaption"))
        sidebar.addSpacing(42)
        self.nav_download = QPushButton("↓    下载视频")
        self.nav_history = QPushButton("≡    下载记录")
        for b in (self.nav_download, self.nav_history):
            b.setObjectName("nav")
            b.setCheckable(True)
            sidebar.addWidget(b)
        self.nav_download.setChecked(True)
        sidebar.addStretch()
        sidebar.addWidget(label("LOCAL FIRST", "sideCaption"))
        sidebar.addSpacing(6)
        sidebar.addWidget(label("链接与会话保存在本机\n用于学习、研究和授权下载", "sideCaption", True))
        sidebar.addSpacing(16)
        sidebar.addWidget(label("拾影  /  v1.0", "sideCaption"))
        layout.addWidget(side)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(self.download_page())
        self.stack.addWidget(scroll)
        self.stack.addWidget(self.history_page())
        self.nav_download.clicked.connect(lambda: self.switch_page(0))
        self.nav_history.clicked.connect(lambda: self.switch_page(1))
        self.refresh_history()

    def switch_page(self, index):
        self.stack.setCurrentIndex(index)
        self.nav_download.setChecked(index == 0)
        self.nav_history.setChecked(index == 1)
        if index:
            self.refresh_history()

    def panel(self):
        frame = QFrame()
        frame.setObjectName("panel")
        box = QVBoxLayout(frame)
        box.setContentsMargins(24, 20, 24, 20)
        box.setSpacing(12)
        return frame, box

    def download_page(self):
        page = QWidget()
        page.setMinimumHeight(970)
        box = QVBoxLayout(page)
        box.setContentsMargins(32, 29, 32, 24)
        box.setSpacing(16)
        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.addWidget(label("CAPTURE YOUR INSPIRATION", "eyebrow"))
        titles.addWidget(label("把喜欢的视频，收进本地", "headline"))
        titles.addWidget(label("粘贴分享链接，预览视频信息，然后开始下载。", "muted"))
        header.addLayout(titles, 1)
        header.addWidget(label("●  本地运行", "badge"))
        box.addLayout(header)

        form, formbox = self.panel()
        row = QHBoxLayout()
        row.addWidget(label("01", "section"))
        row.addWidget(label("添加视频链接", "section"), 1)
        paste = QPushButton("粘贴剪贴板")
        paste.clicked.connect(lambda: self.link_input.setPlainText(QApplication.clipboard().text()))
        row.addWidget(paste)
        formbox.addLayout(row)
        self.link_input = QPlainTextEdit()
        self.link_input.setPlaceholderText("在这里粘贴抖音分享文字或视频链接…\n例如 https://v.douyin.com/xxxxxxxx/\n也支持 yt-dlp 可解析的单个视频网页和 MP4 直链。")
        self.link_input.setFixedHeight(115)
        self.link_input.textChanged.connect(self.link_changed)
        formbox.addWidget(self.link_input)
        actions = QHBoxLayout()
        actions.addWidget(label("自动提取整段分享文字中的链接", "muted"), 1)
        self.browser_button = QPushButton("浏览器辅助解析")
        self.browser_button.setToolTip("打开独立浏览器，可手动完成登录或验证码。请播放目标视频，读取到地址后会自动返回。")
        self.browser_button.clicked.connect(lambda: self.resolve(True))
        actions.addWidget(self.browser_button)
        self.resolve_button = QPushButton("解析视频  →")
        self.resolve_button.setObjectName("primary")
        self.resolve_button.clicked.connect(lambda: self.resolve(False))
        actions.addWidget(self.resolve_button)
        formbox.addLayout(actions)
        box.addWidget(form)

        preview, pb = self.panel()
        row = QHBoxLayout()
        row.addWidget(label("02", "section"))
        row.addWidget(label("视频与保存设置", "section"), 1)
        self.platform_badge = label("等待解析", "badge")
        row.addWidget(self.platform_badge)
        pb.addLayout(row)
        row = QHBoxLayout()
        row.setSpacing(18)
        art = label("", "art")
        art.setPixmap(app_icon().pixmap(56, 56))
        art.setFixedSize(72, 72)
        art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(art)
        vb = QVBoxLayout()
        self.video_title = label("视频信息将在这里显示", "videoTitle", True)
        self.video_title.setMinimumHeight(42)
        self.video_meta = label("解析完成后，可查看标题、作者、时长与可用画质。", "muted", True)
        self.video_meta.setMinimumHeight(22)
        vb.addWidget(self.video_title)
        vb.addWidget(self.video_meta)
        row.addLayout(vb, 1)
        pb.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(label("视频画质"))
        self.formats = QComboBox()
        self.formats.setEnabled(False)
        self.formats.addItem("先解析视频")
        row.addWidget(self.formats, 1)
        self.source_button = QPushButton("查看原视频")
        self.source_button.clicked.connect(self.open_source)
        self.source_button.setEnabled(False)
        row.addWidget(self.source_button)
        pb.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(label("保存位置"))
        self.folder_input = QLineEdit(self.store.settings["download_dir"])
        self.folder_input.setReadOnly(True)
        row.addWidget(self.folder_input, 1)
        self.folder_button = QPushButton("选择文件夹")
        self.folder_button.clicked.connect(self.choose_folder)
        row.addWidget(self.folder_button)
        pb.addLayout(row)
        box.addWidget(preview)

        progress_panel, pr = self.panel()
        row = QHBoxLayout()
        self.status = label("准备就绪", "section")
        row.addWidget(self.status, 1)
        self.percent = label("", "muted")
        row.addWidget(self.percent)
        pr.addLayout(row)
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setValue(0)
        pr.addWidget(self.progress_bar)
        self.detail = label("解析视频后即可开始下载。", "muted", True)
        pr.addWidget(self.detail)
        row = QHBoxLayout()
        self.open_button = QPushButton("打开保存文件夹")
        self.open_button.clicked.connect(self.open_folder)
        row.addWidget(self.open_button)
        row.addStretch()
        self.cancel_button = QPushButton("取消任务")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel)
        row.addWidget(self.cancel_button)
        self.download_button = QPushButton("↓  下载视频")
        self.download_button.setObjectName("primary")
        self.download_button.setEnabled(False)
        self.download_button.clicked.connect(self.download)
        row.addWidget(self.download_button)
        pr.addLayout(row)
        box.addWidget(progress_panel)
        self.logs = QPlainTextEdit()
        self.logs.setObjectName("logs")
        self.logs.setReadOnly(True)
        self.logs.document().setMaximumBlockCount(200)
        self.logs.setPlaceholderText("运行记录 · 解析与下载过程会显示在这里")
        self.logs.setMinimumHeight(65)
        self.logs.setMaximumHeight(95)
        box.addWidget(self.logs)
        return page

    def history_page(self):
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(32, 35, 32, 32)
        box.setSpacing(20)
        box.addWidget(label("你的本地视频库", "headline"))
        box.addWidget(label("最近 300 条完成记录。双击记录可打开文件所在位置。", "muted"))
        panel, pb = self.panel()
        self.history = QTableWidget(0, 4)
        self.history.setHorizontalHeaderLabels(["视频", "来源", "大小", "下载时间"])
        self.history.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.history.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.history.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.history.verticalHeader().hide()
        self.history.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for index in (1, 2, 3):
            self.history.horizontalHeader().setSectionResizeMode(index, QHeaderView.ResizeMode.ResizeToContents)
        self.history.cellDoubleClicked.connect(self.open_history)
        pb.addWidget(self.history)
        box.addWidget(panel, 1)
        return page

    def busy(self):
        return self.worker is not None

    def link_changed(self):
        if not self.busy():
            self.info = None
            self.download_button.setEnabled(False)
            self.source_button.setEnabled(False)
            self.formats.setEnabled(False)
            self.formats.clear()
            self.formats.addItem("先解析视频")
            self.video_title.setText("视频信息将在这里显示")
            self.video_meta.setText("解析完成后，可查看标题、作者、时长与可用画质。")
            self.platform_badge.setText("等待解析")

    def append_log(self, text):
        self.logs.appendPlainText(datetime.now().strftime("%H:%M:%S") + "  " + text)

    def start(self, action, args):
        if self.busy():
            return
        self.operation = action
        self.progress_bar.setRange(0, 0)
        self.percent.setText("")
        self.status.setText("正在解析…" if action == "resolve" else "正在下载…")
        self.detail.setText("请稍候，可随时取消任务。")
        for widget in (self.link_input, self.resolve_button, self.browser_button, self.download_button,
                       self.folder_button, self.formats):
            widget.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.worker = Worker(self.store.root, action, args)
        self.worker.log.connect(self.append_log)
        self.worker.log.connect(self.detail.setText)
        self.worker.progress.connect(self.update_progress)
        self.worker.result.connect(self.completed)
        self.worker.failed.connect(self.failed)
        self.worker.cancelled.connect(self.cancelled)
        self.worker.finished.connect(self.finished)
        self.worker.start()

    def resolve(self, interactive):
        self.link_changed()
        self.start("resolve", (self.link_input.toPlainText(), interactive))

    def download(self):
        if self.info and self.formats.currentIndex() >= 0:
            self.start("download", (self.info, self.info.formats[self.formats.currentIndex()], Path(self.folder_input.text())))

    def completed(self, result):
        self.progress_bar.setRange(0, 100)
        if self.operation == "resolve":
            self.info = result
            title = result.title if len(result.title) <= 100 else result.title[:100] + "…"
            self.video_title.setText(title)
            self.video_title.setToolTip(result.title)
            self.video_meta.setText(" · ".join(filter(None, [result.author, human_duration(result.duration), "ID " + result.video_id])))
            self.platform_badge.setText(result.platform)
            self.formats.clear()
            for f in result.formats:
                self.formats.addItem(f.label + (" · " + human_size(f.size) if f.size else ""))
            self.progress_bar.setValue(0)
            self.status.setText("解析完成")
            self.detail.setText("选择画质和保存位置，点击「下载视频」。")
            self.append_log("解析成功，已匹配视频 ID " + result.video_id)
        else:
            self.last_path = result
            try:
                self.store.add_history(self.info, result)
            except OSError:
                self.append_log("视频已保存，但下载记录写入失败。")
            self.progress_bar.setValue(100)
            self.percent.setText("100%")
            self.status.setText("下载完成")
            self.detail.setText(f"已保存 {human_size(result.stat().st_size)} · {result.name}")
            self.append_log("保存位置：" + str(result))
            self.refresh_history()

    def failed(self, message):
        self.progress_bar.setRange(0, 100)
        self.status.setText("操作未完成")
        self.detail.setText(message[:220])
        self.detail.setToolTip(message)
        self.append_log(message)

    def cancelled(self):
        self.progress_bar.setRange(0, 100)
        self.status.setText("任务已取消")
        self.detail.setText("下载中的临时文件会保留，可重新开始以续传。")
        self.append_log("任务已取消。")

    def finished(self):
        worker = self.worker
        self.worker = None
        worker.deleteLater()
        self.cancel_button.setEnabled(False)
        for widget in (self.link_input, self.resolve_button, self.browser_button, self.folder_button):
            widget.setEnabled(True)
        self.download_button.setEnabled(self.info is not None)
        self.formats.setEnabled(self.info is not None)
        self.source_button.setEnabled(self.info is not None)
        if self.closing:
            self.close()

    def cancel(self):
        if self.worker:
            self.worker.cancel_event.set()
            self.cancel_button.setEnabled(False)
            self.detail.setText("正在停止当前请求，请稍候…")

    def update_progress(self, p):
        if p["total"]:
            value = min(100, int(p["done"] * 100 / p["total"]))
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(value)
            self.percent.setText(f"{value}%")
        else:
            self.progress_bar.setRange(0, 0)
        text = human_size(p["done"]) + " / " + human_size(p["total"])
        if p["speed"]:
            text += "    ·    " + human_size(p["speed"]) + "/s"
        if p["eta"]:
            text += f"    ·    约剩余 {int(p['eta'])} 秒"
        self.detail.setText(text)

    def choose_folder(self):
        path = QFileDialog.getExistingDirectory(self, "选择视频保存位置", self.folder_input.text())
        if path:
            self.folder_input.setText(path)
            self.store.settings["download_dir"] = path
            try:
                self.store.save_settings()
            except OSError as error:
                self.failed("无法保存设置：" + str(error))

    def open_folder(self):
        folder = self.last_path.parent if self.last_path else Path(self.folder_input.text())
        try:
            folder.mkdir(parents=True, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        except OSError as error:
            self.failed("无法打开文件夹：" + str(error))

    def open_source(self):
        if self.info:
            QDesktopServices.openUrl(QUrl(self.info.page_url))

    def refresh_history(self):
        rows = self.store.read("history.json", [])
        self.history.setRowCount(len(rows))
        for row, item in enumerate(rows):
            for column, text in enumerate((item["title"], item["platform"], human_size(item["size"]), item["time"].replace("T", " ")[:16])):
                cell = QTableWidgetItem(text)
                cell.setData(Qt.ItemDataRole.UserRole, item["path"])
                self.history.setItem(row, column, cell)
            self.history.setRowHeight(row, 48)

    def open_history(self, row, column):
        path = Path(self.history.item(row, 0).data(Qt.ItemDataRole.UserRole))
        if path.parent.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))
        else:
            QMessageBox.information(self, "文件位置不可用", "文件可能已被移动，原保存文件夹已不存在。")

    def closeEvent(self, event):
        if self.worker:
            self.closing = True
            self.cancel()
            self.status.setText("正在停止任务并关闭…")
            event.ignore()
        else:
            event.accept()


def run():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    app.setFont(QFont("Microsoft YaHei UI", 10))
    window = Window()
    window.show()
    return app.exec()
