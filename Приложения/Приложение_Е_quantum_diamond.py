"""Управляет квантовым построением алмазной структуры для приложения Е."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence

import networkx as nx

from CppCore import cpp_core_available, cpp_quantum_layer
from .search_methods import BBHTOptions, SearchMethod, search_method, SEARCH_PROTOCOL
from .diamond import _normalize_initial_states, sigma_schedule
from .collision_probability import plan_search_messages
from .statevector_limits import check_layer_resources, check_deadline, DENSE_MAX_STATES
from .grover import GroverResult, simulate_grover_from_marked, optimal_grover_iterations
from .model import ReducedGostModel, constrained_random_block, update_sigma_reduced, validate_sigma_bits, validate_truncate_bits


class QuantumLayerFailure(RuntimeError):
    """Сообщает об отсутствии совершенного паросочетания в вероятностном алгоритме 2."""


@dataclass(frozen=True)
class QuantumLayerParameters:
    state_bits: int
    layer_bits: int
    vertex_count: int
    table_messages: int
    search_messages: int


def _ceil_rational_cube_root(numerator: int, denominator: int = 1) -> int:
    """Вычисляет точный целый потолок кубического корня отношения числителя и знаменателя."""
    low, high = 0, 1 << ((numerator.bit_length() + 2) // 3)
    while low + 1 < high:
        middle = (low + high) // 2
        if middle ** 3 * denominator >= numerator:
            high = middle
        else:
            low = middle
    return high


def algorithm2_parameters(state_bits: int, layer_bits: int) -> QuantumLayerParameters:
    """Вычисляет L = ⌈∛(r² · 2^(n−r))⌉ и S = ⌈∛(2^(2(n−r))/r²)⌉ для r = layer_bits."""
    if state_bits <= 0:
        raise ValueError("state_bits должен быть положительным.")
    if layer_bits < 1 or layer_bits > state_bits:
        raise ValueError("layer_bits должен лежать в диапазоне 1..state_bits.")
    vertex_count = 1 << layer_bits
    # Целочисленные кубы исключают ошибки округления при вычислении L и S.
    gap = state_bits - layer_bits
    table_messages = _ceil_rational_cube_root(layer_bits ** 2 * (1 << gap))
    search_messages = _ceil_rational_cube_root(1 << (2 * gap), layer_bits ** 2)
    return QuantumLayerParameters(
        state_bits=state_bits,
        layer_bits=layer_bits,
        vertex_count=vertex_count,
        table_messages=table_messages,
        search_messages=search_messages,
    )


def select_layer_parameters(
    state_bits: int,
    layer_bits: int,
    *,
    parameter_strategy: str = "theoretical",
    target_probability: float = 0.95,
) -> tuple[QuantumLayerParameters, dict[str, float | int]]:
    """Выбирает размер поиска для одного шага без изменения исходной таблицы алгоритма 2."""
    if parameter_strategy not in ("theoretical", "target_probability"):
        raise ValueError("Неизвестный режим выбора параметров.")
    if not isinstance(target_probability, (int, float)) or not math.isfinite(target_probability) or not 0 < target_probability < 1:
        raise ValueError("Целевая вероятность должна быть строго между 0 и 1.")
    baseline = algorithm2_parameters(state_bits, layer_bits)
    estimate = plan_search_messages(
        state_bits, baseline.vertex_count, baseline.table_messages,
        baseline.search_messages, target_probability,
    )
    if parameter_strategy == "theoretical":
        selected = baseline
        predicted = estimate.baseline_probability
    else:
        selected = QuantumLayerParameters(
            baseline.state_bits, baseline.layer_bits, baseline.vertex_count,
            baseline.table_messages, estimate.search_messages,
        )
        predicted = estimate.predicted_probability
    return selected, {
        "estimated_distinct_targets": estimate.distinct_targets,
        "predicted_candidate_probability": predicted,
        "baseline_candidate_probability": estimate.baseline_probability,
        "baseline_S": baseline.search_messages,
    }


def _new_message_space(
    count: int, rng: random.Random, used: set[str], *, sigma_bits: int = 0,
    current_sigma: int = 0, target_sigma: int = 0,
) -> list[str]:
    messages = []
    while len(messages) < count:
        check_deadline()
        block = constrained_random_block(current_sigma, target_sigma, sigma_bits, rng)
        if block in used:
            continue
        used.add(block)
        messages.append(block)
    return messages


def build_one_layer_quantum(
    states: Sequence[str],
    *,
    level_N: int,
    truncate_bits: int,
    rounds: int = 12,
    rng: Optional[random.Random] = None,
    max_statevector_size: Optional[int] = None,
    stats: Optional[Dict[str, int]] = None,
    use_cpp: Optional[bool] = None,
    sigma_bits: int = 0,
    current_sigma: int = 0,
    target_sigma: int = 0,
    threads: int = 0,
    parameter_strategy: str = "theoretical",
    target_probability: float = 0.95,
    method: str = "grover_fixed",
    bbht_options: BBHTOptions | None = None,
) -> list[tuple[str, str, str, str, str]]:
    """Строит уровень алгоритмом 2 через C++ или резервный Python с проверкой паросочетания и переходов."""
    validate_truncate_bits(truncate_bits)
    validate_sigma_bits(sigma_bits)
    states = list(states)
    vertex_count = len(states)
    if vertex_count < 2 or vertex_count & (vertex_count - 1):
        raise ValueError("Число состояний слоя должно быть степенью двойки >= 2.")
    if len(set(states)) != len(states):
        raise ValueError("Состояния входного слоя должны быть различными.")
    layer_bits = int(math.log2(vertex_count))
    params, probability_stats = select_layer_parameters(
        truncate_bits, layer_bits, parameter_strategy=parameter_strategy,
        target_probability=target_probability,
    )
    if (
        max_statevector_size is not None
        and params.search_messages > max_statevector_size
    ):
        raise ValueError(
            f"Algorithm 2 требует state-vector S={params.search_messages}, "
            f"лимит симулятора={max_statevector_size}."
        )

    selected = search_method(method)
    if selected is SearchMethod.CLASSICAL:
        raise ValueError("Квантовое построение требует фиксированного Гровера или BBHT.")
    cpp_enabled = cpp_core_available() if use_cpp is None else use_cpp
    if selected is SearchMethod.GROVER_BBHT and not cpp_enabled:
        raise RuntimeError("BBHT требует собранное C++-ядро.")
    dense_limit = (bbht_options or BBHTOptions()).dense_max_states if selected is SearchMethod.GROVER_BBHT else DENSE_MAX_STATES
    check_layer_resources(params.table_messages, params.search_messages, vertex_count, layer_bits,
                          python=not cpp_enabled, dense_max_states=dense_limit)
    generator = rng or random.Random()
    model = ReducedGostModel(truncate_bits, rounds)
    graph = nx.Graph()
    graph.add_nodes_from(range(vertex_count))
    quantum_queries = 0
    simulator_evaluations = 0
    grover_successes = 0
    vector_stats = dict(elements=0, iterations=0, attempts=0, marked=0, probability_sum=0.0, norm_max=0.0, seconds=0.0, verification=0)
    diagnostics = []
    if cpp_enabled:
        cpp_result = cpp_quantum_layer(
            states,
            params.table_messages,
            params.search_messages,
            layer_bits,
            level_N,
            truncate_bits,
            rounds,
            generator.getrandbits(64),
            sigma_bits=sigma_bits,
            current_sigma=current_sigma,
            target_sigma=target_sigma,
            threads=threads,
            **({"method": selected, "bbht_options": bbht_options} if selected is SearchMethod.GROVER_BBHT else {}),
        )
        quantum_queries = cpp_result.oracle_queries
        simulator_evaluations = cpp_result.simulator_evaluations
        grover_successes = cpp_result.grover_successes
        vector_stats = dict(elements=cpp_result.statevector_elements_processed, iterations=cpp_result.statevector_iterations,
                            attempts=cpp_result.grover_attempts, marked=cpp_result.marked_elements,
                            probability_sum=cpp_result.success_probability_sum, norm_max=cpp_result.statevector_norm_error_max,
                            seconds=cpp_result.statevector_seconds, verification=cpp_result.verification_evaluations)
        for left, right, left_block, right_block, common in cpp_result.edges:
            if left == right or not (0 <= left < vertex_count and 0 <= right < vertex_count):
                raise AssertionError("C++ quantum-layer вернул некорректное ребро.")
            if not graph.has_edge(left, right):
                graph.add_edge(
                    left,
                    right,
                    common_state=common,
                    blocks={left: left_block, right: right_block},
                )
        qram_entries = cpp_result.qram_entries
    else:
        used_messages: set[str] = set()

        # Общее множество M используется для всех вершин с сохранением каждой записи.
        table_space = _new_message_space(
            params.table_messages, generator, used_messages, sigma_bits=sigma_bits,
            current_sigma=current_sigma, target_sigma=target_sigma,
        )
        qram: dict[str, list[tuple[int, str]]] = {}
        for vertex_index, state in enumerate(states):
            for block_index, block in enumerate(table_space):
                if block_index % 256 == 0:
                    check_deadline()
                output = model.transition(block, state, level_N)
                qram.setdefault(output, []).append((vertex_index, block))
        qram_entries = vertex_count * params.table_messages
        simulator_evaluations = qram_entries

        # Для каждой вершины выполняется layer_bits поисков Гровера.
        for vertex_index, state in enumerate(states):
            for _ in range(layer_bits):
                check_deadline()
                search_space = _new_message_space(
                    params.search_messages, generator, used_messages, sigma_bits=sigma_bits,
                    current_sigma=current_sigma, target_sigma=target_sigma,
                )
                outputs = []
                for block_index, block in enumerate(search_space):
                    if block_index % 256 == 0:
                        check_deadline()
                    outputs.append(model.transition(block, state, level_N))
                simulator_evaluations += params.search_messages
                marked = [
                    index
                    for index, output in enumerate(outputs)
                    if any(other != vertex_index for other, _ in qram.get(output, ()))
                ]
                grover: GroverResult = simulate_grover_from_marked(
                    params.search_messages,
                    marked,
                    iterations=optimal_grover_iterations(params.search_messages, 1),
                    rng=generator,
                    max_statevector_size=max_statevector_size,
                )
                vector_stats['elements'] += grover.statevector_elements_processed
                vector_stats['iterations'] += grover.iterations
                vector_stats['attempts'] += 1
                diagnostics.append(dict(attempt_policy='fixed_single', search_messages=params.search_messages,
                    growth=1.2, effective_max_attempts=1, attempts=1, failures=int(not grover.is_marked),
                    stop_reason='found' if grover.is_marked else 'unmarked_measurement'))
                vector_stats['marked'] += grover.marked_count
                vector_stats['probability_sum'] += grover.success_probability
                vector_stats['norm_max'] = max(vector_stats['norm_max'], grover.norm_error)
                vector_stats['seconds'] += grover.statevector_seconds
                measured = grover.measured_index
                if model.transition(search_space[measured], state, level_N) != outputs[measured]:
                    raise AssertionError('Переход измеренного кандидата не воспроизводится.')
                simulator_evaluations += 1
                vector_stats['verification'] += 1
                quantum_queries += grover.quantum_queries + 1  # Учитывает проверку измеренного кандидата.
                if not grover.is_marked or grover.measured_index is None:
                    continue

                candidate_index = grover.measured_index
                output = outputs[candidate_index]
                candidate_block = search_space[candidate_index]
                other_entries = [
                    entry for entry in qram[output] if entry[0] != vertex_index
                ]
                if not other_entries:
                    raise AssertionError(
                        "Grover отметил значение без межвершинной коллизии."
                    )
                other_vertex, other_block = other_entries[0]
                grover_successes += 1
                if not graph.has_edge(vertex_index, other_vertex):
                    graph.add_edge(
                        vertex_index,
                        other_vertex,
                        common_state=output,
                        blocks={vertex_index: candidate_block, other_vertex: other_block},
                    )

    if not cpp_enabled:
        quantum_queries += qram_entries  # Учитывает запросы функции сжатия при подготовке qRAM.
    grover_iterations = vector_stats['iterations']
    if cpp_enabled and stats is not None:
        stats['amplitude_backend'] = cpp_result.amplitude_backend
    if stats is not None:
        stats['search_protocol'] = cpp_result.search_protocol if cpp_enabled else SEARCH_PROTOCOL
        stats['quantum_search_diagnostics'] = [dict(item, layer_bits=layer_bits,
            vertex=index//layer_bits, repetition=index%layer_bits) for index, item in
            enumerate(cpp_result.search_diagnostics if cpp_enabled else diagnostics)]
        stats['quantum_phase_oracle_queries'] = vector_stats['iterations']
        stats['quantum_verification_queries'] = vector_stats['verification']
        stats['quantum_failed_attempts'] = vector_stats['attempts'] - grover_successes
    if selected is SearchMethod.GROVER_BBHT and stats is not None:
        stats['quantum_phase_oracle_queries'] = cpp_result.phase_oracle_queries
        stats['quantum_verification_queries'] = cpp_result.verification_queries
        stats['quantum_failed_attempts'] = cpp_result.failed_attempts
    # Ищет совершенное паросочетание в графе коллизий.
    raw_matching = nx.algorithms.matching.max_weight_matching(
        graph, maxcardinality=True
    )
    matching = {
        (min(left, right), max(left, right)) for left, right in raw_matching
    }
    if stats is not None:
        for suffix, key in (('elements_processed', 'elements'), ('iterations', 'iterations'), ('seconds', 'seconds')):
            field = 'quantum_statevector_' + suffix
            stats[field] = stats.get(field, 0) + vector_stats[key]
        stats['quantum_statevector_norm_error_max'] = max(stats.get('quantum_statevector_norm_error_max', 0.0), vector_stats['norm_max'])
        for field, key in (('quantum_grover_attempts', 'attempts'), ('quantum_marked_elements', 'marked'), ('quantum_success_probability_sum', 'probability_sum'), ('quantum_verification_hash_evaluations', 'verification')):
            stats[field] = stats.get(field, 0) + vector_stats[key]
        stats['quantum_matching_attempts'] = stats.get('quantum_matching_attempts', 0) + 1
        stats["quantum_oracle_queries"] = stats.get("quantum_oracle_queries", 0) + quantum_queries
        stats["quantum_simulator_hash_evaluations"] = (
            stats.get("quantum_simulator_hash_evaluations", 0) + simulator_evaluations
        )
        stats["quantum_qram_entries"] = stats.get("quantum_qram_entries", 0) + qram_entries
        stats["quantum_qram_total_entries"] = stats.get("quantum_qram_total_entries", 0) + qram_entries
        stats["quantum_qram_peak_entries"] = max(stats.get("quantum_qram_peak_entries", 0), qram_entries)
        stats["quantum_grover_iterations"] = stats.get("quantum_grover_iterations", 0) + grover_iterations
        stats["quantum_table_queries"] = stats.get("quantum_table_queries", 0) + qram_entries
        stats["quantum_search_verification_queries"] = stats.get("quantum_search_verification_queries", 0) + vector_stats["verification"]
        stats["quantum_grover_successes"] = stats.get("quantum_grover_successes", 0) + grover_successes
        stats["collision_queries"] = stats.get("collision_queries", 0) + simulator_evaluations
        for field, value in probability_stats.items():
            stats[f"quantum_layer_{layer_bits}_{field}"] = value
        stats[f"quantum_layer_{layer_bits}_L"] = params.table_messages
        stats[f"quantum_layer_{layer_bits}_S"] = params.search_messages
        stats[f"quantum_layer_{layer_bits}_edges"] = graph.number_of_edges()
        backend_key = "quantum_cpp_layer_calls" if cpp_enabled else "quantum_python_layer_calls"
        stats[backend_key] = stats.get(backend_key, 0) + 1
    if len(matching) != vertex_count // 2:
        raise QuantumLayerFailure(
            "Algorithm 2 не получил perfect matching: "
            f"matching={len(matching)}/{vertex_count // 2}, "
            f"|E|={graph.number_of_edges()}, L={params.table_messages}, "
            f"S={params.search_messages}. Повторите вероятностный слой."
        )
    matched_outputs = [
        graph.get_edge_data(left, right)["common_state"] for left, right in matching
    ]
    if len(set(matched_outputs)) != len(matched_outputs):
        raise QuantumLayerFailure(
            "Perfect matching содержит одинаковые выходные состояния; "
            "для следующего слоя нужны различные вершины. Повторите слой."
        )

    level = []
    for left, right in sorted(matching):
        edge = graph.get_edge_data(left, right)
        common = edge["common_state"]
        blocks = edge["blocks"]
        left_block = blocks[left]
        right_block = blocks[right]
        if model.transition(left_block, states[left], level_N) != common:
            raise AssertionError("Левое ребро Algorithm 2 не воспроизводится.")
        if model.transition(right_block, states[right], level_N) != common:
            raise AssertionError("Правое ребро Algorithm 2 не воспроизводится.")
        if update_sigma_reduced(current_sigma, left_block, sigma_bits) != target_sigma:
            raise AssertionError("Левое sigma-ребро Algorithm 2 не воспроизводится.")
        if update_sigma_reduced(current_sigma, right_block, sigma_bits) != target_sigma:
            raise AssertionError("Правое sigma-ребро Algorithm 2 не воспроизводится.")
        level.append((states[left], states[right], left_block, right_block, common))

    if stats is not None:
        stats['quantum_matching_successes'] = stats.get('quantum_matching_successes', 0) + 1
        stats['quantum_independent_verification_hash_evaluations'] = stats.get('quantum_independent_verification_hash_evaluations', 0) + vertex_count
    return level


def _merge_layer_stats(stats, values, attempt):
    """Объединяет счётчики успешных и неудачных попыток по одинаковым правилам."""
    if stats is None:
        return
    for key, value in values.items():
        if key == 'quantum_search_diagnostics':
            stats.setdefault(key, []).extend(dict(item, level_attempt=attempt) for item in value)
        elif key in ('amplitude_backend', 'search_protocol'):
            stats[key] = value if stats.get(key, value) == value else 'mixed'
        elif key in ('quantum_qram_peak_entries', 'quantum_statevector_norm_error_max'):
            stats[key] = max(stats.get(key, 0), value)
        elif key.startswith('quantum_layer_') and key.endswith(('_L', '_S', '_edges', '_targets', '_probability', '_baseline_S')):
            stats[key] = value
        else:
            stats[key] = stats.get(key, 0) + value


def build_diamond_structure_quantum(
    search,
    depth: int = 3,
    truncate_bits: int = 12,
    trials_limit: int = 1_000_000,
    rounds: int = 12,
    logger: Optional[Any] = None,
    first_level_N: int = 1024,
    stats: Optional[Dict[str, int]] = None,
    initial_states: Optional[Sequence[str]] = None,
    max_layer_attempts: int = 12,
    seed: Optional[int] = None,
    use_cpp: Optional[bool] = None,
    sigma_bits: int = 0,
    sigma_seed: Optional[int] = None,
    threads: int = 0,
    parameter_strategy: str = "theoretical",
    target_probability: float = 0.95,
    method: str = "grover_fixed",
    bbht_options: BBHTOptions | None = None,
):
    """Строит алмазную структуру по уровням с заданными N, частью контрольной суммы и повторными попытками."""
    del search
    validate_truncate_bits(truncate_bits)
    validate_sigma_bits(sigma_bits)
    if depth < 1:
        raise ValueError("depth должен быть не меньше 1.")
    if first_level_N < 512 or first_level_N % 512 != 0:
        raise ValueError("first_level_N должен быть положительным кратным 512.")
    if trials_limit < 1 or max_layer_attempts < 1:
        raise ValueError("Лимиты должны быть положительными.")

    selected = search_method(method)
    if selected is SearchMethod.CLASSICAL:
        raise ValueError("Квантовое построение требует фиксированного Гровера или BBHT.")
    cpp_enabled = cpp_core_available() if use_cpp is None else use_cpp
    if selected is SearchMethod.GROVER_BBHT and not cpp_enabled:
        raise RuntimeError("BBHT требует собранное C++-ядро.")
    for layer_bits in range(depth, 0, -1):
        params, _ = select_layer_parameters(
            truncate_bits, layer_bits, parameter_strategy=parameter_strategy,
            target_probability=target_probability,
        )
        dense_limit = (bbht_options or BBHTOptions()).dense_max_states if selected is SearchMethod.GROVER_BBHT else DENSE_MAX_STATES
        check_layer_resources(params.table_messages, params.search_messages, params.vertex_count, layer_bits,
                              python=not cpp_enabled, dense_max_states=dense_limit)
    generator = random.Random(seed)
    schedule = sigma_schedule(depth, sigma_bits, sigma_seed if sigma_seed is not None else (seed or 0))
    leaf_count = 1 << depth
    leaves_states = _normalize_initial_states(initial_states, leaf_count, truncate_bits, generator)
    leaves = [("", state) for state in leaves_states]
    current = leaves_states[:]
    structure = []
    total_simulator_evaluations = 0
    if stats is not None:
        stats["sigma_bits"] = sigma_bits
        stats["leaf_sigma"] = schedule[0]
        for i, value in enumerate(schedule[1:], start=1):
            stats[f"sigma_level_{i}"] = value

    if logger:
        logger._log(
            f"[{selected.label}] Листьев: {leaf_count}, "
            f"state-vector, без реального квантового ускорения."
        )

    if logger and hasattr(logger, "level_completed"):
        logger.level_completed(leaves, structure)

    for level_index in range(depth):
        level_N = first_level_N + 512 * level_index
        layer = None
        for attempt in range(1, max_layer_attempts + 1):
            check_deadline()
            if stats is not None:
                stats['quantum_layer_attempts'] = stats.get('quantum_layer_attempts', 0) + 1
            attempt_stats: Dict[str, int] = {}
            try:
                candidate = build_one_layer_quantum(
                    current,
                    level_N=level_N,
                    truncate_bits=truncate_bits,
                    rounds=rounds,
                    rng=generator,
                    stats=attempt_stats,
                    use_cpp=use_cpp,
                    sigma_bits=sigma_bits,
                    current_sigma=schedule[level_index],
                    target_sigma=schedule[level_index + 1],
                    threads=threads,
                    parameter_strategy=parameter_strategy,
                    target_probability=target_probability,
                    method=selected, bbht_options=bbht_options,
                )
            except QuantumLayerFailure as exc:
                total_simulator_evaluations += attempt_stats.get(
                    "quantum_simulator_hash_evaluations", 0
                )
                if logger:
                    logger._log(
                        f"[Quantum] Уровень {level_index + 1}, попытка {attempt}: {exc}"
                    )
                _merge_layer_stats(stats, attempt_stats, attempt)
                if total_simulator_evaluations > trials_limit:
                    raise RuntimeError(
                        "Quantum Algorithm 2 превысил лимит классических "
                        f"вычислений симулятора: {total_simulator_evaluations} > "
                        f"{trials_limit}."
                    ) from exc
                continue
            layer = candidate
            total_simulator_evaluations += attempt_stats.get(
                "quantum_simulator_hash_evaluations", 0
            )
            _merge_layer_stats(stats, attempt_stats, attempt)
            if total_simulator_evaluations > trials_limit:
                raise RuntimeError(
                    "Quantum Algorithm 2 превысил лимит классических "
                    f"вычислений симулятора: {total_simulator_evaluations} > "
                    f"{trials_limit}."
                )
            break

        if layer is None:
            raise RuntimeError(
                f"Quantum Algorithm 2: уровень {level_index + 1} не построен "
                f"за {max_layer_attempts} попыток."
            )
        structure.append(layer)
        if logger and hasattr(logger, "level_completed"):
            logger.level_completed(leaves, structure)
        current = [node[4] for node in layer]
        if logger:
            logger._log(
                f"[Quantum] Уровень {level_index + 1}: "
                f"{len(layer)} пар, N={level_N}."
            )

    if stats is not None:
        # Разделяет вычисления симулятора и модельные запросы без множителя 2^s.
        stats["compression_calls"] = int(stats.get("quantum_simulator_hash_evaluations", 0))
        stats["generated_candidates"] = int(stats.get("quantum_simulator_hash_evaluations", 0))
        stats["oracle_queries"] = int(stats.get("quantum_oracle_queries", 0))
        stats["grover_iterations"] = int(stats.get("quantum_grover_iterations", 0))

    return leaves, structure
