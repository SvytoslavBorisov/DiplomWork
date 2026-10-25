from __future__ import annotations

import json
import math
import os
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Callable

from CppCore import cpp_core_available
from algorithms.search_methods import BBHTOptions, SearchMethod, search_method, SEARCH_PROTOCOL
from algorithms.statevector_limits import MODEL_REVISION, bounded_experiment, check_layer_resources
from algorithms.diamond import (
    build_diamond_structure,
    diamond_to_json_dict,
    get_diamond_root,
    validate_diamond_data,
)
from algorithms.herding_attack import AttackResult, execute_attack, algorithm5_link_parameters, execute_algorithm5
from algorithms.quantum_diamond import algorithm2_parameters, build_diamond_structure_quantum, select_layer_parameters
from algorithms.registry import create_search_algorithms
from algorithms.classical import ClassicalSearchAlgorithms


LogCallback = Callable[[str], None]


@dataclass(frozen=True)
class BuildRequest:
    method: str
    depth: int
    truncate_bits: int
    prefix_blocks: int
    rounds: int
    trials_limit: int
    output_directory: Path
    sigma_bits: int = 0
    sigma_seed: int = 0
    seed: int | None = None
    threads: int = 0
    use_cpp: bool | None = None
    parameter_strategy: str = "theoretical"
    target_probability: float = 0.95
    bbht_options: BBHTOptions | None = None


@dataclass(frozen=True)
class BuildResult:
    data: dict[str, Any]
    path: Path
    elapsed_seconds: float


@dataclass(frozen=True)
class AttackRunResult:
    result: AttackResult
    elapsed_seconds: float


class _LoggerProxy:
    def __init__(self, callback: LogCallback, progress=None) -> None:
        self._callback = callback
        self._progress = progress

    def _log(self, message: str) -> None:
        self._callback(message)


    def level_completed(self, leaves, structure):
        if self._progress:
            self._progress(leaves, structure)


class BackendAdapter:
    CLASSICAL = "blackburn"
    QUANTUM = SearchMethod.GROVER_FIXED.storage_id
    BBHT = SearchMethod.GROVER_BBHT.storage_id

    def __init__(self) -> None:
        self.search = create_search_algorithms("classical")

    @staticmethod
    def backend_name() -> str:
        return "C++ backend" if cpp_core_available() else "Python fallback"

    @staticmethod
    def thread_label() -> str:
        # C++ получает threads=0 и сам выбирает число потоков; точное значение не экспортируется.
        return "авто" if cpp_core_available() else "1"

    @staticmethod
    def validate_request(request: BuildRequest) -> None:
        selected = search_method(request.method)
        if request.bbht_options is not None:
            request.bbht_options.validate()
        if selected is SearchMethod.GROVER_BBHT and (request.use_cpp is False or not cpp_core_available()):
            raise RuntimeError("BBHT требует собранное C++-ядро.")
        if request.depth > request.truncate_bits:
            raise ValueError("Глубина превышает размер пространства хэш-кодов.")
        if request.seed is not None and not 0 <= request.seed < 2 ** 64:
            raise ValueError("seed должен лежать в диапазоне 0..2^64-1.")
        if request.threads < 0:
            raise ValueError("threads должен быть неотрицательным.")
        if request.depth < 1:
            raise ValueError("Глубина k должна быть не меньше 1.")
        if request.truncate_bits < 4 or request.truncate_bits > 512 or request.truncate_bits % 4:
            raise ValueError("Размер части хэш-кода n должен быть кратен 4 и лежать в диапазоне 4..512.")
        if request.prefix_blocks < 1:
            raise ValueError("Число блоков префикса должно быть не меньше 1.")
        if request.sigma_bits < 0 or request.sigma_bits > 64:
            raise ValueError("Размер части контрольной суммы s должен лежать в диапазоне 0..64.")
        if not 1 <= request.rounds <= 12:
            raise ValueError("Число раундов должно лежать в диапазоне 1..12.")
        if request.trials_limit < 1:
            raise ValueError("Лимит collision-проб должен быть положительным.")
        if request.parameter_strategy != "theoretical" and not selected.is_quantum:
            raise ValueError("Адаптивный подбор параметров доступен только для квантового построения.")
        if selected.is_quantum:
            select_layer_parameters(
                request.truncate_bits, request.depth,
                parameter_strategy=request.parameter_strategy,
                target_probability=request.target_probability,
            )

    @bounded_experiment
    def build_diamond(self, request: BuildRequest, log: LogCallback, progress=None) -> BuildResult:
        self.validate_request(request)
        selected = search_method(request.method)
        quantum = selected.is_quantum
        log(f"Метод построения: {selected.label}; n={request.truncate_bits}, k={request.depth}, s={request.sigma_bits}.")
        if quantum and request.seed is None:
            import random
            request = replace(request, seed=random.SystemRandom().getrandbits(64))
        builder = build_diamond_structure_quantum if quantum else build_diamond_structure
        stats: dict[str, int] = {}
        started = time.perf_counter()
        search = ClassicalSearchAlgorithms(request.seed, request.threads, request.use_cpp) if request.seed is not None or request.use_cpp is not None or request.threads else self.search
        extra = {
            "use_cpp": request.use_cpp, "threads": request.threads,
            "parameter_strategy": request.parameter_strategy,
            "target_probability": request.target_probability,
        } if quantum else {}
        if selected is SearchMethod.GROVER_BBHT:
            extra.update(method=selected, bbht_options=request.bbht_options)
            log(f"Параметры BBHT: {asdict(request.bbht_options or BBHTOptions())}.")
        def publish_level(leaves, levels):
            if progress:
                progress(diamond_to_json_dict(leaves, levels, request.truncate_bits, request.depth,
                                             request.rounds, request.prefix_blocks, stats, request.sigma_bits))

        try:
            leaves_data, structure = builder(
                search=search,
                depth=request.depth,
                truncate_bits=request.truncate_bits,
                trials_limit=request.trials_limit,
                rounds=request.rounds,
                logger=_LoggerProxy(log, publish_level),
                first_level_N=request.prefix_blocks * 512 + 512,
                stats=stats,
                sigma_bits=request.sigma_bits,
                sigma_seed=request.sigma_seed,
                seed=request.seed,
                **extra,
            )
        except Exception as exc:
            exc.experiment_stats = stats.copy()
            raise
        data = diamond_to_json_dict(
            leaves_data,
            structure,
            truncate_bits=request.truncate_bits,
            depth=request.depth,
            rounds=request.rounds,
            prefix_blocks=request.prefix_blocks,
            stats=stats,
            sigma_bits=request.sigma_bits,
        )
        if quantum:data["builder"] = selected.storage_id
        data['search_protocol'] = stats.get('search_protocol', 'legacy-v0') if quantum else SEARCH_PROTOCOL
        data['attempt_policy'] = 'bbht_auto' if selected is SearchMethod.GROVER_BBHT else ('fixed_single' if quantum else 'classical')
        if selected is SearchMethod.GROVER_BBHT:
            data["bbht_options"] = asdict(request.bbht_options or BBHTOptions())
        if quantum:
            data["amplitude_backend"] = stats.get("amplitude_backend", "dense")
        data["query_model"] = MODEL_REVISION if quantum else "classical-g-v1"
        data["statevector_simulation"] = quantum
        data["seed"] = request.seed
        if quantum:
            data["parameter_strategy"] = request.parameter_strategy
            data["target_candidate_probability"] = request.target_probability
        data["measurement_version"] = MODEL_REVISION
        validate_diamond_data(data)
        if quantum:
            field = 'quantum_independent_verification_hash_evaluations'
            data['stats'][field] = data['stats'].get(field, 0) + 2 * sum(len(level) for level in data['structure'])
        suffix = "_bbht" if selected is SearchMethod.GROVER_BBHT else ("_quantum" if quantum else "")
        sigma_suffix = f"_s{request.sigma_bits}" if request.sigma_bits else ""
        strategy_suffix = (
            f"_adaptive{int(round(100 * request.target_probability))}"
            if quantum and request.parameter_strategy == "target_probability" else ""
        )
        path = request.output_directory / (
            f"diamond_v3{suffix}_{request.depth}_{request.truncate_bits}{sigma_suffix}_p{request.prefix_blocks}{strategy_suffix}.json"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        import tempfile
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                             prefix=path.name + ".", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(data, stream, ensure_ascii=False, indent=2)
            temporary.replace(path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return BuildResult(data, path.resolve(), time.perf_counter() - started)

    @staticmethod
    def load_json(path: str | Path) -> dict[str, Any]:
        from .project_paths import resolve_project_input
        data = json.loads(resolve_project_input(path).read_text(encoding="utf-8"))
        if isinstance(data,dict) and data.get('format')=='herdinglab-experiments-v1':
            raise ValueError('Это база экспериментов; загрузите её кнопкой папки во вкладке «Сравнение».')
        if not isinstance(data,dict) or not {'format_version','model','leaves','structure'}.issubset(data):
            raise ValueError('Выбран JSON без алмазной структуры. Откройте сохранённый файл diamond_v3_*.json из папки data/diamonds рядом с программой.')
        validate_diamond_data(data)
        return data

    @staticmethod
    def save_json(data: dict[str, Any], path: str | Path) -> None:
        # Сохраняется исходная алгоритмическая схема без UI-полей.
        if data.get('builder')=='blackburn':data={key:value for key,value in data.items() if key!='builder'}
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    @bounded_experiment
    def run_attack(
        self,
        data: dict[str, Any],
        description: str,
        event_result: str,
        trials_limit: int,
        quantum: bool | str | SearchMethod = False,
        seed: int | None = None,
        threads: int = 0,
        use_cpp: bool | None = None,
        *,
        method: str | SearchMethod | None = None,
        bbht_options: BBHTOptions | None = None,
    ) -> AttackRunResult:
        selected = search_method(quantum if method is None else method)
        quantum = selected.is_quantum
        if bbht_options is not None:
            bbht_options.validate()
        if trials_limit < 1:
            raise ValueError("Лимит linking-проб должен быть положительным.")
        if quantum:
            depth = int(math.log2(len(data["leaves"])))
            params = algorithm5_link_parameters(int(data["trunc_bits"]), depth)
            if trials_limit < params.search_messages + 1:
                raise ValueError(f"Лимит должен быть не меньше S_link + 1 = {params.search_messages + 1}.")
        started = time.perf_counter()
        if quantum:
            result = execute_algorithm5(
                data=data,
                description=description,
                event_result=event_result,
                trials_limit=trials_limit,
                seed=seed, use_cpp=use_cpp, threads=threads,
                **({"method": selected, "bbht_options": bbht_options} if selected is SearchMethod.GROVER_BBHT else {}),
            )
        else:
            result = execute_attack(
                data=data,
                description=description,
                event_result=event_result,
                search=ClassicalSearchAlgorithms(seed, threads, use_cpp) if seed is not None or use_cpp is not None or threads else self.search,
                trials_limit=trials_limit,
            )
        if not quantum:
            result = replace(result, search_protocol=SEARCH_PROTOCOL, attempt_policy='classical')
        return AttackRunResult(result, time.perf_counter() - started)

    @staticmethod
    def root(data: dict[str, Any]) -> str:
        return get_diamond_root(data)
