"""Связывает научный анализ с существующими карточками, графиком и таблицей Qt."""

from pathlib import Path

from PySide6.QtCore import Qt,QItemSelectionModel,QPoint
from PySide6.QtGui import QIcon,QShortcut,QKeySequence
from PySide6.QtWidgets import (
    QComboBox,QFileDialog,QFrame,QFormLayout,QHBoxLayout,QListView,QDialog,
    QMessageBox,QScrollArea,QSizePolicy,QToolButton,QVBoxLayout,QWidget,QMenu,
)

from algorithms.search_methods import SearchMethod,search_method
from integration.comparison_analysis import (
    AnalysisOptions,ComparisonAnalysis,METHOD_NAMES,STAGES,canonical,field_value,metric_value,
)
from integration.comparison_export import number
from integration.experiment_store import StoredExperiment
from .scientific_chart import ScientificChart
from .chart_presentation import ChartTitleCombo,ChartBackplate,METHOD_COLORS,present_chart
from .chart_point_inspector import ChartPointInspector
from .chart_numbers import human_number
from .fonts import header_font_family
from integration.scientific_charts import TITLES,chart_spec,write_chart


class ScientificComparisonMixin:
    def _setup_dashboard(self):
        self._sync_report={}
        self.setStyleSheet('''
            QWidget#comparisonTab QWidget {font-family:"Segoe UI";font-weight:400;}
            QWidget#comparisonTab QComboBox {min-height:28px;background:white;color:#334155;border:1px solid #DDE5F0;border-radius:7px;padding:0 9px;font-size:12px;}
            QWidget#comparisonTab QPushButton {min-height:28px;font-size:12px;border-radius:7px;}
        ''')
        self._settings_popup=QDialog(self.chart,Qt.WindowType.Popup)
        self._settings_popup.setObjectName('comparisonSettingsPopup')
        self._settings_popup.setWindowTitle('Параметры графика')
        self._settings_popup.setStyleSheet(f'''QDialog#comparisonSettingsPopup {{background:white;border:1px solid #DCE6F5;}}
            QWidget {{font-family:"{header_font_family()}";font-size:12px;}}
            QComboBox {{background:#F7FAFF;border:1px solid #DCE6F5;border-radius:8px;min-height:34px;padding:0 12px;}}''')
        form=QFormLayout(self._settings_popup);form.setContentsMargins(18,16,18,16);form.setSpacing(12)
        for label,combo in [('Стадия',self.stage_filter)]+[(key,self.value_filters[key]) for key in ('n','k','s')]:
            combo.setMinimumWidth(180);combo.setMaximumWidth(260)
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(10);form.addRow(label,combo)
        self._settings_popup.finished.connect(lambda *_:self.expand_button.setChecked(False))
        self.chart.layout_box.setContentsMargins(17,12,17,12);self.chart.layout_box.setSpacing(8)
        heading=QHBoxLayout();heading.setSpacing(8)
        self.graph_kind.setObjectName('comparisonGraphTitle');self.graph_kind.setMinimumWidth(0);self.graph_kind.setMaximumWidth(16777215)
        self.graph_kind.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Fixed)
        self.graph_kind.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.graph_kind.setMinimumContentsLength(14);self.graph_kind.setMaxVisibleItems(12)
        for i in range(self.graph_kind.count()):self.graph_kind.setItemText(i,TITLES[self.graph_kind.itemData(i)])
        self.graph_kind.setStyleSheet(f'QComboBox#comparisonGraphTitle {{font-family:"{header_font_family()}";font-size:20px;background:transparent;border:0;border-radius:0;padding:0;min-height:40px;max-height:44px;}}')
        heading.addWidget(self.graph_kind);heading.addStretch(1)
        for button in (self.expand_button,self.export_button):
            button.setFixedSize(36,36);heading.addWidget(button);button.show()
        self.chart.layout_box.addLayout(heading)
        body=QHBoxLayout();body.setContentsMargins(0,0,0,0);body.setSpacing(10)
        self.scientific_chart=ScientificChart(self.chart)
        self.scientific_chart.selected.connect(self._select_chart_item)
        self.scientific_chart.point_clicked.connect(self._show_chart_point)
        body.addWidget(self.scientific_chart,1)
        self.chart.layout_box.addLayout(body,1)
        self.point_inspector=ChartPointInspector(self.chart)
        self._point_escape=QShortcut(QKeySequence('Escape'),self.point_inspector)
        self._point_escape.activated.connect(self.point_inspector.hide)
        self.chart.setStyleSheet('QFrame#comparisonChart {background:transparent;border:0;}');self._chart_backplate=ChartBackplate(self.chart)
        menu=self.export_button.menu();menu.clear()
        for label,extension in [('PNG · 300 DPI','png'),('SVG','svg'),('CSV','csv'),('JSON','json')]:
            menu.addAction(label,lambda checked=False,ext=extension:self._export_dialog(ext))
        self.chart.setMinimumHeight(220);self.scroll_content.setMinimumHeight(280)
        content=self.scroll_content.layout();content.setContentsMargins(16,8,16,12);content.setSpacing(6)
        self.experiments_dock.show()
        self.experiments_dock.setStyleSheet(f'QWidget {{font-family:"{header_font_family()}";}}')
        for title in (self.experiments_title,self.inspector_title):title.setStyleSheet('font-size:17px;font-weight:400;')

    def _show_chart_point(self,payload):
        import json
        try:point=json.loads(payload)
        except (ValueError,TypeError):return
        identity=point.get('identity')
        group=next((g for g in self._snapshot.groups if g.identity==identity or any(o.uid==identity for o in g.observations)),None)
        method=point.get('method')
        if method not in METHOD_COLORS:return
        if group is None:
            candidates=[g for g in self._snapshot.groups if g.method.value==method]
            axis_value=point.get('axisValue')
            if isinstance(axis_value,(int,float)):
                candidates=[g for g in candidates if abs(g.x-axis_value)<.45]
                exact=[g for g in candidates if (g.summary.median if self._presentation=='dispersion' else g.value)==point.get('value')]
                if len(exact)==1:candidates=exact
            if len(candidates)==1:group=candidates[0]
        fields={'Метод':METHOD_NAMES[SearchMethod(method)]}
        item=next((o for o in group.observations if o.uid==identity),None) if group else None
        if group:
            config=group.configuration
            fields['Параметры']=f'n = {config["n"]} · k = {config["k"]} · s = {config["s"]}'
            if not item:fields['Запусков']=str(group.summary.count)
        else:
            candidates=[g for g in self._snapshot.groups if g.method.value==method]
            if candidates:
                def parameter(key):
                    values=sorted({g.configuration[key] for g in candidates})
                    return str(values[0]) if len(values)==1 else f'{values[0]}–{values[-1]}'
                fields['Параметры']=' · '.join(key+' = '+parameter(key) for key in ('n','k','s'))
        metric=self._snapshot.options.effective_metric
        expression='α' if self._snapshot.options.graph in ('theory','optimal') else 'Q' if metric=='queries' else 'g' if metric=='evaluations' else 'T'
        unit=' с' if metric=='runtime' else ' запросов' if metric=='queries' and expression=='Q' else ' вычислений' if metric=='evaluations' else ''
        fields['Значение']=human_number(point.get('value'))+unit
        graph=self._snapshot.options.graph
        if graph in ('theory','optimal'):
            rows=[row for row in self._chart_spec['rows'] if row['method']==fields['Метод'] and row.get('alpha')==point.get('value')]
            fields.pop('Значение',None);fields['Показатель α']=human_number(point.get('value'))
            if rows:
                fields['Теоретический α']=human_number(rows[0]['theoretical_alpha'])
                fields['Точек регрессии']=str(rows[0]['regression_points'])
                fields['Диапазон n']=f'{min(r["n"] for r in rows)}–{max(r["n"] for r in rows)}'
        elif graph=='dispersion':
            if item:
                fields['Испытание']=str(item.metadata.get('trial','не записано'))
            box=point.get('boxStats')
            if box:
                fields['Разброс']=f'Медиана: {human_number(box["median"])}\nСредние 50%: {human_number(box["q1"])} – {human_number(box["q3"])}\nГраницы без выбросов: {human_number(box["lower"])} – {human_number(box["upper"])}'
            else:fields['Разброс']='Недостаточно измерений'
        elif graph=='speedup' and group:
            fields['Преимущество']=human_number(group.value)+' ×';fields.pop('Значение',None)
            fields['Классический Q']=human_number(group.baseline_mean)
        elif graph=='components':
            fields['Этап']='Связывающий блок' if 'Связывающий' in point.get('traceName','') else 'Алмазная структура'
            fields['Среднее Q']=fields.pop('Значение')
        elif graph=='model_vs_actual':
            expression='g' if ' · g' in point.get('traceName','') else 'Q'
            fields['Значение']=human_number(point.get('value'))
        elif group and not item:
            fields['Разброс успешных']=f'{human_number(group.summary.minimum)} – {human_number(group.summary.maximum)}'
            if group.ci_low is not None and group.ci_high is not None:
                fields['95% интервал']=f'{human_number(group.ci_low)} – {human_number(group.ci_high)}'
        self.point_inspector.present('Точка графика',expression,fields)
        anchor=self.scientific_chart.mapTo(self.chart,QPoint(int(point.get('x',0)),int(point.get('y',0))))
        inspector=self.point_inspector
        inspector.move(max(10,min(anchor.x()+16,self.chart.width()-inspector.width()-10)),max(10,min(anchor.y()+12,self.chart.height()-inspector.height()-10)))
        inspector.raise_();inspector.setFocus()


    def _select_chart_item(self,identity):
        group=next((g for g in self._snapshot.groups if g.identity==identity or any(o.uid==identity for o in g.observations)),None)
        if group:self.select_group(group.identity)

    def set_sync_report(self,report):
        self._sync_report=report


    def _setup_scientific(self):
        self.analysis=ComparisonAnalysis()
        self._snapshot=None;self._selected_group_id=None;self._selecting_group=False
        self._refreshing=False;self._table_signature=None;self._entry_by_record={}
        self._presentation='complexity';self._last_complexity_graph='queries_n'
        self._metric_name='queries';self._axis_name='n';self.value_filters={}
        self.table.setSelectionMode(self.table.SelectionMode.ExtendedSelection)
        self.table.verticalHeader().setDefaultSectionSize(34);self.inspector.setMinimumWidth(290)
        self.graph_kind=ChartTitleCombo()
        for key in ('queries_n','evaluations_n','components','model_vs_actual','depth','speedup','dispersion'):
            self.graph_kind.addItem(TITLES[key],key)
        self.graph_kind.setAccessibleName('Вид графика')
        self.graph_kind.view().setObjectName('comparisonComboList')
        for key in ('n','k','s'):self._new_filter(key)
        self.expand_button=self.filter_button
        self.expand_button.setObjectName('comparisonFilterToggle');self.expand_button.setCheckable(True)
        self.expand_button.setIcon(QIcon(str(Path(__file__).with_name('resources')/'parameter_sliders.svg')))
        self.expand_button.setToolTip('Фильтры');self.expand_button.setAccessibleName('Фильтры')
        self.expand_button.toggled.connect(self._expand_filters)
        self.export_button=QToolButton();self.export_button.setObjectName('comparisonExport')
        self.export_button.setIcon(QIcon(str(Path(__file__).with_name('resources')/'result_save.svg')))
        self.export_button.setToolTip('Экспорт');self.export_button.setAccessibleName('Экспорт')
        self.export_button.setMenu(QMenu(self.export_button))
        self.export_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        old_layout=self.layout();old_layout.removeWidget(self.experiments_panel)
        self.scroll_content=QWidget();self.scroll_content.setObjectName('comparisonScrollContent')
        self.scroll_content.setLayout(old_layout)
        shell=QVBoxLayout(self);shell.setContentsMargins(0,0,0,0);shell.setSpacing(0)
        self.analysis_scroll=QScrollArea();self.analysis_scroll.setWidgetResizable(True)
        self.analysis_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.analysis_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.analysis_scroll.setWidget(self.scroll_content);shell.addWidget(self.analysis_scroll,1)
        self.experiments_dock=QWidget();self.experiments_dock.setObjectName('comparisonExperimentsDock')
        dock=QVBoxLayout(self.experiments_dock);dock.setContentsMargins(15,0,15,14)
        dock.setSpacing(0);dock.addWidget(self.experiments_panel);shell.addWidget(self.experiments_dock)
        self.scroll_content.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Ignored)
        self.graph_kind.currentIndexChanged.connect(self._graph_changed)
        self.stage_filter.currentIndexChanged.connect(self._stage_changed)
        self.stage_filter.setObjectName('comparisonCombo');self.stage_filter.setView(QListView())
        self.stage_filter.view().setObjectName('comparisonComboList')
        self._setup_dashboard();self._scientific_ready=True
        self._populate_values();self._redraw()

    def _new_filter(self,key):
        combo=QComboBox();combo.setObjectName("comparisonCombo");combo.setView(QListView(combo));combo.view().setObjectName("comparisonComboList")
        combo.setProperty('compactParameter',True)
        combo.setMinimumWidth(95);combo.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
        combo.setAccessibleName("Фильтр "+key);self.value_filters[key]=combo
        combo.setToolTip('Все измеренные значения или одно выбранное значение')
        combo.currentIndexChanged.connect(self._controls_changed)
        return combo

    def _populate_values(self, defaults=False):
        self._refreshing=True
        stage=self.stage_filter.currentData()
        self.stage_filter.blockSignals(True);self.stage_filter.clear()
        for key in ("diamond","herding","full"):
            self.stage_filter.addItem({"diamond":"Построение","herding":"Связывание","full":"Полная атака"}[key],key)
        index=self.stage_filter.findData(stage or "full");self.stage_filter.setCurrentIndex(max(0,index));self.stage_filter.blockSignals(False)
        stage=self.stage_filter.currentData()
        for key,combo in self.value_filters.items():
            previous=combo.currentData();combo.blockSignals(True);combo.clear();combo.addItem("Все",None)
            for value in self.analysis.available_values(key,stage):
                combo.addItem("Не записано" if value is None else str(value),canonical(value))
            if key in ('k','s') and combo.findData(canonical(4))<0:combo.addItem('4',canonical(4))
            index=combo.findData(previous);combo.setCurrentIndex(max(0,index));combo.blockSignals(False)
        if defaults:
            for key,value in (('n',None),('k',canonical(4)),('s',canonical(4))):
                combo=self.value_filters[key];index=combo.findData(value);combo.setCurrentIndex(max(0,index))
        self._refreshing=False
        self._adapt_controls()

    def _adapt_controls(self):
        graph=self.graph_kind.currentData();axis=self._effective_axis()
        form=self._settings_popup.layout();full=graph=='components'
        self.stage_filter.setVisible(not full);form.labelForField(self.stage_filter).setVisible(not full)
        if graph!='components':
            variable=self.value_filters[axis];blocked=variable.blockSignals(True);variable.setCurrentIndex(0);variable.blockSignals(blocked)

    def _effective_axis(self):
        if self._presentation=="speedup":return "n"
        return {"sigma":"s","depth":"k"}.get(self.graph_kind.currentData(),self._axis_name if self.graph_kind.currentData() == "dispersion" else "n")

    def _set_parameter_filters(self,sample):
        for key,combo in self.value_filters.items():
            blocked=combo.blockSignals(True)
            index=combo.findData(canonical(field_value(sample,key)))
            combo.setCurrentIndex(max(0,index));combo.blockSignals(blocked)

    def _graph_changed(self,*_):
        if self._refreshing:return
        graph=self.graph_kind.currentData()
        if graph in ("components","optimal") and self.stage_filter.currentData()!="full":
            self.stage_filter.blockSignals(True);self.stage_filter.setCurrentIndex(self.stage_filter.findData("full"));self.stage_filter.blockSignals(False);self._populate_values()
        self._presentation={"speedup":"speedup","dispersion":"dispersion"}.get(graph,"complexity")
        if self._presentation=="complexity":self._last_complexity_graph=graph
        self._adapt_controls();self._controls_changed()

    def reset_initial_view(self):
        self._refreshing=True
        self.stage_filter.setCurrentIndex(self.stage_filter.findData('full'))
        self.graph_kind.setCurrentIndex(self.graph_kind.findData('queries_n'))
        self._refreshing=False
        self._populate_values(defaults=True);self._graph_changed()

    def set_axis(self,axis):
        if axis not in ('n','k','s'):raise ValueError('Неизвестный параметр оси.')
        self._axis_name=axis
        if self.graph_kind.currentData() not in ('theory','dispersion'):
            blocked=self.graph_kind.blockSignals(True)
            self.graph_kind.setCurrentIndex(self.graph_kind.findData({'n':'queries_n','k':'depth','s':'sigma'}[axis]))
            self.graph_kind.blockSignals(blocked)
        self._graph_changed()

    def set_metric(self,metric):
        if metric not in ('queries','runtime','evaluations','memory'):raise ValueError('Неизвестная метрика.')
        self._metric_name=metric
        if self.graph_kind.currentData() in ('queries_n','evaluations_n','runtime_n') and self._presentation=='complexity':
            target={'queries':'queries_n','evaluations':'evaluations_n','runtime':'runtime_n'}.get(metric)
            if target:self.graph_kind.setCurrentIndex(self.graph_kind.findData(target))
        self._controls_changed()

    def _stage_changed(self,*_):
        if self._refreshing:return
        self._populate_values();self._graph_changed()

    def set_presentation(self,presentation):
        target=self._last_complexity_graph if presentation=="complexity" else presentation
        index=self.graph_kind.findData(target)
        if index<0:raise ValueError("Неизвестный вид графика.")
        if self.graph_kind.currentIndex()==index:self._graph_changed()
        else:self.graph_kind.setCurrentIndex(index)

    def _expand_filters(self,expanded):
        if expanded:
            self._settings_popup.adjustSize()
            self._settings_popup.move(self.expand_button.mapToGlobal(QPoint(self.expand_button.width()-self._settings_popup.width(),self.expand_button.height()+6)))
            self._settings_popup.show()
        else:self._settings_popup.hide()


    def _options(self):
        import json
        filters=tuple((key,self.value_filters[key].currentData()) for key in ('n','k','s') if self.value_filters[key].currentData() is not None)
        n=json.loads(self.value_filters['n'].currentData()) if self.value_filters['n'].currentData() is not None else None
        k=json.loads(self.value_filters['k'].currentData()) if self.value_filters['k'].currentData() is not None else None
        return AnalysisOptions(graph=self.graph_kind.currentData(),metric=self._metric_name,axis=self._effective_axis(),presentation=self._presentation,
                               aggregation='mean',stage=self.stage_filter.currentData(),methods=tuple(method.value for method in SearchMethod),
                               n_min=n if n is not None else 1,n_max=n if n is not None else 512,
                               k_min=k if k is not None else 1,k_max=k if k is not None else max(20,max((o.record.k for o in self.analysis.observations),default=20)),
                               filters=filters,comparable_only=False,logarithmic=False,uncertainty='ci',theory_ratio=False,search=self.search.text())

    def _controls_changed(self,*_):
        if self._refreshing or not self._scientific_ready:return
        self.point_inspector.hide()
        self._selected_group_id=None;self._redraw()

    def set_entries(self,entries):
        first=not self.records
        self.records=[entry.record for entry in entries]
        self._records_by_id={id(record):record for record in self.records}
        self._entry_by_record={id(entry.record):entry for entry in entries}
        self.analysis.set_entries(entries)
        stages={entry.record.experiment_type for entry in entries}
        if stages and self.stage_filter.currentData() not in stages:
            self.stage_filter.blockSignals(True)
            self.stage_filter.setCurrentIndex(max(0,self.stage_filter.findData(next(iter(sorted(stages))))))
            self.stage_filter.blockSignals(False)
        if first:
            self.stage_filter.blockSignals(True);self.stage_filter.setCurrentIndex(self.stage_filter.findData('full'));self.stage_filter.blockSignals(False)
        self._populate_values(defaults=first);self._table_signature=None
        if first:self._graph_changed()
        else:self._redraw()

    def set_records(self,records):
        self.set_entries([self._entry_by_record.get(id(record),StoredExperiment(f"session:{id(record)}",record,"")) for record in records])

    def add_entry(self,entry):
        entries=list(self.analysis.entries.values())+[entry]
        self.set_entries(entries);self.select_record(entry.record)

    def add_record(self,record):
        self.add_entry(StoredExperiment(f"session:{id(record)}",record,""))

    def clear_filters(self):
        if not self._scientific_ready:return
        self._refreshing=True
        for combo in self.value_filters.values():combo.setCurrentIndex(0)
        self.search.clear();self._refreshing=False;self._controls_changed()

    def _visible_records(self):
        if not getattr(self,"_scientific_ready",False) or self._snapshot is None:return []
        ids={uid for item in self._snapshot.observations for uid in (item.sources or (item.uid,))}
        return [entry.record for uid,entry in self.analysis.entries.items() if uid in ids]

    def _chart_records(self):
        return [item.record for item in self._snapshot.observations] if self._snapshot else []

    def _selected_group(self):
        group=self._selected_aggregate()
        return [item.record for item in group.observations] if group else []

    def _selected_aggregate(self):
        if not self._snapshot:return None
        if self._selected_group_id:
            return next((group for group in self._snapshot.groups if group.identity==self._selected_group_id),None)
        record=self._selected_record()
        entry=self._entry_by_record.get(id(record)) if record else None
        return next((group for group in self._snapshot.groups if entry and entry.identity in group.source_ids),None)

    def _metric(self,record):
        return metric_value(record,self._snapshot.options.effective_metric if self._snapshot else self._metric_name)

    @staticmethod
    def _g(record):
        return metric_value(record,"evaluations")

    def _redraw(self,*_,refill_table=True):
        if not getattr(self,"_scientific_ready",False) or self._refreshing:return
        self._redrawing=True
        self._snapshot=self.analysis.analyze(self._options())
        signature=tuple(id(record) for record in self._visible_records())
        if signature!=self._table_signature:
            self._table_signature=signature;self._fill_table()
        self._chart_spec=present_chart(chart_spec(self._snapshot,'auto',False,'auto'))
        self.scientific_chart.set_spec(self._chart_spec)
        self._redrawing=False
        self._show_record_details()
        self._sync_chart_selection()


    def _selection_changed(self):
        if not getattr(self,"_scientific_ready",False) or self._selecting_group:return
        self._selected_group_id=None
        self._show_record_details()
        if not self._redrawing:self._sync_chart_selection()

    def _sync_chart_selection(self):
        record=self._selected_record();entry=self._entry_by_record.get(id(record))
        target=None
        if entry and self._snapshot:
            groups={g.identity for g in self._snapshot.groups if entry.identity in g.source_ids}
            candidates=[]
            for curve,trace in enumerate(self._chart_spec['data']):
                for index,identity in enumerate(trace.get('customdata',[])):
                    if trace['y'][index] is not None and (identity==entry.identity or identity in groups):
                        candidates.append((0 if identity==entry.identity else 1,curve,index))
                if trace['type']=='bar' and self._snapshot.options.graph in ('theory','optimal'):
                    if any(row['id']==entry.identity and row.get('alpha')==trace['y'][0] for row in self._chart_spec['rows']):
                        candidates.append((2,curve,0))
            if candidates:
                _,curve,index=min(candidates);target=dict(trace=curve,index=index)
        self.scientific_chart.set_selection(target)

    def _show_record_details(self):
        record=self._selected_record()
        individual=record is not None and self._selected_group_id is None
        self.delete_button.setEnabled(individual);self.repeat_button.setEnabled(individual)
        if record is None:
            for label in self.inspector_values.values():label.setText("–")
            return
        for key,value in (("method",METHOD_NAMES[search_method(record.method)]),("stage",STAGES.get(record.experiment_type,record.stage_label)),
                          ("n",record.n),("k",record.k),("s",record.sigma_bits),("time",self._number(record.elapsed_seconds,True)),
                          ("Q",number(metric_value(record,"queries"))),("g",number(metric_value(record,"evaluations")))):
            self.inspector_values[key].setText(str(value));self.inspector_values[key].show()
        self.inspector_names["time"].setText("Время симулятора" if record.is_quantum else "Время выполнения")


    def select_group(self,identity):
        group=next((group for group in self._snapshot.groups if group.identity==identity),None)
        if group is None:return
        self._selected_group_id=identity;self._selecting_group=True
        selected=set(group.source_ids);self.table.clearSelection();first=None
        for row in range(self.table.rowCount()):
            record=self._records_by_id.get(self.table.item(row,0).data(Qt.ItemDataRole.UserRole));entry=self._entry_by_record.get(id(record))
            if entry and entry.identity in selected:
                self.table.selectionModel().select(self.table.model().index(row,0),QItemSelectionModel.SelectionFlag.Select|QItemSelectionModel.SelectionFlag.Rows)
                if first is None:first=self.table.item(row,0)
        if first:self.table.scrollToItem(first)
        self._selecting_group=False;self._show_record_details();self._sync_chart_selection()


    def select_record(self,record):
        if record not in self._visible_records():
            self._refreshing=True
            stage=self.stage_filter.findData(record.experiment_type)
            if stage>=0:self.stage_filter.setCurrentIndex(stage)
            self._refreshing=False;self._populate_values();self.clear_filters()
        for row in range(self.table.rowCount()):
            if self.table.item(row,0).data(Qt.ItemDataRole.UserRole)==id(record):
                self.table.selectRow(row);self.table.scrollToItem(self.table.item(row,0));return

    def export_to(self,path):
        path=Path(path)
        write_chart(path,self._chart_spec,self.analysis.entries.values())

    def _export_dialog(self,extension):
        filename="scientific_"+str(self.graph_kind.currentData())+"."+extension
        path,_=QFileDialog.getSaveFileName(self,"Экспорт научного графика",filename,f"{extension.upper()} (*.{extension})")
        if not path:return
        try:self.export_to(path)
        except Exception as exc:QMessageBox.warning(self,"Экспорт",str(exc))
