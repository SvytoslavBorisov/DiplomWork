"""Показывает важные сведения точки в существующей карточке вершины алмаза."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel,QVBoxLayout,QWidget

from .fonts import header_font_family
from .graph_inspector import GraphInspector


class ChartPointInspector(GraphInspector):
    def __init__(self,parent):
        super().__init__(parent)
        for row in self.rows.values():
            self.body.layout().removeWidget(row);row.hide()
        self.rows={};self.values={}
        self.setStyleSheet(f'QWidget {{font-family:"{header_font_family()}";}}')
        self.closed.connect(self.hide)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def present(self,title,expression,fields):
        for key in fields:
            if key in self.rows:continue
            row=QWidget(self.body);box=QVBoxLayout(row);box.setContentsMargins(0,0,0,0);box.setSpacing(2)
            label=QLabel(key);label.setObjectName('graphInspectorCaption')
            value=QLabel();value.setWordWrap(True)
            value.setTextFormat(Qt.TextFormat.PlainText)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            box.addWidget(label);box.addWidget(value)
            self.body.layout().insertWidget(self.body.layout().count()-1,row)
            self.rows[key]=row;self.values[key]=value
        super().present(title,expression,fields)
