"""Управляет стадиями сценария Нострадамуса без оформления виджетов."""

from enum import Enum
from algorithms.diamond import get_diamond_root_state
from algorithms.herding_attack import encode_text_prefix_blocks
from algorithms.search_methods import search_method


class HerdingStage(str, Enum):
    EMPTY = "empty"
    LOADED = "loaded"
    COMMITTED = "committed"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"


class HerdingWorkflow:
    def __init__(self, controller):
        self.controller = controller
        self.data = None
        self.description = None
        self.stage = HerdingStage.EMPTY
        self.result = None

    def load(self, data):
        if self.stage is HerdingStage.RUNNING:
            raise RuntimeError("Дождитесь завершения поиска или остановите его.")
        self.data = data
        self.description = None
        self.result = None
        self.stage = HerdingStage.LOADED

    def commit(self, description):
        if self.data is None:
            raise ValueError("Сначала загрузите алмазную структуру.")
        if not description:
            raise ValueError("Введите публикуемую часть префикса.")
        if self.stage is HerdingStage.RUNNING:
            raise RuntimeError("Сначала остановите поиск связующего блока.")
        encode_text_prefix_blocks(description, int(self.data["prefix_blocks"]))
        self.description = description
        self.stage = HerdingStage.COMMITTED
        return get_diamond_root_state(self.data).h

    def start(self, description, event_result, trials_limit, method, *, bbht_options=None):
        if self.description is None:
            raise ValueError("Сначала зафиксируйте коммитмент.")
        if description != self.description:
            raise ValueError("Публикуемая часть изменилась; зафиксируйте коммитмент заново.")
        if self.stage is HerdingStage.RUNNING:
            raise RuntimeError("Поиск связующего блока уже выполняется.")
        if trials_limit < 1:
            raise ValueError("Лимит поиска должен быть положительным.")
        encode_text_prefix_blocks(description + event_result, int(self.data["prefix_blocks"]))
        selected = search_method(method)
        if bbht_options is not None:
            bbht_options.validate()
        self.stage = HerdingStage.RUNNING
        try:
            self.controller.start_attack(self.data, description, event_result, trials_limit, selected.value,
                                         **({"bbht_options": bbht_options} if bbht_options is not None else {}))
        except Exception:
            self.stage = HerdingStage.ERROR
            raise

    def complete(self, result):
        root = get_diamond_root_state(self.data)
        if result.root != root.h or result.verified_root != root.h or getattr(result, "verified_sigma", root.sigma) != root.sigma:
            self.stage = HerdingStage.ERROR
            raise ValueError("Независимая проверка не подтвердила зафиксированное корневое состояние.")
        self.result = result
        self.stage = HerdingStage.COMPLETED

    def cancel(self):
        self.result = None
        self.stage = HerdingStage.COMMITTED if self.description is not None else HerdingStage.LOADED

    def fail(self):
        self.result = None
        self.stage = HerdingStage.ERROR
