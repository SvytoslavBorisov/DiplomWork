from __future__ import annotations

from dataclasses import asdict
import json
import sys
import traceback
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QThread, Signal, Slot

from algorithms.herding_attack import AttackResult
from algorithms.search_methods import search_method
from .structure_verification import VerificationWorker, MessageVerificationWorker
from .backend_adapter import AttackRunResult, BackendAdapter, BuildRequest, BuildResult


class _Worker(QObject):
    finished = Signal(object)
    failed = Signal(str, str)
    log = Signal(str)

    def __init__(self, operation: Callable[..., Any], args: tuple[Any, ...], with_log: bool) -> None:
        super().__init__()
        self.operation = operation
        self.args = args
        self.with_log = with_log

    @Slot()
    def run(self) -> None:
        try:
            if self.with_log:
                value = self.operation(*self.args, self.log.emit)
            else:
                value = self.operation(*self.args)
            self.finished.emit(value)
        except Exception as exc:  # Сохраняет сведения об исключении в техническом журнале.
            self.failed.emit(str(exc), traceback.format_exc())


class ExperimentController(QObject):
    verification_progress = Signal(int, object)
    verification_finished = Signal(int, object)
    build_started = Signal()
    build_log = Signal(str)
    build_level = Signal(object)
    build_finished = Signal(object)
    build_failed = Signal(str, str)
    build_cancelled = Signal()
    attack_cancelled = Signal()
    attack_started = Signal()
    attack_finished = Signal(object)
    attack_failed = Signal(str, str)

    def __init__(self, adapter: BackendAdapter | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.adapter = adapter or BackendAdapter()
        self._verification_worker = None
        self._threads: dict[int, QThread] = {}
        self._workers: dict[int, _Worker] = {}
        self._attack_controller = None
        self._build_process: QProcess | None = None
        self._build_buffer = bytearray()
        self._build_result: dict | None = None
        self._build_error: dict | None = None
        self._build_cancel_requested = False

    def _start_worker(
        self,
        operation: Callable[..., Any],
        args: tuple[Any, ...],
        with_log: bool,
        success: Signal,
        failure: Signal,
    ) -> None:
        thread = QThread(self)
        thread_key = id(thread)
        worker = _Worker(operation, args, with_log)
        worker_key = id(worker)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        if with_log:
            worker.log.connect(self.build_log)
        worker.finished.connect(success)
        worker.failed.connect(failure)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(lambda: self._threads.pop(thread_key, None))
        thread.finished.connect(lambda: self._workers.pop(worker_key, None))
        thread.finished.connect(thread.deleteLater)
        self._threads[thread_key] = thread
        self._workers[worker_key] = worker
        thread.start()

    def start_verification(self, token, data):
        self._start_verification_worker(VerificationWorker(token,data))

    def start_message_verification(self,token,data,result):
        self._start_verification_worker(MessageVerificationWorker(token,data,result))

    def _start_verification_worker(self,worker):
        self.cancel_verification()
        thread = QThread(self)
        thread_key, worker_key = id(thread), id(worker)
        self._verification_worker = worker
        self._threads[thread_key] = thread
        self._workers[worker_key] = worker
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self.verification_progress)
        worker.finished.connect(self.verification_finished)
        worker.done.connect(worker.deleteLater)
        worker.done.connect(thread.quit)
        def release():
            self._threads.pop(thread_key, None)
            self._workers.pop(worker_key, None)
            if self._verification_worker is worker:
                self._verification_worker = None
        thread.finished.connect(release)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def cancel_verification(self):
        if self._verification_worker is not None:
            self._verification_worker.cancel_event.set()

    def start_build(self, request: BuildRequest) -> None:
        if self._build_process is not None:
            raise RuntimeError("Построение уже выполняется.")
        self.build_started.emit()
        if type(self.adapter) is not BackendAdapter:
            self._start_worker(self.adapter.build_diamond, (request,), True, self.build_finished, self.build_failed)
            return
        self._launch_process(request)

    def _launch_process(self, request):
        process = QProcess(self)
        environment=QProcessEnvironment.systemEnvironment();environment.insert('PYINSTALLER_SUPPRESS_SPLASH_SCREEN','1')
        process.setProcessEnvironment(environment)
        process.setWorkingDirectory(str(Path(__file__).resolve().parents[1]))
        self._build_process = process
        self._build_buffer.clear()
        self._build_result = None
        self._build_error = None
        self._build_cancel_requested = False
        values = asdict(request) if isinstance(request, BuildRequest) else request
        if "output_directory" in values:
            values["output_directory"] = str(values["output_directory"])
        request_bytes = json.dumps(values).encode("utf-8")
        process.started.connect(lambda: (process.write(request_bytes), process.closeWriteChannel()))
        process.readyReadStandardOutput.connect(self._read_build_output)
        process.finished.connect(self._build_process_finished)
        process.errorOccurred.connect(self._build_process_error)
        arguments=['--build-worker'] if getattr(sys,'frozen',False) else ['-u','-m','integration.build_process']
        process.start(sys.executable,arguments)

    def cancel_build(self) -> None:
        if self._build_process is None:
            return
        self._build_cancel_requested = True
        if self._build_process.state() != QProcess.ProcessState.NotRunning:
            self._build_process.kill()

    def _read_build_output(self) -> None:
        process = self._build_process
        if process is None:
            return
        self._build_buffer.extend(bytes(process.readAllStandardOutput()))
        while b"\n" in self._build_buffer:
            raw, _, tail = self._build_buffer.partition(b"\n")
            self._build_buffer = bytearray(tail)
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("HERDINGLAB:"):
                if line:
                    self.build_log.emit(line)
                continue
            try:
                event = json.loads(line[len("HERDINGLAB:"):])
            except json.JSONDecodeError:
                continue
            if event.get("type") == "log":
                self.build_log.emit(str(event.get("message", "")))
            elif event.get("type") == "level":
                self.build_level.emit(event["data"])
            elif event.get("type") == "result":
                self._build_result = event
            elif event.get("type") == "error":
                self._build_error = event

    def _build_process_finished(self, exit_code: int, _status: QProcess.ExitStatus) -> None:
        process = self._build_process
        if process is None:
            return
        self._read_build_output()
        stderr = bytes(process.readAllStandardError()).decode("utf-8", "replace")
        self._build_process = None
        process.deleteLater()
        if self._build_cancel_requested:
            self.build_cancelled.emit()
        elif exit_code == 0 and self._build_result:
            try:
                if "attack" in self._build_result:
                    self.build_finished.emit(AttackRunResult(AttackResult(**self._build_result["attack"]), float(self._build_result["elapsed_seconds"])))
                    return
                path = Path(self._build_result["path"])
                data = self.adapter.load_json(path)
                self.build_finished.emit(BuildResult(data, path, float(self._build_result["elapsed_seconds"])))
            except Exception as exc:
                self.build_failed.emit(str(exc), traceback.format_exc())
        else:
            error = self._build_error or {}
            self.build_failed.emit(str(error.get("message") or "Построение завершилось с ошибкой."),
                                   str(error.get("trace") or stderr))

    def _build_process_error(self, error: QProcess.ProcessError) -> None:
        if error != QProcess.ProcessError.FailedToStart or self._build_process is None:
            return
        process = self._build_process
        self._build_process = None
        message = process.errorString()
        process.deleteLater()
        self.build_failed.emit(f"Не удалось запустить построение: {message}", "")

    def start_attack(self, data, description, event_result, trials_limit, method="classical", *, bbht_options=None, quantum=None):
        if quantum is not None:
            method = search_method(quantum).value
        if self._attack_controller is not None:
            raise RuntimeError("Поиск связующего блока уже выполняется.")
        self.attack_started.emit()
        if type(self.adapter) is not BackendAdapter:
            self._start_worker(self.adapter.run_attack, (data, description, event_result, trials_limit, method),
                               False, self.attack_finished, self.attack_failed)
            return
        child = ExperimentController(self.adapter, self)
        self._attack_controller = child
        def release(*_):
            self._attack_controller = None
            child.deleteLater()
        child.build_finished.connect(self.attack_finished)
        child.build_failed.connect(self.attack_failed)
        child.build_cancelled.connect(self.attack_cancelled)
        child.build_finished.connect(release)
        child.build_failed.connect(release)
        child.build_cancelled.connect(release)
        child._launch_process(dict(operation="attack", data=data, description=description,
                                   event_result=event_result, trials_limit=trials_limit,
                                   method=search_method(method).value,
                                   bbht_options=asdict(bbht_options) if bbht_options else None))

    def cancel_attack(self):
        if self._attack_controller is not None:
            self._attack_controller.cancel_build()

    def has_running_tasks(self) -> bool:
        if self._attack_controller is not None:
            return True
        if self._build_process is not None and self._build_process.state() != QProcess.ProcessState.NotRunning:
            return True
        stale: list[int] = []
        running = False
        for key, thread in self._threads.items():
            try:
                running = thread.isRunning() or running
            except RuntimeError:
                stale.append(key)
        for key in stale:
            self._threads.pop(key, None)
        return running
