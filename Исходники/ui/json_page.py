"""Показывает исходные данные структуры без возможности их редактирования."""

import json
import re
from pathlib import Path

from PySide6.QtCore import Qt, QRect, QSize
from PySide6.QtGui import QColor, QPainter, QSyntaxHighlighter, QTextCharFormat, QTextCursor, QFont, QIcon, QShortcut, QKeySequence
from PySide6.QtWidgets import QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QToolButton, QVBoxLayout, QWidget


RESOURCES = Path(__file__).with_name("resources")


def action_button(icon, tooltip):
    button = QToolButton()
    button.setObjectName("resultActionButton")
    button.setFixedSize(26, 28)
    button.setIcon(QIcon(str(RESOURCES / f"result_{icon}.svg")))
    button.setIconSize(QSize(17, 17))
    button.setToolTip(tooltip)
    button.setAccessibleName(tooltip)
    return button


class JsonHighlighter(QSyntaxHighlighter):
    TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|\b(?:true|false|null)\b|-?\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?')

    def highlightBlock(self, text):
        for match in self.TOKEN.finditer(text):
            token = match.group()
            key = token.startswith('"') and text[match.end():].lstrip().startswith(":")
            color = "#B13939" if key else "#2563EB" if token.startswith('"') or token[0] in "-0123456789" else "#8552B7"
            format = QTextCharFormat()
            format.setForeground(QColor(color))
            self.setFormat(match.start(), len(token), format)


class LineNumbers(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def paintEvent(self, event):
        self.editor.paint_numbers(event)


class JsonEditor(QPlainTextEdit):
    def __init__(self):
        super().__init__()
        self.setObjectName("structureJsonEditor")
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        font = QFont("Consolas")
        font.setPixelSize(12)
        self.setFont(font)
        self.numbers = LineNumbers(self)
        self.blockCountChanged.connect(self.update_margin)
        self.updateRequest.connect(self.update_numbers)
        self.update_margin()
        self.highlighter = JsonHighlighter(self.document())

    def update_margin(self, *_):
        self.number_width = 13 + self.fontMetrics().horizontalAdvance("9") * len(str(max(1, self.blockCount())))
        self.setViewportMargins(self.number_width, 0, 0, 0)

    def update_numbers(self, rect, dy):
        if dy:
            self.numbers.scroll(0, dy)
        else:
            self.numbers.update(0, rect.y(), self.number_width, rect.height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        rect = self.contentsRect()
        self.numbers.setGeometry(QRect(rect.left(), rect.top(), self.number_width, rect.height()))

    def paint_numbers(self, event):
        painter = QPainter(self.numbers)
        painter.fillRect(event.rect(), QColor("#F2F6FC"))
        painter.setFont(self.font())
        painter.setPen(QColor("#8194B1"))
        block = self.firstVisibleBlock()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        while block.isValid() and top <= event.rect().bottom():
            height = round(self.blockBoundingRect(block).height())
            if block.isVisible() and top + height >= event.rect().top():
                painter.drawText(0, top, self.number_width - 6, self.fontMetrics().height(), Qt.AlignmentFlag.AlignRight, str(block.blockNumber() + 1))
            block = block.next()
            top += height


class JsonPage(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("structureJsonPage")
        self._text = ""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        row = QHBoxLayout()
        row.setSpacing(4)
        title = QLabel("ДАННЫЕ АЛМАЗНОЙ СТРУКТУРЫ")
        self.title=title
        title.setObjectName("resultPageCaption")
        title.setWordWrap(True)
        row.addWidget(title, 1)
        self.search_button = action_button("search", "Поиск по JSON")
        self.copy_button = action_button("copy", "Копировать JSON")
        self.save_button = action_button("save", "Сохранить JSON")
        for button in (self.search_button, self.copy_button, self.save_button):
            row.addWidget(button)
        layout.addLayout(row)
        self.identity = QLabel()
        self.identity.setObjectName("jsonIdentity")
        self.identity.setWordWrap(True)
        self.identity.hide()
        layout.addWidget(self.identity)
        self.search_row = QWidget()
        search_layout = QHBoxLayout(self.search_row)
        search_layout.setContentsMargins(0, 0, 0, 0)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Найти в JSON…")
        self.search.setClearButtonEnabled(True)
        self.next_button = action_button("next", "Следующее совпадение")
        search_layout.addWidget(self.search, 1)
        search_layout.addWidget(self.next_button)
        self.search_row.hide()
        layout.addWidget(self.search_row)
        self.editor = JsonEditor()
        self.editor.setPlaceholderText("Данные JSON пока отсутствуют")
        layout.addWidget(self.editor, 1)
        self.search_button.clicked.connect(self.toggle_search)
        self.search.textChanged.connect(self.search_changed)
        self.search.returnPressed.connect(self.find_next)
        self.next_button.clicked.connect(self.find_next)
        self.copy_button.clicked.connect(self.copy_all)
        self.save_button.clicked.connect(self.save)
        self.find_shortcut = QShortcut(QKeySequence.StandardKey.Find, self)
        self.find_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.find_shortcut.activated.connect(self.open_search)
        self.copy_button.setEnabled(False)
        self.save_button.setEnabled(False)

    def set_json(self, data):
        if data.get('builder')=='blackburn':data={key:value for key,value in data.items() if key!='builder'}
        self._text = json.dumps(data, ensure_ascii=False, indent=2)
        self.editor.setPlainText(self._text)
        self.copy_button.setEnabled(True)
        self.save_button.setEnabled(True)
        self.identity.hide()

    def mark_previous(self,message="Предыдущая структура; данные нового построения ещё не получены."):
        self.identity.setText(message)
        self.identity.setVisible(bool(self._text))

    def toggle_search(self):
        self.search_row.setVisible(self.search_row.isHidden())
        if self.search_row.isVisible():
            self.search.setFocus()

    def open_search(self):
        self.search_row.show()
        self.search.setFocus()

    def search_changed(self):
        cursor = self.editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self.editor.setTextCursor(cursor)
        self.find_next()

    def find_next(self):
        if not self.search.text():
            return False
        found = self.editor.find(self.search.text())
        if not found:
            cursor = self.editor.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self.editor.setTextCursor(cursor)
            found = self.editor.find(self.search.text())
        self.search.setToolTip("" if found else "Совпадений нет")
        return found

    def copy_all(self):
        if self._text:
            QApplication.clipboard().setText(self._text)

    def save_to(self, path):
        if self._text:
            Path(path).write_text(self._text, encoding="utf-8")

    def save(self):
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить JSON", "diamond.json", "JSON (*.json)")
        if path:
            self.save_to(path)
