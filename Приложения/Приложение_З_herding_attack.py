"""Управляет классической и квантовой herding-атакой с независимой проверкой пути по состояниям (h_n, Sigma_s)."""

from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass, replace
from typing import Any, Dict, List, Optional, Sequence

from CppCore import cpp_core_available, cpp_quantum_link
from .search_methods import BBHTOptions, SearchMethod, search_method, SEARCH_PROTOCOL
from .diamond import get_diamond_root, get_diamond_root_state, validate_diamond_data
from .statevector_limits import check_resources, check_native_resources, check_deadline, DENSE_MAX_STATES
from .grover import GroverResult, optimal_grover_iterations, simulate_grover_from_marked
from .interfaces import SearchAlgorithms
from .model import (DiamondState, ReducedGostModel, constrained_random_block,
                    update_sigma_reduced, validate_sigma_bits, validate_truncate_bits)


@dataclass
class AttackResult:
    description: str
    event_result: str
    prefix_blocks: List[str]
    prefix_state: str
    linking_block: str
    leaf_state: str
    suffix_blocks: List[str]
    root: str
    verified_root: str
    forged_hex: str
    link_queries: int
    link_backend: str = "classical"
    link_simulator_hash_evaluations: int = 0
    link_attempts: int = 1
    link_marked_count: int = 0
    link_success_probability: float = 0.0
    sigma_bits: int = 0
    prefix_sigma: int = 0
    leaf_sigma: int = 0
    root_sigma: int = 0
    verified_sigma: int = 0
    link_grover_iterations: int = 0
    link_statevector_elements_processed: int = 0
    link_statevector_norm_error_max: float = 0.0
    link_statevector_seconds: float = 0.0
    link_success_probability_sum: float = 0.0
    link_search_messages: int = 0
    link_verification_hash_evaluations: int = 0
    link_independent_verification_hash_evaluations: int = 0
    link_seed: Optional[int] = None
    build_method: str = ""
    link_method: str = ""
    link_phase_oracle_queries: int | None = None
    link_verification_queries: int | None = None
    link_failed_attempts: int = 0
    amplitude_backend: str = "dense"
    bbht_options: dict | None = None
    search_protocol: str = "legacy-v0"
    attempt_policy: str = ""
    search_diagnostics: list | None = None


def encode_text_prefix_blocks(text: str, expected_blocks: int) -> List[str]:
    if expected_blocks <= 0:
        raise ValueError("expected_blocks должен быть положительным.")
    try:
        raw = text.encode("windows-1251")
    except UnicodeEncodeError as exc:
        raise ValueError("Текст содержит символы вне windows-1251.") from exc
    capacity = expected_blocks * 64
    if len(raw) + 1 > capacity:
        raise ValueError(
            f"Префикс слишком длинный: зарезервировано {capacity} байт, а требуется {len(raw) + 1}."
        )
    aligned = raw + b"\x80" + b"\x00" * (capacity - len(raw) - 1)
    return [aligned[i:i + 64].hex() for i in range(0, len(aligned), 64)]


def process_prefix_blocks(blocks: Sequence[str], truncate_bits: int, rounds: int):
    """Обрабатывает префикс без части контрольной суммы для совместимости."""
    return ReducedGostModel(truncate_bits, rounds).process_blocks(list(blocks), 0)


def process_prefix_state(
    blocks: Sequence[str], truncate_bits: int, rounds: int, sigma_bits: int
) -> tuple[DiamondState, int]:
    return ReducedGostModel(truncate_bits, rounds).process_blocks_pair(
        list(blocks), sigma_bits, 0, 0
    )


def reconstruct_suffix(
    leaves: List[str], structure: List[List[dict]], target_leaf: str
) -> List[str]:
    if target_leaf not in leaves:
        raise ValueError("Целевой лист отсутствует в diamond.")
    suffix = []
    current_state = target_leaf
    for level_index, level in enumerate(structure, start=1):
        selected = None
        for node in level:
            if node["h_left"] == current_state:
                selected = (node["m_link_left"], node["h_common"])
                break
            if node["h_right"] == current_state:
                selected = (node["m_link_right"], node["h_common"])
                break
        if selected is None:
            raise ValueError(f"Для состояния {current_state} нет ребра на уровне {level_index}.")
        block, current_state = selected
        suffix.append(block)
    return suffix


def find_linking_message(
    search: SearchAlgorithms,
    prefix_state: str,
    target_states: List[str],
    N: int,
    truncate_bits: int,
    trials_limit: int = 1_000_000,
    rounds: int = 12,
    stats: Optional[Dict[str, int]] = None,
    *,
    sigma_bits: int = 0,
    prefix_sigma: int = 0,
    leaf_sigma: int = 0,
):
    result = search.find_link(
        prefix_state, target_states, N, truncate_bits, rounds, trials_limit,
        sigma_bits=sigma_bits, current_sigma=prefix_sigma, target_sigma=leaf_sigma,
    )
    if stats is not None:
        stats["link_queries"] = stats.get("link_queries", 0) + result.queries
        stats["linking_attempts"] = stats.get("linking_attempts", 0) + result.queries
    return result.block, result.target_state


def _leaf_sigma(data: dict, leaf_h: str) -> int:
    for item in data["leaves"]:
        if item["state"] == leaf_h:
            return int(item.get("sigma", data.get("leaf_sigma", 0)))
    raise AssertionError("Выбранный leaf отсутствует в JSON.")


def verify_forged_path(
    prefix_blocks: List[str],
    linking_message: str,
    target_leaf: str,
    suffix_blocks: List[str],
    data: dict,
) -> str:
    """Проверяет путь до корня по состоянию (h_n, Σ_s, N)."""
    truncate_bits = int(data["trunc_bits"])
    sigma_bits = int(data.get("sigma_bits", 0))
    rounds = int(data.get("rounds", 12))
    link_N = int(data["link_N"])
    first_level_N = int(data["first_level_N"])
    root_state = get_diamond_root_state(data)
    model = ReducedGostModel(truncate_bits, rounds)

    state, N = process_prefix_state(prefix_blocks, truncate_bits, rounds, sigma_bits)
    if N != link_N:
        raise AssertionError(f"N после префикса равен {N}, а JSON ожидает {link_N}.")

    state = model.transition_pair(linking_message, state, N, sigma_bits)
    expected_leaf = DiamondState(target_leaf, _leaf_sigma(data, target_leaf))
    if state != expected_leaf:
        raise AssertionError(
            f"Linking-блок дал {(state.h, state.sigma)}, ожидается {(expected_leaf.h, expected_leaf.sigma)}."
        )

    current = state
    if len(suffix_blocks) != len(data["structure"]):
        raise AssertionError("Длина suffix не совпадает с глубиной diamond.")
    for level_index, block in enumerate(suffix_blocks):
        level = data["structure"][level_index]
        selected = None
        for node in level:
            left_sigma = int(node.get("sigma_left", 0))
            right_sigma = int(node.get("sigma_right", 0))
            if node["h_left"] == current.h and left_sigma == current.sigma and node["m_link_left"] == block:
                selected = node
                break
            if node["h_right"] == current.h and right_sigma == current.sigma and node["m_link_right"] == block:
                selected = node
                break
        if selected is None:
            raise AssertionError(f"Suffix block не соответствует фактическому ребру уровня {level_index + 1}.")
        level_N = first_level_N + 512 * level_index
        current = model.transition_pair(block, current, level_N, sigma_bits)
        expected_parent = DiamondState(
            selected["h_common"], int(selected.get("sigma_common", 0))
        )
        if current != expected_parent:
            raise AssertionError(
                f"Replay уровня {level_index + 1}: получено {(current.h, current.sigma)}, "
                f"ожидается {(expected_parent.h, expected_parent.sigma)}."
            )

    if current != root_state:
        raise AssertionError(
            f"Путь закончился в {(current.h, current.sigma)}, корень {(root_state.h, root_state.sigma)}."
        )
    return current.h


def _finish_attack(data, description, event_result, prefix_blocks, prefix_pair,
                   linking_block, leaf_state, root_state, *, leaves, independent_replay=False,
                   **metrics):
    """Восстанавливает и проверяет общий путь перед созданием результата любого метода."""
    suffix = reconstruct_suffix(leaves, data['structure'], leaf_state)
    verified = verify_forged_path(prefix_blocks, linking_block, leaf_state, suffix, data)
    if independent_replay:
        metrics['link_independent_verification_hash_evaluations'] = (
            2 * sum(len(level) for level in data['structure'])
            + 2 * len(prefix_blocks) + 2 + len(suffix))
    return AttackResult(
        description=description, event_result=event_result, prefix_blocks=prefix_blocks,
        prefix_state=prefix_pair.h, linking_block=linking_block, leaf_state=leaf_state,
        suffix_blocks=suffix, root=root_state.h, verified_root=verified,
        forged_hex=''.join(prefix_blocks) + linking_block + ''.join(suffix),
        sigma_bits=int(data.get('sigma_bits', 0)), prefix_sigma=prefix_pair.sigma,
        leaf_sigma=int(data.get('leaf_sigma', 0)), root_sigma=root_state.sigma,
        verified_sigma=root_state.sigma,
        build_method=search_method(data.get('builder', 'blackburn')).value, **metrics)


def execute_attack(
    data: dict,
    description: str,
    event_result: str,
    search: SearchAlgorithms,
    trials_limit: int = 2_000_000,
) -> AttackResult:
    validate_diamond_data(data)
    truncate_bits = int(data["trunc_bits"])
    sigma_bits = int(data.get("sigma_bits", 0))
    rounds = int(data.get("rounds", 12))
    prefix_blocks_count = int(data["prefix_blocks"])
    leaves = [x["state"] for x in data["leaves"]]
    root_state = get_diamond_root_state(data)
    leaf_sigma = int(data.get("leaf_sigma", 0))

    prefix_blocks = encode_text_prefix_blocks(description + event_result, prefix_blocks_count)
    prefix_pair, actual_N = process_prefix_state(prefix_blocks, truncate_bits, rounds, sigma_bits)
    if actual_N != int(data["link_N"]):
        raise RuntimeError("Длина префикса не соответствует N, с которым построен diamond.")

    stats: Dict[str, int] = {}
    linking_message, leaf_state = find_linking_message(
        search, prefix_pair.h, leaves, actual_N, truncate_bits,
        trials_limit=trials_limit, rounds=rounds, stats=stats,
        sigma_bits=sigma_bits, prefix_sigma=prefix_pair.sigma, leaf_sigma=leaf_sigma,
    )
    return _finish_attack(data, description, event_result, prefix_blocks, prefix_pair,
                          linking_message, leaf_state, root_state, leaves=leaves,
                          link_queries=stats.get('link_queries', 0),
                          link_method=SearchMethod.CLASSICAL.value)


class QuantumLinkFailure(RuntimeError):
    """Сообщает о неудаче вероятностных попыток поиска связующего блока алгоритмом 5."""


@dataclass(frozen=True)
class Algorithm5LinkParameters:
    state_bits: int
    diamond_bits: int
    target_count: int
    search_messages: int


def algorithm5_link_parameters(
    state_bits: int,
    diamond_bits: int,
) -> Algorithm5LinkParameters:
    """Вычисляет S_link = 2^(n−k) для поиска связующего блока к 2^k листьям."""
    validate_truncate_bits(state_bits)
    if diamond_bits < 1 or diamond_bits > state_bits:
        raise ValueError("diamond_bits должен лежать в диапазоне 1..state_bits.")
    return Algorithm5LinkParameters(
        state_bits=state_bits,
        diamond_bits=diamond_bits,
        target_count=1 << diamond_bits,
        search_messages=1 << (state_bits - diamond_bits),
    )


def _random_message_space(
    count: int,
    rng: random.Random,
    *, sigma_bits: int = 0, current_sigma: int = 0, target_sigma: int = 0,
) -> list[str]:
    messages: list[str] = []
    used: set[str] = set()
    while len(messages) < count:
        block = constrained_random_block(current_sigma, target_sigma, sigma_bits, rng)
        if block not in used:
            used.add(block)
            messages.append(block)
    return messages


def find_linking_message_quantum(
    prefix_state: str,
    target_states: Sequence[str],
    N: int,
    truncate_bits: int,
    *,
    rounds: int = 12,
    trials_limit: int = 2_000_000,
    max_attempts: int = 12,
    max_statevector_size: Optional[int] = None,
    rng: Optional[random.Random] = None,
    stats: Optional[Dict[str, Any]] = None,
    use_cpp: Optional[bool] = None,
    sigma_bits: int = 0,
    prefix_sigma: int = 0,
    leaf_sigma: int = 0,
    threads: int = 0,
    method: str = "grover_fixed",
    bbht_options: BBHTOptions | None = None,
) -> tuple[str, str]:
    """Ищет связующий блок алгоритмом 5 через C++ или резервное моделирование Гровера на Python."""
    selected = search_method(method)
    validate_truncate_bits(truncate_bits)
    validate_sigma_bits(sigma_bits)
    targets = list(dict.fromkeys(target_states))
    target_count = len(targets)
    if target_count < 2 or target_count & (target_count - 1):
        raise ValueError("Число различных целевых листьев должно быть степенью двойки >= 2.")
    diamond_bits = int(math.log2(target_count))
    params = algorithm5_link_parameters(truncate_bits, diamond_bits)
    if (
        max_statevector_size is not None
        and params.search_messages > max_statevector_size
    ):
        raise ValueError(
            f"Algorithm 5 требует state-vector S_link={params.search_messages}, "
            f"лимит симулятора={max_statevector_size}."
        )
    if trials_limit < params.search_messages:
        raise ValueError(
            f"Лимит симулятора должен быть не меньше S_link={params.search_messages}."
        )
    if max_attempts < 1:
        raise ValueError("max_attempts должен быть положительным.")

    generator = rng or random.Random()
    model = ReducedGostModel(truncate_bits, rounds)
    target_set = set(targets)
    cpp_enabled = cpp_core_available() if use_cpp is None else use_cpp
    if selected is SearchMethod.GROVER_BBHT and not cpp_enabled:
        raise RuntimeError("BBHT требует собранное C++-ядро.")
    phase_queries = 0
    failed_attempts = 0
    search_attempts = 0
    iterations_total = 0
    total_evaluations = 0
    total_queries = 0
    total_marked = 0
    vector_elements = 0
    vector_seconds = 0.0
    norm_max = 0.0
    probability_sum = 0.0
    verification_evaluations = 0
    iterations = optimal_grover_iterations(params.search_messages, 1)
    other_bytes = 262144 + len(targets) * 256
    if cpp_enabled:
        check_native_resources(params.search_messages, iterations, other_bytes,
            dense_max_states=(bbht_options or BBHTOptions()).dense_max_states if selected is SearchMethod.GROVER_BBHT else DENSE_MAX_STATES)
    else:
        check_resources(params.search_messages, iterations, other_bytes + params.search_messages * 256, python=True)

    for attempt in range(1, max_attempts + 1):
        check_deadline()
        if total_evaluations + params.search_messages + 1 > trials_limit:
            raise QuantumLinkFailure(
                "Algorithm 5 исчерпал лимит классических вычислений симулятора: "
                f"{total_evaluations}/{trials_limit}."
            )

        if cpp_enabled:
            effective_options = bbht_options or BBHTOptions()
            if selected is SearchMethod.GROVER_BBHT:
                effective_options = replace(effective_options, max_attempts=min(effective_options.max_attempts,
                    trials_limit - total_evaluations - params.search_messages))
            result = cpp_quantum_link(
                prefix_state,
                targets,
                params.search_messages,
                N,
                truncate_bits,
                rounds,
                generator.getrandbits(64),
                sigma_bits=sigma_bits,
                current_sigma=prefix_sigma,
                target_sigma=leaf_sigma,
                threads=threads,
                **({"method": selected, "bbht_options": effective_options} if selected is SearchMethod.GROVER_BBHT else {}),
            )
            if selected is SearchMethod.GROVER_BBHT:
                phase_queries += result.phase_oracle_queries
                failed_attempts += result.failed_attempts
                search_attempts += result.search_attempts
                iterations_total += result.statevector_iterations
            block = result.block
            target = result.target_state
            queries = result.oracle_queries
            evaluations = result.simulator_evaluations
            marked_count = result.marked_count
            success_probability = result.success_probability
            norm_error = result.norm_error
            elements = result.statevector_elements_processed
            seconds = result.statevector_seconds
            verified_evaluations = result.verification_evaluations
        else:
            messages = _random_message_space(
                params.search_messages, generator, sigma_bits=sigma_bits,
                current_sigma=prefix_sigma, target_sigma=leaf_sigma,
            )
            outputs = []
            for index, block in enumerate(messages):
                if index % 256 == 0:
                    check_deadline()
                outputs.append(model.transition(block, prefix_state, N))
            marked = [index for index, output in enumerate(outputs) if output in target_set]
            grover: GroverResult = simulate_grover_from_marked(
                params.search_messages,
                marked,
                iterations=optimal_grover_iterations(params.search_messages, 1),
                rng=generator,
                max_statevector_size=max_statevector_size,
            )
            block = messages[grover.measured_index] if grover.is_marked else None
            target = outputs[grover.measured_index] if grover.is_marked else None
            queries = grover.quantum_queries + 1
            if model.transition(messages[grover.measured_index], prefix_state, N) != outputs[grover.measured_index]:
                raise AssertionError('Измеренный переход не воспроизводится.')
            evaluations = params.search_messages + 1
            elements = grover.statevector_elements_processed
            seconds = grover.statevector_seconds
            verified_evaluations = 1
            marked_count = grover.marked_count
            success_probability = grover.success_probability
            norm_error = grover.norm_error

        total_evaluations += evaluations
        total_queries += queries
        total_marked += marked_count
        vector_elements += elements
        vector_seconds += seconds
        norm_max = max(norm_max, norm_error)
        probability_sum += success_probability * (result.search_attempts if cpp_enabled and selected is SearchMethod.GROVER_BBHT else 1)
        verification_evaluations += verified_evaluations
        if norm_error > 1e-9:
            raise AssertionError(f"Нарушена нормировка Grover state-vector: {norm_error}.")

        if stats is not None:
            if cpp_enabled:
                stats['quantum_link_amplitude_backend'] = result.amplitude_backend
            stats['search_protocol'] = result.search_protocol if cpp_enabled else SEARCH_PROTOCOL
            diagnostics = result.search_diagnostics if cpp_enabled else (dict(attempt_policy='fixed_single',
                search_messages=params.search_messages, growth=1.2, effective_max_attempts=1,
                attempts=1, failures=int(block is None), stop_reason='found' if block is not None else 'unmarked_measurement'),)
            stats.setdefault('quantum_link_search_diagnostics', []).extend(dict(item, batch_attempt=attempt) for item in diagnostics)
            stats['quantum_link_phase_oracle_queries'] = iterations_total if selected is SearchMethod.GROVER_BBHT else attempt * iterations
            stats['quantum_link_verification_queries'] = verification_evaluations
            stats['quantum_link_failed_attempts'] = failed_attempts if selected is SearchMethod.GROVER_BBHT else sum(item['failures'] for item in stats['quantum_link_search_diagnostics'])
            stats.update(quantum_link_statevector_elements_processed=vector_elements,
                         quantum_link_statevector_seconds=vector_seconds, quantum_link_statevector_norm_error_max=norm_max,
                         quantum_link_success_probability_sum=probability_sum,
                         quantum_link_verification_hash_evaluations=verification_evaluations)
            stats["quantum_link_oracle_queries"] = total_queries
            stats["quantum_link_grover_iterations"] = iterations_total if selected is SearchMethod.GROVER_BBHT else attempt * optimal_grover_iterations(params.search_messages, 1)
            if selected is SearchMethod.GROVER_BBHT:
                stats.update(quantum_link_phase_oracle_queries=phase_queries,
                             quantum_link_verification_queries=verification_evaluations,
                             quantum_link_failed_attempts=failed_attempts,
                             quantum_link_amplitude_backend=result.amplitude_backend,
                             quantum_link_bbht_attempts=search_attempts)
            stats["quantum_link_simulator_hash_evaluations"] = total_evaluations
            stats["quantum_link_marked_states"] = total_marked
            stats["quantum_link_attempts"] = attempt
            stats["quantum_link_success_probability"] = success_probability
            stats["quantum_link_search_messages"] = params.search_messages
            backend_key = (
                "quantum_link_cpp_calls" if cpp_enabled else "quantum_link_python_calls"
            )
            stats[backend_key] = stats.get(backend_key, 0) + 1

        if block is None or target is None:
            continue
        if target not in target_set:
            raise AssertionError("Grover вернул состояние вне множества листьев.")
        if model.transition(block, prefix_state, N) != target:
            raise AssertionError("Linking-блок Algorithm 5 не воспроизводится.")
        if update_sigma_reduced(prefix_sigma, block, sigma_bits) != leaf_sigma:
            raise AssertionError("Quantum linking-блок нарушает sigma constraint.")
        return block, target

    raise QuantumLinkFailure(
        f"Algorithm 5 не нашёл linking-блок за {max_attempts} попыток "
        f"по S_link={params.search_messages} сообщений."
    )


def execute_algorithm5(
    data: dict,
    description: str,
    event_result: str,
    *,
    trials_limit: int = 2_000_000,
    seed: Optional[int] = None,
    use_cpp: Optional[bool] = None,
    threads: int = 0,
    method: str = "grover_fixed",
    bbht_options: BBHTOptions | None = None,
) -> AttackResult:
    """Выполняет квантовую herding-атаку алгоритмом 5 для модели части хэш-кода."""
    effective_seed = random.SystemRandom().getrandbits(64) if seed is None else seed
    validate_diamond_data(data)
    truncate_bits = int(data["trunc_bits"])
    rounds = int(data.get("rounds", 12))
    prefix_blocks_count = int(data["prefix_blocks"])
    leaves = [item["state"] for item in data["leaves"]]
    sigma_bits = int(data.get("sigma_bits", 0))
    leaf_sigma = int(data.get("leaf_sigma", 0))
    root = get_diamond_root(data)
    root_sigma = int(data.get("sigma_schedule", [0])[-1])

    prefix_blocks = encode_text_prefix_blocks(
        description + event_result, prefix_blocks_count
    )
    prefix_pair, actual_N = process_prefix_state(
        prefix_blocks, truncate_bits, rounds, sigma_bits
    )
    if actual_N != int(data["link_N"]):
        raise RuntimeError("Длина префикса не соответствует N quantum diamond.")

    stats: Dict[str, Any] = {}
    try:
        linking_block, leaf_state = find_linking_message_quantum(
            prefix_pair.h,
            leaves,
            actual_N,
            truncate_bits,
            rounds=rounds,
            trials_limit=trials_limit,
            rng=random.Random(effective_seed),
            stats=stats,
            use_cpp=use_cpp,
            sigma_bits=sigma_bits,
            prefix_sigma=prefix_pair.sigma,
            leaf_sigma=leaf_sigma,
            threads=threads if threads else (1 if seed is not None else 0),
            method=method, bbht_options=bbht_options,
        )
    except Exception as exc:
        exc.experiment_stats = stats.copy()
        raise
    metrics = {}
    for convert, fields in (
        (int, ('simulator_hash_evaluations', 'grover_iterations',
               'statevector_elements_processed', 'search_messages',
               'verification_hash_evaluations')),
        (float, ('success_probability', 'statevector_norm_error_max',
                 'statevector_seconds', 'success_probability_sum')),
    ):
        metrics.update(('link_' + key, convert(stats.get('quantum_link_' + key, 0)))
                       for key in fields)
    return _finish_attack(
        data, description, event_result, prefix_blocks, prefix_pair,
        linking_block, leaf_state, DiamondState(root, root_sigma), leaves=leaves,
        independent_replay=True,
        link_queries=int(stats.get("quantum_link_oracle_queries", 0)),
        link_backend=(
            "quantum-bbht-cpp" if search_method(method) is SearchMethod.GROVER_BBHT else "quantum-cpp" if stats.get("quantum_link_cpp_calls", 0)
            else "quantum-python"
        ),
        link_attempts=int(stats.get("quantum_link_bbht_attempts", stats.get("quantum_link_attempts", 0))),
        link_marked_count=int(stats.get("quantum_link_marked_states", 0)),
        link_seed=effective_seed,
        link_method=search_method(method).value,
        link_phase_oracle_queries=stats.get('quantum_link_phase_oracle_queries'),
        link_verification_queries=stats.get('quantum_link_verification_queries'),
        link_failed_attempts=stats.get('quantum_link_failed_attempts', 0),
        amplitude_backend=stats.get('quantum_link_amplitude_backend', 'dense'),
        search_protocol=stats.get('search_protocol', 'legacy-v0'),
        attempt_policy='bbht_auto' if search_method(method) is SearchMethod.GROVER_BBHT else 'fixed_single',
        search_diagnostics=stats.get('quantum_link_search_diagnostics', []),
        bbht_options=asdict(bbht_options or BBHTOptions()) if search_method(method) is SearchMethod.GROVER_BBHT else None,
        **metrics,
    )
