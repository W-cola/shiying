import sys
import time
from datetime import datetime
from pathlib import Path
from threading import Event

from PySide6.QtCore import Qt, QThread, Signal, QUrl, QMimeData, QTimer
from PySide6.QtGui import QColor, QDesktopServices, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QApplication, QFileDialog, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
    QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QHeaderView, QScrollArea, QSizePolicy, QMenu)

from .engine import Engine, safe_message
from .models import AppError, Cancelled, VideoInfo, SavedMedia, human_duration, human_size
from .store import Store
from .icons import app_icon, glyph
from .widgets import ComboBox as QComboBox, ShareInput
from . import __version__

STYLE = """
* { font-family: 'Microsoft YaHei UI', 'Microsoft YaHei', sans-serif; font-size: 14px; }
QMainWindow, QDialog, QWidget#main { background: #f4f7f5; color: #173b2f; }
QFrame#sidebar { background: #132d24; }
QLabel { color: #173b2f; background: transparent; }
QLabel#logo { color: #effbf2; font-size: 30px; font-weight: 700; }
QLabel#sideCaption { color: #98b0a2; font-size: 12px; }
QLabel#headline { font-size: 24px; font-weight: 700; }
QLabel#muted { color: #708378; font-size: 13px; }
QLabel#eyebrow { color: #359768; font-weight: 600; font-size: 11px; }
QLabel#number { color: #198359; font-size: 34px; font-weight: 700; }
QLabel#section { font-size: 17px; font-weight: 600; }
QLabel#videoTitle { font-size: 21px; font-weight: 600; }
QLabel#fieldCaption { font-size: 12px; color: #7a8a7d; }
QLabel#statusText { font-size: 12px; color: #3d7150; font-weight: 600; }
QLabel#badge { background: #e6f2e9; border-radius: 12px; color: #347550; padding: 6px 12px; font-size: 12px; }
QLabel#art { background: #e9f5ee; color: #238757; border-radius: 12px; font-size: 35px; }
QFrame#panel { background: white; border: 1px solid #e2eae5; border-radius: 15px; }
QFrame#composer { background: #ffffff; border: 1px solid #d8e2d9; border-radius: 18px; }
QFrame#resultCard { background: #ffffff; border: 1px solid #e1e8e2; border-radius: 18px; }
QPlainTextEdit#shareInput { border: none; background: transparent; padding: 6px 4px; font-size: 14px; }
QPushButton { background: white; color: #35604b; border: 1px solid #d6e2d9; border-radius: 8px; padding: 10px 17px; font-weight: 600; }
QPushButton:hover { background: #eff7f1; border-color: #9ec7ab; }
QPushButton:pressed { background: #d9ebde; }
QPushButton:disabled { color: #a2b1a7; background: #f3f5f3; border-color: #e5ebe6; }
QPushButton#primary { background: #218956; color: white; border: none; }
QPushButton#primary:hover { background: #176d42; }
QPushButton#primary:disabled { background: #a4c5b1; color: #f3f6f4; }
QPushButton#quiet { border: none; background: transparent; padding: 7px 10px; font-weight: 400; font-size: 12px; color: #6c8173; }
QPushButton#quiet:hover { background: #eef5ef; color: #2c6543; }
QPushButton#quiet:pressed { background: #dfece2; }
QPushButton#quiet:disabled { color: #b2beb5; }
QPushButton#nav { color: #b2c6bb; background: transparent; border: none; text-align: left; padding: 13px 16px; }
QPushButton#nav:checked { color: #e3f7e6; background: #274a37; }
QPushButton#nav:hover { background: #203f31; }
QPushButton#filterChip { border: none; background: transparent; padding: 9px 15px; color: #708378; font-weight: 400; }
QPushButton#filterChip:hover { background: #edf3ee; color: #315e44; }
QPushButton#filterChip:checked { background: #deeee3; color: #21633d; font-weight: 600; }
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
        self.resize(1180, 890)
        self.setMinimumSize(1000, 760)
        root = QWidget()
        root.setObjectName("main")
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(174)
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
        self.nav_history = QPushButton("≡    资料库")
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
        from .speech_gui import TranscriptWorkspace
        self.speech = TranscriptWorkspace(self.store.root)
        self.speech.stopped.connect(lambda: self.close() if self.closing else None)
        self.speech.backRequested.connect(lambda: self.switch_page(1))
        self.speech.libraryChanged.connect(self.refresh_history)
        self.stack.addWidget(self.speech)
        self.nav_download.clicked.connect(lambda: self.switch_page(0))
        self.nav_history.clicked.connect(lambda: self.switch_page(1))
        self.refresh_history()
        from .windows import bind_window
        bind_window(self)

    def switch_page(self, index):
        if index:
            self.inline_preview.media.player.pause()
        self.stack.setCurrentIndex(index)
        self.nav_download.setChecked(index == 0)
        self.nav_history.setChecked(index in (1, 2))
        if index == 1:
            self.refresh_history()

    def panel(self):
        frame = QFrame()
        frame.setObjectName("panel")
        box = QVBoxLayout(frame)
        box.setContentsMargins(24, 20, 24, 20)
        box.setSpacing(12)
        return frame, box

    def download_page(self):
        from .preview_widget import PreviewPane
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(28, 24, 28, 20)
        box.setSpacing(16)
        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(4)
        titles.addWidget(label("收下此刻的灵感", "headline"))
        titles.addWidget(label("分享链接，直接预览。喜欢的，再留在本地。", "muted"))
        header.addLayout(titles, 1)
        header.addWidget(label("●  本地收藏", "badge"))
        box.addLayout(header)

        form = QFrame()
        form.setObjectName("composer")
        fb = QVBoxLayout(form)
        fb.setContentsMargins(16, 10, 12, 10)
        fb.setSpacing(6)
        self.link_input = ShareInput()
        self.link_input.setObjectName("shareInput")
        self.link_input.setPlaceholderText("粘贴分享文字或链接…\n抖音 / 小红书 / B站 / 快手 / 视频号")
        self.link_input.setFixedHeight(70)
        self.link_input.textChanged.connect(self.link_changed)
        self.link_input.submitted.connect(lambda: self.resolve(False) if not self.busy() else None)
        fb.addWidget(self.link_input)
        actions = QHBoxLayout()
        paste = QPushButton("粘贴链接")
        paste.setObjectName("quiet")
        paste.clicked.connect(lambda: self.link_input.setPlainText(QApplication.clipboard().text()))
        actions.addWidget(paste)
        self.clear_button = QPushButton("清空")
        self.clear_button.setObjectName("quiet")
        self.clear_button.clicked.connect(self.clear_input)
        actions.addWidget(self.clear_button)
        self.browser_button = QPushButton("辅助解析")
        self.browser_button.setObjectName("quiet")
        self.browser_button.setToolTip("普通解析遇到登录或验证时，再打开独立浏览器手动完成。")
        self.browser_button.clicked.connect(lambda: self.resolve(True))
        actions.addWidget(self.browser_button)
        actions.addStretch()
        hint = label("Ctrl + Enter", "muted")
        actions.addWidget(hint)
        self.resolve_button = QPushButton("解析链接  →")
        self.resolve_button.setObjectName("primary")
        self.resolve_button.setEnabled(False)
        self.resolve_button.clicked.connect(lambda: self.resolve(False))
        actions.addWidget(self.resolve_button)
        fb.addLayout(actions)
        box.addWidget(form)

        result = QFrame()
        result.setObjectName("resultCard")
        rb = QHBoxLayout(result)
        rb.setContentsMargins(18, 18, 22, 18)
        rb.setSpacing(24)
        self.inline_preview = PreviewPane(self.store.root)
        self.inline_preview.setMinimumWidth(300)
        self.inline_preview.stopped.connect(lambda: self.close() if self.closing else None)
        self.inline_preview.notice.connect(self.preview_notice)
        self.inline_preview.ready.connect(lambda: self.preview_button.setText("重新加载预览"))
        rb.addWidget(self.inline_preview, 5)
        right = QWidget()
        right.setMinimumWidth(280)
        right.setMaximumWidth(410)
        pb = QVBoxLayout(right)
        pb.setContentsMargins(0, 6, 0, 2)
        pb.setSpacing(12)
        top = QHBoxLayout()
        self.platform_badge = label("等待解析", "badge")
        top.addWidget(self.platform_badge)
        top.addStretch()
        self.source_button = QPushButton("原页面 ↗")
        self.source_button.setObjectName("quiet")
        self.source_button.setEnabled(False)
        self.source_button.clicked.connect(self.open_source)
        top.addWidget(self.source_button)
        pb.addLayout(top)
        self.video_title = label("等待一个值得收藏的瞬间", "videoTitle", True)
        self.video_title.setMinimumHeight(44)
        self.video_title.setAlignment(Qt.AlignmentFlag.AlignTop)
        pb.addWidget(self.video_title)
        self.video_meta = label("解析后，这里会显示作者、时长和画质。", "muted", True)
        pb.addWidget(self.video_meta)
        pb.addSpacing(6)
        self.format_caption = label("视频画质", "fieldCaption")
        pb.addWidget(self.format_caption)
        self.formats = QComboBox()
        self.formats.addItem("解析后选择画质")
        self.formats.setEnabled(False)
        self.formats.currentIndexChanged.connect(self.format_changed)
        pb.addWidget(self.formats)
        pb.addWidget(label("保存到", "fieldCaption"))
        folder_row = QHBoxLayout()
        self.folder_input = QLineEdit(self.store.settings["download_dir"])
        self.folder_input.setReadOnly(True)
        self.folder_input.setToolTip(self.store.settings["download_dir"])
        self.folder_input.setStyleSheet("font-size:12px;padding:9px 10px;")
        folder_row.addWidget(self.folder_input, 1)
        self.folder_button = QPushButton("更改")
        self.folder_button.setObjectName("quiet")
        self.folder_button.clicked.connect(self.choose_folder)
        folder_row.addWidget(self.folder_button)
        pb.addLayout(folder_row)
        pb.addStretch(1)
        self.preview_button = QPushButton("重新加载预览")
        self.preview_button.setObjectName("quiet")
        self.preview_button.setEnabled(False)
        self.preview_button.clicked.connect(self.preview)
        pb.addWidget(self.preview_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.download_button = QPushButton("保存视频")
        self.download_button.setObjectName("primary")
        self.download_button.setIcon(glyph("download", "#ffffff"))
        self.download_button.setMinimumHeight(44)
        self.download_button.setEnabled(False)
        self.download_button.clicked.connect(self.download)
        pb.addWidget(self.download_button)
        self.transcribe_button = QPushButton("提取视频文案")
        self.transcribe_button.setEnabled(False)
        self.transcribe_button.clicked.connect(self.transcribe_video)
        pb.addWidget(self.transcribe_button)
        self.audio_button = QPushButton("只保存原声 · M4A")
        self.audio_button.setObjectName("quiet")
        self.audio_button.setEnabled(False)
        self.audio_button.clicked.connect(self.extract_sound)
        pb.addWidget(self.audio_button)
        rb.addWidget(right, 4)
        result.setMinimumHeight(370)
        box.addWidget(result, 1)

        status_row = QHBoxLayout()
        status_row.setSpacing(10)
        self.status = label("准备就绪", "statusText")
        status_row.addWidget(self.status)
        self.detail = label("粘贴链接即可开始", "muted")
        self.detail.setMinimumWidth(0)
        self.detail.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        status_row.addWidget(self.detail, 1)
        self.percent = label("", "muted")
        status_row.addWidget(self.percent)
        self.cancel_button = QPushButton("取消")
        self.cancel_button.setObjectName("quiet")
        self.cancel_button.setEnabled(False)
        self.cancel_button.setVisible(False)
        self.cancel_button.clicked.connect(self.cancel)
        status_row.addWidget(self.cancel_button)
        self.open_button = QPushButton("打开文件夹")
        self.open_button.setObjectName("quiet")
        self.open_button.clicked.connect(self.open_folder)
        status_row.addWidget(self.open_button)
        self.log_toggle = QPushButton("任务详情")
        self.log_toggle.setObjectName("quiet")
        self.log_toggle.setCheckable(True)
        status_row.addWidget(self.log_toggle)
        box.addLayout(status_row)
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setValue(0)
        self.progress_bar.hide()
        box.addWidget(self.progress_bar)
        self.logs = QPlainTextEdit()
        self.logs.setObjectName("logs")
        self.logs.setReadOnly(True)
        self.logs.document().setMaximumBlockCount(200)
        self.logs.setFixedHeight(92)
        self.logs.hide()
        self.log_toggle.toggled.connect(self.logs.setVisible)
        box.addWidget(self.logs)
        return page

    def history_page(self):
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(32, 35, 32, 32)
        box.setSpacing(20)
        heading = QHBoxLayout()
        titles = QVBoxLayout()
        titles.addWidget(label("资料库", "headline"))
        titles.addWidget(label("内容和文案，放在一起。", "muted"))
        heading.addLayout(titles, 1)
        self.library_import = QPushButton("导入音视频提取文案")
        self.library_import.setObjectName("primary")
        self.library_import.clicked.connect(self.import_library_media)
        heading.addWidget(self.library_import)
        box.addLayout(heading)
        filters = QHBoxLayout()
        from .widgets import FilterBar
        self.history_kind = FilterBar([("全部", ""), ("视频", "video"), ("图文", "images"), ("音频", "audio")])
        self.history_has_text = QPushButton("有文案")
        self.history_has_text.setObjectName("filterChip")
        self.history_has_text.setCheckable(True)
        self.history_has_text.toggled.connect(self.refresh_history)
        self.history_search = QLineEdit()
        self.history_search.setPlaceholderText("搜索内容、作者或文案全文")
        self.history_search.setClearButtonEnabled(True)
        filters.addWidget(self.history_kind)
        filters.addWidget(self.history_has_text)
        filters.addWidget(self.history_search, 1)
        box.addLayout(filters)
        self.history_kind.currentIndexChanged.connect(self.refresh_history)
        self.history_search.textChanged.connect(self.refresh_history)
        panel, pb = self.panel()
        self.history = QTableWidget(0, 4)
        self.history.setWordWrap(False)
        self.history.setHorizontalHeaderLabels(["内容", "类型 / 文案", "大小", "保存时间"])
        self.history.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.history.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.history.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.history.verticalHeader().hide()
        self.history.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for index in (1, 2, 3):
            self.history.horizontalHeader().setSectionResizeMode(index, QHeaderView.ResizeMode.ResizeToContents)
        self.history.cellDoubleClicked.connect(self.open_history)
        self.history.itemSelectionChanged.connect(self.library_selection_changed)
        pb.addWidget(self.history)
        self.library_empty = label("还没有收藏内容。粘贴分享链接保存，或导入本地音视频提取文案。", "muted", True)
        pb.addWidget(self.library_empty)
        actions = QHBoxLayout()
        self.library_buttons = []
        for text, callback in (("播放 / 预览", self.play_record), ("阅读文案", self.read_record), ("提取文案", self.transcribe_record)):
            button = QPushButton(text)
            button.clicked.connect(callback)
            actions.addWidget(button)
            self.library_buttons.append(button)
        actions.addStretch()
        more = QPushButton("更多  ···")
        menu = QMenu(more)
        self.library_record_actions = []
        for title, callback in (("打开位置", self.reveal_record), ("提取原声", self.extract_record), ("复制文件", self.copy_record),
                                ("重新解析", self.resolve_record), ("删除片段…", self.delete_record)):
            self.library_record_actions.append(menu.addAction(title, callback))
        more.setMenu(menu)
        actions.addWidget(more)
        pb.addLayout(actions)
        box.addWidget(panel, 1)
        return page

    def busy(self):
        return self.worker is not None

    def link_changed(self):
        if not self.busy():
            self.info = None
            self.inline_preview.clear()
            self.download_button.setEnabled(False)
            self.source_button.setEnabled(False)
            self.formats.setEnabled(False)
            self.formats.clear()
            self.formats.addItem("解析后选择画质")
            self.video_title.setText("等待一个值得收藏的瞬间")
            self.video_meta.setText("解析后，这里会显示作者、时长和画质。")
            self.platform_badge.setText("等待解析")
            self.preview_button.setEnabled(False)
            self.audio_button.setEnabled(False)
            self.transcribe_button.setEnabled(False)
            self.transcribe_button.show()
            self.download_button.setText("保存视频")
            self.format_caption.setText("视频画质")
            self.audio_button.show()
            self.resolve_button.setEnabled(bool(self.link_input.toPlainText().strip()))

    def append_log(self, text):
        self.logs.appendPlainText(datetime.now().strftime("%H:%M:%S") + "  " + text)

    def start(self, action, args):
        if self.busy():
            return
        self.operation = action
        self.started_at = time.perf_counter()
        self.pending_info = args[0] if args and isinstance(args[0], VideoInfo) else None
        self.progress_bar.setRange(0, 0)
        self.progress_bar.show()
        self.percent.setText("")
        self.status.setText("正在解析" if action == "resolve" else "正在保存")
        self.resolve_button.setText("解析中…" if action == "resolve" else "解析链接  →")
        self.detail.setText("正在读取分享内容…" if action == "resolve" else "正在保存到本地…")
        for widget in (self.link_input, self.resolve_button, self.browser_button, self.download_button,
                       self.folder_button, self.formats, self.preview_button, self.audio_button, self.transcribe_button, self.clear_button):
            widget.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.cancel_button.show()
        self.worker = Worker(self.store.root, action, args)
        self.worker.log.connect(self.append_log)
        self.worker.log.connect(lambda text: self.detail.setText(text[:60]))
        self.worker.progress.connect(self.update_progress)
        self.worker.result.connect(self.completed)
        self.worker.failed.connect(self.failed)
        self.worker.cancelled.connect(self.cancelled)
        self.worker.finished.connect(self.finished)
        self.worker.start()

    def resolve(self, interactive):
        if self.busy() or not self.link_input.toPlainText().strip():
            return
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
            self.video_meta.setText(" · ".join(filter(None, [result.author, human_duration(result.duration) if result.kind != "images" else f"{len(result.images)} 张图片"])))
            self.video_meta.setToolTip("内容编号 " + result.video_id)
            self.platform_badge.setText(result.platform)
            self.formats.blockSignals(True)
            self.formats.clear()
            for f in result.formats:
                from .models import format_label
                self.formats.addItem(format_label(f))
            self.formats.blockSignals(False)
            self.progress_bar.setValue(0)
            elapsed = max(0, time.perf_counter()-getattr(self, "started_at", time.perf_counter()))
            self.status.setText(f"解析完成 · {elapsed:.1f} 秒")
            self.download_button.setText("保存图文" if result.kind == "images" else "保存视频")
            self.format_caption.setText("保存范围" if result.kind == "images" else "视频画质")
            self.preview_button.setText("重新加载预览")
            self.audio_button.setVisible(result.kind != "images")
            self.transcribe_button.setVisible(result.kind != "images")
            self.detail.setText("预览已在左侧加载，选择画质即可保存")
            self.append_log("解析成功，已匹配视频 ID " + result.video_id)
            self.inline_preview.set_info(result, result.formats[0])
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
        self.cancel_button.hide()
        self.resolve_button.setText("解析链接  →")
        if self.operation == "resolve":
            self.progress_bar.hide()
        for widget in (self.link_input, self.resolve_button, self.browser_button, self.folder_button, self.clear_button):
            widget.setEnabled(True)
        self.download_button.setEnabled(self.info is not None)
        self.formats.setEnabled(self.info is not None)
        self.source_button.setEnabled(self.info is not None)
        self.preview_button.setEnabled(self.info is not None)
        self.audio_button.setEnabled(self.info is not None and self.info.kind != "images")
        self.transcribe_button.setEnabled(self.info is not None and self.info.kind != "images")
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
            self.folder_input.setToolTip(path)
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
        if not hasattr(self, "speech"):
            return
        from .library import library_entries
        selected = self.selected_entry()
        selected_key = selected.get("id") if selected else None
        rows = library_entries(self.store.records(), self.speech.store.rows(), self.history_kind.currentData() or "",
                               self.history_search.text(), self.history_has_text.isChecked())
        self.history.blockSignals(True)
        self.history.setRowCount(len(rows))
        self.history.clearSelection()
        self.history.setCurrentCell(-1, -1)
        for row, item in enumerate(rows):
            kind = {"video": "视频", "images": "图文", "audio": "音频"}.get(item.get("kind", "video"), "视频")
            state = kind + (f" · 文案 {len(item['_doc_ids'])} 份" if item['_doc_ids'] else "")
            for column, text in enumerate((item.get("title", "未命名"), state, human_size(item.get("size", 0)) if item.get("size") else "—", item.get("time", "").replace("T", " ")[:16])):
                cell = QTableWidgetItem(text)
                cell.setData(Qt.ItemDataRole.UserRole, item)
                cell.setToolTip(item.get("title", "") + "\n" + item.get("platform", "") + "\n" + item["path"])
                self.history.setItem(row, column, cell)
            self.history.setRowHeight(row, 48)
            if item.get("id") == selected_key:
                self.history.selectRow(row)
        self.history.blockSignals(False)
        self.library_empty.setVisible(not rows)
        self.library_empty.setText("没有匹配的内容。可以换个关键词，或取消筛选。" if self.history_search.text() or self.history_kind.currentData() or self.history_has_text.isChecked() else "还没有收藏内容。粘贴分享链接保存，或导入本地音视频提取文案。")
        self.library_selection_changed()

    def library_selection_changed(self):
        if not hasattr(self, "library_buttons"):
            return
        item = self.selected_entry()
        path = Path(item["path"]) if item and item.get("path") else None
        self.library_buttons[0].setEnabled(bool(item and path and path.exists()))
        self.library_buttons[1].setEnabled(bool(item and item.get("_doc_ids")))
        self.library_buttons[2].setEnabled(bool(item and item.get("kind", "video") in ("video", "audio") and path and path.is_file()))
        self.library_buttons[2].setText("提取新稿" if item and item.get("_doc_ids") else "提取文案")
        self.library_buttons[2].setToolTip("另存一份新文案，原稿保留。" if item and item.get("_doc_ids") else "在本机提取视频或音频的文案。")
        for action in self.library_record_actions:
            action.setEnabled(bool(item and item.get("_record")))

    def import_library_media(self):
        if self.speech.worker:
            self.switch_page(2)
            self.speech.status.setText("请先暂停当前任务，再导入新的文件。")
        elif self.speech.import_media():
            self.switch_page(2)

    def read_record(self):
        item = self.selected_entry()
        if item and item.get("_doc_ids"):
            self.speech.save_edit()
            self.speech.search.clear()
            self.speech.show_document(self.speech.store.read(item["_doc_ids"][0]))
            self.speech.refresh()
            self.switch_page(2)

    def open_history(self, row, column):
        item = self.selected_entry()
        if item and item.get("_doc_ids") and (self.history_has_text.isChecked() or not item.get("_record") or not Path(item["path"]).exists()):
            self.read_record()
        else:
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
            self.inline_preview.set_info(self.info, self.info.formats[self.formats.currentIndex()])

    def format_changed(self, index):
        if self.info and 0 <= index < len(self.info.formats) and not self.busy():
            self.inline_preview.set_info(self.info, self.info.formats[index])

    def preview_notice(self, message):
        self.preview_button.setText("重试预览")
        self.preview_button.setToolTip(message)
        self.append_log(message)

    def extract_sound(self):
        if self.info and self.info.kind != "images" and not self.busy():
            self.start("extract_audio", (self.info, self.info.formats[self.formats.currentIndex()], Path(self.folder_input.text()) / "原声"))

    def transcribe_video(self):
        if self.info and self.info.kind != "images" and not self.busy():
            self.switch_page(2)
            self.speech.start_online(self.info, self.info.formats[self.formats.currentIndex()])

    def transcribe_record(self):
        record = self.selected_entry()
        if not record:
            return
        if record.get("kind", "video") not in ("video", "audio"):
            QMessageBox.information(self, "选择音视频", "图文正文在图片预览中；提取原声文案请先选择视频或音频。")
            return
        self.switch_page(2)
        self.speech.start_local(Path(record["path"]), record["title"])

    def selected_record(self):
        item = self.selected_entry()
        return item.get("_record") if item else None

    def selected_entry(self):
        row = self.history.currentRow()
        cell = self.history.item(row, 0) if row >= 0 else None
        return cell.data(Qt.ItemDataRole.UserRole) if cell else None

    def show_viewer(self, result, title, description=""):
        from .player import GalleryDialog, PlayerDialog
        dialog = GalleryDialog(result, title, description, self) if result.kind == "images" else PlayerDialog(result, title, self)
        self.viewers.append(dialog)
        dialog.destroyed.connect(lambda: self.viewers.remove(dialog) if dialog in self.viewers else None)
        dialog.show()

    def play_record(self):
        record = self.selected_entry()
        if not record:
            return
        if not record.get("_record"):
            path = Path(record["path"]) if record.get("path") else None
            if path and path.is_file():
                self.show_viewer(SavedMedia(path, [path], record["kind"]), record["title"])
            elif record.get("_doc_ids"):
                self.read_record()
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
        previews_stopped = self.inline_preview.shutdown()
        speech_stopped = self.speech.shutdown()
        if self.worker or not previews_stopped or not speech_stopped:
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
