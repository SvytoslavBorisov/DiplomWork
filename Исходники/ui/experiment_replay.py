"""Показывает параметры и реальный прогресс повторного запуска поверх затемнения."""

from PySide6.QtCore import Qt, QEvent, Signal
from PySide6.QtWidgets import QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton, QPlainTextEdit

from .math_text import math_html


class ReplayDialog(QDialog):
    stop_requested = Signal()
    view_requested = Signal()

    def __init__(self, plan, parent):
        super().__init__(parent)
        self.setObjectName("experimentReplay")
        self.setWindowTitle("Повтор эксперимента")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setFixedWidth(520)
        self.running = True
        self.overlay = QWidget(parent)
        self.overlay.setObjectName("replayOverlay")
        self.overlay.setStyleSheet("QWidget#replayOverlay { background: rgba(12, 25, 50, 135); }")
        self.overlay.setGeometry(parent.rect())
        self.overlay.show();self.overlay.raise_()
        parent.installEventFilter(self)
        layout=QVBoxLayout(self);layout.setContentsMargins(28,24,28,24);layout.setSpacing(16)
        title=QLabel("Повтор эксперимента");title.setObjectName("sectionTitle");layout.addWidget(title)
        record=plan.entry.record
        text=f"{record.method_label}\n{record.stage_label}\nn = {record.n} · k = {record.k} · s = {record.sigma_bits}\nБлоков префикса: {record.prefix_blocks} · Раундов: {record.rounds}"
        seed=plan.request.seed if plan.request else plan.attack.get("seed")
        limit=plan.request.trials_limit if plan.request else plan.attack["trials_limit"]
        text+=f"\nЛимит вычислений: {limit:,}".replace(","," ")+f"\nseed: {seed if seed is not None else 'новый случайный'}"
        if plan.request:
            text+=f"\nПотоки: {plan.request.threads or 'авто'} · seed контрольной суммы: {plan.request.sigma_seed}"
            if record.is_quantum:
                text+="\nПодбор параметров: "+("теоретический" if plan.request.parameter_strategy=="theoretical" else f"целевая вероятность {plan.request.target_probability:g}")
        if record.search_configuration:
            text+="\nBBHT: "+record.search_configuration
        parameters=QLabel(math_html(text).replace("\n","<br>"));parameters.setWordWrap(True);layout.addWidget(parameters)
        if plan.attack:
            message=QPlainTextEdit();message.setReadOnly(True);message.setMaximumHeight(100)
            message.setPlainText("Префикс: "+plan.attack["description"]+"\nСобытие: "+plan.attack["event_result"])
            layout.addWidget(message)
        self.note=QLabel("Запуск вычислений…");self.note.setWordWrap(True);layout.addWidget(self.note)
        self.progress=QProgressBar();self.progress.setTextVisible(False)
        self.progress.setRange(0,plan.request.depth if plan.request else 0);layout.addWidget(self.progress)
        actions=QHBoxLayout();actions.addStretch()
        self.close_button=QPushButton("Остановить");self.close_button.clicked.connect(self._close_or_stop)
        self.view_button=QPushButton("Посмотреть");self.view_button.setObjectName("primaryButton");self.view_button.hide()
        self.view_button.clicked.connect(self._view)
        actions.addWidget(self.close_button);actions.addWidget(self.view_button);layout.addLayout(actions)

    def eventFilter(self, watched, event):
        if watched is self.parentWidget() and event.type()==QEvent.Type.Resize:
            self.overlay.setGeometry(watched.rect())
        return super().eventFilter(watched,event)

    def level_completed(self, data):
        count=len(data["structure"]);self.progress.setValue(count)
        self.note.setText(f"Построено уровней: {count} из {data['depth']}")

    def complete(self):
        self.running=False;self.progress.setRange(0,1);self.progress.setValue(1)
        self.note.setText("Повтор завершён. Новый эксперимент сохранён и выбран в таблице.")
        self.close_button.setText("Закрыть");self.close_button.setEnabled(True);self.view_button.show()

    def fail(self, message):
        self.running=False;self.progress.setRange(0,1);self.progress.setValue(0)
        self.note.setText(message);self.close_button.setText("Закрыть");self.close_button.setEnabled(True)

    def _close_or_stop(self):
        if self.running:
            self.close_button.setEnabled(False);self.note.setText("Остановка…");self.stop_requested.emit()
        else:self.reject()

    def _view(self):
        self.view_requested.emit();self.accept()

    def reject(self):
        if not self.running:super().reject()

    def closeEvent(self,event):
        if self.running:event.ignore()
        else:super().closeEvent(event)

    def done(self,result):
        if self.running:return
        self.parentWidget().removeEventFilter(self)
        self.overlay.hide();self.overlay.deleteLater()
        super().done(result)
