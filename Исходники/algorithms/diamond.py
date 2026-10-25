from __future__ import annotations

import math
import random
from contextlib import nullcontext
from collections import Counter
from typing import Any, Dict, Optional, Sequence

import networkx as nx

from .interfaces import SearchAlgorithms
from .model import (
    FORMAT_VERSION,
    MODEL_NAME,
    DiamondState,
    LEGACY_FORMAT_VERSION,
    LEGACY_MODEL_NAME,
    ReducedGostModel,
    random_reduced_state,
    sigma_mask,
    update_sigma_reduced,
    validate_sigma_bits,
    validate_truncate_bits,
)


def _unique_random_states(count: int, truncate_bits: int, rng: random.Random | None = None) -> list[str]:
    if count > (1 << truncate_bits):
        raise ValueError(
            "Число листьев превышает размер пространства редуцированных состояний."
        )
    states: set[str] = set()
    ordered: list[str] = []
    while len(states) < count:
        state = random_reduced_state(truncate_bits, rng)
        if state not in states:
            states.add(state)
            ordered.append(state)
    return ordered


def _normalize_initial_states(
    initial_states: Optional[Sequence[str]],
    count: int,
    truncate_bits: int,
    rng: random.Random | None = None,
) -> list[str]:
    if initial_states is None:
        return _unique_random_states(count, truncate_bits, rng)

    states = [state.lower() for state in initial_states]
    expected_len = truncate_bits // 4
    if len(states) != count:
        raise ValueError(
            f"Ожидалось {count} начальных состояний, получено {len(states)}."
        )
    if len(set(states)) != len(states):
        raise ValueError("Начальные состояния должны быть различными.")
    if any(len(state) != expected_len for state in states):
        raise ValueError(
            f"Каждое начальное состояние должно содержать {expected_len} hex-символов."
        )
    try:
        for state in states:
            int(state, 16)
    except ValueError as exc:
        raise ValueError("Начальные состояния должны быть шестнадцатеричными строками.") from exc
    return [state.lower() for state in states]


def blackburn_list_size(
    vertex_count: int,
    truncate_bits: int,
    safety_factor: float = 1.0,
) -> int:
    """Вычисляет L ≈ √(r ln 2) · 2^((n−r)/2) для 2^r вершин с заданным коэффициентом запаса."""
    if vertex_count < 2 or vertex_count & (vertex_count - 1):
        raise ValueError("vertex_count должен быть степенью двойки не меньше 2.")
    if truncate_bits <= 0:
        raise ValueError("truncate_bits должен быть положительным.")
    if safety_factor <= 0:
        raise ValueError("safety_factor должен быть положительным.")

    r = math.log2(vertex_count)
    estimate = math.sqrt(r * math.log(2.0)) * (2.0 ** ((truncate_bits - r) / 2.0))
    return max(1, math.ceil(safety_factor * estimate))


def sigma_schedule(depth: int, sigma_bits: int, seed: int = 0) -> list[int]:
    """Возвращает общие для каждого уровня значения части контрольной суммы от листьев до корня."""
    validate_sigma_bits(sigma_bits)
    if sigma_bits == 0:
        return [0] * (depth + 1)
    rng = random.Random(seed)
    mask = sigma_mask(sigma_bits)
    return [rng.getrandbits(sigma_bits) & mask for _ in range(depth + 1)]


def build_diamond_structure_kelsey(
    search: SearchAlgorithms,
    depth: int = 3,
    truncate_bits: int = 16,
    trials_limit: int = 1_000_000,
    rounds: int = 12,
    logger: Optional[Any] = None,
    first_level_N: int = 1024,
    stats: Optional[Dict[str, int]] = None,
    initial_states: Optional[Sequence[str]] = None,
    sigma_bits: int = 0,
    sigma_seed: int = 0,
):
    """Строит структуру с заранее заданными соседними парами для регрессионных сравнений."""
    validate_truncate_bits(truncate_bits)
    validate_sigma_bits(sigma_bits)
    if depth < 1:
        raise ValueError("depth должен быть не меньше 1.")
    if first_level_N < 512 or first_level_N % 512 != 0:
        raise ValueError("first_level_N должен быть положительным кратным 512.")

    model = ReducedGostModel(truncate_bits, rounds)
    schedule = sigma_schedule(depth, sigma_bits, sigma_seed)
    num_leaves = 2 ** depth
    leaves_states = _normalize_initial_states(initial_states, num_leaves, truncate_bits)
    leaves = [("", state) for state in leaves_states]
    current = [DiamondState(h, schedule[0]) for h in leaves_states]
    structure = []
    if stats is not None:
        stats["sigma_bits"] = sigma_bits
        stats["leaf_sigma"] = schedule[0]
        for i, value in enumerate(schedule[1:], start=1):
            stats[f"sigma_level_{i}"] = value

    if logger:
        logger._log(f"[Kelsey] Создано {num_leaves} различных n-битных листьев.")

    if logger and hasattr(logger, "level_completed"):
        logger.level_completed(leaves, structure)

    level_index = 0
    while len(current) > 1:
        level_N = first_level_N + 512 * level_index
        if logger:
            logger._log(
                f"[Kelsey] Уровень {level_index + 1}: "
                f"{len(current)} вершин, N={level_N}."
            )

        next_level = []
        level_info = []
        for i in range(0, len(current), 2):
            left_state = current[i]
            right_state = current[i + 1]
            h_left = left_state.h
            h_right = right_state.h
            result = search.find_collision(
                h_left, h_right, level_N, truncate_bits, rounds, trials_limit,
                sigma_bits=sigma_bits, left_sigma=left_state.sigma,
                right_sigma=right_state.sigma, target_sigma=schedule[level_index + 1],
            )
            if stats is not None:
                stats["collision_queries"] = (
                    stats.get("collision_queries", 0) + result.queries
                )
                stats["kelsey_collision_queries"] = (
                    stats.get("kelsey_collision_queries", 0) + result.queries
                )

            check_left = model.transition(result.left_block, h_left, level_N)
            check_right = model.transition(result.right_block, h_right, level_N)
            check_sigma_left = update_sigma_reduced(left_state.sigma, result.left_block, sigma_bits)
            check_sigma_right = update_sigma_reduced(right_state.sigma, result.right_block, sigma_bits)
            if not (check_left == check_right == result.common_state and
                    check_sigma_left == check_sigma_right == schedule[level_index + 1]):
                raise AssertionError(
                    "Найденная коллизия не проходит независимую проверку модели."
                )

            level_info.append(
                (
                    h_left,
                    h_right,
                    result.left_block,
                    result.right_block,
                    result.common_state,
                )
            )
            next_level.append(DiamondState(result.common_state, schedule[level_index + 1]))
            if logger:
                logger._log(
                    f"[Kelsey] Коллизия: {h_left} / {h_right} -> "
                    f"{result.common_state}"
                )

        structure.append(level_info)
        if logger and hasattr(logger, "level_completed"):
            logger.level_completed(leaves, structure)
        current = next_level
        level_index += 1

    if stats is not None:
        # Сохраняет общие счётчики, поскольку каждый блок сразу удовлетворяет ограничению части контрольной суммы.


        transition_queries = int(stats.get("blackburn_transition_queries", stats.get("collision_queries", 0)))
        stats["compression_calls"] = transition_queries
        stats["generated_candidates"] = transition_queries
        stats.setdefault("oracle_queries", 0)
        stats.setdefault("grover_iterations", 0)

    return leaves, structure


def _matching_covers_all_vertices(
    matching: set[tuple[int, int]],
    vertex_count: int,
) -> bool:
    if len(matching) != vertex_count // 2:
        return False
    used: set[int] = set()
    for left, right in matching:
        if left == right or left in used or right in used:
            return False
        used.add(left)
        used.add(right)
    return len(used) == vertex_count


def _add_vertex_samples(
    *,
    vertex_index: int,
    samples: Sequence[tuple[str, str]],
    graph: nx.Graph,
    buckets: dict[str, dict[int, str]],
) -> int:
    """Добавляет вычисленные переходы вершины в граф межвершинных коллизий."""
    for block, output_state in samples:
        by_vertex = buckets.setdefault(output_state, {})
        for other_vertex, other_block in tuple(by_vertex.items()):
            if other_vertex == vertex_index:
                continue
            if graph.has_edge(other_vertex, vertex_index):
                continue

            graph.add_edge(
                other_vertex,
                vertex_index,
                common_state=output_state,
                blocks={
                    other_vertex: other_block,
                    vertex_index: block,
                },
            )

        # Для каждой пары вершины и выходного состояния сохраняется первый блок.
        by_vertex.setdefault(vertex_index, block)

    return len(samples)


def build_diamond_structure_blackburn(
    search: SearchAlgorithms,
    depth: int = 3,
    truncate_bits: int = 16,
    trials_limit: int = 1_000_000,
    rounds: int = 12,
    logger: Optional[Any] = None,
    first_level_N: int = 1024,
    stats: Optional[Dict[str, int]] = None,
    initial_states: Optional[Sequence[str]] = None,
    list_safety_factor: float = 1.0,
    growth_factor: float = 1.5,
    sigma_bits: int = 0,
    sigma_seed: int = 0,
    seed: int | None = None,
):
    """Строит уровни по схеме Blackburn–Stinson–Upadhyay с расширяемыми списками переходов и совершенным паросочетанием."""
    validate_truncate_bits(truncate_bits)
    validate_sigma_bits(sigma_bits)
    if depth < 1:
        raise ValueError("depth должен быть не меньше 1.")
    if first_level_N < 512 or first_level_N % 512 != 0:
        raise ValueError("first_level_N должен быть положительным кратным 512.")
    if trials_limit < 1:
        raise ValueError("trials_limit должен быть положительным.")
    if list_safety_factor <= 0:
        raise ValueError("list_safety_factor должен быть положительным.")
    if growth_factor <= 1.0:
        raise ValueError("growth_factor должен быть больше 1.")

    model = ReducedGostModel(truncate_bits, rounds)
    schedule = sigma_schedule(depth, sigma_bits, sigma_seed)
    num_leaves = 2 ** depth
    leaves_states = _normalize_initial_states(initial_states, num_leaves, truncate_bits, random.Random(seed) if seed is not None else None)
    leaves = [("", state) for state in leaves_states]
    current = [DiamondState(h, schedule[0]) for h in leaves_states]
    structure = []
    if stats is not None:
        stats["sigma_bits"] = sigma_bits
        stats["leaf_sigma"] = schedule[0]
        for i, value in enumerate(schedule[1:], start=1):
            stats[f"sigma_level_{i}"] = value

    if logger:
        logger._log(
            f"[Blackburn] Создано {num_leaves} различных n-битных листьев."
        )

    if logger and hasattr(logger, "level_completed"):
        logger.level_completed(leaves, structure)

    level_index = 0
    while len(current) > 1:
        vertex_count = len(current)
        level_N = first_level_N + 512 * level_index
        base_L = blackburn_list_size(
            vertex_count,
            truncate_bits,
            safety_factor=list_safety_factor,
        )

        graph = nx.Graph()
        graph.add_nodes_from(range(vertex_count))
        buckets: dict[str, dict[int, str]] = {}
        sampled_per_vertex = [0] * vertex_count
        level_queries = 0
        matching_attempts = 0
        target_L = base_L

        if logger:
            logger._log(
                f"[Blackburn] Уровень {level_index + 1}: "
                f"ν={vertex_count}, N={level_N}, начальный L={base_L}."
            )

        chosen_matching: Optional[set[tuple[int, int]]] = None

        factory = getattr(search, "blackburn_layer", None)
        session = factory([state.h for state in current], level_N, truncate_bits, rounds,
                          sigma_bits=sigma_bits, current_sigma=schedule[level_index],
                          target_sigma=schedule[level_index + 1]) if factory else nullcontext(None)
        with session as discovery:
            while level_queries < trials_limit:
                # Один вызов C++ расширяет списки всех вершин, распределяя пакетные вычисления между потоками.

                if len(set(sampled_per_vertex)) != 1:
                    raise AssertionError("Размеры Blackburn-списков рассинхронизированы.")
                already_sampled = sampled_per_vertex[0]
                remaining = trials_limit - level_queries
                add_per_vertex = min(
                    max(0, target_L - already_sampled),
                    remaining // vertex_count,
                )
                if add_per_vertex <= 0:
                    break

                if discovery is None:
                    sampled_lists = search.sample_transitions(
                        [state.h for state in current],
                        add_per_vertex,
                        level_N,
                        truncate_bits,
                        rounds,
                        sigma_bits=sigma_bits,
                        current_sigma=schedule[level_index],
                        target_sigma=schedule[level_index + 1],
                    )
                    if len(sampled_lists) != vertex_count:
                        raise RuntimeError("Backend вернул неверное число Blackburn-списков.")
                    for vertex_index, samples in enumerate(sampled_lists):
                        if len(samples) != add_per_vertex:
                            raise RuntimeError("Backend вернул неполный Blackburn-список.")
                        performed = _add_vertex_samples(
                            vertex_index=vertex_index,
                            samples=samples,
                            graph=graph,
                            buckets=buckets,
                        )
                        sampled_per_vertex[vertex_index] += performed
                        level_queries += performed
                else:
                    edges, performed = discovery.grow(add_per_vertex, search._seed())
                    for left, right, left_block, right_block, common, sigma in edges:
                        if not (0 <= left < vertex_count and 0 <= right < vertex_count and left != right):
                            raise AssertionError("Invalid Blackburn collision vertices")
                        if not (model.transition(left_block, current[left].h, level_N) ==
                                model.transition(right_block, current[right].h, level_N) == common and
                                update_sigma_reduced(schedule[level_index], left_block, sigma_bits) ==
                                update_sigma_reduced(schedule[level_index], right_block, sigma_bits) ==
                                sigma == schedule[level_index + 1]):
                            raise AssertionError("C++ Blackburn edge failed independent hash/Sigma validation")
                        graph.add_edge(left, right, common_state=common,
                                       blocks={left:left_block, right:right_block})
                    sampled_per_vertex = [value + add_per_vertex for value in sampled_per_vertex]
                    level_queries += performed

                matching_attempts += 1
                raw_matching = nx.algorithms.matching.max_weight_matching(
                    graph,
                    maxcardinality=True,
                )
                normalized_matching = {
                    (min(left, right), max(left, right))
                    for left, right in raw_matching
                }

                if logger:
                    logger._log(
                        f"[Blackburn] Граф: |E|={graph.number_of_edges()}, "
                        f"matching={len(normalized_matching)}/{vertex_count // 2}, "
                        f"L={target_L}, вычислений={level_queries}."
                    )

                if _matching_covers_all_vertices(normalized_matching, vertex_count):
                    # Удаляет рёбра с совпадающими родительскими состояниями и продолжает расширение списков.

                    seen_outputs: set[str] = set()
                    duplicates = []
                    for edge_pair in sorted(normalized_matching):
                        output = graph.get_edge_data(*edge_pair)["common_state"]
                        if output in seen_outputs:
                            duplicates.append(edge_pair)
                        seen_outputs.add(output)
                    if not duplicates:
                        chosen_matching = normalized_matching
                        break
                    graph.remove_edges_from(duplicates)
                    if discovery is not None:
                        discovery.drop_edges(duplicates)

                next_target = max(target_L + 1, math.ceil(target_L * growth_factor))
                target_L = next_target

        if chosen_matching is None:
            isolated = list(nx.isolates(graph))
            raise RuntimeError(
                "Blackburn: не удалось получить совершенное паросочетание "
                f"на уровне {level_index + 1} за {level_queries} переходов. "
                f"ν={vertex_count}, |E|={graph.number_of_edges()}, "
                f"изолированные вершины={isolated}. "
                "Увеличьте trials_limit или list_safety_factor."
            )

        level_info = []
        next_level = []

        for left_index, right_index in sorted(chosen_matching):
            edge = graph.get_edge_data(left_index, right_index)
            if edge is None:
                raise AssertionError("Ребро matching отсутствует в графе.")

            common_state = edge["common_state"]
            blocks = edge["blocks"]
            left_block = blocks[left_index]
            right_block = blocks[right_index]
            left_state = current[left_index]
            right_state = current[right_index]
            h_left = left_state.h
            h_right = right_state.h

            check_left = model.transition(left_block, h_left, level_N)
            check_right = model.transition(right_block, h_right, level_N)
            check_sigma_left = update_sigma_reduced(left_state.sigma, left_block, sigma_bits)
            check_sigma_right = update_sigma_reduced(right_state.sigma, right_block, sigma_bits)
            if not (check_left == check_right == common_state and
                    check_sigma_left == check_sigma_right == schedule[level_index + 1]):
                raise AssertionError(
                    "Ребро графа Blackburn не проходит независимую проверку модели."
                )

            level_info.append(
                (
                    h_left,
                    h_right,
                    left_block,
                    right_block,
                    common_state,
                )
            )
            next_level.append(DiamondState(common_state, schedule[level_index + 1]))

        if stats is not None:
            stats["collision_queries"] = (
                stats.get("collision_queries", 0) + level_queries
            )
            stats["blackburn_transition_queries"] = (
                stats.get("blackburn_transition_queries", 0) + level_queries
            )
            stats["blackburn_matching_attempts"] = (
                stats.get("blackburn_matching_attempts", 0) + matching_attempts
            )
            stats["blackburn_graph_edges"] = (
                stats.get("blackburn_graph_edges", 0) + graph.number_of_edges()
            )
            stats[f"blackburn_level_{level_index + 1}_L"] = max(sampled_per_vertex)
            stats[f"blackburn_level_{level_index + 1}_edges"] = graph.number_of_edges()

        structure.append(level_info)
        if logger and hasattr(logger, "level_completed"):
            logger.level_completed(leaves, structure)
        current = next_level
        level_index += 1

    if stats is not None:
        transition_queries = int(stats.get("blackburn_transition_queries", stats.get("collision_queries", 0)))
        stats["compression_calls"] = transition_queries
        stats["generated_candidates"] = transition_queries
        stats.setdefault("oracle_queries", 0)
        stats.setdefault("grover_iterations", 0)

    return leaves, structure


def build_diamond_structure(
    search: SearchAlgorithms,
    depth: int = 3,
    truncate_bits: int = 16,
    trials_limit: int = 1_000_000,
    rounds: int = 12,
    logger: Optional[Any] = None,
    first_level_N: int = 1024,
    stats: Optional[Dict[str, int]] = None,
    initial_states: Optional[Sequence[str]] = None,
    sigma_bits: int = 0,
    sigma_seed: int = 0,
    seed: int | None = None,
):
    """Строит алмазную структуру через основную реализацию Blackburn."""
    return build_diamond_structure_blackburn(
        search=search,
        depth=depth,
        truncate_bits=truncate_bits,
        trials_limit=trials_limit,
        rounds=rounds,
        logger=logger,
        first_level_N=first_level_N,
        stats=stats,
        initial_states=initial_states,
        sigma_bits=sigma_bits,
        sigma_seed=sigma_seed,
        seed=seed,
    )


def diamond_to_json_dict(
    leaves_data,
    structure,
    truncate_bits: int,
    depth: int,
    rounds: int,
    prefix_blocks: int,
    stats: Optional[Dict[str, int]] = None,
    sigma_bits: int | None = None,
) -> dict:
    stats_dict = dict(stats or {})
    s_bits = int(stats_dict.get("sigma_bits", 0) if sigma_bits is None else sigma_bits)
    validate_sigma_bits(s_bits)
    leaf_sigma = int(stats_dict.get("leaf_sigma", 0)) if s_bits else 0
    schedule = [leaf_sigma] + [int(stats_dict.get(f"sigma_level_{i}", 0)) for i in range(1, depth + 1)]
    link_N = prefix_blocks * 512
    first_level_N = link_N + 512
    return {
        "format_version": FORMAT_VERSION,
        "model": MODEL_NAME,
        "trunc_bits": truncate_bits,
        "sigma_bits": s_bits,
        "sigma_projection": "low_bits",
        "sigma_mode": "constrained" if s_bits else "disabled",
        "leaf_sigma": leaf_sigma,
        "sigma_schedule": schedule,
        "depth": depth,
        "rounds": rounds,
        "prefix_blocks": prefix_blocks,
        "link_N": link_N,
        "first_level_N": first_level_N,
        "stats": stats_dict,
        "leaves": [{"block": b, "state": h, "sigma": leaf_sigma} for b, h in leaves_data],
        "structure": [
            [
                {
                    "h_left": l,
                    "h_right": r,
                    "sigma_left": schedule[level_index],
                    "sigma_right": schedule[level_index],
                    "m_link_left": m1,
                    "m_link_right": m2,
                    "h_common": c,
                    "sigma_common": schedule[level_index + 1],
                }
                for (l, r, m1, m2, c) in level
            ]
            for level_index, level in enumerate(structure)
        ],
        "theory": {
            "naive_collision_bits": truncate_bits + s_bits,
            "sigma_aware_collision_bits": truncate_bits,
            "naive_linking_exponent": truncate_bits + s_bits - depth,
            "sigma_aware_linking_exponent": truncate_bits - depth,
        },
    }


def _is_legacy_data(data: dict) -> bool:
    return data.get("format_version") == LEGACY_FORMAT_VERSION and data.get("model") == LEGACY_MODEL_NAME


class DiamondValidationError(ValueError):
    """Указывает проверяемый переход при несовпадении сохранённого состояния."""

    def __init__(self, level, pair, side):
        self.level, self.pair, self.side = level, pair, side
        super().__init__(f"Ошибка на уровне {level}, пара {pair + 1}, {'левый' if side == 'left' else 'правый'} переход: результат функции сжатия или часть контрольной суммы не совпадает с сохранённым состоянием.")


def validate_diamond_data(data: dict, *, on_transition=None, check_cancelled=None) -> bool:
    legacy = _is_legacy_data(data)
    if not legacy and (data.get("format_version") != FORMAT_VERSION or data.get("model") != MODEL_NAME):
        raise ValueError("JSON создан несовместимой версией программы. Постройте diamond заново.")

    truncate_bits = int(data["trunc_bits"])
    rounds = int(data.get("rounds", 12))
    first_level_N = int(data["first_level_N"])
    sigma_bits = 0 if legacy else int(data.get("sigma_bits", 0))
    validate_sigma_bits(sigma_bits)
    expected_len = truncate_bits // 4
    model = ReducedGostModel(truncate_bits, rounds)
    depth = int(data["depth"])
    prefix_blocks = int(data["prefix_blocks"])
    if depth < 1 or prefix_blocks < 1 or len(data["structure"]) != depth:
        raise ValueError("Некорректная глубина или число блоков префикса.")
    if int(data["link_N"]) != 512 * prefix_blocks or first_level_N != 512 * (prefix_blocks + 1):
        raise ValueError("N не согласован с числом блоков префикса.")

    leaves = [x["state"] for x in data["leaves"]]
    if len(leaves) != 2 ** depth:
        raise ValueError("Число листьев не равно 2^depth.")
    leaf_sigmas = [0 if legacy else int(x.get("sigma", data.get("leaf_sigma", 0))) for x in data["leaves"]]
    if len(set(leaves)) != len(leaves):
        raise ValueError("В JSON имеются повторяющиеся листья.")
    if any(len(h) != expected_len for h in leaves):
        raise ValueError("Некорректная длина редуцированного h в листьях.")
    if len(set(leaf_sigmas)) != 1:
        raise ValueError("Все leaves должны иметь один leaf_sigma.")

    current = [DiamondState(h, sig) for h, sig in zip(leaves, leaf_sigmas)]
    schedule = [leaf_sigmas[0]] if legacy else list(map(int, data.get("sigma_schedule", [leaf_sigmas[0]])))
    if not legacy and len(schedule) != int(data["depth"]) + 1:
        raise ValueError("Некорректная длина sigma_schedule.")
    if not legacy and (schedule[0] != leaf_sigmas[0] or
                       any(value < 0 or value > sigma_mask(sigma_bits) for value in schedule) or
                       int(data.get("leaf_sigma", schedule[0])) != schedule[0]):
        raise ValueError("Некорректные значения sigma_schedule / leaf_sigma.")

    for level_index, level in enumerate(data["structure"]):
        if len(level) * 2 != len(current):
            raise ValueError("Нарушена бинарная структура diamond.")
        level_N = first_level_N + 512 * level_index
        next_level: list[DiamondState] = []
        used_children: list[tuple[str, int]] = []
        for pair_index, node in enumerate(level):
            h_left, h_right = node["h_left"], node["h_right"]
            sigma_left = 0 if legacy else int(node.get("sigma_left", schedule[level_index]))
            sigma_right = 0 if legacy else int(node.get("sigma_right", schedule[level_index]))
            sigma_common = 0 if legacy else int(node.get("sigma_common", schedule[level_index + 1]))
            if not legacy and (sigma_left != schedule[level_index] or sigma_right != schedule[level_index]
                               or sigma_common != schedule[level_index + 1]):
                raise ValueError("Sigma ребра не соответствует sigma_schedule.")
            used_children.extend(((h_left, sigma_left), (h_right, sigma_right)))
            for side, h, sigma in (("left", h_left, sigma_left), ("right", h_right, sigma_right)):
                if check_cancelled:
                    check_cancelled()
                block = node[f"m_link_{side}"]
                actual_h = model.transition(block, h, level_N)
                actual_sigma = update_sigma_reduced(sigma, block, sigma_bits)
                if actual_h != node["h_common"] or actual_sigma != sigma_common:
                    raise DiamondValidationError(level_index + 1, pair_index, side)
                if on_transition:
                    on_transition(level_index + 1, pair_index, side)
            next_level.append(DiamondState(node["h_common"], sigma_common))
        if Counter(used_children) != Counter((st.h, st.sigma) for st in current):
            raise ValueError("JSON содержит несогласованные связи между уровнями.")
        if not legacy and len({st.sigma for st in next_level}) != 1:
            raise ValueError("На одном diamond level все parent nodes должны иметь общий sigma.")
        if data.get("measurement_version") in ("audited-v1", "grover-statevector-v2") and len({st.h for st in next_level}) != len(next_level):
            raise ValueError("На уровне diamond повторяются родительские хэш-коды.")
        current = next_level

    if len(current) != 1:
        raise ValueError("Diamond не сводится к единственному корню.")
    return True


def get_diamond_root(data: dict) -> str:
    if not data.get("structure"):
        return data["leaves"][0]["state"]
    return data["structure"][-1][0]["h_common"]


def get_diamond_root_state(data: dict) -> DiamondState:
    h = get_diamond_root(data)
    if _is_legacy_data(data):
        return DiamondState(h, 0)
    schedule = data.get("sigma_schedule", [data.get("leaf_sigma", 0)])
    return DiamondState(h, int(schedule[-1]))
