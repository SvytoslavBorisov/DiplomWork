from __future__ import annotations

import math
import random
import os
import time

from .statevector_limits import check_resources, check_deadline, SIMULATION_TIMEOUT
from dataclasses import dataclass
from typing import Callable, Iterable, Optional


@dataclass(frozen=True)
class GroverResult:
    measured_index: Optional[int]
    is_marked: bool
    domain_size: int
    marked_count: int
    iterations: int
    quantum_queries: int
    success_probability: float
    norm_error: float
    statevector_elements_processed: int = 0
    statevector_seconds: float = 0.0


def optimal_grover_iterations(domain_size: int, marked_count: int = 1) -> int:
    """Вычисляет целое число итераций Гровера для амплитудного усиления помеченных состояний."""
    if domain_size <= 0:
        raise ValueError("domain_size должен быть положительным.")
    if marked_count < 0 or marked_count > domain_size:
        raise ValueError("marked_count должен лежать в диапазоне 0..domain_size.")
    if marked_count == 0 or marked_count == domain_size:
        return 0
    theta = math.asin(math.sqrt(marked_count / domain_size))
    return max(0, round(math.pi / (4.0 * theta) - 0.5))


def grover_success_probability(
    domain_size: int,
    marked_count: int,
    iterations: int,
) -> float:
    if domain_size <= 0 or not 0 <= marked_count <= domain_size:
        raise ValueError("Некорректные размеры пространства Grover.")
    if iterations < 0:
        raise ValueError("iterations должен быть неотрицательным.")
    if marked_count == 0:
        return 0.0
    theta = math.asin(math.sqrt(marked_count / domain_size))
    return math.sin((2 * iterations + 1) * theta) ** 2


def simulate_grover_from_marked(
    domain_size: int,
    marked_indices: Iterable[int],
    *,
    iterations: Optional[int] = None,
    rng: Optional[random.Random] = None,
    max_statevector_size: Optional[int] = None,
    final_amplitudes: Optional[list[float]] = None,
) -> GroverResult:
    """Моделирует поиск Гровера фазовым оракулом и диффузией вектора состояния на классическом компьютере."""
    if domain_size <= 0:
        raise ValueError("domain_size должен быть положительным.")
    if max_statevector_size is not None and domain_size > max_statevector_size:
        raise ValueError(
            f"State-vector из {domain_size} состояний превышает лимит "
            f"{max_statevector_size}. Уменьшите n/depth."
        )
    check_resources(domain_size, 0, python=True)
    marked = frozenset(marked_indices)
    if any(index < 0 or index >= domain_size for index in marked):
        raise ValueError("Отмеченный индекс находится вне пространства поиска.")
    marked_count = len(marked)
    if iterations is None:
        iterations = optimal_grover_iterations(domain_size, marked_count)
    if iterations < 0:
        raise ValueError("iterations должен быть неотрицательным.")

    check_resources(domain_size, iterations, python=True)
    started = time.monotonic()
    timeout = min(SIMULATION_TIMEOUT, float(os.environ.get('GROVER_TIMEOUT_SECONDS', SIMULATION_TIMEOUT)))
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('Лимит времени моделирования должен быть положительным.')
    amplitude = 1.0 / math.sqrt(domain_size)
    state = [amplitude] * domain_size
    for _ in range(iterations):
        check_deadline()
        if time.monotonic() - started > timeout:
            raise TimeoutError('Превышен лимит времени моделирования вектора амплитуд.')
        for index in range(domain_size):
            if index in marked:
                state[index] = -state[index]
        mean = math.fsum(state) / domain_size
        for index, value in enumerate(state):
            state[index] = 2.0 * mean - value

    probabilities = [value * value for value in state]
    probability_sum = math.fsum(probabilities)
    norm_error = abs(probability_sum - 1.0)
    success_probability = math.fsum(probabilities[index] for index in marked)

    generator = rng or random.Random()
    threshold = generator.random() * probability_sum
    cumulative = 0.0
    measured_index = domain_size - 1
    for index, probability in enumerate(probabilities):
        cumulative += probability
        if threshold < cumulative:
            measured_index = index
            break

    if final_amplitudes is not None:
        final_amplitudes[:] = state
    check_deadline()
    if time.monotonic() - started > timeout:
        raise TimeoutError('Превышен лимит времени моделирования вектора амплитуд.')
    return GroverResult(
        measured_index=measured_index,
        is_marked=measured_index in marked,
        domain_size=domain_size,
        marked_count=marked_count,
        iterations=iterations,
        quantum_queries=iterations,
        success_probability=success_probability,
        norm_error=norm_error,
        statevector_elements_processed=domain_size * (2 + 3 * iterations) + measured_index + 1,
        statevector_seconds=time.monotonic() - started,
    )


def simulate_grover_search(
    domain_size: int,
    oracle: Callable[[int], bool],
    **kwargs,
) -> GroverResult:
    """Формирует помеченные индексы оракула для моделирования поиска Гровера."""
    marked = [index for index in range(domain_size) if oracle(index)]
    return simulate_grover_from_marked(domain_size, marked, **kwargs)
