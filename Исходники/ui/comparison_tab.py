from __future__ import annotations


from PySide6.QtCore import Qt, Signal, QSize, QEvent, QVariantAnimation, QEasingCurve
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QComboBox, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QPushButton, QScrollArea,
    QTableWidget, QVBoxLayout, QWidget, QLineEdit, QFrame, QMenu, QLayout, QSizePolicy,
)
from pathlib import Path
from .comparison_widgets import COLORS, SortableItem, ExperimentDelegate, action_button
from .scientific_comparison import ScientificComparisonMixin

from algorithms.search_methods import SearchMethod, search_method
from integration.result_adapter import comparison_key, comparable_pairs
from .math_text import math_html
from .math_renderer import MathHeaderView
from .metric_widgets import formatted_number
from .widgets import Card


class ComparisonTab(ScientificComparisonMixin, QWidget):
    QUERIES = "queries"
    RUNTIME = "runtime"
    EVALUATIONS = "evaluations"
    MEMORY = "memory"
    load_requested = Signal()
    delete_requested = Signal(object)
    repeat_requested = Signal(object)
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setObjectName("comparisonTab")
        self.setAccessibleName("Сравнение алгоритмов")
        self._scientific_ready=False
        self._sort_column=None;self._sort_order=None;self._experiments_collapsed=False
        self._experiments_progress=1.;self._expanded_panel_height=260
        self.records=[];self._redrawing=False;self._records_by_id={}
        layout=QVBoxLayout(self);layout.setContentsMargins(15,14,15,14);layout.setSpacing(12)
        self.chart=Card();self.chart.setObjectName("comparisonChart")
        layout.addWidget(self.chart,5)
        self.experiments_panel=QWidget();self.experiments_panel.setObjectName("comparisonExperimentsPanel")
        lower=QHBoxLayout(self.experiments_panel);lower.setContentsMargins(0,0,0,0);lower.setSpacing(12)
        self.table_card=Card();self.table_card.setObjectName("comparisonTableCard")
        self.table_card.layout_box.setSpacing(0)
        self.experiments_heading=QWidget();self.experiments_heading.setFixedHeight(36)
        table_heading=QHBoxLayout(self.experiments_heading);table_heading.setContentsMargins(0,0,0,0);table_heading.setSpacing(8)
        self.experiments_title=QPushButton("Эксперименты");self.experiments_title.setObjectName("comparisonSectionToggle")
        self.experiments_title.setCursor(Qt.CursorShape.PointingHandCursor)
        self.experiments_title.clicked.connect(self.toggle_experiments)
        self.experiments_icon=QLabel();self.experiments_icon.setPixmap(QIcon(str(Path(__file__).with_name("resources")/"comparison_database.svg")).pixmap(24,24))
        table_heading.addWidget(self.experiments_icon);table_heading.addWidget(self.experiments_title);table_heading.addStretch()
        self.experiments_tools=QWidget();self.experiments_tools.setMinimumWidth(0)
        tools=QHBoxLayout(self.experiments_tools);tools.setContentsMargins(0,0,0,0);tools.setSpacing(8);tools.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.search=QLineEdit();self.search.setObjectName("comparisonSearch");self.search.setPlaceholderText("Поиск по экспериментам…")
        self.search.setToolTip("Метод, этап или статус; параметры: n:20 k:3 s:0 N:1024")
        self.search.setClearButtonEnabled(True);self.search.setMaximumWidth(260);self.search.setMinimumWidth(100)
        tools.addWidget(self.search,1)
        self.stage_filter=QComboBox()
        self.filter_button=action_button("settings","Фильтры экспериментов")
        tools.addWidget(self.filter_button)
        self.load_button=QPushButton();self.load_button.setObjectName("comparisonImport")
        self.load_button.setIcon(QIcon(str(Path(__file__).with_name("resources")/"parameter_folder.svg")))
        for button in (self.filter_button,self.load_button):
            button.setFixedSize(36,36);button.setIconSize(QSize(18,18))
        self.load_button.setToolTip("Загрузить базу экспериментов или JSON структуры")
        self.load_button.clicked.connect(self.load_requested);tools.addWidget(self.load_button)
        table_heading.addWidget(self.experiments_tools)
        self.table_card.layout_box.addWidget(self.experiments_heading)
        self.experiments_content=QWidget();self.experiments_content.setObjectName("comparisonPanelContent")
        content=QVBoxLayout(self.experiments_content);content.setContentsMargins(0,12,0,0);content.setSpacing(0);content.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.experiments_content.setMinimumHeight(0);self.experiments_content.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Ignored)
        self.table=QTableWidget(0,12);self.table.setObjectName("comparisonExperiments")
        self.table.setHorizontalHeader(MathHeaderView(self.table))
        self.table.setHorizontalHeaderLabels(("Метод","n","k","N","s","Раунды","Q","g","qRAM","Время","Статус","Этап"))
        header=self.table.horizontalHeader();header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setSectionResizeMode(0,QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(0,230)
        self.table.viewport().installEventFilter(self)
        for column,width in ((1,52),(2,52),(3,70),(4,52),(5,65),(6,85),(7,95),(8,85),(9,95),(10,115),(11,140)):self.table.setColumnWidth(column,width)
        self.table.horizontalHeaderItem(0).setTextAlignment(Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter)
        header.moveSection(11,1)
        for column in (3,5,8):self.table.setColumnHidden(column,True)
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self._columns_menu)
        self.table.setItemDelegate(ExperimentDelegate(self.table))
        self.table.verticalHeader().hide();self.table.verticalHeader().setDefaultSectionSize(38)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setWordWrap(False);self.table.setShowGrid(False)
        self.table.setToolTip("Q — модельные запросы к оракулу; g — вычисления функции сжатия; qRAM — пиковое число записей. Остальные столбцы доступны через меню заголовка.")
        header.setSortIndicator(-1,Qt.SortOrder.AscendingOrder)
        header.setSortIndicatorShown(False);header.setSectionsClickable(True)
        header.sectionClicked.connect(self._sort_experiments)
        self.table.setSortingEnabled(False)
        content.addWidget(self.table);self.table_card.layout_box.addWidget(self.experiments_content,1)
        self.inspector=Card();self.inspector.setObjectName("comparisonInspector")
        self.inspector.setMinimumWidth(340);self.inspector.setMaximumWidth(350)
        self.inspector.layout_box.setSpacing(0)
        self.inspector_heading=QWidget();self.inspector_heading.setFixedHeight(36)
        title=QHBoxLayout(self.inspector_heading);title.setContentsMargins(0,0,0,0);title.setSpacing(8)
        self.inspector_icon=QLabel();self.inspector_icon.setPixmap(QIcon(str(Path(__file__).with_name("resources")/"comparison_info.svg")).pixmap(23,23))
        self.inspector_title=QPushButton("Выбранный эксперимент");self.inspector_title.setObjectName("comparisonSectionToggle")
        self.inspector_title.setCursor(Qt.CursorShape.PointingHandCursor);self.inspector_title.clicked.connect(self.toggle_experiments)
        title.addWidget(self.inspector_icon);title.addWidget(self.inspector_title,1)
        self.inspector.layout_box.addWidget(self.inspector_heading)
        self.inspector_content=QWidget();self.inspector_content.setObjectName("comparisonPanelContent")
        inspector_box=QVBoxLayout(self.inspector_content);inspector_box.setContentsMargins(0,12,0,0);inspector_box.setSpacing(12);inspector_box.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.inspector_content.setMinimumHeight(0);self.inspector_content.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Ignored)
        scroll=QScrollArea();scroll.setObjectName("comparisonInspectorScroll");scroll.viewport().setObjectName("comparisonInspectorViewport")
        scroll.setWidgetResizable(True);scroll.setFrameShape(QScrollArea.Shape.NoFrame);scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setMinimumHeight(0);scroll.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Ignored)
        body=QWidget();body.setObjectName("inspectorBody");body_layout=QVBoxLayout(body);body_layout.setContentsMargins(0,0,2,0);body_layout.setSpacing(4)
        self.inspector_values={};self.inspector_names={}
        badges=QHBoxLayout()
        for key in ("method","stage"):
            badge=QLabel("Нет данных");badge.setObjectName("comparisonBadge");badge.setWordWrap(True)
            self.inspector_values[key]=badge;badges.addWidget(badge)
        badges.addStretch();body_layout.addLayout(badges)
        for key,name in (("time","Время выполнения"),("Q","Запросов к оракулу"),("g","Вычислений функции сжатия")):
            self._inspector_row(body_layout,key,name)
        line=QFrame();line.setFixedHeight(1);line.setObjectName("comparisonDivider");body_layout.addWidget(line)
        body_layout.addWidget(QLabel("Параметры"))
        parameters=QGridLayout();parameters.setHorizontalSpacing(10);parameters.setVerticalSpacing(3)
        for index,key in enumerate(("n","k","s")):
            pair=QHBoxLayout();pair.setSpacing(4)
            name=QLabel(math_html(("Раунды" if key=="rounds" else key)+" ="));name.setObjectName("inspectorName")
            value=QLabel("–");value.setObjectName("inspectorValue");value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            pair.addWidget(name);pair.addWidget(value);pair.addStretch()
            parameters.addLayout(pair,index//3,index%3,1,2 if key=="rounds" else 1)
            self.inspector_names[key]=name;self.inspector_values[key]=value
        body_layout.addLayout(parameters)
        body_layout.addStretch();scroll.setWidget(body);inspector_box.addWidget(scroll,1)
        actions=QHBoxLayout()
        self.delete_button=QPushButton("Удалить");self.repeat_button=QPushButton("Повторить")
        self.repeat_button.setObjectName("primaryButton")
        self.delete_button.setObjectName("comparisonDelete")
        for button in (self.delete_button,self.repeat_button):
            button.setProperty("comparisonAction",True);button.setFixedHeight(44)
        actions.addWidget(self.delete_button);actions.addWidget(self.repeat_button)
        inspector_box.addLayout(actions);self.inspector.layout_box.addWidget(self.inspector_content,1)
        self.delete_button.clicked.connect(lambda:self.delete_requested.emit(self._selected_record()))
        self.repeat_button.clicked.connect(lambda:self.repeat_requested.emit(self._selected_record()))
        lower.addWidget(self.table_card,1);lower.addWidget(self.inspector)
        layout.addWidget(self.experiments_panel,4)
        self.search.textChanged.connect(self._controls_changed)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self._setup_scientific()
        self._collapse_animation=QVariantAnimation(self);self._collapse_animation.setDuration(240)
        self._collapse_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._collapse_animation.valueChanged.connect(self._reveal_experiments)
        self._collapse_animation.finished.connect(self._finish_experiments_transition)
        self._reveal_experiments(1.)

    def _sort_experiments(self,column):
        if column!=self._sort_column:
            self._sort_column=column;self._sort_order=Qt.SortOrder.AscendingOrder
        elif self._sort_order==Qt.SortOrder.AscendingOrder:
            self._sort_order=Qt.SortOrder.DescendingOrder
        else:
            self._sort_column=None;self._sort_order=None
        previous=self.table.blockSignals(True)
        try:self._apply_experiment_sort()
        finally:self.table.blockSignals(previous)

    def _apply_experiment_sort(self):
        header=self.table.horizontalHeader();previous=header.blockSignals(True)
        try:
            if self._sort_column is None:
                cells=[self.table.item(row,0) for row in range(self.table.rowCount())]
                for cell in cells:cell.use_natural_order=True
                try:self.table.sortItems(0,Qt.SortOrder.AscendingOrder)
                finally:
                    for cell in cells:cell.use_natural_order=False
                header.setSortIndicator(-1,Qt.SortOrder.AscendingOrder);header.setSortIndicatorShown(False)
            else:
                self.table.sortItems(self._sort_column,self._sort_order)
                header.setSortIndicator(self._sort_column,self._sort_order);header.setSortIndicatorShown(True)
        finally:header.blockSignals(previous)

    def toggle_experiments(self):
        self._experiments_collapsed=not self._experiments_collapsed
        self._collapse_animation.stop();self.experiments_tools.show()
        self._collapse_animation.setStartValue(self._experiments_progress)
        self._collapse_animation.setEndValue(0. if self._experiments_collapsed else 1.)
        self._collapse_animation.start()

    def _reveal_experiments(self,progress):
        self._experiments_progress=float(progress)
        margins=self.table_card.layout_box.contentsMargins()
        heading=margins.top()+self.experiments_heading.height()+margins.bottom()
        height=round(heading+(self._expanded_panel_height-heading)*self._experiments_progress)
        self.experiments_panel.setFixedHeight(height)
        for body in (self.experiments_content,self.inspector_content):
            body.setMaximumHeight(max(0,height-heading));body.setVisible(self._experiments_progress>0)
        self.experiments_tools.setMaximumWidth(round(340*self._experiments_progress))

    def _finish_experiments_transition(self):
        self.experiments_tools.setVisible(not self._experiments_collapsed)


    def eventFilter(self,watched,event):
        if hasattr(self,"table") and watched is self.table.viewport() and event.type()==QEvent.Type.Resize:
            header=self.table.horizontalHeader()
            others=sum(header.sectionSize(column) for column in range(1,self.table.columnCount()) if not self.table.isColumnHidden(column))
            self.table.setColumnWidth(0,max(210,self.table.viewport().width()-others))
        return super().eventFilter(watched,event)


    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,"inspector"):
            self.inspector.setMinimumWidth(340 if self.width()>=1350 else 275)
        if hasattr(self,"_collapse_animation"):
            self._expanded_panel_height=max(140,min(360,round(self.height()*.32)))
            self._reveal_experiments(self._experiments_progress)


    def closeEvent(self,event):
        if hasattr(self,'scientific_chart'):self.scientific_chart.shutdown()
        super().closeEvent(event)


    def _columns_menu(self,point):
        menu=QMenu(self.table)
        for column in range(self.table.columnCount()):
            action=menu.addAction(self.table.horizontalHeaderItem(column).text());action.setCheckable(True)
            action.setChecked(not self.table.isColumnHidden(column))
            action.toggled.connect(lambda checked,c=column:self.table.setColumnHidden(c,not checked))
        menu.exec(self.table.horizontalHeader().mapToGlobal(point))


    def _selected_record(self):
        selected=self.table.selectionModel().selectedRows()
        if not selected:return None
        cell=self.table.item(selected[0].row(),0)
        return self._records_by_id.get(cell.data(Qt.ItemDataRole.UserRole)) if cell else None


    def _inspector_row(self, layout: QVBoxLayout, key: str, label: str) -> None:
        line = QHBoxLayout()
        line.setSpacing(8)
        name = QLabel(math_html(label))
        name.setObjectName("inspectorName")
        name.setWordWrap(True)
        name.setMinimumHeight(32)
        value = QLabel("–")
        value.setObjectName("inspectorValue")
        value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        value.setWordWrap(True)
        value.setMinimumHeight(32)
        value.setMaximumWidth(110)
        line.addWidget(name, 3)
        line.addWidget(value, 1)
        layout.addLayout(line)
        self.inspector_values[key] = value
        self.inspector_names[key] = name


    @staticmethod
    def _counter(record):
        value = record.link_N if record.experiment_type == "herding" else record.first_level_N
        return "–" if value is None else value


    @staticmethod
    def _number(value: float | int | None, runtime: bool = False) -> str:
        if value is None:
            return "–"
        if runtime:return f"{value:.3f}".replace(".",",")+" с"
        if isinstance(value,float) and not value.is_integer():
            return f"{value:,.2f}".rstrip("0").rstrip(".").replace(","," ").replace(".",",")
        return formatted_number(int(value))


    def _fill_table(self) -> None:
        records = self._visible_records()
        selected = self.table.selectionModel().selectedRows()
        previously_selected = None
        if selected and selected[0].row() < self.table.rowCount():
            previously_selected = self.table.item(selected[0].row(), 0)
            previously_selected = previously_selected.data(Qt.ItemDataRole.UserRole) if previously_selected else None
        self.table.setUpdatesEnabled(False)
        self.table.blockSignals(True)
        sorting=self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(records))
        for row, record in enumerate(records):
            values = (
                "BBHT" if search_method(record.method) is SearchMethod.GROVER_BBHT else record.method_label,
                record.n, record.k, self._counter(record), record.sigma_bits,
                record.rounds, formatted_number(record.algorithmic_queries),
                formatted_number(self._g(record)), formatted_number(record.quantum_qram_peak_entries),
                self._number(record.elapsed_seconds, True), record.status,record.stage_label,
            )
            numeric={1:record.n,2:record.k,3:record.link_N if record.experiment_type=="herding" else record.first_level_N,4:record.sigma_bits,5:record.rounds,6:record.algorithmic_queries,7:self._g(record),8:record.quantum_qram_peak_entries,9:record.elapsed_seconds}
            for col, value in enumerate(values):
                cell = SortableItem(str(value))
                cell.natural_order=row
                cell.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter if col == 0 else
                                      Qt.AlignmentFlag.AlignCenter)
                if col == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, id(record))
                    cell.setData(Qt.ItemDataRole.UserRole+2,COLORS[search_method(record.method)])
                if col in numeric:cell.sort_value=numeric[col] if numeric[col] is not None else -1
                cell.setToolTip(str(value))
                self.table.setItem(row, col, cell)
        self.table.setSortingEnabled(sorting)
        self._apply_experiment_sort()
        if previously_selected not in {id(record) for record in records} and records:
            previously_selected=id(records[0])
        self.table.clearSelection()
        for row in range(self.table.rowCount()):
            if self.table.item(row,0).data(Qt.ItemDataRole.UserRole) == previously_selected:
                self.table.selectRow(row)
                break
        self.table.blockSignals(False)
        self.table.setUpdatesEnabled(True)
        self.experiments_title.setText("Эксперименты")
        self.experiments_title.setToolTip(f"Показано {len(records)} из {len(self.records)} записей")
        self._selection_changed()
