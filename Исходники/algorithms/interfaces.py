from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence


@dataclass(frozen=True)
class CollisionResult:
    left_block: str
    right_block: str
    common_state: str
    queries: int


@dataclass(frozen=True)
class LinkingResult:
    block: str
    target_state: str
    queries: int


class SearchAlgorithms(Protocol):
    """Задаёт поиск коллизий и связующего блока с конструктивным ограничением части контрольной суммы."""

    name: str

    def find_collision(
        self,
        h1: str,
        h2: str,
        N: int,
        truncate_bits: int,
        rounds: int,
        trials_limit: int,
        *,
        sigma_bits: int = 0,
        left_sigma: int = 0,
        right_sigma: int = 0,
        target_sigma: int = 0,
    ) -> CollisionResult: ...

    def find_link(
        self,
        prefix_state: str,
        target_states: Sequence[str],
        N: int,
        truncate_bits: int,
        rounds: int,
        trials_limit: int,
        *,
        sigma_bits: int = 0,
        current_sigma: int = 0,
        target_sigma: int = 0,
    ) -> LinkingResult: ...

    def sample_transitions(
        self,
        states: Sequence[str],
        samples_per_state: int,
        N: int,
        truncate_bits: int,
        rounds: int,
        *,
        sigma_bits: int = 0,
        current_sigma: int = 0,
        target_sigma: int = 0,
    ) -> list[list[tuple[str, str]]]: ...
