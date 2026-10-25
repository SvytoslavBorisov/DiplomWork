from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
import json

from PySide6.QtCore import Qt, Signal, QSize, QRect
from PySide6.QtGui import QIcon, QPainter
from PySide6.QtWidgets import QComboBox, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QSplitter, QVBoxLayout, QWidget, QStyle, QStyleOptionButton, QSizePolicy

from algorithms.search_methods import SearchMethod, search_method
from .parameter_panel import ParameterPanel, ParameterCombo, ParameterTitle
from .result_panel import ResultPanel
from .diamond_view import DiamondView
from .metric_widgets import formatted_number
from .widgets import Card, graph_zoom_controls

RESOURCES=Path(__file__).with_name("resources")


class CommitmentButton(QPushButton):
    def __init__(self):
        super().__init__("Зафиксировать")
        self.setObjectName("commitmentButton")
        self.setMinimumHeight(44)
        self.setProperty("committed",False)

    def set_commitment(self,value=""):
        self.setText(value or "Зафиксировать")
        self.setProperty("committed",bool(value))
        self.setIcon(QIcon(str(RESOURCES/"result_check.svg")) if value else QIcon())
        self.setToolTip(value)
        self.style().unpolish(self);self.style().polish(self)
        self._adjust_height();self.update()

    def _adjust_height(self):
        bounds=self.fontMetrics().boundingRect(QRect(0,0,max(40,self.width()-54),1000),Qt.TextFlag.TextWrapAnywhere,self.text())
        self.setMinimumHeight(max(44,bounds.height()+20))

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self._adjust_height()

    def paintEvent(self,event):
        painter=QPainter(self)
        option=QStyleOptionButton();self.initStyleOption(option)
        option.text="";option.icon=QIcon()
        self.style().drawControl(QStyle.ControlElement.CE_PushButton,option,painter,self)
        rect=self.rect().adjusted(12,8,-12,-8)
        if self.property("committed"):
            self.icon().paint(painter,QRect(12,(self.height()-18)//2,18,18))
            rect.adjust(24,0,0,0)
        painter.setFont(self.font());painter.setPen(Qt.GlobalColor.white)
        painter.drawText(rect,Qt.AlignmentFlag.AlignCenter|Qt.TextFlag.TextWrapAnywhere,self.text())


class HerdingTab(QWidget):
    load_requested=Signal()
    commit_requested=Signal(str)
    attack_requested=Signal(str,str,object,str)
    stop_requested=Signal()

    def __init__(self,parent=None):
        super().__init__(parent)
        self._data=None;self._last_result=None;self._committed=False;self._busy=False
        layout=QVBoxLayout(self);layout.setContentsMargins(7,6,7,2)
        self.splitter=QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setContentsMargins(8,8,8,12)
        workflow=Card();self.parameters=workflow
        workflow.setObjectName("experimentParameterPanel")
        workflow.setMinimumWidth(290);workflow.setMaximumWidth(315)
        workflow.layout_box.setContentsMargins(14,16,14,16);workflow.layout_box.setSpacing(14)
        title=ParameterTitle("Параметры");title.setObjectName("parameterPanelTitle");self.title=title
        heading=QHBoxLayout();heading.addWidget(title,1);heading.setContentsMargins(0,0,0,0)
        heading.setSpacing(6);heading.addSpacing(0)
        title.setMinimumHeight(36)
        workflow.layout_box.addLayout(heading)
        scroll=QScrollArea();scroll.setObjectName("parameterScroll");scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame);scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        groups=QWidget();groups.setObjectName("parameterContent")
        group_layout=QVBoxLayout(groups);group_layout.setContentsMargins(0,0,2,2);group_layout.setSpacing(12)
        first,box=ParameterPanel._section("Алмазная структура","cube")
        self.load_button=QPushButton("Загрузить структуру")
        self.load_button.setIcon(QIcon(str(RESOURCES/"parameter_folder.svg")))
        self.load_button.setToolTip("Загрузить алмазную структуру")
        ParameterPanel._add_shadow(self.load_button)
        self.load_button.clicked.connect(self.load_requested)
        self.file_label=QLabel();self.file_label.setWordWrap(True)
        self.file_label.hide()
        self.file_label.setMinimumWidth(0);self.file_label.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        box.addWidget(self.load_button);box.addWidget(self.file_label);group_layout.addWidget(first)
        second,box=ParameterPanel._section("Коммитмент","sliders")
        box.addWidget(QLabel("Префикс"))
        self.description=QLineEdit("Матч выиграет ");self.description.setObjectName("herdingInput")
        ParameterPanel._add_shadow(self.description)
        self.description.textChanged.connect(self._invalidate_commitment)
        self.commit_button=CommitmentButton();self.commit_button.setEnabled(False)
        self.commit_button.clicked.connect(lambda: self.commit_requested.emit(self.description.text()) if not self._committed else None)
        box.addWidget(self.description);box.addWidget(self.commit_button);group_layout.addWidget(second)
        self.step3,box=ParameterPanel._section("Поиск связывающего блока","gear")
        self.step3.setEnabled(False)
        for label in self.step3.findChildren(QLabel,"parameterSectionTitle"):
            label.setWordWrap(True);label.setMinimumWidth(0)
        self.event_result=QLineEdit("Реал Мадрид");self.event_result.setObjectName("herdingInput")
        ParameterPanel._add_shadow(self.event_result)
        self.method=ParameterCombo();self.method.setObjectName("parameterCombo");self.method.setFixedHeight(46)
        for method in SearchMethod:
            name={SearchMethod.CLASSICAL:"Классический алгоритм",SearchMethod.GROVER_FIXED:"Квантовый алгоритм — фиксированный Гровер",SearchMethod.GROVER_BBHT:"Квантовый алгоритм BBHT"}[method]
            self.method.addItem(QIcon(str(RESOURCES/("parameter_quantum.svg" if method.is_quantum else "parameter_cube.svg"))),name,method.value)
        self.method.view().setMinimumWidth(460)
        self.limit=ParameterPanel._spin(1,2**53-1,2_000_000_000)
        self.limit.setMinimumWidth(0);self.limit.setMaximumWidth(16777215);self.limit.setGroupSeparatorShown(True)
        form=QFormLayout();form.setContentsMargins(0,0,0,0);form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows);form.setVerticalSpacing(9)
        for name,widget in (("Результат события",self.event_result),("Метод",self.method),("Лимит",self.limit)):form.addRow(name,widget)
        self.search_fields=QWidget();self.search_fields.setLayout(form)
        box.addWidget(self.search_fields)
        self.run_button=QPushButton("Начать поиск");self.run_button.setObjectName("primaryButton");self.run_button.setEnabled(False)
        self.run_button.clicked.connect(self._emit_attack);box.addWidget(self.run_button)
        group_layout.addWidget(self.step3);group_layout.addStretch()
        scroll.setWidget(groups);workflow.layout_box.addWidget(scroll,1)
        self.center=Card();self.center.setObjectName("diamondCanvasCard")
        top=QHBoxLayout();label=QLabel("Путь в алмазной структуре");label.setObjectName("diamondCanvasTitle")
        top.addWidget(label,1);self.view=DiamondView(message_mode=True)
        zoom,buttons=graph_zoom_controls(self.view);top.addWidget(zoom)
        self.zoom_out_button,self.fit_button,self.zoom_in_button=buttons
        self.center.layout_box.addLayout(top)
        line=QFrame();line.setObjectName("resultHeadingDivider");line.setFixedHeight(1);self.center.layout_box.addWidget(line)
        self.center.layout_box.addWidget(self.view,1)
        self.results=ResultPanel(message_mode=True)
        self.result_card=self.results;self.result_status=self.results.status.value_label
        self.result_rows=self.results.rows;self.result_scroll=self.results.scroll
        for widget in (workflow,self.center,self.results):self.splitter.addWidget(widget)
        self.splitter.setSizes([315,800,325]);self.splitter.setStretchFactor(1,1)
        layout.addWidget(self.splitter)

    def _emit_attack(self):
        if self._busy:self.stop_requested.emit()
        else:self.attack_requested.emit(self.description.text(),self.event_result.text(),self.limit.value(),str(self.method.currentData()))

    def set_diamond(self,data,name):
        self._data=data;self._last_result=None
        self.file_label.setText(name);self.file_label.hide();self.commit_button.setEnabled(True)
        self.load_button.setText(self.load_button.fontMetrics().elidedText(name, Qt.TextElideMode.ElideMiddle, 195))
        self.load_button.setToolTip(name + "\nНажмите, чтобы загрузить другую структуру")
        self.view.set_data(data)
        self.results.set_json(data)
        self.results.json_page.title.setText("ДАННЫЕ АЛМАЗНОЙ СТРУКТУРЫ")
        self.results.append_log(f"Загружена алмазная структура: {name}.")
        self._invalidate_commitment();self._clear_result();self.results.show_results()

    def set_commitment(self,root):
        self._committed=True;self.commit_button.set_commitment(root)
        self.run_button.setEnabled(True);self.step3.setEnabled(True)
        self.results.append_log("Коммитмент зафиксирован","DONE")

    def _invalidate_commitment(self):
        self._committed=False;self.commit_button.set_commitment()
        self.run_button.setEnabled(False);self.step3.setEnabled(False)

    def set_busy(self,busy):
        self._busy=busy;self.load_button.setEnabled(not busy)
        self.run_button.setEnabled(self._committed);self.run_button.setText("Остановить" if busy else "Начать поиск")
        self.step3.setEnabled(self._committed);self.search_fields.setEnabled(not busy and self._committed);self.description.setEnabled(not busy)
        self.commit_button.setEnabled(not busy and self._data is not None)
        if busy:
            if self._last_result is not None:
                self.results.json_page.mark_previous("Предыдущий результат поиска; новые данные ещё не получены.")
            self._last_result=None;self._clear_result()
            self.results.empty.hide();self.results.status.show();self.results.status.set_value("Поиск связывающего блока…","running")
            self.results._operation_page("Выполняется поиск")
            if self._data is not None:self.view.set_data(self._data)
            self.view.start_search();self.results.append_log("Поиск связывающего блока запущен.")
        else:self.view.stop_search()

    def _clear_result(self):
        self.results.set_empty();self.results.clear_metrics()

    def show_result(self,result,elapsed):
        self._clear_result();self._last_result=result
        passed=result.verified_root==result.root
        self.results.empty.hide();self.results.status.show()
        self.results.status.set_value("Поиск завершен успешно" if passed else "Поиск не прошёл проверку","success" if passed else "error")
        self.results.metrics_host.show()
        self.results.add_metric("elapsed","время выполнения",f"{elapsed:.3f}".replace(".",",")+" с")
        quantum=search_method(getattr(result,"link_method","") or result.link_backend).is_quantum
        if quantum:
            self.results.add_metric("oracle","модельных запросов к оракулу",formatted_number(result.link_queries))
            self.results.add_metric("simulator","вычислений функции сжатия",formatted_number(result.link_simulator_hash_evaluations))
        else:self.results.add_metric("queries","вычислений функции сжатия",formatted_number(result.link_queries))
        payload=asdict(result) if is_dataclass(result) else vars(result)
        self.results.set_json(payload);self.results.json_page.title.setText("ДАННЫЕ HERDING-АТАКИ")
        self.results.verify_button.setVisible(passed);self.results.verify_button.setEnabled(passed)
        self.results._operation_page()
        self.results.append_log(f"Поиск {'завершен успешно' if passed else 'не прошёл проверку'} за {elapsed:.3f} с","DONE" if passed else "WARN")
        if self._data is not None:self.view.set_data(self._data)
        self.view.animate_attack_path(result.leaf_state,result.prefix_state,result.linking_block)

    def show_error(self,text):
        self._clear_result();self.results.empty.hide();self.results.status.show()
        self.results.status.set_value("Ошибка поиска","error")
        self.results.set_experiment_details(text);self.results._operation_page()

    def set_cancelled(self):
        self.results.status.set_value("Поиск остановлен","neutral")
        self.results._operation_page()
