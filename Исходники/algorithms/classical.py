from __future__ import annotations

import math
import random
import os
from contextlib import nullcontext
from typing import Sequence

from CppCore import BlackburnLayerSession, cpp_core_available, cpp_find_collision, cpp_find_link, cpp_sample_transitions
from HashCalculator import random_block
from .interfaces import CollisionResult, LinkingResult
from .model import ReducedGostModel, constrained_random_block, update_sigma_reduced, validate_sigma_bits


class ClassicalSearchAlgorithms:
    """Выполняет классический поиск на множестве блоков с заданным переходом части контрольной суммы."""

    name = "classical"

    def __init__(self, seed: int | None = None, threads: int = 0, use_cpp: bool | None = None):
        self.rng = random.Random(seed) if seed is not None else None
        self.threads = threads
        self.use_cpp = use_cpp

    def _cpp_enabled(self) -> bool:
        return cpp_core_available() if self.use_cpp is None else self.use_cpp

    def _seed(self) -> int | None:
        return self.rng.getrandbits(64) if self.rng is not None else None

    def blackburn_layer(self,states,N,truncate_bits,rounds,**sigma):
        if os.environ.get('NOSTRADAMUS_BLACKBURN_BACKEND','legacy')!='cpp-layer' or not self._cpp_enabled():
            return nullcontext(None)
        return BlackburnLayerSession(states,N,truncate_bits,rounds,self.threads,**sigma)

    def _block(self, current: int, target: int, sigma_bits: int) -> str:
        return constrained_random_block(current, target, sigma_bits, self.rng)

    @property
    def backend_label(self) -> str:
        return "C++ (многопоточное)" if cpp_core_available() else "Python fallback"

    def find_collision(
        self, h1: str, h2: str, N: int, truncate_bits: int, rounds: int,
        trials_limit: int, *, sigma_bits: int = 0, left_sigma: int = 0,
        right_sigma: int = 0, target_sigma: int = 0,
    ) -> CollisionResult:
        validate_sigma_bits(sigma_bits)
        if self._cpp_enabled():
            m1, m2, common, queries = cpp_find_collision(
                h1, h2, N, truncate_bits, rounds, trials_limit,
                sigma_bits=sigma_bits, left_sigma=left_sigma,
                right_sigma=right_sigma, target_sigma=target_sigma,
                seed=self._seed(), threads=self.threads,
            )
            return CollisionResult(m1, m2, common, queries)

        model = ReducedGostModel(truncate_bits, rounds)
        table_size = max(16, min(1 << math.ceil(truncate_bits / 2), 1 << 18))
        tested = 0
        while tested < trials_limit:
            table: dict[str, str] = {}
            left_count = min(table_size, trials_limit - tested)
            for _ in range(left_count):
                m1 = self._block(left_sigma, target_sigma, sigma_bits)
                out1 = model.transition(m1, h1, N)
                table.setdefault(out1, m1)
            tested += left_count
            if tested >= trials_limit:
                break
            right_count = min(table_size, trials_limit - tested)
            for _ in range(right_count):
                m2 = self._block(right_sigma, target_sigma, sigma_bits)
                out2 = model.transition(m2, h2, N)
                tested += 1
                m1 = table.get(out2)
                if m1 is not None:
                    if sigma_bits:
                        assert update_sigma_reduced(left_sigma, m1, sigma_bits) == target_sigma
                        assert update_sigma_reduced(right_sigma, m2, sigma_bits) == target_sigma
                    return CollisionResult(m1, m2, out2, tested)
        raise RuntimeError("Не удалось найти pair-collision в пределах trials_limit.")

    def find_link(
        self, prefix_state: str, target_states: Sequence[str], N: int,
        truncate_bits: int, rounds: int, trials_limit: int, *, sigma_bits: int = 0,
        current_sigma: int = 0, target_sigma: int = 0,
    ) -> LinkingResult:
        validate_sigma_bits(sigma_bits)
        targets = list(dict.fromkeys(target_states))
        if not targets:
            raise ValueError("Список целевых состояний пуст.")
        if self._cpp_enabled():
            block, state, queries = cpp_find_link(
                prefix_state, targets, N, truncate_bits, rounds, trials_limit,
                sigma_bits=sigma_bits, current_sigma=current_sigma, target_sigma=target_sigma,
                seed=self._seed(), threads=self.threads,
            )
            return LinkingResult(block, state, queries)

        model = ReducedGostModel(truncate_bits, rounds)
        target_set = set(targets)
        for query_index in range(1, trials_limit + 1):
            block = self._block(current_sigma, target_sigma, sigma_bits)
            state = model.transition(block, prefix_state, N)
            if state in target_set:
                if sigma_bits:
                    assert update_sigma_reduced(current_sigma, block, sigma_bits) == target_sigma
                return LinkingResult(block, state, query_index)
        raise RuntimeError("Не удалось найти linking-блок в пределах trials_limit.")

    def sample_transitions(
        self, states: Sequence[str], samples_per_state: int, N: int,
        truncate_bits: int, rounds: int, *, sigma_bits: int = 0,
        current_sigma: int = 0, target_sigma: int = 0,
    ) -> list[list[tuple[str, str]]]:
        validate_sigma_bits(sigma_bits)
        states = list(states)
        if not states:
            raise ValueError("Список состояний пуст.")
        if samples_per_state <= 0:
            raise ValueError("samples_per_state должен быть положительным.")
        if self._cpp_enabled():
            return cpp_sample_transitions(
                states, samples_per_state, N, truncate_bits, rounds,
                sigma_bits=sigma_bits, current_sigma=current_sigma, target_sigma=target_sigma,
                seed=self._seed(), threads=self.threads,
            )
        model = ReducedGostModel(truncate_bits, rounds)
        result = []
        for state in states:
            items = []
            for _ in range(samples_per_state):
                block = self._block(current_sigma, target_sigma, sigma_bits)
                items.append((block, model.transition(block, state, N)))
            result.append(items)
        return result
