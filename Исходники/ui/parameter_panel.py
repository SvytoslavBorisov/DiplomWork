from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QFontMetricsF, QIcon
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (
    QAbstractSpinBox, QComboBox, QFrame, QGraphicsDropShadowEffect, QGridLayout,
    QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy, QSpinBox, QDoubleSpinBox,
    QStyle, QStyleOptionComboBox, QStylePainter, QToolButton, QToolTip,
    QVBoxLayout, QWidget, QListView, QStyledItemDelegate,
)

from integration.backend_adapter import BackendAdapter, BuildRequest
from algorithms.search_methods import BBHTOptions, SearchMethod, search_method
from .math_text import math_html
from .math_renderer import MathLabel
from .widgets import Card
from .build_button import BuildButton


RESOURCES = Path(__file__).with_name("resources")


class ParameterSpinBox(QSpinBox):
    """Меняет значение колёсиком только при фокусе внутри числового поля."""

    def wheelEvent(self, event) -> None:
        if self.hasFocus() or self.lineEdit().hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class ParameterLimitSpinBox(QDoubleSpinBox):
    """Передаёт целочисленный лимит до 2⁵³−1 без переполнения штатного QSpinBox."""

    def __init__(self):
        super().__init__()
        self.setDecimals(0)

    def value(self) -> int:
        self.interpretText()
        return int(super().value())

    def wheelEvent(self, event) -> None:
        if self.hasFocus() or self.lineEdit().hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class ParameterCombo(QComboBox):
    """Переносит длинное название метода внутри штатного выпадающего списка."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setView(QListView(self))
        self.setItemDelegate(QStyledItemDelegate(self))
        self.view().setObjectName("parameterComboList")
        self.view().setSpacing(3)
        self.view().setMinimumWidth(460)
        self.setMaxVisibleItems(6)

    def sizeHint(self) -> QSize:
        return QSize(200, 46)

    def minimumSizeHint(self) -> QSize:
        return QSize(120, 46)

    def paintEvent(self, event) -> None:
        painter = QStylePainter(self)
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        option.currentText = ""
        option.currentIcon = QIcon()
        painter.drawComplexControl(QStyle.ComplexControl.CC_ComboBox, option)
        icon_rect = self.rect().adjusted(12, 0, 0, 0)
        icon_rect.setTop((self.height() - 20) // 2)
        icon_rect.setSize(QSize(20, 20))
        self.itemIcon(self.currentIndex()).paint(painter, icon_rect)
        painter.setFont(self.font())
        painter.setPen(QColor("#101B38" if self.isEnabled() else "#98A2B3"))
        painter.drawText(self.rect().adjusted(42, 2, -30, -2),
                         Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap,
                         self.currentText())


class ParameterTitle(QLabel):
    """Подбирает размер заголовка без переноса в узкой панели."""

    def minimumSizeHint(self) -> QSize:
        return QSize(0, 36)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        font = self.font()
        for pixels in range(17, 12, -1):
            font.setPixelSize(pixels)
            if QFontMetricsF(font).horizontalAdvance(self.text()) <= self.width():
                break
        self.setStyleSheet(f"font-size: {pixels}px; font-weight: 400;")


class ParameterPanel(Card):
    PREFIX_BLOCKS = 1
    ROUNDS = 12
    SIGMA_SEED = 0
    build_requested = Signal()
    stop_requested = Signal()
    open_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent=parent)
        self.setObjectName("experimentParameterPanel")
        self.setMinimumWidth(290)
        self.setMaximumWidth(315)
        self.layout_box.setContentsMargins(14, 16, 14, 16)
        self.layout_box.setSpacing(14)
        self._busy = False
        heading = QHBoxLayout()
        heading.setSpacing(6)
        self.title = ParameterTitle("Параметры")
        self.title.setObjectName("parameterPanelTitle")
        self.title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        heading.addWidget(self.title, 1)
        self.open_button = QToolButton()
        self.open_button.setObjectName("parameterFileButton")
        self.open_button.setFixedSize(36, 36)
        self.open_button.setIcon(QIcon(str(RESOURCES / "parameter_folder.svg")))
        self.open_button.setIconSize(QSize(22, 22))
        self._add_shadow(self.open_button)
        self.open_button.setToolTip("Открыть JSON")
        self.open_button.setAccessibleName("Открыть JSON")
        self.open_button.clicked.connect(self.open_requested)
        heading.addWidget(self.open_button)
        self.layout_box.addLayout(heading)

        self.groups_scroll = QScrollArea()
        self.groups_scroll.setObjectName("parameterScroll")
        self.groups_scroll.setWidgetResizable(True)
        self.groups_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.groups_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        groups = QWidget()
        groups.setObjectName("parameterContent")
        groups_layout = QVBoxLayout(groups)
        groups_layout.setContentsMargins(0, 0, 2, 2)
        groups_layout.setSpacing(12)

        algorithm, algorithm_layout = self._section("Алгоритм построения", "gear")
        self.method_combo = ParameterCombo()
        self.method_combo.setObjectName("parameterCombo")
        self.method_combo.setFixedHeight(46)
        self.method_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        for title, value, icon in (
            ("Классический алгоритм", BackendAdapter.CLASSICAL, "cube"),
            ("Квантовый алгоритм — фиксированный Гровер", BackendAdapter.QUANTUM, "quantum"),
            ("Квантовый алгоритм BBHT", BackendAdapter.BBHT, "quantum"),
        ):
            self.method_combo.addItem(QIcon(str(RESOURCES / f"parameter_{icon}.svg")), title, value)
            self.method_combo.setItemData(self.method_combo.count() - 1, title, Qt.ItemDataRole.ToolTipRole)
        self.method_combo.view().setMinimumWidth(460)
        algorithm_layout.addWidget(self.method_combo)
        groups_layout.addWidget(algorithm)

        model, model_layout = self._section("Параметры модели", "sliders")
        model_grid = QGridLayout()
        model_grid.setHorizontalSpacing(6)
        model_grid.setVerticalSpacing(10)
        model_grid.setColumnStretch(0, 1)
        self.n_spin = self._spin(4, 512, 20, 4, " бит")
        self.k_spin = self._spin(1, 20, 3)
        self.sigma_spin = self._spin(0, 64, 0, 1, " бит")
        rows = (
            ("Часть хэш-кода, n", self.n_spin, "Число сохраняемых бит промежуточного хэш-кода"),
            ("Глубина, k", self.k_spin, "Глубина алмазной структуры. Число начальных хэш-кодов равно 2^k"),
            ("Часть Σₛ", self.sigma_spin, "Число младших бит контрольной суммы"),
        )
        for row, (text, spin, hint) in enumerate(rows):
            label_row = QWidget()
            label_layout = QHBoxLayout(label_row)
            label_layout.setContentsMargins(0, 0, 0, 0)
            label_layout.setSpacing(4)
            label = QLabel("Часть" if spin is self.sigma_spin else math_html(text).replace("Часть хэш-кода", "Часть<br>хэш-кода"))
            label.setObjectName("parameterFieldLabel")
            label.setWordWrap(True)
            label.setMinimumWidth(0)
            label.setBuddy(spin)
            label_layout.addWidget(label)
            if spin is self.sigma_spin:
                self.sigma_symbol=MathLabel(r"\Sigma_s",20)
                self.sigma_symbol.setObjectName("parameterSigmaSymbol")
                label_layout.addWidget(self.sigma_symbol)
            help_button=self._hint(hint)
            if spin is self.n_spin:
                label_row.setFixedHeight(36)
                label_layout.addWidget(help_button,0,Qt.AlignmentFlag.AlignBottom)
            else:
                label_layout.addWidget(help_button)
            label_layout.addStretch(1)
            spin.setAccessibleName(text)
            model_grid.addWidget(label_row, row, 0)
            model_grid.addWidget(spin, row, 1, Qt.AlignmentFlag.AlignVCenter)
            model_grid.setRowMinimumHeight(row, 54)
        model_layout.addLayout(model_grid)
        groups_layout.addWidget(model)

        search, search_layout = self._section("Ограничения", "shield")
        limit_row = QHBoxLayout()
        limit_row.setSpacing(4)
        self.limit_label = QLabel()
        self.limit_label.setObjectName("parameterLimitLabel")
        self.limit_label.setWordWrap(True)
        limit_row.addWidget(self.limit_label)
        self.limit_hint = self._hint("")
        limit_row.addWidget(self.limit_hint)
        limit_row.addStretch(1)
        search_layout.addLayout(limit_row)
        self.limin_spin = self._spin(1, 2**53 - 1, 1_000_000_000)
        self.limin_spin.setMinimumWidth(0)
        self.limin_spin.setMaximumWidth(16777215)
        self.limin_spin.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.limin_spin.setGroupSeparatorShown(True)
        self.limin_spin.setAccessibleName("Лимит вычислений")
        search_layout.addWidget(self.limin_spin)
        groups_layout.addWidget(search)
        groups_layout.addStretch(1)
        self.groups_scroll.setWidget(groups)
        self.layout_box.addWidget(self.groups_scroll, 1)

        self.build_button = BuildButton("Построить алмазную структуру")
        self.build_button.setObjectName("primaryButton")
        self.build_button.clicked.connect(self._build_or_stop)
        self.method_combo.currentIndexChanged.connect(self._update_limit_label)
        self._update_limit_label()

    @staticmethod
    def _section(title: str, icon: str) -> tuple[QFrame, QVBoxLayout]:
        section = QFrame()
        section.setObjectName("parameterSection")
        layout = QVBoxLayout(section)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        row = QHBoxLayout()
        row.setSpacing(8)
        image = QSvgWidget(str(RESOURCES / f"parameter_{icon}.svg"))
        image.setObjectName("parameterSectionIcon")
        image.setFixedSize(22, 22)
        row.addWidget(image)
        label = QLabel(title)
        label.setObjectName("parameterSectionTitle")
        row.addWidget(label, 1)
        layout.addLayout(row)
        return section, layout

    @staticmethod
    def _hint(text: str) -> QToolButton:
        button = QToolButton()
        button.setObjectName("parameterHintButton")
        button.setFixedSize(16, 16)
        button.setIcon(QIcon(str(RESOURCES / "parameter_help.svg")))
        button.setIconSize(QSize(16, 16))
        button.setToolTip(math_html(text))
        button.setAccessibleName(text or "Подсказка о лимите")
        button.clicked.connect(lambda: QToolTip.showText(QCursor.pos(), button.toolTip(), button))
        return button

    @staticmethod
    def _add_shadow(widget: QWidget) -> None:
        shadow = QGraphicsDropShadowEffect(widget)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 5)
        shadow.setColor(QColor(77, 119, 182, 36))
        widget.setGraphicsEffect(shadow)

    @staticmethod
    def _spin(minimum: int, maximum: int, value: int, step: int = 1, suffix: str = "") -> ParameterSpinBox | ParameterLimitSpinBox:
        spin = ParameterLimitSpinBox() if maximum > 2_147_483_647 else ParameterSpinBox()
        spin.setObjectName("parameterInput")
        spin.setRange(minimum, maximum)
        spin.setSingleStep(step)
        spin.setValue(value)
        spin.setSuffix(suffix)
        spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.UpDownArrows)
        spin.setAlignment(Qt.AlignmentFlag.AlignLeft)
        spin.setFixedSize(100, 42)
        ParameterPanel._add_shadow(spin)
        return spin

    def _build_or_stop(self) -> None:
        (self.stop_requested if self._busy else self.build_requested).emit()

    def _update_limit_label(self) -> None:
        selected = search_method(self.method_combo.currentData())
        quantum = selected.is_quantum
        self.limit_label.setText("Лимит вычислений" if quantum else "Лимит поиска коллизии")
        hint = ("Ограничивает число классических вычислений при моделировании квантового алгоритма."
                if quantum else "Максимальное число попыток поиска коллизии.")
        self.limin_spin.setToolTip(hint)
        self.limit_hint.setToolTip(hint)
        self.limit_hint.setAccessibleName(hint)

    def request(self, output_directory) -> BuildRequest:
        return BuildRequest(
            str(self.method_combo.currentData()), self.k_spin.value(), self.n_spin.value(),
            self.PREFIX_BLOCKS, self.ROUNDS, self.limin_spin.value(),
            output_directory, sigma_bits=self.sigma_spin.value(), sigma_seed=self.SIGMA_SEED,
            parameter_strategy="theoretical", target_probability=0.95,
            bbht_options=BBHTOptions() if search_method(self.method_combo.currentData()) is SearchMethod.GROVER_BBHT else None,
        )

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.build_button.setEnabled(True)
        self.build_button.setText("Остановить" if busy else "Построить алмазную структуру")
        self.open_button.setEnabled(not busy)
        for control in (self.method_combo, self.n_spin, self.k_spin, self.sigma_spin, self.limin_spin):
            control.setEnabled(not busy)
        self._update_limit_label()

    def set_stopping(self) -> None:
        self.build_button.setEnabled(False)
        self.build_button.setText("Остановка…")
