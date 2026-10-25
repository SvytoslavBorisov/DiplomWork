from __future__ import annotations

import re
import json
import hashlib
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from algorithms.search_methods import SearchMethod, search_method
from algorithms.statevector_limits import MODEL_REVISION, MODEL_LABEL

QUANTUM_BUILDER = "quantum_algorithm_2_simulator"
METHOD_LABELS = {method.storage_id: method.label for method in SearchMethod}


@dataclass(frozen=True)
class GraphNode:
    node_id: str
    state: str
    level: int
    index: int
    kind: str
    sigma: int | None = None


@dataclass(frozen=True)
class GraphEdge:
    source: str
    target: str
    block: str
    level: int
    counter_N: int | None = None


@dataclass(frozen=True)
class DiamondGraph:
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
    depth: int
    sigma_bits: int = 0


@dataclass(frozen=True)
class QuantumLayerRecord:
    layer_bits: int
    vertex_count: int
    table_messages_L: int | None
    search_messages_S: int | None
    graph_edges: int | None


@dataclass(frozen=True)
class ExperimentRecord:
    method: str
    n: int
    k: int
    prefix_blocks: int
    rounds: int
    elapsed_seconds: float | None
    status: str
    collision_queries: int | None = None
    blackburn_transition_queries: int | None = None
    blackburn_matching_attempts: int | None = None
    blackburn_graph_edges: int | None = None
    quantum_oracle_queries: int | None = None
    quantum_simulator_hash_evaluations: int | None = None
    quantum_qram_entries: int | None = None
    quantum_grover_successes: int | None = None
    quantum_layer_attempts: int | None = None
    sigma_bits: int = 0
    model: str = ""
    link_N: int | None = None
    first_level_N: int | None = None
    sigma_schedule: tuple[int, ...] = ()
    compression_calls: int | None = None
    generated_candidates: int | None = None
    oracle_queries: int | None = None
    grover_iterations: int | None = None
    naive_collision_bits: int | None = None
    sigma_aware_collision_bits: int | None = None
    naive_linking_exponent: int | None = None
    sigma_aware_linking_exponent: int | None = None
    quantum_layers: tuple[QuantumLayerRecord, ...] = ()
    experiment_type: str = "diamond"
    attack_diamond_digest: str = ""
    attack_prefix_state: str = ""
    attack_message_digest: str = ""
    attack_trials_limit: int | None = None
    quantum_qram_total_entries: int | None = None
    quantum_qram_peak_entries: int | None = None
    measurement_version: str = "legacy-v0"
    link_attempts: int | None = None
    link_marked_count: int | None = None
    link_success_probability: float | None = None
    statevector_elements_processed: int | None = None
    statevector_iterations: int | None = None
    statevector_norm_error_max: float | None = None
    statevector_seconds: float | None = None
    grover_attempts: int | None = None
    marked_elements: int | None = None
    success_probability_sum: float | None = None
    matching_successes: int | None = None
    verification_hash_evaluations: int | None = None
    independent_verification_hash_evaluations: int | None = None
    search_messages: int | None = None
    build_method: str = ""
    link_method: str = ""
    phase_oracle_queries: int | None = None
    verification_queries: int | None = None
    failed_attempts: int | None = None
    amplitude_backend: str = "unknown"
    parameter_strategy: str = "theoretical"
    target_probability: float | None = None
    search_configuration: str = ""
    search_protocol: str = "legacy-v0"

    @property
    def t(self) -> int:
        """Сохраняет чтение старого обозначения размера части хэш-кода."""
        return self.n

    def to_storage_dict(self) -> dict:
        """Сохраняет поле t прежнего формата базы экспериментов."""
        from dataclasses import asdict
        return {"t" if key == "n" else key: value for key, value in asdict(self).items()}

    @property
    def is_quantum(self) -> bool:
        return search_method(self.method).is_quantum

    @property
    def algorithmic_queries(self) -> int | None:
        if self.is_quantum:
            return self.quantum_oracle_queries
        return self.blackburn_transition_queries if self.blackburn_transition_queries is not None else self.collision_queries

    @property
    def method_label(self) -> str:
        return search_method(self.method).label

    @property
    def stage_label(self) -> str:
        return {'herding':'Поиск связывающего блока','full':'Полная атака'}.get(self.experiment_type,'Построение алмаза')


def _optional_int(values: dict[str, Any], key: str) -> int | None:
    value = values.get(key)
    return None if value is None else int(value)


def parse_quantum_layers(stats: dict[str, Any]) -> tuple[QuantumLayerRecord, ...]:
    bits_found: set[int] = set()
    for key in stats:
        match = re.fullmatch(r"quantum_layer_(\d+)_(?:L|S|edges)", key)
        if match:
            bits_found.add(int(match.group(1)))
    return tuple(
        QuantumLayerRecord(
            bits,
            2 ** bits,
            _optional_int(stats, f"quantum_layer_{bits}_L"),
            _optional_int(stats, f"quantum_layer_{bits}_S"),
            _optional_int(stats, f"quantum_layer_{bits}_edges"),
        )
        for bits in sorted(bits_found, reverse=True)
    )


def record_from_data(data: dict[str, Any], elapsed_seconds: float | None, status: str) -> ExperimentRecord:
    stats = data.get("stats", {})
    theory = data.get("theory", {})
    return ExperimentRecord(
        search_protocol=str(data.get('search_protocol', 'legacy-v0')),
        build_method=search_method(data.get("builder", "blackburn")).value,
        search_configuration=json.dumps(data.get("bbht_options", {}), sort_keys=True) if data.get("bbht_options") else "",
        phase_oracle_queries=_optional_int(stats, "quantum_phase_oracle_queries"),
        verification_queries=_optional_int(stats, "quantum_verification_queries"),
        failed_attempts=_optional_int(stats, "quantum_failed_attempts"),
        amplitude_backend=str(data.get("amplitude_backend", "dense" if data.get("measurement_version") == MODEL_REVISION else "unknown")),
        parameter_strategy=str(data.get("parameter_strategy", "theoretical")),
        target_probability=data.get("target_candidate_probability"),
        method=str(data.get("builder", "blackburn")), n=int(data["trunc_bits"]), k=int(data["depth"]),
        prefix_blocks=int(data["prefix_blocks"]), rounds=int(data.get("rounds", 12)),
        elapsed_seconds=elapsed_seconds, status=status,
        collision_queries=_optional_int(stats, "collision_queries"),
        blackburn_transition_queries=_optional_int(stats, "blackburn_transition_queries"),
        blackburn_matching_attempts=_optional_int(stats, "blackburn_matching_attempts"),
        blackburn_graph_edges=_optional_int(stats, "blackburn_graph_edges"),
        quantum_oracle_queries=_optional_int(stats, "quantum_oracle_queries"),
        quantum_simulator_hash_evaluations=_optional_int(stats, "quantum_simulator_hash_evaluations"),
        quantum_qram_entries=_optional_int(stats, "quantum_qram_entries"),
        quantum_qram_total_entries=_optional_int(stats, "quantum_qram_total_entries") or _optional_int(stats, "quantum_qram_entries"),
        quantum_qram_peak_entries=_optional_int(stats, "quantum_qram_peak_entries"),
        measurement_version=str(data.get("measurement_version", "legacy-v0")),
        quantum_grover_successes=_optional_int(stats, "quantum_grover_successes"),
        quantum_layer_attempts=_optional_int(stats, "quantum_layer_attempts"),
        sigma_bits=int(data.get("sigma_bits", 0)),
        model=str(data.get("model", "")),
        link_N=_optional_int(data, "link_N"),
        first_level_N=_optional_int(data, "first_level_N"),
        sigma_schedule=tuple(map(int, data.get("sigma_schedule", ()))),
        compression_calls=_optional_int(stats, "compression_calls"),
        generated_candidates=_optional_int(stats, "generated_candidates"),
        oracle_queries=_optional_int(stats, "oracle_queries"),
        grover_iterations=_optional_int(stats, "grover_iterations"),
        naive_collision_bits=_optional_int(theory, "naive_collision_bits"),
        sigma_aware_collision_bits=_optional_int(theory, "sigma_aware_collision_bits"),
        naive_linking_exponent=_optional_int(theory, "naive_linking_exponent"),
        sigma_aware_linking_exponent=_optional_int(theory, "sigma_aware_linking_exponent"),
        quantum_layers=parse_quantum_layers(stats),
        statevector_elements_processed=_optional_int(stats, 'quantum_statevector_elements_processed'),
        statevector_iterations=_optional_int(stats, 'quantum_statevector_iterations'),
        statevector_norm_error_max=stats.get('quantum_statevector_norm_error_max'),
        statevector_seconds=stats.get('quantum_statevector_seconds'),
        grover_attempts=_optional_int(stats, 'quantum_grover_attempts'),
        marked_elements=_optional_int(stats, 'quantum_marked_elements'),
        success_probability_sum=stats.get('quantum_success_probability_sum'),
        matching_successes=_optional_int(stats, 'quantum_matching_successes'),
        verification_hash_evaluations=_optional_int(stats, 'quantum_verification_hash_evaluations'),
        independent_verification_hash_evaluations=_optional_int(stats, 'quantum_independent_verification_hash_evaluations'),
    )


def record_from_attack(data: dict[str, Any], result: Any, elapsed_seconds: float,
                       diamond_digest: str, trials_limit: int | None = None) -> ExperimentRecord:
    """Сохраняет измеренные счётчики связывания и полное время атаки."""
    from .campaign_runner import MODEL_REVISION as measurement_revision
    measurement_revision=getattr(result,"measurement_version",None) or (measurement_revision if measurement_revision==MODEL_REVISION else str(data.get("measurement_version","legacy-v0")))
    selected = search_method(getattr(result, "link_method", "") or result.link_backend)
    quantum = selected.is_quantum
    return ExperimentRecord(
        method=selected.storage_id,
        search_protocol=getattr(result, 'search_protocol', 'legacy-v0'),
        build_method=search_method(data.get("builder", "blackburn")).value,
        link_method=selected.value,
        search_configuration=json.dumps(getattr(result, "bbht_options", None), sort_keys=True) if getattr(result, "bbht_options", None) else "",
        phase_oracle_queries=getattr(result, "link_phase_oracle_queries", None),
        verification_queries=getattr(result, "link_verification_queries", None),
        failed_attempts=getattr(result, "link_failed_attempts", None),
        amplitude_backend=getattr(result, "amplitude_backend", "dense"),
        n=int(data["trunc_bits"]), k=int(data["depth"]),
        prefix_blocks=int(data["prefix_blocks"]), rounds=int(data.get("rounds", 12)),
        elapsed_seconds=elapsed_seconds,
        status="Завершено" if result.verified_root == result.root else "Ошибка",
        collision_queries=None if quantum else int(result.link_queries),
        quantum_oracle_queries=int(result.link_queries) if quantum else None,
        quantum_simulator_hash_evaluations=(int(result.link_simulator_hash_evaluations) if quantum else None),
        sigma_bits=int(data.get("sigma_bits", 0)), model=str(data.get("model", "")),
        link_N=_optional_int(data, "link_N"), first_level_N=_optional_int(data, "first_level_N"),
        sigma_schedule=tuple(map(int, data.get("sigma_schedule", ()))),
        experiment_type="herding", attack_diamond_digest=diamond_digest,
        attack_prefix_state=str(result.prefix_state),
        attack_message_digest=hashlib.sha256(
            (str(result.description) + str(result.event_result)).encode("utf-8")
        ).hexdigest(),
        attack_trials_limit=trials_limit,
        measurement_version=measurement_revision,
        link_attempts=getattr(result, "link_attempts", None),
        link_marked_count=getattr(result, "link_marked_count", None),
        link_success_probability=getattr(result, "link_success_probability", None),
        grover_iterations=getattr(result, "link_grover_iterations", None) if quantum else None,
        statevector_elements_processed=getattr(result, 'link_statevector_elements_processed', None) if quantum else None,
        statevector_iterations=getattr(result, 'link_grover_iterations', None) if quantum else None,
        statevector_norm_error_max=getattr(result, 'link_statevector_norm_error_max', None) if quantum else None,
        statevector_seconds=getattr(result, 'link_statevector_seconds', None) if quantum else None,
        success_probability_sum=getattr(result, 'link_success_probability_sum', None) if quantum else None,
        grover_attempts=getattr(result, 'link_attempts', None) if quantum else None,
        quantum_grover_successes=1 if quantum else None,
        marked_elements=getattr(result, 'link_marked_count', None) if quantum else None,
        verification_hash_evaluations=getattr(result, 'link_verification_hash_evaluations', None) if quantum else None,
        independent_verification_hash_evaluations=getattr(result, 'link_independent_verification_hash_evaluations', None) if quantum else None,
        search_messages=getattr(result, 'link_search_messages', None) if quantum else None,
    )


def comparison_key(record: ExperimentRecord, omit_axis: str | None = None) -> tuple:
    """Отделяет несовместимые модели, этапы, методики и параметры поиска."""
    return tuple(value for name, value in (
        ("n", record.n), ("k", record.k), ("prefix_blocks", record.prefix_blocks),
        ("N", record.link_N if record.experiment_type == "herding" else record.first_level_N),
        ("s", record.sigma_bits), ("rounds", record.rounds), ("model", record.model),
        ("link_N", record.link_N), ("first_level_N", record.first_level_N),
        ("sigma_schedule", record.sigma_schedule), ("stage", record.experiment_type),
        ("attack_diamond", record.attack_diamond_digest), ("attack_prefix", record.attack_prefix_state),
        ("attack_message", record.attack_message_digest), ("attack_limit", record.attack_trials_limit),
        ("measurement_version", record.measurement_version),
        ("search_protocol", record.search_protocol),
        ("amplitude_backend", record.amplitude_backend),
        ("parameter_strategy", record.parameter_strategy),
        ("target_probability", record.target_probability if record.parameter_strategy != "theoretical" else None),
    ) if name != omit_axis)


def comparable_pairs(records: Iterable[ExperimentRecord]) -> list[tuple[ExperimentRecord, ExperimentRecord]]:
    """Возвращает пары разных методов без смешения BBHT и фиксированного Гровера."""
    from itertools import combinations
    groups = defaultdict(dict)
    for record in records:
        if record.status in ("Завершено", "Загружено"):
            groups[comparison_key(record)][search_method(record.method)] = record
    return [pair for group in groups.values() for pair in combinations(group.values(), 2)]


def matched_algorithmic_pair(records: Iterable[ExperimentRecord]) -> tuple[ExperimentRecord, ExperimentRecord] | None:
    for a, b in reversed(comparable_pairs(records)):
        if a.algorithmic_queries is not None and b.algorithmic_queries is not None and a.is_quantum != b.is_quantum:
            return (b, a) if a.is_quantum else (a, b)
    return None


def algorithmic_ratio(classical: ExperimentRecord, quantum: ExperimentRecord) -> float | None:
    if classical.algorithmic_queries is None or not quantum.algorithmic_queries:
        return None
    return classical.algorithmic_queries / quantum.algorithmic_queries


def series_by_method(
    records: Iterable[ExperimentRecord], x_value: Callable[[ExperimentRecord], int],
    y_value: Callable[[ExperimentRecord], float | int | None],
) -> dict[str, list[tuple[int, float]]]:
    series: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for record in records:
        value = y_value(record)
        if value is not None and value > 0:
            series[record.method_label].append((x_value(record), float(value)))
    return {name: sorted(points) for name, points in series.items()}


def build_diamond_graph(data: dict[str, Any]) -> DiamondGraph:
    """Преобразует существующий JSON в UI-граф, не вычисляя связи заново."""
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    def sigma_value(values, key, level):
        if key in values:
            return int(values[key])
        schedule = data.get("sigma_schedule", [])
        if level < len(schedule):
            return int(schedule[level])
        return int(data["leaf_sigma"]) if level == 0 and "leaf_sigma" in data else None
    by_state: dict[str, deque[str]] = defaultdict(deque)
    for index, leaf in enumerate(data["leaves"]):
        state = str(leaf["state"])
        node_id = f"leaf:{index}"
        nodes.append(GraphNode(node_id, state, 0, index, "leaf",
                               sigma_value(leaf, "sigma", 0)))
        by_state[state].append(node_id)
    structure = data.get("structure", [])
    for level_index, level in enumerate(structure, start=1):
        for index, pair in enumerate(level):
            parent_id = f"level:{level_index}:{index}"
            common = str(pair["h_common"])
            nodes.append(GraphNode(parent_id, common, level_index, index, "root" if level_index == int(data.get("depth", len(structure))) else "state",
                                   sigma_value(pair, "sigma_common", level_index)))
            try:
                left_id = by_state[str(pair["h_left"])].popleft()
                right_id = by_state[str(pair["h_right"])].popleft()
            except IndexError as exc:
                raise ValueError("JSON содержит ребро без исходной вершины.") from exc
            first_N = data.get("first_level_N")
            counter_N = int(first_N) + 512 * (level_index - 1) if first_N is not None else None
            edges.append(GraphEdge(left_id, parent_id, str(pair["m_link_left"]), level_index, counter_N))
            edges.append(GraphEdge(right_id, parent_id, str(pair["m_link_right"]), level_index, counter_N))
            by_state[common].append(parent_id)
    return DiamondGraph(tuple(nodes), tuple(edges), int(data.get("depth", len(structure))), int(data.get("sigma_bits", 0)))


def query_count(data: dict[str, Any]) -> int:
    """Возвращает старый счётчик классических поисковых вычислений."""
    return int(data.get("stats", {}).get("collision_queries", 0))


def path_edge_ids(graph: DiamondGraph, leaf_state: str) -> set[tuple[str, str]]:
    leaf = next((node for node in graph.nodes if node.kind == "leaf" and node.state == leaf_state), None)
    if leaf is None:
        return set()
    outgoing = {edge.source: edge.target for edge in graph.edges}
    result: set[tuple[str, str]] = set()
    current = leaf.node_id
    while current in outgoing:
        target = outgoing[current]
        result.add((current, target))
        current = target
    return result


def related_paths(graph: DiamondGraph, node_id: str) -> tuple[set[str], set[tuple[str, str]], set[tuple[str, str]]]:
    """Находит предшественников и пути к корню по фактическим рёбрам UI-графа."""
    incoming = defaultdict(list)
    outgoing = defaultdict(list)
    for edge in graph.edges:
        incoming[edge.target].append(edge.source)
        outgoing[edge.source].append(edge.target)
    nodes = {node_id}
    before = set()
    after = set()
    for adjacency, edges in ((incoming, before), (outgoing, after)):
        seen = {node_id}
        pending = [node_id]
        while pending:
            current = pending.pop()
            for other in adjacency[current]:
                edges.add((other, current) if adjacency is incoming else (current, other))
                nodes.add(other)
                if other not in seen:
                    seen.add(other)
                    pending.append(other)
    return nodes, before, after
