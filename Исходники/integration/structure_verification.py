"""Выполняет независимую проверку без изменения статистики построения."""

from copy import deepcopy
from threading import Event
from time import perf_counter
import traceback

from PySide6.QtCore import QObject, Signal, Slot
from algorithms.diamond import validate_diamond_data


class VerificationCancelled(Exception):
    """Останавливает проверку между двумя переходами."""


class VerificationWorker(QObject):
    progress = Signal(int, object)
    finished = Signal(int, object)
    done = Signal()

    def __init__(self, token, data):
        super().__init__()
        self.token = token
        self.data = deepcopy(data)
        self.cancel_event = Event()

    def check_cancelled(self):
        if self.cancel_event.is_set():
            raise VerificationCancelled()

    @Slot()
    def run(self):
        started = perf_counter()
        completed = 0
        pending = []
        total = 2 * sum(len(level) for level in self.data.get("structure", []))

        def confirmed(level, pair, side):
            nonlocal completed
            completed += 1
            pending.append(dict(level=level, pair=pair, side=side, completed=completed, total=total))
            if total <= 256 or len(pending) >= 32:
                self.progress.emit(self.token, pending[:])
                pending.clear()

        try:
            self.check_cancelled()
            validate_diamond_data(self.data, on_transition=confirmed, check_cancelled=self.check_cancelled)
            self.check_cancelled()
            if pending:
                self.progress.emit(self.token, pending[:])
            outcome = dict(state="verified", completed=completed, total=total)
        except VerificationCancelled:
            outcome = dict(state="cancelled", completed=completed, total=total)
        except Exception as exc:
            outcome = dict(state="failed", message=str(exc), trace=traceback.format_exc(),
                           level=getattr(exc,"level",None), pair=getattr(exc,"pair",None),
                           side=getattr(exc,"side",None), completed=completed, total=total)
        outcome["elapsed_seconds"] = perf_counter() - started
        self.finished.emit(self.token, outcome)
        self.done.emit()


class MessageVerificationWorker(VerificationWorker):
    """Повторно проверяет только сформированное сообщение и выбранный путь до корня."""

    def __init__(self,token,data,result):
        super().__init__(token,data)
        self.result=deepcopy(result)

    @Slot()
    def run(self):
        from algorithms.herding_attack import verify_forged_path
        from integration.result_adapter import build_diamond_graph, path_edge_ids
        import re
        started=perf_counter()
        result=self.result
        events=[]
        try:
            self.check_cancelled()
            graph=build_diamond_graph(self.data)
            path=path_edge_ids(graph,result.leaf_state)
            incoming={}
            for edge in graph.edges:incoming.setdefault(edge.target,[]).append(edge)
            for edge in sorted((edge for edge in graph.edges if (edge.source,edge.target) in path),key=lambda edge:edge.level):
                events.append(dict(level=edge.level,pair=int(edge.target.split(":")[-1]),
                                   side="left" if incoming[edge.target][0] is edge else "right",
                                   completed=len(events)+1,total=graph.depth))
            blocks=[result.forged_hex[i:i+128] for i in range(0,len(result.forged_hex),128)]
            expected=list(result.prefix_blocks)+[result.linking_block]+list(result.suffix_blocks)
            if blocks!=expected:
                raise ValueError("Сформированное сообщение не совпадает с префиксом, связующим блоком и суффиксом.")
            root=verify_forged_path(result.prefix_blocks,result.linking_block,result.leaf_state,
                                    result.suffix_blocks,self.data)
            self.check_cancelled()
            if root!=result.root:
                raise ValueError("Хэш-код сообщения не совпадает с зафиксированным значением.")
            self.progress.emit(self.token,events)
            outcome=dict(state="verified",completed=len(expected),total=len(expected),path_transitions=len(events))
        except VerificationCancelled:
            outcome=dict(state="cancelled",completed=0,total=len(events))
        except Exception as exc:
            match=re.search(r"(?:уровня|уровне) (\d+)",str(exc))
            failed=next((event for event in events if match and event["level"]==int(match[1])),{})
            outcome=dict(state="failed",message=str(exc),trace=traceback.format_exc(),
                         level=failed.get("level"),pair=failed.get("pair"),side=failed.get("side"),completed=0)
        outcome["elapsed_seconds"]=perf_counter()-started
        self.finished.emit(self.token,outcome)
        self.done.emit()
