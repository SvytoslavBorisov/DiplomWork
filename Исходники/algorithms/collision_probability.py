"""Оценивает существование коллизий при равномерной модели части хэш-кода."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class CandidateProbabilityEstimate:
    """Хранит расчётные показатели одного квантового поиска в слое."""

    distinct_targets: int
    predicted_probability: float
    baseline_probability: float
    table_messages: int
    search_messages: int
    baseline_search_messages: int


def probability_of_match(n: int, distinct_targets: int, candidates: int) -> float:
    """Оценивает вероятность хотя бы одного попадания среди независимых кандидатов."""
    if n < 1 or n > 512:
        raise ValueError("Размер части хэш-кода n должен лежать в диапазоне 1..512.")
    if not isinstance(distinct_targets, int) or not isinstance(candidates, int):
        raise TypeError("Количество целей и кандидатов должно быть целым.")
    if not 0 <= distinct_targets <= (1 << n) or candidates < 0:
        raise ValueError("Количество целей или кандидатов выходит за допустимые границы.")
    if distinct_targets == 0 or candidates == 0:
        return 0.0
    if distinct_targets == (1 << n):
        return 1.0
    p = distinct_targets / (1 << n)
    return -math.expm1(candidates * math.log1p(-p))


def minimum_candidates(n: int, distinct_targets: int, target_probability: float) -> int:
    """Находит минимальное число кандидатов с заданной вероятностью существования совпадения."""
    if not isinstance(target_probability, (int, float)) or not math.isfinite(target_probability) or not 0 < target_probability < 1:
        raise ValueError("Целевая вероятность должна быть строго между 0 и 1.")
    probability_of_match(n, distinct_targets, 0)
    if distinct_targets == 0:
        raise ValueError("Без целевых значений совпадение невозможно.")
    if distinct_targets == (1 << n):
        return 1
    p = distinct_targets / (1 << n)
    ratio = math.log1p(-target_probability) / math.log1p(-p)
    if not math.isfinite(ratio):
        raise ValueError("Нельзя вычислить число кандидатов для заданных параметров.")
    result = max(1, math.ceil(ratio))
    if ratio >= (1 << 48):
        return result
    # Округление вещественных чисел вблизи целого не должно завышать минимум.
    while result > 1 and probability_of_match(n, distinct_targets, result - 1) >= target_probability:
        result -= 1
    while probability_of_match(n, distinct_targets, result) < target_probability:
        result += 1
    return result


def estimated_distinct_targets(n: int, other_vertex_count: int, table_messages: int) -> int:
    """Оценивает число различных значений таблицы других вершин в модели случайного отображения."""
    if n < 1 or n > 512 or other_vertex_count < 0 or table_messages < 0:
        raise ValueError("Параметры таблицы находятся вне допустимого диапазона.")
    samples = other_vertex_count * table_messages
    if not samples:
        return 0
    total = 1 << n
    # При большой разрядности нельзя вычислять 1 - 1/2^n вычитанием.
    population = float(total)
    expected = population * -math.expm1(samples * math.log1p(-1.0 / population))
    return min(total, samples, max(1, math.floor(expected)))


def plan_search_messages(
    n: int,
    vertex_count: int,
    table_messages: int,
    baseline_search_messages: int,
    target_probability: float,
) -> CandidateProbabilityEstimate:
    """Подбирает поисковое множество по вероятности одного поиска без гарантии паросочетания."""
    if vertex_count < 2 or table_messages < 1 or baseline_search_messages < 1:
        raise ValueError("Количество вершин и размеры множеств должны быть положительными.")
    distinct = estimated_distinct_targets(n, vertex_count - 1, table_messages)
    selected = minimum_candidates(n, distinct, target_probability)
    return CandidateProbabilityEstimate(
        distinct_targets=distinct,
        predicted_probability=probability_of_match(n, distinct, selected),
        baseline_probability=probability_of_match(n, distinct, baseline_search_messages),
        table_messages=table_messages,
        search_messages=selected,
        baseline_search_messages=baseline_search_messages,
    )
