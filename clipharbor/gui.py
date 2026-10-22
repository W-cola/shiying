import sys
from datetime import datetime
from pathlib import Path
from threading import Event

from PySide6.QtCore import Qt, QThread, Signal, QUrl, QMimeData
from PySide6.QtGui import QColor, QDesktopServices, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QApplication, QFileDialog, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
    QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QHeaderView, QScrollArea)

from .engine import Engine, safe_message
from .models import AppError, Cancelled, VideoInfo, SavedMedia, human_duration, human_size
from .store import Store
from .icons import app_icon
from .widgets import ComboBox as QComboBox
from . import __version__

STYLE = """
* { font-family: 'Microsoft YaHei UI', 'Microsoft YaHei', sans-serif; font-size: 14px; }
QMainWindow, QDialog, QWidget#main { background: #f4f7f5; color: #173b2f; }
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
QComboBox { min-height: 20px; padding: 9px 42px 9px 12px; }
QComboBox:hover { background: #f4faf6; border-color: #9cbea7; }
QComboBox:focus, QComboBox:on { border-color: #45976a; background: #f4faf6; }
QComboBox:disabled { background: #f5f8f5; color: #9aafa0; border-color: #e2eae3; }
QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 38px; border: none; background: transparent; }
QComboBox::down-arrow { image: url(:/shiying/chevron-down.svg); width: 16px; height: 16px; }
QComboBox::down-arrow:disabled { image: url(:/shiying/chevron-disabled.svg); }
QComboBox QAbstractItemView { background: #ffffff; border: 1px solid #cddfd2; border-radius: 10px; padding: 5px; outline: none; color: #31533f; selection-background-color: transparent; }
QFrame#pickerPopup { background: transparent; border: none; }
QFrame#pickerCard { background: #ffffff; border: 1px solid #cddfd2; border-radius: 12px; }
QListView#pickerList { background: transparent; border: none; padding: 0; outline: none; selection-background-color: transparent; }
QCheckBox { spacing: 8px; color: #42624d; }
QCheckBox::indicator { width: 18px; height: 18px; border: 1px solid #c5d7ca; border-radius: 5px; background: #ffffff; }
QCheckBox::indicator:hover { border-color: #70aa83; background: #f0f7f1; }
QCheckBox::indicator:checked { background: #278357; border-color: #278357; image: url(:/shiying/check.svg); }
QCheckBox::indicator:disabled { border-color: #dfe8e1; background: #f2f6f3; }
QSlider::groove:horizontal { height: 6px; background: #dfe9e2; border: none; border-radius: 3px; }
QSlider::sub-page:horizontal { background: #2a8b5b; border-radius: 3px; }
QSlider::add-page:horizontal { background: #dfe9e2; border-radius: 3px; }
QSlider::handle:horizontal { background: #ffffff; border: 2px solid #2a8b5b; width: 12px; height: 12px; margin: -5px 0; border-radius: 8px; }
QSlider::handle:horizontal:hover { background: #dff0e4; border-color: #176e44; }
QSlider::handle:horizontal:pressed { background: #278357; }
QFrame#playerControls { background: #f4f8f5; border-top: 1px solid #dce7de; }
QToolTip { color: #244c35; background: #f4faf5; border: 1px solid #ccdfd0; padding: 6px 9px; }
QMenu { color: #31533f; background: #ffffff; border: 1px solid #d4e2d8; border-radius: 10px; padding: 6px; }
QMenu::item { padding: 9px 22px; border-radius: 6px; }
QMenu::item:selected { background: #e8f3eb; color: #1d6544; }
QMenu::separator { height: 1px; background: #e5ece6; margin: 4px 8px; }
QProgressBar { border: none; border-radius: 4px; background: #eaf0eb; max-height: 8px; min-height: 8px; }
QProgressBar::chunk { background: #2e9b65; border-radius: 4px; }
QTableWidget { border: none; background: white; gridline-color: #eff2ef; color: #2d4b39; selection-background-color: #e0f1e6; selection-color: #173b2f; }
QHeaderView::section { background: #f7faf8; color: #728176; border: none; border-bottom: 1px solid #e6eee8; padding: 12px; text-align: left; }
QPlainTextEdit#logs { font-family: 'Cascadia Code', 'Microsoft YaHei UI'; font-size: 12px; background: #f7faf8; color: #63806d; }
QScrollBar:vertical { background: #f1f5f2; width: 8px; }
QScrollBar::handle:vertical { background: #cad7cd; min-height: 20px; border-radius: 4px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: #f1f5f2; height: 8px; }
QScrollBar::handle:horizontal { background: #cad7cd; min-width: 20px; border-radius: 4px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
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
        self.viewers = []
        self.pending_info = None
        self.setWindowTitle("拾影 · 视频、图文与原声")
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
        self.nav_download = QPushButton("↓    收下内容")
        self.nav_history = QPushButton("≡    我的片段")
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
        sidebar.addWidget(label(f"拾影桌面版  /  v{__version__}", "sideCaption"))
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
        titles.addWidget(label("把喜欢的内容，收进本地", "headline"))
        titles.addWidget(label("视频、整组图文和原声，在电脑上收藏与播放。", "muted"))
        header.addLayout(titles, 1)
        header.addWidget(label("●  本地运行", "badge"))
        box.addLayout(header)

        form, formbox = self.panel()
        row = QHBoxLayout()
        row.addWidget(label("01", "section"))
        row.addWidget(label("添加分享链接", "section"), 1)
        self.clear_button = QPushButton("清空")
        self.clear_button.clicked.connect(self.clear_input)
        row.addWidget(self.clear_button)
        paste = QPushButton("粘贴剪贴板")
        paste.clicked.connect(lambda: self.link_input.setPlainText(QApplication.clipboard().text()))
        row.addWidget(paste)
        formbox.addLayout(row)
        self.link_input = QPlainTextEdit()
        self.link_input.setPlaceholderText("粘贴抖音、小红书、B站、快手或视频号分享文字…\n支持单条视频、图文与媒体直链。\n视频号 sph 分享链接使用与安卓版相同的在线解析服务。")
        self.link_input.setFixedHeight(115)
        self.link_input.textChanged.connect(self.link_changed)
        formbox.addWidget(self.link_input)
        actions = QHBoxLayout()
        actions.addWidget(label("自动提取整段分享文字中的链接", "muted"), 1)
        self.browser_button = QPushButton("浏览器辅助解析")
        self.browser_button.setToolTip("打开独立浏览器，可手动完成登录或验证码。请播放目标视频，读取到地址后会自动返回。")
        self.browser_button.clicked.connect(lambda: self.resolve(True))
        actions.addWidget(self.browser_button)
        self.resolve_button = QPushButton("解析内容  →")
        self.resolve_button.setObjectName("primary")
        self.resolve_button.clicked.connect(lambda: self.resolve(False))
        actions.addWidget(self.resolve_button)
        formbox.addLayout(actions)
        box.addWidget(form)

        preview, pb = self.panel()
        row = QHBoxLayout()
        row.addWidget(label("02", "section"))
        row.addWidget(label("内容与保存设置", "section"), 1)
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
        self.format_caption = label("视频画质")
        row.addWidget(self.format_caption)
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
        media_actions = QHBoxLayout()
        self.preview_button = QPushButton("应用内播放 / 预览")
        self.preview_button.setEnabled(False)
        self.preview_button.clicked.connect(self.preview)
        self.audio_button = QPushButton("只收下声音 · M4A")
        self.audio_button.setEnabled(False)
        self.audio_button.clicked.connect(self.extract_sound)
        media_actions.addWidget(self.preview_button)
        media_actions.addWidget(self.audio_button)
        media_actions.addStretch()
        pb.addLayout(media_actions)
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
        box.addWidget(label("我的片段", "headline"))
        box.addWidget(label("视频、图文和音频集中收藏。双击即可在应用内播放或预览。", "muted"))
        filters = QHBoxLayout()
        self.history_kind = QComboBox()
        for title, kind in (("全部", ""), ("视频", "video"), ("图文", "images"), ("音频", "audio")):
            self.history_kind.addItem(title, kind)
        self.history_search = QLineEdit()
        self.history_search.setPlaceholderText("搜索标题或作者")
        self.history_search.setClearButtonEnabled(True)
        filters.addWidget(self.history_kind)
        filters.addWidget(self.history_search, 1)
        box.addLayout(filters)
        self.history_kind.currentIndexChanged.connect(self.refresh_history)
        self.history_search.textChanged.connect(self.refresh_history)
        panel, pb = self.panel()
        self.history = QTableWidget(0, 4)
        self.history.setHorizontalHeaderLabels(["内容", "来源 / 类型", "大小", "保存时间"])
        self.history.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.history.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.history.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.history.verticalHeader().hide()
        self.history.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for index in (1, 2, 3):
            self.history.horizontalHeader().setSectionResizeMode(index, QHeaderView.ResizeMode.ResizeToContents)
        self.history.cellDoubleClicked.connect(self.open_history)
        pb.addWidget(self.history)
        actions = QHBoxLayout()
        for text, callback in (("播放 / 预览", self.play_record), ("提取原声", self.extract_record),
                               ("复制文件", self.copy_record), ("打开位置", self.reveal_record),
                               ("重新解析", self.resolve_record), ("删除", self.delete_record)):
            button = QPushButton(text)
            button.clicked.connect(callback)
            actions.addWidget(button)
        pb.addLayout(actions)
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
            self.preview_button.setEnabled(False)
            self.audio_button.setEnabled(False)
            self.download_button.setText("↓  保存内容")
            self.format_caption.setText("视频画质")

    def append_log(self, text):
        self.logs.appendPlainText(datetime.now().strftime("%H:%M:%S") + "  " + text)

    def start(self, action, args):
        if self.busy():
            return
        self.operation = action
        self.pending_info = args[0] if args and isinstance(args[0], VideoInfo) else None
        self.progress_bar.setRange(0, 0)
        self.percent.setText("")
        self.status.setText("正在解析…" if action == "resolve" else "正在下载…")
        self.detail.setText("请稍候，可随时取消任务。")
        for widget in (self.link_input, self.resolve_button, self.browser_button, self.download_button,
                       self.folder_button, self.formats, self.preview_button, self.audio_button, self.clear_button):
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
            self.download_button.setText("↓  保存图文" if result.kind == "images" else "↓  保存视频")
            self.format_caption.setText("保存范围" if result.kind == "images" else "视频画质")
            self.preview_button.setText("应用内预览图文" if result.kind == "images" else "应用内播放")
            self.detail.setText(f"共 {len(result.images)} 张图片，可保存整组或选择单张，并附带正文。" if result.kind == "images" else "选择画质后播放、保存视频，或只保存声音。")
            self.append_log("解析成功，已匹配视频 ID " + result.video_id)
        elif self.operation == "prepare_preview":
            if self.closing:
                import shutil
                shutil.rmtree(result.cache_dir, ignore_errors=True)
                return
            self.show_viewer(result, self.pending_info.title, self.pending_info.description)
            self.status.setText("应用内预览")
            self.detail.setText("预览不会新增下载记录；关闭播放器后清理临时文件。")
        else:
            saved = result if isinstance(result, SavedMedia) else SavedMedia(result, [result], "video")
            self.last_path = Path(saved.path)
            try:
                self.store.add_history(self.pending_info or self.info, saved)
            except OSError:
                self.append_log("视频已保存，但下载记录写入失败。")
            self.progress_bar.setValue(100)
            self.percent.setText("100%")
            self.status.setText("下载完成")
            self.detail.setText(f"已保存 {human_size(sum(Path(p).stat().st_size for p in saved.files))} · {self.last_path.name}")
            self.append_log("保存位置：" + str(self.last_path))
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
        for widget in (self.link_input, self.resolve_button, self.browser_button, self.folder_button, self.clear_button):
            widget.setEnabled(True)
        self.download_button.setEnabled(self.info is not None)
        self.formats.setEnabled(self.info is not None)
        self.source_button.setEnabled(self.info is not None)
        self.preview_button.setEnabled(self.info is not None)
        self.audio_button.setEnabled(self.info is not None and self.info.kind != "images")
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
        rows = self.store.records(self.history_kind.currentData() or "", self.history_search.text())
        self.history.setRowCount(len(rows))
        for row, item in enumerate(rows):
            kind = {"video": "视频", "images": "图文", "audio": "音频"}.get(item.get("kind", "video"), "视频")
            for column, text in enumerate((item.get("title", "未命名"), item.get("platform", "") + " · " + kind, human_size(item.get("size", 0)), item.get("time", "").replace("T", " ")[:16])):
                cell = QTableWidgetItem(text)
                cell.setData(Qt.ItemDataRole.UserRole, item)
                cell.setToolTip(item.get("title", "") + "\n" + item.get("author", "") + "\n" + item["path"])
                self.history.setItem(row, column, cell)
            self.history.setRowHeight(row, 48)

    def open_history(self, row, column):
        self.play_record()

    def clear_input(self):
        if not self.busy():
            self.link_input.clear()
            self.link_changed()
            self.status.setText("准备就绪")
            self.detail.setText("粘贴一条新的分享链接。")
            self.progress_bar.setValue(0)

    def preview(self):
        if self.info and not self.busy():
            self.start("prepare_preview", (self.info, self.info.formats[self.formats.currentIndex()]))

    def extract_sound(self):
        if self.info and self.info.kind != "images" and not self.busy():
            self.start("extract_audio", (self.info, self.info.formats[self.formats.currentIndex()], Path(self.folder_input.text()) / "原声"))

    def selected_record(self):
        row = self.history.currentRow()
        return self.history.item(row, 0).data(Qt.ItemDataRole.UserRole) if row >= 0 else None

    def show_viewer(self, result, title, description=""):
        from .player import GalleryDialog, PlayerDialog
        dialog = GalleryDialog(result, title, description, self) if result.kind == "images" else PlayerDialog(result, title, self)
        self.viewers.append(dialog)
        dialog.destroyed.connect(lambda: self.viewers.remove(dialog) if dialog in self.viewers else None)
        dialog.show()

    def play_record(self):
        record = self.selected_record()
        if not record:
            return
        files = [Path(x) for x in record.get("files") or [record["path"]]]
        if not files or any(not path.is_file() for path in files):
            QMessageBox.information(self, "文件不可用", "文件已移动或删除，可选择「重新解析」再次保存。")
            return
        self.show_viewer(SavedMedia(Path(record["path"]), files, record.get("kind", "video")), record["title"], record.get("description", ""))

    def extract_record(self):
        record = self.selected_record()
        if not record or self.busy():
            return
        if record.get("kind", "video") != "video":
            QMessageBox.information(self, "选择视频", "请先选择一条已保存的视频，再提取原声。")
            return
        info = VideoInfo(record.get("url", ""), record.get("url", ""), Path(record["path"]).stem[-30:], record["title"],
                         record.get("author", ""), platform=record.get("platform", ""))
        self.start("extract_audio", (info, None, Path(self.folder_input.text()) / "原声", Path(record["path"])))

    def copy_record(self):
        record = self.selected_record()
        if record:
            mime = QMimeData()
            mime.setUrls([QUrl.fromLocalFile(x) for x in record.get("files") or [record["path"]] if Path(x).is_file()])
            QApplication.clipboard().setMimeData(mime)
            QMessageBox.information(self, "文件已复制", "可以粘贴到文件夹或支持接收文件的聊天窗口中。")

    def reveal_record(self):
        record = self.selected_record()
        if record:
            path = Path(record["path"])
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path if path.is_dir() else path.parent)))

    def resolve_record(self):
        record = self.selected_record()
        if record and not self.busy():
            self.link_input.setPlainText(record.get("url", ""))
            self.switch_page(0)
            self.resolve(False)

    def delete_record(self):
        record = self.selected_record()
        if not record or self.busy():
            return
        if self.viewers:
            QMessageBox.information(self, "请先关闭预览", "关闭播放器或图文预览后，再删除本地文件。")
            return
        answer = QMessageBox.question(self, "删除这条片段？", "将删除这条记录及本次保存的实际文件。图文会整组删除，包括正文。\n其他批次的文件会保留。",
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
        if answer == QMessageBox.StandardButton.Yes:
            try:
                self.store.delete_record(record)
                self.refresh_history()
            except OSError as error:
                QMessageBox.warning(self, "未能完成删除", str(error))

    def closeEvent(self, event):
        if self.worker:
            self.closing = True
            self.cancel()
            self.status.setText("正在停止任务并关闭…")
            event.ignore()
        else:
            for viewer in list(self.viewers):
                viewer.close()
            event.accept()


def run():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    app.setFont(QFont("Microsoft YaHei UI", 10))
    app.setWindowIcon(app_icon())
    window = Window()
    window.show()
    return app.exec()
