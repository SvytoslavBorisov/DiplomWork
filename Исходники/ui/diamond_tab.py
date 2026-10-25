from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QSplitter, QToolButton, QVBoxLayout, QWidget

from .diamond_view import DiamondView
from .parameter_panel import ParameterPanel
from .result_panel import ResultPanel
from .widgets import Card, graph_zoom_controls


class DiamondTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(7, 6, 7, 2)
        layout.setSpacing(12)
        upper = QSplitter(Qt.Orientation.Horizontal)
        upper.setContentsMargins(8,8,8,12)
        self.parameters = ParameterPanel()
        self.results = ResultPanel()

        center = Card()
        center.setObjectName("diamondCanvasCard")
        self.center = center
        title_row = QHBoxLayout()
        title = QLabel("Алмазная структура")
        title.setObjectName("diamondCanvasTitle")
        title_row.addWidget(title)
        title_row.addStretch(1)
        self.view = DiamondView()
        zoom_group,buttons=graph_zoom_controls(self.view)
        title_row.addWidget(zoom_group)
        self.zoom_out_button,self.fit_button,self.zoom_in_button=buttons
        center.layout_box.addLayout(title_row)
        self.build_status = QLabel("")
        self.build_status.setObjectName("progressText")
        self.build_status.setVisible(False)
        center.layout_box.addWidget(self.build_status)
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet("color: #EEF1F5")
        center.layout_box.addWidget(separator)
        self.view.setMinimumHeight(200)
        center.layout_box.addWidget(self.view, 1)
        build_row = QHBoxLayout()
        build_row.addStretch()
        button = self.parameters.build_button
        button.setObjectName("buildDiamondButton")
        button.setFixedHeight(48)
        shadow = QGraphicsDropShadowEffect(button)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(33, 100, 245, 45))
        button.setGraphicsEffect(shadow)
        build_row.addWidget(button)
        center.layout_box.addLayout(build_row)

        upper.addWidget(self.parameters)
        upper.addWidget(center)
        upper.addWidget(self.results)
        upper.setSizes([315, 800, 325])
        upper.setStretchFactor(1, 1)
        self.splitter = upper
        layout.addWidget(upper,1)

    @staticmethod
    def _tool_button(kind: str, tooltip: str) -> QToolButton:
        button = QToolButton()
        button.setObjectName("diamondZoomButton")
        button.setFixedSize(34, 34)
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.setIcon(QIcon(str(Path(__file__).with_name("resources") / f"diamond_{kind}.svg")))
        button.setIconSize(QSize(20, 20))
        return button

    def set_building(self, building: bool, depth: int = 0, level: int = 1) -> None:
        self.build_status.setVisible(building)
        if building:
            self.build_status.setText(f"Построение уровня {level} из {depth}…")
