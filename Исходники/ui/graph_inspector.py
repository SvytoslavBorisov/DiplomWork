"""Показывает переиспользуемую немодальную карточку реальной вершины или перехода."""

from pathlib import Path
from .widgets import add_panel_shadow

from PySide6.QtCore import QSize, Qt, Signal, QEvent
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import QApplication, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QScrollArea, QToolButton, QVBoxLayout, QWidget
from .math_renderer import MathLabel
from .math_text import math_html


class GraphInspector(QFrame):
    closed = Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("graphInspector")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)
        heading = QHBoxLayout()
        self.title = QLabel()
        self.title.setObjectName("graphInspectorTitle")
        heading.addWidget(self.title, 1)
        self.close_button = QToolButton()
        self.close_button.setObjectName("graphInspectorClose")
        self.close_button.setFixedSize(26,26)
        self.close_button.setIcon(QIcon(str(Path(__file__).with_name("resources") / "close.svg")))
        self.close_button.setIconSize(QSize(14,14))
        self.close_button.setAccessibleName("Закрыть информацию")
        self.close_button.clicked.connect(self.closed)
        heading.addWidget(self.close_button)
        layout.addLayout(heading)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body = QWidget()
        self.body.setObjectName("graphInspectorBody")
        body_layout = QVBoxLayout(self.body)
        body_layout.setContentsMargins(0, 0, 4, 0)
        body_layout.setSpacing(8)
        self.symbol = MathLabel("h", 25)
        body_layout.addWidget(self.symbol)
        self.values = {}
        self.rows = {}
        self.copy_buttons = {}
        self._raw_values = {}
        for key in ("Хэш-код", "Уровень", "Тип вершины", "Контрольная сумма", "N входящего перехода", "Исходное состояние", "Конечное состояние", "Блок сообщения", "N перед обработкой блока", "Изменение Σₛ"):
            row = QWidget()
            box = QVBoxLayout(row)
            box.setContentsMargins(0, 0, 0, 0)
            box.setSpacing(2)
            caption = QHBoxLayout()
            name = QLabel(math_html(key))
            name.setObjectName("graphInspectorCaption")
            name.setWordWrap(True)
            caption.addWidget(name, 1)
            if key in ("Хэш-код", "Исходное состояние", "Конечное состояние", "Блок сообщения"):
                button = QToolButton()
                button.setIcon(QIcon(str(Path(__file__).with_name("resources") / "diamond_copy.svg")))
                button.setIconSize(QSize(15, 15))
                button.setAccessibleName("Копировать: " + key)
                button.setToolTip("Копировать полное значение")
                button.clicked.connect(lambda checked=False, key=key: QApplication.clipboard().setText(self._raw_values[key]))
                caption.addWidget(button)
                self.copy_buttons[key] = button
            box.addLayout(caption)
            value = QLabel()
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            value.setTextFormat(Qt.TextFormat.PlainText)
            if key in self.copy_buttons:
                value.setObjectName("graphInspectorHex")
            box.addWidget(value)
            body_layout.addWidget(row)
            self.rows[key] = row
            self.values[key] = value
        body_layout.addStretch()
        scroll.setWidget(self.body)
        layout.addWidget(scroll, 1)
        add_panel_shadow(self)
        self.hide()
        QApplication.instance().installEventFilter(self)

    def eventFilter(self,watched,event):
        if self.isVisible() and event.type()==QEvent.Type.MouseButtonPress:
            if not self.rect().contains(self.mapFromGlobal(event.globalPosition().toPoint())):
                self.closed.emit();self.hide()
        return False

    def present(self, title: str, expression: str, fields: dict[str, str]) -> None:
        self.title.setText(title)
        self.symbol.set_formula(expression)
        self._raw_values = dict(fields)
        for key, row in self.rows.items():
            row.setVisible(key in fields)
            if key in fields:
                value = str(fields[key])
                if key == "Блок сообщения" and len(value) > 40:
                    value = value[:32] + "…"
                elif key in self.copy_buttons:
                    value = '\u200b'.join(value[i:i+16] for i in range(0, len(value), 16))
                self.values[key].setText(value)
        self.fit_to_viewport()
        self.show()
        self.raise_()

    def fit_to_viewport(self) -> None:
        self.setFixedWidth(max(150, min(280, self.parentWidget().width() - 16)))
        self.body.layout().invalidate()
        self.body.layout().activate()
        desired = self.body.layout().sizeHint().height() + 66
        self.setFixedHeight(max(80, min(desired, 390, self.parentWidget().height() - 16)))
