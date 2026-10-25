"""Определяет методы поиска и преобразует прежние обозначения на границах совместимости."""

from dataclasses import dataclass
from enum import Enum
import math

SEARCH_PROTOCOL = "fixed-single-bbht-auto-v1"


class SearchMethod(str, Enum):
    CLASSICAL = "classical"
    GROVER_FIXED = "grover_fixed"
    GROVER_BBHT = "grover_bbht"

    @property
    def is_quantum(self) -> bool:
        return self is not SearchMethod.CLASSICAL

    @property
    def storage_id(self) -> str:
        return {self.CLASSICAL: "blackburn", self.GROVER_FIXED: "quantum_algorithm_2_simulator",
                self.GROVER_BBHT: "grover_bbht"}[self]

    @property
    def label(self) -> str:
        return {self.CLASSICAL: "Классический алгоритм", self.GROVER_FIXED: "Фиксированный Гровер",
                self.GROVER_BBHT: "Адаптивный Гровер (BBHT)"}[self]


_ALIASES = {method.value: method for method in SearchMethod}
_ALIASES.update({method.storage_id: method for method in SearchMethod})
_ALIASES.update(quantum=SearchMethod.GROVER_FIXED, bbht=SearchMethod.GROVER_BBHT,
                **{"quantum-cpp": SearchMethod.GROVER_FIXED, "quantum-python": SearchMethod.GROVER_FIXED,
                   "quantum-bbht-cpp": SearchMethod.GROVER_BBHT})


def search_method(value: str | SearchMethod | bool) -> SearchMethod:
    """Преобразует старые строки и булевы аргументы без переименования исторических результатов."""
    if isinstance(value, bool):
        return SearchMethod.GROVER_FIXED if value else SearchMethod.CLASSICAL
    try:
        return _ALIASES[value]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"Неизвестный метод поиска: {value}.") from exc


@dataclass(frozen=True)
class BBHTOptions:
    """Хранит верхние пределы автоматического адаптивного C++-поиска BBHT."""

    growth: float = 1.2
    max_attempts: int = 128
    max_oracle_queries: int = 100000
    dense_max_states: int = 8192
    max_stage_seconds: float = 0.0

    def validate(self) -> None:
        if not math.isfinite(self.growth) or not 1 < self.growth < 4 / 3:
            raise ValueError("Коэффициент роста BBHT должен лежать строго между 1 и 4/3.")
        for value in (self.max_attempts, self.max_oracle_queries, self.dense_max_states):
            if not isinstance(value, int) or not 1 <= value < 2**64:
                raise ValueError("Целые ограничения BBHT должны лежать в диапазоне 1..2^64−1.")
        if not math.isfinite(self.max_stage_seconds) or self.max_stage_seconds < 0:
            raise ValueError("Ограничение времени BBHT должно быть неотрицательным.")
