from __future__ import annotations

from .classical import ClassicalSearchAlgorithms
from .interfaces import SearchAlgorithms


_ALGORITHMS = {
    "classical": ClassicalSearchAlgorithms,
    # Регистрирует доступные реализации поисковых алгоритмов.
}


def available_algorithms() -> tuple[str, ...]:
    return tuple(_ALGORITHMS.keys())


def create_search_algorithms(name: str = "classical") -> SearchAlgorithms:
    try:
        cls = _ALGORITHMS[name]
    except KeyError as exc:
        raise ValueError(f"Неизвестный набор алгоритмов: {name}") from exc
    return cls()
