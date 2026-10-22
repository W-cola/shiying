"""Offline transcript library: continuous text, local inference and audio replay."""
from pathlib import Path
from threading import Event

from PySide6.QtCore import Qt, QThread, Signal, QUrl
from PySide6.QtGui import QColor, QTextCursor, QTextCharFormat
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton, QSlider, QSplitter, QTextEdit, QVBoxLayout, QWidget)

from .engine import Engine, safe_message
from .models import AppError, Cancelled, human_duration, human_size
from .speech import LocalSpeech, TranscriptStore, document_text, text_ranges
from .speech_models import SpeechModels
from .widgets import ComboBox


STATES = {"new": "等待提取", "working": "正在识别", "paused": "已暂停", "done": "已完成",
          "failed": "未完成", "unclear": "未检测到清晰讲话", "singing": "检测到歌声"}


def caption(text, name="muted"):
    result = QLabel(text)
    result.setObjectName(name)
    result.setTextFormat(Qt.TextFormat.PlainText)
    result.setWordWrap(True)
    return result


def qposition(text, index):
    return len(text[:index].encode("utf-16-le"))//2


def selection_range(doc, begin, end):
    """Use actual segment or word alignment, never distribute time by text length."""
    if begin == end:
        return None
    text = document_text(doc)
    begin = len(text.encode("utf-16-le")[:begin*2].decode("utf-16-le", errors="ignore"))
    end = len(text.encode("utf-16-le")[:end*2].decode("utf-16-le", errors="ignore"))
    matches = []
    for part in text_ranges(doc):
        if part["from"] >= end or part["to"] <= begin:
            continue
        words = [w for w in part.get("words", []) if part["from"]+w["from"] < end and part["from"]+w["to"] > begin]
        matches.append((words[0]["start"], words[-1]["end"]) if words else (part["start"], part["end"]))
    return (matches[0][0], matches[-1][1]) if matches else None


class SpeechWorker(QThread):
    progress = Signal(dict)
    updated = Signal(dict)
    notice = Signal(str)

    def __init__(self, store, action, doc=None, args=None):
        super().__init__()
        self.store, self.action, self.doc, self.args = store, action, doc, args or {}
        self.cancel_event = Event()

    def run(self):
        try:
            if self.action == "model":
                models = SpeechModels(self.store.data_dir)
                if self.args.get("archive"):
                    models.import_zip(self.args["archive"], self.cancel_event, self.progress.emit)
                else:
                    models.install(self.cancel_event, self.progress.emit)
                self.notice.emit("离线识别包已就绪")
                return
            args = dict(self.args)
            if not (self.store.folder(self.doc["id"])/"audio.m4a").exists() and not args.get("info") and not args.get("local_path"):
                if self.doc.get("local_path"):
                    args["local_path"] = self.doc["local_path"]
                else:
                    self.progress.emit({"stage": "重新读取分享内容", "done": 0, "total": 0})
                    info = Engine(self.store.data_dir, cancel=self.cancel_event).resolve(self.doc["source"])
                    args.update(info=info, fmt=info.formats[0])
            LocalSpeech(self.store, self.cancel_event, self.progress.emit, self.updated.emit).run(self.doc, **args)
        except Cancelled:
            self.notice.emit("已暂停，完成的文案和进度已保留")
        except Exception as error:
            self.notice.emit(str(error) if isinstance(error, AppError) else "操作未完成："+safe_message(error))


class TranscriptWorkspace(QWidget):
    stopped = Signal()

    def __init__(self, data_dir):
        super().__init__()
        self.store = TranscriptStore(data_dir)
        self.models = SpeechModels(data_dir)
        self.worker = None
        self.current = None
        self.pending_args = {}
        self.editing = False
        self.closing = False
        self.stop_at = None
        self.follow = False
        self.player = QMediaPlayer(self)
        self.output = QAudioOutput(self)
        self.player.setAudioOutput(self.output)
        self.output.setVolume(.85)
        box = QVBoxLayout(self)
        box.setContentsMargins(28, 28, 28, 22)
        box.setSpacing(16)
        top = QHBoxLayout()
        heading = QVBoxLayout()
        heading.addWidget(caption("原声文案", "headline"))
        heading.addWidget(caption("把声音留下，也把有用的文字留下。"))
        top.addLayout(heading, 1)
        self.model_button = QPushButton()
        self.model_button.setObjectName("quiet")
        model_menu = QMenu(self.model_button)
        model_menu.addAction("下载 / 继续下载识别包", lambda: self.model_job())
        model_menu.addAction("导入离线识别包 ZIP…", self.import_models)
        self.model_button.setMenu(model_menu)
        top.addWidget(self.model_button)
        self.import_button = QPushButton("导入音频 / 视频")
        self.import_button.setObjectName("primary")
        self.import_button.clicked.connect(self.import_media)
        top.addWidget(self.import_button)
        box.addLayout(top)
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        left = QWidget()
        lb = QVBoxLayout(left)
        lb.setContentsMargins(0, 0, 12, 0)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索标题或文案全文")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh)
        lb.addWidget(self.search)
        self.library = QListWidget()
        self.library.setStyleSheet("QListWidget{background:transparent;border:none;outline:none;} QListWidget::item{padding:15px 10px;margin:3px 0;border-radius:9px;color:#476551;} QListWidget::item:selected{background:#e0eee4;color:#173b2f;} QListWidget::item:hover{background:#eaf2ec;}")
        self.library.currentItemChanged.connect(self.select_item)
        lb.addWidget(self.library, 1)
        left.setMinimumWidth(190)
        split.addWidget(left)
        paper = QFrame()
        paper.setObjectName("panel")
        pb = QVBoxLayout(paper)
        pb.setContentsMargins(24, 22, 24, 18)
        pb.setSpacing(12)
        row = QHBoxLayout()
        self.title = caption("让声音变成可阅读的文稿", "section")
        row.addWidget(self.title, 1)
        self.more = QPushButton("···")
        self.more.setObjectName("quiet")
        menu = QMenu(self.more)
        menu.addAction("导出为 TXT…", self.export_text)
        menu.addAction("恢复原始识别文本", self.restore_original)
        menu.addAction("重新识别，保留原稿", self.recognize_again)
        menu.addSeparator()
        menu.addAction("删除这份文案…", self.delete_document)
        self.more.setMenu(menu)
        row.addWidget(self.more)
        pb.addLayout(row)
        self.meta = caption("支持本地音频、视频，也可以从分享视频的「提取视频文案」进入。")
        pb.addWidget(self.meta)
        self.editor = QPlainTextEdit()
        self.editor.setReadOnly(True)
        self.editor.setPlaceholderText("文案会以完整段落显示在这里。\n\n识别在本机完成，声音不会上传。首次使用需下载或导入约 240 MB 的离线识别包。")
        self.editor.setStyleSheet("QPlainTextEdit{border:none;background:white;font-size:18px;padding:10px 0;selection-background-color:#cce8d5;} QPlainTextEdit:focus{border:none;}")
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.editor.selectionChanged.connect(self.selection_changed)
        self.editor.verticalScrollBar().actionTriggered.connect(lambda _: setattr(self, "follow", False))
        pb.addWidget(self.editor, 1)
        self.hint = caption("识别结果适合作为初稿，人名、方言、歌曲请回听校对。")
        pb.addWidget(self.hint)
        self.seek = QSlider(Qt.Orientation.Horizontal)
        self.seek.setRange(0, 0)
        self.seek.sliderMoved.connect(self.seek_audio)
        pb.addWidget(self.seek)
        audio_row = QHBoxLayout()
        self.play = QPushButton("回听原声")
        self.play.clicked.connect(self.toggle_play)
        audio_row.addWidget(self.play)
        self.clock = caption("0:00 / 0:00")
        audio_row.addWidget(self.clock, 1)
        self.speed = ComboBox()
        for rate in (.75, 1., 1.25, 1.5, 2.):
            self.speed.addItem(f"{rate:g}×", rate)
        self.speed.setCurrentIndex(1)
        self.speed.setFixedWidth(112)
        self.speed.setStyleSheet("QComboBox{padding:6px 28px 6px 10px;min-height:20px;} QComboBox::drop-down{width:24px;}")
        self.speed.currentIndexChanged.connect(lambda: self.player.setPlaybackRate(self.speed.currentData()))
        audio_row.addWidget(self.speed)
        self.follow_button = QPushButton("回到播放处")
        self.follow_button.setObjectName("quiet")
        self.follow_button.clicked.connect(self.follow_audio)
        audio_row.addWidget(self.follow_button)
        pb.addLayout(audio_row)
        controls = QHBoxLayout()
        self.run_button = QPushButton("开始提取")
        self.run_button.clicked.connect(self.resume)
        controls.addWidget(self.run_button)
        self.pause_button = QPushButton("暂停识别")
        self.pause_button.setObjectName("quiet")
        self.pause_button.clicked.connect(self.pause)
        controls.addWidget(self.pause_button)
        controls.addStretch()
        self.edit_button = QPushButton("修改文案")
        self.edit_button.setObjectName("quiet")
        self.edit_button.clicked.connect(self.toggle_edit)
        controls.addWidget(self.edit_button)
        self.copy_button = QPushButton("复制正文")
        self.copy_button.setObjectName("primary")
        self.copy_button.clicked.connect(self.copy_text)
        controls.addWidget(self.copy_button)
        pb.addLayout(controls)
        split.addWidget(paper)
        split.setSizes([230, 650])
        box.addWidget(split, 1)
        self.status = caption("声音只在本机处理 · 文案独立保存")
        box.addWidget(self.status)
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.hide()
        box.addWidget(self.progress_bar)
        self.player.positionChanged.connect(self.position_changed)
        self.player.durationChanged.connect(lambda d: self.seek.setRange(0, d))
        self.player.playbackStateChanged.connect(self.play_state)
        self.player.errorOccurred.connect(lambda *args: self.status.setText("原声暂时无法播放，请检查音频缓存是否完整。"))
        self.refresh()
        self.update_controls()

    def refresh(self, *_):
        key = self.current["id"] if self.current else None
        self.library.blockSignals(True)
        self.library.clear()
        for doc in self.store.rows(self.search.text()):
            item = QListWidgetItem(doc["title"][:34]+"\n"+STATES.get(doc["state"], doc["state"])+f"  ·  {len(document_text(doc))} 字")
            item.setData(Qt.ItemDataRole.UserRole, doc["id"])
            item.setToolTip(doc["title"])
            self.library.addItem(item)
            if doc["id"] == key:
                self.library.setCurrentItem(item)
        self.library.blockSignals(False)

    def select_item(self, item, old=None):
        if item:
            self.save_edit()
            self.show_document(self.store.read(item.data(Qt.ItemDataRole.UserRole)))

    def show_document(self, doc):
        if doc["state"] == "working" and not (self.worker and self.worker.doc and self.worker.doc["id"] == doc["id"]):
            doc["state"] = "paused"
            self.store.save(doc)
        changed = not self.current or self.current["id"] != doc["id"]
        if changed:
            self.player.stop()
            self.stop_at = None
            self.follow = False
            self.editing = False
            self.editor.setReadOnly(True)
        self.current = doc
        self.title.setText(doc["title"])
        self.meta.setText(doc["platform"]+"  ·  "+STATES.get(doc["state"], "")+"  ·  "+human_duration(doc.get("duration", 0)))
        text = document_text(doc)
        if not self.editing and self.editor.toPlainText() != text:
            scroll = self.editor.verticalScrollBar().value()
            self.editor.setPlainText(text)
            if not changed:
                self.editor.verticalScrollBar().setValue(scroll)
        audio = self.store.folder(doc["id"])/doc.get("audio", "audio.m4a")
        url = QUrl.fromLocalFile(str(audio.resolve())) if audio.is_file() else QUrl()
        if self.player.source() != url:
            self.player.setSource(url)
        hints = {"singing": "检测到歌声，结果可能是歌词；可继续尝试提取剩余内容。",
                 "unclear": "没有检测到清晰讲话。可回听原声，或点击「仍然尝试」按音轨识别。",
                 "failed": doc.get("error", "操作未完成，可重试。"),
                 "paused": "已保留完成的文字，继续时从检查点开始。"}
        self.hint.setText(hints.get(doc["state"], "修改会保留原稿。选中文字后，可回听对应原声。" if text else "正在准备文案，识别过程中可以暂停。"))
        self.update_controls()

    def update_controls(self):
        active = self.worker is not None
        doc = self.current
        own = active and self.worker.doc and doc and self.worker.doc["id"] == doc["id"]
        self.model_button.setText("● 离线识别已就绪" if self.models.ready() else "下载 / 导入识别包")
        self.model_button.setEnabled(not active)
        self.import_button.setEnabled(not active)
        self.pause_button.setVisible(active)
        self.pause_button.setEnabled(active and not self.worker.cancel_event.is_set())
        self.pause_button.setText("暂停下载" if active and self.worker.action == "model" else "暂停识别")
        state = doc.get("state") if doc else ""
        self.run_button.setVisible(bool(doc and state not in ("done", "working")))
        self.run_button.setText("仍然尝试" if state == "unclear" else "继续提取" if state in ("paused", "singing") else "开始提取")
        self.run_button.setEnabled(bool(doc and not active))
        text = bool(doc and document_text(doc))
        self.edit_button.setText("保存修改" if self.editing else "修改文案")
        self.edit_button.setEnabled(text and not own)
        self.copy_button.setEnabled(text)
        self.more.setEnabled(bool(doc and not active and not self.editing))
        self.play.setEnabled(bool(doc and not self.player.source().isEmpty() and not self.editing))

    def start_local(self, path, title=None):
        if self.worker:
            self.status.setText("请先暂停当前任务，再导入新的文件。")
            return False
        path = Path(path)
        if not path.is_file():
            self.status.setText("本地文件已移动或删除，请重新选择。")
            return False
        self.save_edit()
        doc = self.store.create(title or path.stem)
        doc["local_path"] = str(path.resolve())
        self.store.save(doc)
        self.show_document(doc)
        self.refresh()
        self.resume()
        return True

    def start_online(self, info, fmt):
        if self.worker:
            self.status.setText("请先暂停当前任务，再提取新的视频。")
            return False
        self.save_edit()
        doc = self.store.create(info.title, info.source_url, info.platform)
        self.pending_args[doc["id"]] = {"info": info, "fmt": fmt}
        self.show_document(doc)
        self.refresh()
        self.resume()
        return True

    def import_media(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择音频或视频", "", "音视频 (*.mp4 *.mkv *.mov *.webm *.avi *.mp3 *.m4a *.aac *.wav *.flac *.ogg *.opus *.wma);;所有文件 (*)")
        if path:
            self.start_local(path)

    def start_worker(self, worker):
        self.player.pause()
        self.worker = worker
        worker.progress.connect(self.update_progress)
        worker.updated.connect(self.document_updated)
        worker.notice.connect(self.status.setText)
        worker.finished.connect(self.finished)
        self.progress_bar.setRange(0, 0)
        self.progress_bar.show()
        self.update_controls()
        worker.start()

    def resume(self):
        if not self.current or self.worker:
            return
        if not self.models.ready():
            self.status.setText("请在右上角下载或导入约 240 MB 的离线识别包，完成后即可提取。")
            return
        self.save_edit()
        doc = self.store.read(self.current["id"])
        args = dict(self.pending_args.get(doc["id"], {}))
        args["force"] = doc["state"] in ("unclear", "singing")
        self.start_worker(SpeechWorker(self.store, "recognize", doc, args))

    def document_updated(self, doc):
        if self.current and self.current["id"] == doc["id"]:
            self.show_document(doc)
        self.refresh()
        if doc["state"] == "done":
            self.status.setText("文案已保存 · 可复制、修改或回听原声")
        elif doc["state"] in ("unclear", "singing"):
            self.status.setText("提取已停在此处，可回听确认后继续尝试。")

    def update_progress(self, p):
        total, done = p.get("total", 0), p.get("done", 0)
        self.progress_bar.setRange(0, 100 if total else 0)
        percent = min(100, int(100*done/total)) if total else 0
        self.progress_bar.setValue(percent)
        extra = f" · {percent}%" if total else "…"
        if self.worker and self.worker.action == "model" and total:
            extra += " · "+human_size(done)+" / "+human_size(total)
        self.status.setText(p.get("stage", "正在处理")+extra)

    def pause(self):
        if self.worker:
            self.worker.cancel_event.set()
            self.status.setText("正在暂停，当前短语处理结束后保存检查点…")
            self.update_controls()

    def finished(self):
        worker = self.worker
        self.worker = None
        worker.deleteLater()
        self.progress_bar.hide()
        self.update_controls()
        self.refresh()
        if self.closing:
            self.stopped.emit()
        elif worker.action == "model" and self.models.ready() and self.current and self.current["state"] == "new":
            self.resume()

    def model_job(self, archive=None):
        if not self.worker:
            self.start_worker(SpeechWorker(self.store, "model", args={"archive": archive}))

    def import_models(self):
        path, _ = QFileDialog.getOpenFileName(self, "导入离线识别包", "", "离线识别包 (*.zip)")
        if path:
            self.model_job(path)

    def toggle_edit(self):
        if self.editing:
            self.save_edit()
        elif self.current:
            self.player.pause()
            self.editing = True
            self.editor.setReadOnly(False)
            self.editor.setFocus()
            self.hint.setText("编辑后按「保存修改」。原始识别文本会保留。")
            self.editor.setExtraSelections([])
            self.update_controls()

    def save_edit(self):
        if self.editing and self.current:
            self.current = self.store.edit(self.current["id"], self.editor.toPlainText())
            self.editing = False
            self.editor.setReadOnly(True)
            self.hint.setText("修改已保存；可在更多菜单中恢复原稿。编辑后的文案回听完整原声。")
            self.refresh()
            self.update_controls()

    def copy_text(self):
        if self.current:
            QApplication.clipboard().setText(self.editor.textCursor().selectedText().replace("\u2029", "\n") or self.editor.toPlainText())
            self.status.setText("正文已复制")

    def restore_original(self):
        if self.current:
            self.show_document(self.store.restore_original(self.current["id"]))
            self.refresh()

    def export_text(self):
        if not self.current:
            return
        from .links import safe_filename
        path, _ = QFileDialog.getSaveFileName(self, "导出文案", safe_filename(self.current["title"], "文案")+".txt", "文本文档 (*.txt)")
        if path:
            try:
                Path(path).write_text(document_text(self.current), encoding="utf-8")
                self.status.setText("文案已导出")
            except OSError:
                self.status.setText("导出未完成，请检查保存位置。")

    def recognize_again(self):
        if not self.current or self.worker:
            return
        old = self.current
        audio = self.store.folder(old["id"])/old.get("audio", "audio.m4a")
        if audio.is_file():
            self.start_local(audio, old["title"]+" · 新稿")
        else:
            self.status.setText("原声缓存不存在，请重新导入媒体；已有文案已保留。")

    def delete_document(self):
        if not self.current or self.worker:
            return
        if QMessageBox.question(self, "删除这份文案？", "会删除文案及它的回听缓存，原始音视频文件会保留。", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel) != QMessageBox.StandardButton.Yes:
            return
        self.player.stop()
        self.player.setSource(QUrl())
        try:
            self.store.delete(self.current["id"])
        except (OSError, AppError):
            self.status.setText("删除未完成，请稍后重试。")
            return
        self.current = None
        self.editor.clear()
        self.title.setText("选择一份文案，继续阅读")
        self.meta.clear()
        self.refresh()
        self.update_controls()

    def selection_changed(self):
        if self.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
            self.play.setText("回听选中文字" if self.editor.textCursor().hasSelection() and self.current and self.current.get("edited_text") is None else "回听原声")

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            return
        cursor = self.editor.textCursor()
        bounds = selection_range(self.current, cursor.selectionStart(), cursor.selectionEnd()) if self.current else None
        if bounds:
            start, end = int(bounds[0]*1000), int(bounds[1]*1000)
            if self.stop_at != end or not start <= self.player.position() < end:
                self.player.setPosition(start)
            self.stop_at = end
        else:
            self.stop_at = None
            if self.player.position() >= self.player.duration()-50:
                self.player.setPosition(0)
        self.player.play()

    def seek_audio(self, position):
        self.stop_at = None
        self.player.setPosition(position)

    def play_state(self, state):
        self.play.setText("暂停回听" if state == QMediaPlayer.PlaybackState.PlayingState else "继续回听")

    def follow_audio(self):
        self.follow = True
        self.position_changed(self.player.position())

    def position_changed(self, position):
        if self.stop_at is not None and position >= self.stop_at:
            stop = self.stop_at
            self.stop_at = None
            self.player.pause()
            self.player.setPosition(stop)
        if not self.seek.isSliderDown():
            self.seek.setValue(position)
        self.clock.setText(human_duration(max(.001, position/1000))+" / "+human_duration(max(.001, self.player.duration()/1000)))
        if not self.current or self.editing:
            return
        selections, current_cursor = [], None
        text = document_text(self.current)
        for part in text_ranges(self.current):
            if part["start"] <= position/1000 < part["end"]:
                def mark(start, end, foreground=False):
                    selection = QTextEdit.ExtraSelection()
                    cursor = self.editor.textCursor()
                    cursor.setPosition(qposition(text, start))
                    cursor.setPosition(qposition(text, end), QTextCursor.MoveMode.KeepAnchor)
                    selection.cursor = cursor
                    selection.format = QTextCharFormat()
                    selection.format.setForeground(QColor("#18854d")) if foreground else selection.format.setBackground(QColor("#edf6ef"))
                    selections.append(selection)
                    return cursor
                current_cursor = mark(part["from"], part["to"])
                for word in part.get("words", []):
                    if word["start"] <= position/1000 < word["end"]:
                        current_cursor = mark(part["from"]+word["from"], part["from"]+word["to"], True)
                        break
                break
        self.editor.setExtraSelections(selections)
        if self.follow and current_cursor:
            # Scrolling never changes the user's text selection.
            rect = self.editor.cursorRect(current_cursor)
            if rect.top() < 0 or rect.bottom() > self.editor.viewport().height():
                bar = self.editor.verticalScrollBar()
                bar.setValue(bar.value()+int(rect.top()/max(1, self.editor.fontMetrics().height())))

    def shutdown(self):
        self.save_edit()
        self.player.stop()
        self.player.setSource(QUrl())
        if self.worker:
            self.closing = True
            self.pause()
            return False
        return True
