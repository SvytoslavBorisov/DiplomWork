from __future__ import annotations

from pathlib import Path
from dataclasses import asdict
import re

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)

from algorithms.search_methods import BBHTOptions, search_method
from integration.backend_adapter import AttackRunResult, BackendAdapter, BuildResult
from integration.herding_workflow import HerdingWorkflow
from integration.experiment_controller import ExperimentController
from integration.experiment_store import ExperimentStore
from integration.result_adapter import ExperimentRecord, record_from_data
from integration.experiment_replay import prepare_replay
from integration.comparison_import import ComparisonImport
from .experiment_replay import ReplayDialog
from .comparison_tab import ComparisonTab
from .diamond_tab import DiamondTab
from .header import Header
from .fonts import configure_application_fonts
from .herding_tab import HerdingTab
from .math_text import math_html
from .resource_check import available_physical_memory, memory_warning
from .titlebar import apply_light_windows_titlebar
from .report_sync_controller import ReportSyncController
from integration.project_paths import PROJECT_ROOT,DATA_ROOT,DIAMONDS_DIR


class MainWindow(QMainWindow):
    def __init__(self, adapter: BackendAdapter | None = None,
                 experiment_store: ExperimentStore | None = None) -> None:
        super().__init__()
        configure_application_fonts(QApplication.instance())
        self.setWindowTitle("КвантАлмаз")
        self.setWindowIcon(QIcon(str(Path(__file__).resolve().parent / "resources" / "app.ico")))
        self.resize(1500, 900)
        self.setMinimumSize(900, 500)
        self.adapter = adapter or BackendAdapter()
        self.experiment_store = experiment_store or ExperimentStore()
        self.controller = ExperimentController(self.adapter, self)
        self.herding_workflow = HerdingWorkflow(self.controller)
        self._close_pending = False
        self._verification_kind = "diamond"
        self._verification_id = 0
        self._verification_outcome = None
        self.current_diamond: dict | None = None
        self.current_path: Path | None = None
        self.current_elapsed: float | None = None
        self.committed_description: str | None = None
        self._attack_trials_limit: int | None = None
        self._build_request = None
        self._replay_dialog = None
        self._replay_controller = None
        self._database_import = None
        root = QWidget()
        root.setObjectName("appRoot")
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.header = Header(self.adapter.backend_name(), self.adapter.thread_label())
        root_layout.addWidget(self.header)
        self.tabs = QStackedWidget()
        self.tabs.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Ignored)
        self.diamond_tab = DiamondTab()
        self.herding_tab = HerdingTab()
        self.comparison_tab = ComparisonTab()
        self._comparison_opened=False
        self.comparison_tab.set_entries(self.experiment_store.entries)
        self.comparison_tab.load_errors = self.experiment_store.load_errors
        if self.experiment_store.load_errors:self.comparison_tab._redraw(refill_table=False)
        for widget, title in ((self.diamond_tab, "Алмазная структура"),
                              (self.herding_tab, "Herding-атака"),
                              (self.comparison_tab, "Сравнение")):
            self.tabs.addWidget(widget)
            self.header.tabs.addTab(title)
        self.header.tabs.currentChanged.connect(self._activate_tab)
        root_layout.addWidget(self.tabs, 1)
        self.setCentralWidget(root)
        self._connect()
        self.report_sync = None
        if experiment_store is None:
            self.report_sync = ReportSyncController(self.experiment_store, DATA_ROOT/'experiments/reports', self)
            self.report_sync.completed.connect(self._reports_synced)

    def _activate_tab(self,index):
        if index==2 and not self._comparison_opened:
            self._comparison_opened=True;self.comparison_tab.reset_initial_view()
        self.tabs.setCurrentIndex(index)

    def _reports_synced(self, report):
        if report.get('added'):
            first_import = not any(entry.metadata.get('run_id') for entry in self.comparison_tab.analysis.entries.values())
            self.comparison_tab.set_entries(self.experiment_store.snapshot())
            if first_import:
                self.comparison_tab._graph_changed()
        self.comparison_tab.set_sync_report(report)

    def _connect(self) -> None:
        params = self.diamond_tab.parameters
        params.build_requested.connect(self._start_build)
        params.stop_requested.connect(self._stop_build)
        params.open_requested.connect(self._open_json)
        params.method_combo.currentIndexChanged.connect(
            lambda: self.header.set_mode(search_method(params.method_combo.currentData()).is_quantum)
        )
        self.herding_tab.results.verify_button.clicked.connect(self._start_message_verification)
        self.herding_tab.results.cancel_button.clicked.connect(self._cancel_verification)
        self.herding_tab.view.verification_progress.connect(self._verification_visual_progress)
        self.herding_tab.view.verification_animation_finished.connect(self._verification_animation_finished)
        self.herding_tab.view.verification_restored.connect(self._verification_restored)
        self.herding_tab.load_requested.connect(self._open_json)
        self.herding_tab.commit_requested.connect(self._commit)
        self.herding_tab.attack_requested.connect(self._start_attack)
        self.herding_tab.stop_requested.connect(self.controller.cancel_attack)
        self.controller.attack_cancelled.connect(self._attack_cancelled)
        self.comparison_tab.load_requested.connect(self._load_experiment_database)
        self.comparison_tab.delete_requested.connect(self._delete_experiment)
        self.comparison_tab.repeat_requested.connect(self._repeat_experiment)
        self.diamond_tab.results.verify_button.clicked.connect(self._start_verification)
        self.diamond_tab.results.cancel_button.clicked.connect(self._cancel_verification)
        self.controller.verification_progress.connect(self._verification_progress)
        self.controller.verification_finished.connect(self._verification_finished)
        self.diamond_tab.view.verification_progress.connect(self._verification_visual_progress)
        self.diamond_tab.view.verification_animation_finished.connect(self._verification_animation_finished)
        self.diamond_tab.view.verification_restored.connect(self._verification_restored)
        self.controller.build_level.connect(self._build_level)
        self.controller.build_started.connect(self._build_started)
        self.controller.build_log.connect(self._build_log)
        self.controller.build_finished.connect(self._build_finished)
        self.controller.build_failed.connect(self._build_failed)
        self.controller.build_cancelled.connect(self._build_cancelled)
        self.controller.attack_started.connect(lambda: self.herding_tab.set_busy(True))
        self.controller.attack_finished.connect(self._attack_finished)
        self.controller.attack_failed.connect(self._attack_failed)

    def _invalidate_verification(self, *, reset_success=True):
        self._verification_id += 1
        self.controller.cancel_verification()
        self._verification_outcome = None
        self.diamond_tab.view.clear_verification()
        self.herding_tab.view.clear_verification()
        for panel in (self.diamond_tab.results,self.herding_tab.results):
            if panel.verification_state=="verifying":panel.finish_verification("cancelled")
            elif reset_success and panel.verification_state=="verified":panel.reset_verification()

    def _start_verification(self):
        if self.current_diamond is None or self.controller.has_running_tasks(): return
        self._invalidate_verification(reset_success=False)
        self._verification_kind = "diamond"
        token = self._verification_id
        total = 2 * sum(len(level) for level in self.current_diamond["structure"])
        self.diamond_tab.results.set_verifying(total)
        self.diamond_tab.view.begin_verification(token)
        self.controller.start_verification(token, self.current_diamond)
        self.diamond_tab.results.append_log("Независимая проверка структуры запущена.", "INFO")

    def _verification_target(self):
        tab=self.herding_tab if self._verification_kind=="message" else self.diamond_tab
        return tab.results,tab.view

    def _start_message_verification(self):
        result=self.herding_tab._last_result
        if result is None or self.current_diamond is None or self.controller.has_running_tasks():return
        self._invalidate_verification(reset_success=False)
        self._verification_kind="message"
        panel,view=self._verification_target()
        view.finish_attack_animation()
        token=self._verification_id
        panel.set_verifying(len(result.suffix_blocks))
        view.begin_verification(token)
        self.controller.start_message_verification(token,self.current_diamond,result)
        panel.append_log("Независимая проверка сообщения запущена: префикс, связывающий блок и выбранный путь до корня.")

    def _verification_progress(self, token, events):
        if token==self._verification_id:
            panel,view=self._verification_target()
            if self._verification_kind=="message":view.mark_messages_verified()
            view.enqueue_verification(token, events)

    def _verification_visual_progress(self, token, completed, total):
        if token==self._verification_id:
            panel,_=self._verification_target()
            panel.set_verification_progress(completed,total)
            panel.append_log(f"Подтверждено {completed} из {total} переходов.","INFO")

    def _verification_finished(self, token, outcome):
        if token!=self._verification_id:return
        self._verification_outcome=outcome
        panel,view=self._verification_target()
        if outcome["state"]=="verified":view.verification_computed(token)
        elif outcome["state"]=="failed":
            view.fail_verification(token,outcome)
            if self._verification_kind=="message":view.mark_messages_verified(failed=True)
            panel.finish_verification("failed","Проверка не пройдена. "+outcome["message"])
            panel.append_log(outcome["message"],"ERROR");panel.set_experiment_details(outcome["trace"])
        else:
            view.clear_verification();panel.finish_verification("cancelled")

    def _verification_animation_finished(self, token):
        if token!=self._verification_id:return
        panel,_=self._verification_target();panel.finish_verification("verified")
        outcome=self._verification_outcome or {}
        panel.append_log(f"Проверка пройдена: {outcome.get('completed',0)} дополнительных вычислений функции сжатия; {outcome.get('elapsed_seconds',0):.3f} с. Исходная статистика не изменена.","DONE")

    def _verification_restored(self, token):
        if token==self._verification_id:self._verification_target()[0].verification_restored()

    def _cancel_verification(self):
        panel,_=self._verification_target()
        self._invalidate_verification(reset_success=False);panel.finish_verification("cancelled")
        panel.append_log("Независимая проверка отменена.")

    def _start_build(self) -> None:
        if self.controller.has_running_tasks():
            QMessageBox.information(self, "Вычисление выполняется", "Сначала остановите текущее вычисление.")
            return
        from integration.project_paths import new_diamond_directory
        request = self.diamond_tab.parameters.request(new_diamond_directory())
        try:
            self.adapter.validate_request(request)
        except Exception as exc:
            message = str(exc)
            QMessageBox.warning(self, "Параметры", math_html(message))
            return
        if search_method(request.method).is_quantum:
            warning = memory_warning(
                request.truncate_bits, request.depth, available_physical_memory(),
                parameter_strategy=request.parameter_strategy, target_probability=request.target_probability,
                dense_max_states=request.bbht_options.dense_max_states if request.bbht_options else 8192,
            )
            if warning:
                QMessageBox.warning(self, "Недостаточно памяти", math_html(warning))
                return
        self.header.set_mode(search_method(request.method).is_quantum)
        self._build_request = request
        self.controller.start_build(request)

    def _build_started(self) -> None:
        self._invalidate_verification()
        self.diamond_tab.view.show_placeholder()
        self.diamond_tab.parameters.set_busy(True)
        depth = self.diamond_tab.parameters.k_spin.value()
        self.diamond_tab.results.set_running(depth)
        self.diamond_tab.set_building(True, depth)
        self.diamond_tab.results.append_log("Построение алмазной структуры запущено", "INFO")

    def _build_level(self, data):
        self.diamond_tab.view.set_partial_data(data)
        completed = len(data["structure"])
        self.diamond_tab.results.set_progress_level(completed, data["depth"])
        self.diamond_tab.set_building(True, data["depth"], completed)

    def _build_log(self, message: str) -> None:
        translated = (message.replace("Blackburn", "Классический алгоритм")
                      .replace("Quantum Algorithm 2", "Квантовый алгоритм")
                      .replace(", без реального квантового ускорения.", "")
                      .replace("state-vector", "классический симулятор"))
        self.diamond_tab.results.append_log(translated, "MATCH" if "matching=" in message else "INFO")
        match = re.search(r"Уровень (\d+)", message)
        if match:
            level = int(match.group(1))
            depth = self.diamond_tab.parameters.k_spin.value()
            self.diamond_tab.set_building(True, depth, level)
            complete = level if message.startswith("[Quantum]") and "пар," in message else level - 1
            self.diamond_tab.results.set_progress_level(complete, depth)

    def _stop_build(self) -> None:
        self.diamond_tab.parameters.set_stopping()
        self.diamond_tab.results.append_log("Остановка построения…", "INFO")
        self.controller.cancel_build()

    def _build_cancelled(self) -> None:
        self.diamond_tab.parameters.set_busy(False)
        self.diamond_tab.set_building(False)
        self.diamond_tab.results.set_cancelled()
        self.diamond_tab.results.append_log("Построение остановлено", "DONE")

    def _build_finished(self, value: object) -> None:
        result = value
        if not isinstance(result, BuildResult):
            self._build_failed("Backend вернул неизвестный результат.", "")
            return
        self.diamond_tab.parameters.set_busy(False)
        self.diamond_tab.set_building(False)
        self._set_current_diamond(result.data, result.path, result.elapsed_seconds, preserve_view=True)
        self.diamond_tab.results.set_result(result.data, result.elapsed_seconds)
        self.diamond_tab.results.append_log(f"Алмазная структура построена за {result.elapsed_seconds:.3f} с", "DONE")
        self.diamond_tab.results.append_log(f"Сохранено: {result.path}", "DONE")
        try:
            metadata = {"build_request": self._request_metadata(self._build_request)} if self._build_request else None
            entry = self.experiment_store.add_completed(result.data, result.elapsed_seconds, result.path, metadata)
            self.comparison_tab.add_entry(entry)
        except Exception as exc:
            self.comparison_tab.add_record(self._record(result.data, result.elapsed_seconds, "Завершено"))
            self.diamond_tab.results.append_log(f"Не удалось сохранить эксперимент в базу: {exc}", "ERROR")

    def _build_failed(self, message: str, trace: str) -> None:
        self.diamond_tab.parameters.set_busy(False)
        self.diamond_tab.set_building(False)
        self.diamond_tab.results.set_error()
        allocation_failure = "bad allocation" in (message + trace).lower() or "memoryerror" in (message + trace).lower()
        if allocation_failure:
            message = ("Недостаточно памяти для построения алмазной структуры. "
                       "Уменьшите размер хэш-кода или глубину алмаза и повторите попытку.")
        self.diamond_tab.results.append_log(message, "ERROR")
        if trace and not allocation_failure:
            self.diamond_tab.results.set_experiment_details(trace)
        elif allocation_failure:
            self.diamond_tab.results.set_experiment_details(message)
        QMessageBox.critical(self, "Ошибка построения", message)

    def _set_current_diamond(self, data: dict, path: Path | None, elapsed: float | None = None, *, preserve_view: bool = False) -> None:
        self._invalidate_verification()
        self.herding_workflow.load(data)
        self.current_diamond = data
        self.current_path = path
        self.current_elapsed = elapsed
        self.committed_description = None
        quantum = search_method(data.get("builder", "blackburn")).is_quantum
        self.header.set_mode(quantum)
        index = self.diamond_tab.parameters.method_combo.findData(search_method(data.get("builder", "blackburn")).storage_id)
        if index >= 0:
            self.diamond_tab.parameters.method_combo.setCurrentIndex(index)
        self.diamond_tab.view.set_data(data, preserve_view=preserve_view)
        self.diamond_tab.results.set_json(data)
        self.herding_tab.set_diamond(data, path.name if path else "Алмазная структура текущей сессии")

    def _open_json(self) -> None:
        if self.controller.has_running_tasks():
            QMessageBox.information(self, "Вычисление выполняется", "Сначала остановите текущее вычисление.")
            return
        DIAMONDS_DIR.mkdir(parents=True,exist_ok=True)
        path, _ = QFileDialog.getOpenFileName(self, "Открыть JSON алмазной структуры", str(DIAMONDS_DIR), "Структуры (diamond_v*.json);;JSON (*.json);;Все файлы (*)")
        if not path:
            return
        try:
            data = self.adapter.load_json(path)
            self._set_current_diamond(data, Path(path))
            self.diamond_tab.results.set_loaded(data)
            self.diamond_tab.results.append_log(f"Загружен и проверен {Path(path).name}", "DONE")
            if self.experiment_store.import_diamond(Path(path), self.adapter):
                self.comparison_tab.set_entries(self.experiment_store.entries)
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка загрузки", str(exc))

    def _commit(self, description: str) -> None:
        if not self._require_diamond() or not description:
            return
        try:
            root = self.herding_workflow.commit(description)
        except Exception as exc:
            QMessageBox.warning(self, "Коммитмент", str(exc))
            return
        self.committed_description = description
        self.herding_tab.set_commitment(root)

    def _start_attack(self, description: str, event_result: str, limit: int, method: str) -> None:
        self._invalidate_verification(reset_success=False)
        if not self._require_diamond():
            return
        if self.committed_description is None:
            QMessageBox.warning(self, "Коммитмент", "Сначала зафиксируйте коммитмент.")
            return
        if description != self.committed_description:
            QMessageBox.warning(self, "Коммитмент", "Публикуемая часть изменилась. Зафиксируйте коммитмент заново.")
            return
        self.header.set_mode(search_method(method).is_quantum)
        self._attack_trials_limit = limit
        try:
            self.herding_workflow.start(description, event_result, limit, method,
                                        bbht_options=BBHTOptions() if search_method(method).value == "grover_bbht" else None)
        except Exception as exc:
            QMessageBox.warning(self, "Параметры поиска", str(exc))

    def _attack_finished(self, value: object) -> None:
        self.herding_tab.set_busy(False)
        if not isinstance(value, AttackRunResult):
            self._attack_failed("Backend вернул неизвестный результат.", "")
            return
        try:
            self.herding_workflow.complete(value.result)
        except Exception as exc:
            self._attack_failed(str(exc), "")
            return
        self.herding_tab.show_result(value.result, value.elapsed_seconds)
        if self.current_diamond is not None:
            try:
                entry = self.experiment_store.add_attack(
                    self.current_diamond, value.result, value.elapsed_seconds, self.current_path,
                    self._attack_trials_limit,
                )
                self.comparison_tab.add_entry(entry)
            except Exception as exc:
                self.herding_tab.show_error(f"Не удалось сохранить эксперимент в базу: {exc}")

    def _load_experiment_database(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Загрузить эксперименты", str(Path.cwd()), "JSON (*.json);;Все файлы (*)",
        )
        if not paths:
            return
        progress=QProgressDialog("Загрузка и проверка базы экспериментов…","",0,0,self)
        progress.setWindowModality(Qt.WindowModality.WindowModal);progress.setCancelButton(None)
        progress.setMinimumDuration(0);progress.show()
        worker=ComparisonImport(self.experiment_store,paths,self.adapter,self)
        self._database_import=worker
        def completed(added,errors):
            self.comparison_tab.set_entries(self.experiment_store.entries)
            progress.close()
            message=f"Добавлено записей: {added}. Всего в базе: {len(self.experiment_store.records)}."
            if errors:QMessageBox.warning(self,"Загрузка экспериментов",message+"\n\n"+"\n".join(errors))
            else:QMessageBox.information(self,"Загрузка экспериментов",message)
        worker.completed.connect(completed)
        worker.finished.connect(lambda:setattr(self,"_database_import",None))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    @staticmethod
    def _request_metadata(request):
        values = asdict(request)
        values["output_directory"] = str(values["output_directory"])
        return values

    def _delete_experiment(self, record):
        if record is None:return
        try:
            self.experiment_store.remove_record(record)
            self.comparison_tab.set_entries(self.experiment_store.entries)
        except Exception as exc:
            QMessageBox.warning(self,"Удаление эксперимента",str(exc))

    def _repeat_experiment(self, record):
        if record is None:return
        if self.controller.has_running_tasks() or self._replay_controller is not None:
            QMessageBox.information(self,"Повтор эксперимента","Сначала дождитесь завершения текущего вычисления.")
            return
        entry=self.experiment_store.find_record(record)
        if entry is None:return
        try:
            plan=prepare_replay(entry,self.experiment_store,self.adapter)
            if plan.request and search_method(plan.request.method).is_quantum:
                warning=memory_warning(plan.request.truncate_bits,plan.request.depth,available_physical_memory(),
                                       parameter_strategy=plan.request.parameter_strategy,target_probability=plan.request.target_probability,
                                       dense_max_states=plan.request.bbht_options.dense_max_states if plan.request.bbht_options else 8192)
                if warning:raise ValueError(warning)
        except Exception as exc:
            QMessageBox.warning(self,"Повтор эксперимента",str(exc));return
        dialog=ReplayDialog(plan,self);self._replay_dialog=dialog
        controller=ExperimentController(self.adapter,self);self._replay_controller=controller
        full_build={}
        def release():
            self._replay_controller=None
            controller.deleteLater()
        def failed(message,*_):
            dialog.fail("Повтор не завершён: "+message);release()
        def completed(result):
            try:
                metadata={"repeated_from":entry.identity}
                if isinstance(result,BuildResult) and plan.attack is not None:
                    full_build['result']=result
                    dialog.note.setText('Поиск связывающего блока…')
                    controller._launch_process(dict(plan.attack,data=result.data))
                    return
                if isinstance(result,BuildResult):
                    metadata["build_request"]=self._request_metadata(plan.request)
                    new_entry=self.experiment_store.add_completed(result.data,result.elapsed_seconds,result.path,metadata)
                elif isinstance(result,AttackRunResult):
                    metadata["seed"]=plan.attack.get("seed")
                    if full_build:
                        metadata['build_request']=self._request_metadata(plan.request)
                        new_entry=self.experiment_store.add_full(full_build['result'],result,plan.attack['trials_limit'],metadata)
                    else:
                        new_entry=self.experiment_store.add_attack(plan.data,result.result,result.elapsed_seconds,plan.source,
                                                                   plan.attack["trials_limit"],metadata)
                else:raise ValueError("Неизвестный результат повторного запуска.")
                self.comparison_tab.add_entry(new_entry)
                self.comparison_tab.select_record(new_entry.record)
                dialog.complete()
            except Exception as exc:
                dialog.fail("Не удалось сохранить повтор: "+str(exc))
            release()
        controller.build_level.connect(dialog.level_completed)
        controller.build_log.connect(lambda message:dialog.note.setText(message[-240:]))
        controller.build_finished.connect(completed)
        controller.build_failed.connect(failed)
        controller.build_cancelled.connect(lambda:failed("Вычисление остановлено."))
        dialog.stop_requested.connect(controller.cancel_build)
        dialog.view_requested.connect(lambda:self.header.tabs.setCurrentIndex(2))
        dialog.finished.connect(lambda _:setattr(self,"_replay_dialog",None))
        dialog.finished.connect(dialog.deleteLater)
        dialog.open()
        try:
            if plan.request:controller.start_build(plan.request)
            else:controller._launch_process(plan.attack)
        except Exception as exc:failed(str(exc))

    def _attack_cancelled(self) -> None:
        self.herding_workflow.cancel()
        self.herding_tab.set_busy(False)
        self.herding_tab.set_cancelled()
        self.herding_tab.results.append_log("Поиск связывающего блока остановлен.")

    def _attack_failed(self, message: str, trace: str) -> None:
        self.herding_workflow.fail()
        self.herding_tab.set_busy(False)
        self.herding_tab.show_error(trace or message)
        QMessageBox.critical(self, "Ошибка herding", message)

    def _require_diamond(self) -> bool:
        if self.current_diamond is not None:
            return True
        QMessageBox.warning(self, "Алмазная структура", "Сначала постройте или загрузите алмазную структуру.")
        return False

    @staticmethod
    def _record(data: dict, elapsed: float | None, status: str) -> ExperimentRecord:
        return record_from_data(data, elapsed, status)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        apply_light_windows_titlebar(self)

    def _close_after_verification(self):
        if self.controller._verification_worker is not None:
            QTimer.singleShot(25,self._close_after_verification)
        else:
            self._close_pending = False
            self.close()

    def closeEvent(self, event) -> None:
        if self._replay_controller is not None or self._database_import is not None:
            event.ignore()
            return
        if self.controller._verification_worker is not None:
            self._invalidate_verification()
            if not self._close_pending:
                self._close_pending = True
                QTimer.singleShot(25,self._close_after_verification)
            event.ignore()
            return
        if self.controller.has_running_tasks():
            QMessageBox.information(
                self,
                "Вычисление выполняется",
                "Остановите текущее вычисление или дождитесь его завершения перед закрытием.",
            )
            event.ignore()
            return
        if self.report_sync is not None and not self.report_sync.stop():
            QTimer.singleShot(100,self.close)
            event.ignore()
            return
        self.comparison_tab.scientific_chart.shutdown()
        self._invalidate_verification()
        event.accept()
