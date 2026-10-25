"""Показывает необязательные ограничения BBHT в сворачиваемом разделе."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDoubleSpinBox, QFormLayout, QSpinBox, QToolButton, QVBoxLayout, QWidget
from algorithms.search_methods import BBHTOptions


class BBHTParameters(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.toggle = QToolButton()
        self.toggle.setText("Дополнительные параметры BBHT")
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.toggle.setCheckable(True)
        layout.addWidget(self.toggle)
        self.body = QWidget()
        form = QFormLayout(self.body)
        defaults = BBHTOptions()
        self.growth = QDoubleSpinBox()
        self.growth.setDecimals(3)
        self.growth.setRange(1.001, 1.333)
        self.growth.setSingleStep(0.05)
        self.growth.setValue(defaults.growth)
        self.growth.setToolTip("Множитель диапазона итераций после неудачного измерения: 1 < рост < 4/3.")
        form.addRow("Коэффициент роста", self.growth)
        self.attempts = self._integer(form, "Попыток на поиск", defaults.max_attempts,
                                      "Число измерений на одном множестве кандидатов с учётом неудач.")
        self.queries = self._integer(form, "Запросов на поиск", defaults.max_oracle_queries,
                                     "Модельные фазовые запросы и проверки одного поиска; qRAM учитывается отдельно.")
        self.dense = self._integer(form, "Порог плотного вектора", defaults.dense_max_states,
                                   "Для большего S используется существующая точная двухамплитудная модель.")
        self.seconds = QDoubleSpinBox()
        self.seconds.setRange(0, 86400)
        self.seconds.setValue(defaults.max_stage_seconds)
        self.seconds.setToolTip("Время этапа в секундах; 0 сохраняет исходное отсутствие внутреннего таймера BBHT.")
        form.addRow("Время этапа, с", self.seconds)
        layout.addWidget(self.body)
        self.body.hide()
        self.toggle.toggled.connect(self._expand)

    @staticmethod
    def _integer(form, label, value, tooltip):
        spin = QSpinBox()
        spin.setRange(1, 2147483647)
        spin.setValue(value)
        spin.setToolTip(tooltip)
        form.addRow(label, spin)
        return spin

    def _expand(self, expanded):
        self.body.setVisible(expanded)
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)

    def options(self):
        result = BBHTOptions(self.growth.value(), self.attempts.value(), self.queries.value(),
                             self.dense.value(), self.seconds.value())
        result.validate()
        return result
