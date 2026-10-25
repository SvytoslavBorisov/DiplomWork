from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget, QGraphicsDropShadowEffect


def add_panel_shadow(widget: QWidget) -> None:
    """Применяет к панели такую же мягкую тень, как у общей шапки."""
    shadow=QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(22)
    shadow.setOffset(0,5)
    shadow.setColor(QColor(46,98,161,22))
    widget.setGraphicsEffect(shadow)


class Card(QFrame):
    def __init__(self, title: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        add_panel_shadow(self)
        self.layout_box = QVBoxLayout(self)
        self.layout_box.setContentsMargins(17, 16, 17, 16)
        self.layout_box.setSpacing(12)
        if title:
            label = QLabel(title)
            label.setObjectName("sectionTitle")
            self.layout_box.addWidget(label)


def group_title(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setObjectName("groupTitle")
    return label


class SubCard(QFrame):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("subCard")
        add_panel_shadow(self)
        self.layout_box = QVBoxLayout(self)
        self.layout_box.setContentsMargins(12, 11, 12, 12)
        self.layout_box.setSpacing(8)
        self.layout_box.addWidget(group_title(title))


def wrap_label(text: str, object_name: str = "") -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    if object_name:
        label.setObjectName(object_name)
    return label


def graph_zoom_controls(view):
    """Создаёт одинаковые кнопки масштаба для обеих панелей графа."""
    from pathlib import Path
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QHBoxLayout, QToolButton
    group=QFrame()
    group.setObjectName("diamondZoomGroup")
    layout=QHBoxLayout(group)
    layout.setContentsMargins(0,0,0,0)
    layout.setSpacing(0)
    buttons=[]
    for index,(name,title,slot) in enumerate((("minus","Уменьшить",view.zoom_out),("fit","Показать целиком",view.fit_to_view),("plus","Увеличить",view.zoom_in))):
        if index:
            line=QFrame();line.setObjectName("diamondZoomDivider");line.setFixedWidth(1);layout.addWidget(line)
        button=QToolButton();button.setObjectName("diamondZoomButton");button.setFixedSize(34,34)
        button.setToolTip(title);button.setAccessibleName(title)
        button.setIcon(QIcon(str(Path(__file__).with_name("resources")/f"diamond_{name}.svg")))
        button.setIconSize(QSize(20,20));button.clicked.connect(slot)
        layout.addWidget(button);buttons.append(button)
    return group,buttons
