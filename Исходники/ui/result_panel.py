from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import Qt, QSize, QTimer, QPointF
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPainterPath, QPixmap
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QProgressBar, QScrollArea, QVBoxLayout, QHBoxLayout, QWidget, QGraphicsDropShadowEffect, QStackedWidget, QButtonGroup, QToolButton

from integration.result_adapter import ExperimentRecord, record_from_data
from .metric_widgets import formatted_number
from .parameter_panel import ParameterPanel
from .widgets import Card
from .log_panel import LogPage
from .json_page import JsonPage

RESOURCES = Path(__file__).with_name("resources")


class ResultIllustration(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(260)
        self._pixmap = QPixmap(str(RESOURCES / "result_empty.png"))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        size = self._pixmap.size().scaled(
            max(1, self.width() - 24), 244, Qt.AspectRatioMode.KeepAspectRatio
        )
        painter.drawPixmap(
            (self.width() - size.width()) // 2,
            (self.height() - size.height()) // 2,
            size.width(), size.height(), self._pixmap,
        )


class MetricTile(QFrame):
    def __init__(self, caption, value):
        super().__init__()
        self.setObjectName("resultMetricTile")
        self.setMinimumHeight(96)
        layout=QVBoxLayout(self); layout.setContentsMargins(10,14,10,14); layout.setSpacing(5)
        self.value_label=QLabel(value); self.value_label.setObjectName("resultMetricValue")
        self.name_label=QLabel(caption); self.name_label.setObjectName("resultMetricCaption"); self.name_label.setWordWrap(True)
        for label in (self.value_label,self.name_label):
            label.setAlignment(Qt.AlignmentFlag.AlignCenter); label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse); layout.addWidget(label)

    def set_value(self, value):
        self.value_label.setText(value)


class StatusGlyph(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(24,24)
        self.state="success"
        self.angle=0

    def paintEvent(self,event):
        painter=QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color=QColor("#009863" if self.state=="success" else "#C53030" if self.state=="error" else "#3485FF")
        painter.setPen(QPen(color,1.8))
        if self.state=="running":
            painter.drawArc(3,3,18,18,self.angle*16,270*16)
        else:
            painter.setBrush(color)
            painter.drawEllipse(2,2,20,20)
            painter.setPen(QPen(QColor("#FFFFFF"),1.7,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))
            path=QPainterPath(QPointF(7,12))
            if self.state=="success":
                path.lineTo(10,15);path.lineTo(17,8)
            else:
                path.moveTo(12,7);path.lineTo(12,13);path.moveTo(12,16);path.lineTo(12,17)
            painter.drawPath(path)


class StatusBanner(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("resultStatusBanner")
        layout=QHBoxLayout(self); layout.setContentsMargins(12,12,12,12); layout.setSpacing(9)
        self.symbol=StatusGlyph()
        self.value_label=QLabel(); self.value_label.setWordWrap(True)
        layout.addWidget(self.symbol); layout.addWidget(self.value_label,1)
        self._phase=0
        self.timer=QTimer(self); self.timer.timeout.connect(self._spin)

    def _spin(self):
        self._phase=(self._phase+1)%4
        self.symbol.angle=(self.symbol.angle+24)%360
        self.symbol.update()

    def set_value(self, text, state="success"):
        self.value_label.setText(text)
        self.symbol.state=state
        self.symbol.update()
        self.setProperty("state",state)
        for widget in (self,*self.findChildren(QWidget)):
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.update()
        self.timer.start(120) if state=="running" else self.timer.stop()


class ResultsPage(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("structureResultsPage")


class ResultPanel(Card):
    def __init__(self, parent=None, *, verification=True, message_mode=False):
        super().__init__(parent=parent)
        self.message_mode=message_mode
        self.completed_title="Поиск завершен успешно" if message_mode else "Построение завершено"
        self.verification_title="Проверка сообщения" if message_mode else "Проверка структуры"
        self.setObjectName("structureResultPanel")
        self.setMinimumWidth(300); self.setMaximumWidth(650)
        self.layout_box.setSpacing(12)
        heading=QHBoxLayout(); title=QLabel("Результат"); title.setObjectName("resultPanelTitle")
        heading.addWidget(title,1)
        self.page_buttons = []
        self.page_group = QButtonGroup(self)
        if verification:
            group = QFrame()
            group.setObjectName("resultPageSelector")
            group_layout = QHBoxLayout(group)
            group_layout.setContentsMargins(0,0,0,0)
            group_layout.setSpacing(5)
            for index,(name,tooltip) in enumerate((("results","Результаты"),("logs","Журнал"),("json","JSON"))):
                button = QToolButton()
                button.setObjectName("resultPageButton")
                button.setFixedSize(32,32)
                button.setIconSize(QSize(19,19))
                button.setCheckable(True)
                button.setToolTip(tooltip)
                button.setAccessibleName(tooltip)
                self.page_group.addButton(button,index)
                self.page_buttons.append(button)
                group_layout.addWidget(button)
            self.page_group.idClicked.connect(self.set_active_page)
            heading.addWidget(group)
        else:
            icon=QSvgWidget(str(RESOURCES/"result_analytics.svg"))
            icon.setFixedSize(21,21)
            heading.addWidget(icon)
        self.layout_box.addLayout(heading)
        line=QFrame()
        line.setObjectName("resultHeadingDivider")
        line.setFixedHeight(1)
        self.layout_box.addWidget(line)
        self.pages=QStackedWidget()
        self.layout_box.addWidget(self.pages,1)
        self.results_page=ResultsPage()
        self.results_layout=QVBoxLayout(self.results_page)
        self.results_layout.setContentsMargins(0,0,0,0)
        self.results_layout.setSpacing(12)
        self.pages.addWidget(self.results_page)
        self.log_page=LogPage() if verification else None
        self.json_page=JsonPage() if verification else None
        if verification:
            self.pages.addWidget(self.log_page)
            self.pages.addWidget(self.json_page)
        self.scroll=QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content=QWidget(); content.setObjectName("resultContent")
        self.content_layout=QVBoxLayout(content); self.content_layout.setContentsMargins(0,4,2,4); self.content_layout.setSpacing(12)
        self.status=StatusBanner(); self.content_layout.addWidget(self.status)
        self.progress=QProgressBar(); self.progress.setTextVisible(False); self.progress.setFixedHeight(8); self.content_layout.addWidget(self.progress)
        self.progress_label=QLabel(); self.progress_label.setObjectName("resultProgressCaption"); self.progress_label.setWordWrap(True); self.content_layout.addWidget(self.progress_label)
        self.metrics_host=QWidget(); self.metrics_layout=QVBoxLayout(self.metrics_host); self.metrics_layout.setContentsMargins(0,0,0,0); self.metrics_layout.setSpacing(12); self.content_layout.addWidget(self.metrics_host)
        self.verification_note=QLabel("Проверяются переходы и хэш-коды…\n\nДополнительные вычисления не учитываются в статистике.")
        self.verification_note.setObjectName("resultVerificationNote"); self.verification_note.setWordWrap(True); self.content_layout.addWidget(self.verification_note)
        self.empty=QWidget(); empty_layout=QVBoxLayout(self.empty); empty_layout.setContentsMargins(0,0,0,0); empty_layout.addStretch()
        empty_layout.addWidget(ResultIllustration())
        empty_text=QLabel("Результатов пока нет"); empty_text.setObjectName("resultEmptyTitle"); empty_text.setAlignment(Qt.AlignmentFlag.AlignCenter); empty_text.setWordWrap(True)
        empty_layout.addWidget(empty_text); empty_layout.addStretch()
        self.content_layout.addWidget(self.empty,1); self.content_layout.addStretch()
        self.scroll.setWidget(content); self.results_layout.addWidget(self.scroll,1)
        self.verification_result=QLabel(); self.verification_result.setObjectName("resultVerificationOutcome"); self.verification_result.setWordWrap(True); self.results_layout.addWidget(self.verification_result)
        self.verify_button=QPushButton(self.verification_title); self.verify_button.setObjectName("verifyStructureButton"); self.verify_button.setIcon(QIcon(str(RESOURCES/"result_shield.svg"))); self.verify_button.setIconSize(QSize(18,18))
        self.verify_button.setFixedHeight(48); ParameterPanel._add_shadow(self.verify_button); self.results_layout.addWidget(self.verify_button)
        self.cancel_button=QPushButton("Отменить проверку"); self.cancel_button.setObjectName("cancelVerificationButton"); self.results_layout.addWidget(self.cancel_button)
        self.verification_enabled=verification
        self.rows={}; self.verification_state="idle"
        self.set_empty()
        self.set_active_page(0)
        if self.log_page:
            self.log_page.cancel_button.clicked.connect(self.cancel_button.click)

    def set_active_page(self,page):
        index={"results":0,"logs":1,"json":2}.get(page,page)
        if not isinstance(index,int) or not 0<=index<self.pages.count():
            raise ValueError("Неизвестная страница результатов.")
        self.pages.setCurrentIndex(index)
        for number,button in enumerate(self.page_buttons):
            button.setChecked(number==index)
            name=("results","logs","json")[number]
            state="active" if number==index else "inactive"
            button.setIcon(QIcon(str(RESOURCES/f"result_page_{name}_{state}.svg")))

    def show_results(self): self.set_active_page(0)
    def show_logs(self): self.set_active_page(1)
    def show_json(self): self.set_active_page(2)

    def append_log(self,message,level="INFO"):
        if self.log_page: self.log_page.append(message,level)

    def set_json(self,data):
        if self.json_page: self.json_page.set_json(data)

    def set_experiment_details(self,text):
        self.append_log("Подробности эксперимента:\n"+text,"ERROR" if "Traceback" in text else "INFO")

    def _operation_page(self,text="",verification=False):
        if self.log_page:
            self.log_page.set_activity(text,verification)
            self.set_active_page(1 if text else 0)

    def set_empty(self):
        self.reset_verification()
        self.status.hide(); self.metrics_host.hide(); self.progress.hide(); self.progress_label.hide(); self.verify_button.hide(); self.cancel_button.hide(); self.verification_note.hide(); self.verification_result.hide(); self.empty.show()
        self.status.timer.stop()
        self.verification_state="idle"

    def clear_metrics(self):
        while self.metrics_layout.count():
            widget=self.metrics_layout.takeAt(0).widget()
            if widget: widget.deleteLater()
        self.rows.clear()

    def add_metric(self,key,caption,value):
        tile=MetricTile(caption,value); self.metrics_layout.addWidget(tile); self.rows[key]=tile
        return tile

    def set_running(self,total_levels):
        self.set_empty(); self.empty.hide(); self.status.show(); self.status.set_value("Построение структуры…","running")
        self.progress.show(); self.progress_label.show(); self.set_progress_level(0,total_levels)
        if self.json_page: self.json_page.mark_previous()
        self._operation_page("Выполняется построение")

    def set_progress_level(self,completed,total_levels):
        self.progress.setRange(0,total_levels); self.progress.setValue(completed)
        self.progress_label.setText(f"Построено уровней: {completed} из {total_levels}")

    def set_result(self,data,elapsed_seconds):
        self.set_record(record_from_data(data,elapsed_seconds,"Завершено"),data)

    def set_record(self,record: ExperimentRecord,data):
        self.set_empty(); self.empty.hide(); self.status.show(); self.status.set_value(self.completed_title)
        self.clear_metrics(); self.metrics_host.show()
        self.add_metric("elapsed","время выполнения","–" if record.elapsed_seconds is None else f"{record.elapsed_seconds:.3f}".replace(".",",")+" с")
        if record.is_quantum:
            self.add_metric("oracle","модельных запросов к оракулу",formatted_number(record.quantum_oracle_queries))
            self.add_metric("simulator","вычислений функции сжатия",formatted_number(record.quantum_simulator_hash_evaluations))
        else:
            self.add_metric("queries","вычислений функции сжатия",formatted_number(record.algorithmic_queries))
        self.verify_button.setVisible(self.verification_enabled); self.verify_button.setEnabled(True)
        self.set_json(data)
        self._operation_page()

    def set_loaded(self,data): self.set_result(data,None)

    def set_error(self):
        self.set_empty(); self.empty.hide(); self.status.show(); self.status.set_value("Ошибка построения","error")
        self._operation_page()

    def set_cancelled(self):
        self.set_empty(); self.empty.hide(); self.status.show(); self.status.set_value("Остановлено","neutral")
        self._operation_page()

    def set_verifying(self,total):
        self.verification_state="verifying"; self.empty.hide(); self.status.show(); self.status.set_value(self.verification_title,"running")
        self.verify_button.hide(); self.cancel_button.show(); self.verification_note.show(); self.verification_result.hide(); self.progress.show(); self.progress_label.show(); self.set_verification_progress(0,total)
        self._operation_page(self.verification_title,True)

    def set_verification_progress(self,completed,total):
        self.progress.setRange(0,max(1,total)); self.progress.setValue(completed)
        self.progress_label.setText(f"Проверено {completed} из {total} переходов")
        if self.log_page:
            self.log_page.note.setText(self.progress_label.text()+"\nДополнительные вычисления не учитываются в статистике.")

    def finish_verification(self,state,message=""):
        self.verification_state=state; self.cancel_button.hide(); self.verification_note.hide(); self.progress.hide(); self.progress_label.hide()
        self.status.set_value(self.completed_title)
        self.verification_result.setText(message or {"verified":"✓ Проверка пройдена","failed":"Проверка не пройдена","cancelled":"Проверка отменена"}[state])
        self.verification_result.setProperty("state",state); self.verification_result.style().unpolish(self.verification_result); self.verification_result.style().polish(self.verification_result); self.verification_result.setVisible(state!="verified")
        self.verify_button.setText("Проверка пройдена" if state=="verified" else self.verification_title)
        self.verify_button.setIcon(QIcon(str(RESOURCES/("result_check.svg" if state=="verified" else "result_shield.svg"))))
        self.verify_button.setProperty("verified",state=="verified")
        self.verify_button.style().unpolish(self.verify_button); self.verify_button.style().polish(self.verify_button)
        self.verify_button.show(); self.verify_button.setEnabled(state!="verified")
        self._operation_page()

    def verification_restored(self):
        if self.verification_state != "verified":
            self.verify_button.setEnabled(True)

    def reset_verification(self):
        self.verification_state="idle"
        self.verify_button.setText(self.verification_title)
        self.verify_button.setIcon(QIcon(str(RESOURCES/"result_shield.svg")))
        self.verify_button.setProperty("verified",False)
        self.verify_button.style().unpolish(self.verify_button); self.verify_button.style().polish(self.verify_button)
        self.verification_result.hide()
        self.verify_button.setEnabled(True)
