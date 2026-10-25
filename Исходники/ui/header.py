from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QLinearGradient, QPainter, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QTabBar, QWidget

from .fonts import header_font_family

RESOURCES = Path(__file__).with_name("resources")


class HeaderTabBar(QTabBar):
    """Рисует навигацию по эталону, сохраняя стандартное поведение QTabBar."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("headerTabs")
        self.setExpanding(False)
        self.setUsesScrollButtons(False)
        self.setElideMode(Qt.TextElideMode.ElideNone)
        self.setDrawBase(False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self._compact = False
        self._narrow = False
        self._hovered = -1
        self._keyboard_focus = False
        self._icons = {}
        for name in ("diamond", "graph", "comparison"):
            for state in ("inactive", "active"):
                self._icons[name, state] = QSvgRenderer(str(RESOURCES / f"nav_{name}_{state}.svg"), self)
        self.set_compact(False)

    def set_compact(self, compact: bool, narrow: bool = False) -> None:
        self._compact = compact
        self._narrow = narrow
        family = header_font_family()
        font = QFont(family)
        font.setPixelSize(14 if narrow else 16)
        font.setWeight(QFont.Weight.Normal)
        self.setFont(font)
        self.setStyleSheet(f'QTabBar#headerTabs {{ font-family: "{family}"; font-size: {14 if narrow else 16}px; font-weight: 400; }}')
        self.setFixedHeight(78)
        self.setFixedWidth(self.sizeHint().width())
        self.updateGeometry()
        self.update()

    def tabSizeHint(self, index: int) -> QSize:
        text_width = QFontMetricsF(self.font()).horizontalAdvance(self.tabText(index))
        padding = 18 if self._compact else 20
        return QSize(round(text_width) + 26 + 12 + 2 * padding + (10 if index<self.count()-1 else 0), 78)

    def pillRect(self,index):
        """Возвращает границы вкладки с промежутком ровно десять логических пикселей."""
        return QRectF(self.tabRect(index)).adjusted(0,12,-10 if index<self.count()-1 else 0,-12)

    def tabInserted(self, index: int) -> None:
        super().tabInserted(index)
        self.setFixedWidth(self.sizeHint().width())

    def mouseMoveEvent(self, event) -> None:
        hovered = self.tabAt(event.position().toPoint())
        if hovered>=0 and not self.pillRect(hovered).contains(event.position()):hovered=-1
        if hovered != self._hovered:
            self._hovered = hovered
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = -1
        self.update()
        super().leaveEvent(event)

    def focusInEvent(self, event) -> None:
        self._keyboard_focus = event.reason() in (Qt.FocusReason.TabFocusReason, Qt.FocusReason.BacktabFocusReason, Qt.FocusReason.ShortcutFocusReason)
        super().focusInEvent(event)
        self.update()

    def keyPressEvent(self, event) -> None:
        self._keyboard_focus = True
        super().keyPressEvent(event)
        self.update()

    def mousePressEvent(self, event) -> None:
        index=self.tabAt(event.position().toPoint())
        if index>=0 and not self.pillRect(index).contains(event.position()):
            event.ignore();return
        self._keyboard_focus = False
        super().mousePressEvent(event)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(self.font())
        for index in range(self.count()):
            rect = self.pillRect(index)
            selected = index == self.currentIndex()
            shadow = rect.adjusted(6, 1, -6, -1).translated(0, 5)
            for spread in range(11, 0, -1):
                painter.setPen(QPen(QColor(46, 98, 161, 2), spread * 2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(shadow, 27, 27)
            if selected:
                gradient = QLinearGradient(rect.topLeft(), rect.topRight())
                gradient.setColorAt(0, QColor("#389BFF"))
                gradient.setColorAt(1, QColor("#2164F5"))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(gradient)
                painter.drawRoundedRect(rect, 27, 27)
            else:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor("#F2F7FE" if index == self._hovered else "#FFFFFF"))
                painter.drawRoundedRect(rect, 27, 27)
            padding = 18 if self._compact else 20
            icon_rect = QRectF(rect.left() + padding, rect.center().y() - 13, 26, 26)
            names = ("diamond", "graph", "comparison")
            if index < len(names):
                self._icons[names[index], "active" if selected else "inactive"].render(painter, icon_rect)
            painter.setPen(QColor("#FFFFFF" if selected else "#485873"))
            text_rect = rect.adjusted(padding + 38, 0, -padding, 0)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.tabText(index))
            if selected and self.hasFocus() and self._keyboard_focus:
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(QColor(255, 255, 255, 170), 1, Qt.PenStyle.DotLine))
                painter.drawRoundedRect(rect.adjusted(4, 4, -4, -4), 24, 24)


class Header(QFrame):
    def __init__(self, backend: str, threads: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("headerHost")
        self.setFixedHeight(110)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 12)
        self.card = QFrame(self)
        self.card.setObjectName("header")
        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(22)
        shadow.setOffset(QPointF(0, 5))
        shadow.setColor(QColor(46, 98, 161, 22))
        self.card.setGraphicsEffect(shadow)
        outer.addWidget(self.card)
        self._layout = QHBoxLayout(self.card)
        self._layout.setContentsMargins(48, 0, 26, 0)
        self._layout.setSpacing(0)
        self.logo = QLabel(self.card)
        self._logo_pixmap = QPixmap(str(RESOURCES / "Глянцевый атомный кристалл.png")).copy(130, 255, 990, 705)
        self.logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.logo.setObjectName("headerLogo")
        self.logo.setFixedSize(70, 62)
        self._resize_logo()
        self.logo.setAccessibleName("Кристалл КвантАлмаз")
        self._layout.addWidget(self.logo, 0, Qt.AlignmentFlag.AlignVCenter)
        self._layout.addSpacing(24)
        self.title = QLabel("КвантАлмаз", self.card)
        self.title.setObjectName("appTitle")
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        self._title_family = header_font_family()
        self._set_title_size(39.6)
        self._layout.addWidget(self.title, 0, Qt.AlignmentFlag.AlignVCenter)
        self._layout.addStretch(1)
        self.tabs = HeaderTabBar(self.card)
        self.tabs.setAccessibleName("Основная навигация")
        self._layout.addWidget(self.tabs, 0, Qt.AlignmentFlag.AlignVCenter)
        self._compact = False
        self._narrow = False

    def _resize_logo(self) -> None:
        self.logo.setPixmap(self._logo_pixmap.scaled(self.logo.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def _set_title_size(self, pixels: float) -> None:
        self.title.setStyleSheet(f'font-family: "{self._title_family}"; font-size: {pixels}px; font-weight: 400;')

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        compact = self.width() < 1250
        narrow = self.width() < 1050
        if compact != self._compact or narrow != self._narrow:
            self._compact = compact
            self._narrow = narrow
            self._layout.setContentsMargins(24 if compact else 48, 0, 16 if compact else 26, 0)
            self.logo.setFixedSize(52 if narrow else 64 if compact else 70, 48 if narrow else 57 if compact else 62)
            self._resize_logo()
            self._set_title_size(24 if narrow else 32.4 if compact else 39.6)
            self.tabs.set_compact(compact,narrow)

    @staticmethod
    def _badge(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("badge")
        return label

    def set_mode(self, quantum: bool) -> None:
        pass
