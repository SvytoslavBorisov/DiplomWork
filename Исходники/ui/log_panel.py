from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Signal, QTimer
from PySide6.QtGui import QFont, QColor, QTextCursor, QTextCharFormat
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QPlainTextEdit, QPushButton, QTabWidget, QTextEdit, QWidget, QLabel, QVBoxLayout, QFrame, QProgressBar

from .widgets import Card
from .json_page import action_button
from .log_translation import translate_log


LOG_COLORS = {"INFO": "#2563EB", "MATCH": "#7862BA", "DONE": "#009863", "WARN": "#B7791F", "ERROR": "#C53030"}


def append_entry(editor, message, level="INFO"):
    cursor = QTextCursor(editor.document())
    cursor.movePosition(QTextCursor.MoveOperation.End)
    if not editor.document().isEmpty():
        cursor.insertBlock()
    font = QFont("Consolas")
    font.setPixelSize(12)
    format = QTextCharFormat()
    format.setFont(font)
    format.setForeground(QColor("#8190A9"))
    cursor.insertText(datetime.now().strftime("%H:%M:%S")+"  ",format)
    format.setForeground(QColor(LOG_COLORS.get(level,"#71819B")))
    cursor.insertText({'INFO':'ИНФО','MATCH':'СОВПАДЕНИЯ','DONE':'ГОТОВО','WARN':'ВНИМАНИЕ','ERROR':'ОШИБКА'}.get(level,level)+"  ",format)
    format.setForeground(QColor("#526581"))
    cursor.insertText(translate_log(message),format)


class LogPage(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("structureLogPage")
        self._follow = True
        self._updating = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(10)
        row = QHBoxLayout()
        title = QLabel("ЖУРНАЛ СОБЫТИЙ")
        title.setObjectName("resultPageCaption")
        row.addWidget(title,1)
        self.save_button = action_button("save","Сохранить журнал")
        self.clear_button = action_button("clear","Очистить журнал")
        row.addWidget(self.save_button)
        row.addWidget(self.clear_button)
        layout.addLayout(row)
        self.editor = QTextEdit()
        self.editor.setObjectName("resultLogEditor")
        self.editor.setReadOnly(True)
        self.editor.setAcceptRichText(False)
        layout.addWidget(self.editor,1)
        self.footer = QFrame()
        self.footer.setObjectName("resultLogActivity")
        footer_layout = QVBoxLayout(self.footer)
        footer_layout.setContentsMargins(12,12,12,12)
        self.activity = QLabel()
        self.activity.setWordWrap(True)
        self.activity.setObjectName("resultLogActivityTitle")
        footer_layout.addWidget(self.activity)
        self.progress = QProgressBar()
        self.progress.setRange(0,0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(4)
        footer_layout.addWidget(self.progress)
        self.note = QLabel();self.note.hide()
        self.note.setObjectName("resultLogActivityNote")
        self.note.setWordWrap(True)
        footer_layout.addWidget(self.note)
        self.cancel_button = QPushButton("Отменить проверку")
        self.cancel_button.setObjectName("cancelVerificationButton")
        footer_layout.addWidget(self.cancel_button)
        self.footer.hide()
        layout.addWidget(self.footer)
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setSingleShot(True)
        self._scroll_timer.timeout.connect(self._scroll_bottom)
        self.editor.verticalScrollBar().valueChanged.connect(self._scrolled)
        self.editor.verticalScrollBar().rangeChanged.connect(self._range_changed)
        self.clear_button.clicked.connect(self.clear)
        self.save_button.clicked.connect(self.save)

    def _scrolled(self,value):
        if not self._updating:
            self._follow = value >= self.editor.verticalScrollBar().maximum()-2

    def _range_changed(self,*_):
        if self._follow:
            self._scroll_timer.start(0)

    def _scroll_bottom(self):
        if self._follow:
            self._updating = True
            bar = self.editor.verticalScrollBar()
            bar.setValue(bar.maximum())
            self._updating = False

    def append(self,message,level="INFO"):
        self._updating = True
        append_entry(self.editor,message,level)
        self._updating = False
        if self._follow:
            self._scroll_timer.start(0)

    def clear(self):
        self.editor.clear()
        self._follow = True

    def set_activity(self,text="",verification=False):
        self.activity.setText(text)
        if not verification:
            self.note.clear();self.note.hide()
        self.cancel_button.setVisible(verification)
        self.footer.setVisible(bool(text))

    def save_to(self,path):
        Path(path).write_text(self.editor.toPlainText(),encoding="utf-8")

    def save(self):
        path,_ = QFileDialog.getSaveFileName(self,"Сохранить журнал","kvantalmaz.log","Log (*.log);;Text (*.txt)")
        if path:
            self.save_to(path)


class LogPanel(Card):
    half_requested = Signal()
    hide_requested = Signal()
    COLORS = LOG_COLORS

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent=parent)
        self.layout_box.setContentsMargins(10, 8, 10, 9)
        self.tabs = QTabWidget()
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setFont(QFont("Consolas", 11))
        self.experiment_edit = self._editor()
        self.json_edit = self._editor()
        self.tabs.addTab(self.log_edit, "Журнал")
        self.tabs.addTab(self.experiment_edit, "Эксперимент")
        self.tabs.addTab(self.json_edit, "JSON")
        actions = QWidget()
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 4, 0)
        clear = QPushButton("Очистить")
        save = QPushButton("Сохранить…")
        half = QPushButton("½ экрана")
        hide = QPushButton("Скрыть")
        for button in (clear, save, half, hide):
            button.setObjectName("compactLogButton")
        clear.clicked.connect(self.log_edit.clear)
        save.clicked.connect(self._save_log)
        half.clicked.connect(self.half_requested)
        hide.clicked.connect(self.hide_requested)
        actions_layout.addWidget(clear)
        actions_layout.addWidget(save)
        actions_layout.addWidget(half)
        actions_layout.addWidget(hide)
        self.tabs.setCornerWidget(actions)
        self.layout_box.addWidget(self.tabs)

    @staticmethod
    def _editor() -> QPlainTextEdit:
        edit = QPlainTextEdit()
        edit.setReadOnly(True)
        edit.setFont(QFont("Consolas", 11))
        return edit

    def append(self, message: str, level: str = "INFO") -> None:
        append_entry(self.log_edit,message,level)
        bar = self.log_edit.verticalScrollBar()
        bar.setValue(bar.maximum())

    def set_json(self, data: dict) -> None:
        if data.get('builder')=='blackburn':data={key:value for key,value in data.items() if key!='builder'}
        self.json_edit.setPlainText(json.dumps(data, ensure_ascii=False, indent=2))

    def set_experiment(self, text: str) -> None:
        self.experiment_edit.setPlainText(text)

    def _save_log(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить журнал", "herdinglab.log", "Log (*.log);;Text (*.txt)")
        if path:
            Path(path).write_text(self.log_edit.toPlainText(), encoding="utf-8")
