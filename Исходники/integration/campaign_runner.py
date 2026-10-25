"""Организует воспроизводимые эксперименты через алгоритмы BackendAdapter."""
from __future__ import annotations

import hashlib
import itertools
import json
import os
import platform
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from algorithms.search_methods import BBHTOptions, search_method
from CppCore import _run, cpp_core_available
from HashCalculator import HashCalculator
from .backend_adapter import BackendAdapter, BuildRequest, BuildResult
from .experiment_store import ExperimentStore
from .result_adapter import ExperimentRecord

ROOT = Path(__file__).resolve().parents[1]
from algorithms.statevector_limits import MODEL_REVISION, check_resources, check_layer_resources
from algorithms.grover import optimal_grover_iterations
from algorithms.quantum_diamond import algorithm2_parameters


def code_fingerprint() -> str:
    if getattr(sys,'frozen',False):
        manifest=json.loads((ROOT/'bundle_metadata.json').read_text(encoding='utf-8'))
        value=manifest.get('code_sha256','')
        if len(value)!=64 or any(c not in '0123456789abcdef' for c in value):
            raise ValueError('Повреждена контрольная сумма исходников автономной сборки.')
        return value
    digest = hashlib.sha256()
    files = sorted((ROOT / "algorithms").glob("*.py")) + [ROOT / "HashCalculator.py", ROOT / "CppCore.py", ROOT / "cpp_core/gost_core.cpp"]
    files += sorted((ROOT / "cpp_core").glob("*.hpp"))
    files += sorted((ROOT / "integration").glob("*.py")) + [ROOT / "cli.py"]
    for file in files:
        digest.update(file.relative_to(ROOT).as_posix().encode())
        digest.update(file.read_bytes())
    return digest.hexdigest()


def environment(seed: int | None, threads: int = 0) -> dict:
    return {
        "seed": seed, "model_revision": MODEL_REVISION, "code_sha256": code_fingerprint(),
        "backend": _run(["version"])[0] if cpp_core_available() else "python",
        "statevector_simulation": True,
        "threads": threads or None,
        "classical_threads": threads or None,
        "rng": os.environ.get("NOSTRADAMUS_RNG", "mt19937"),
        "qram_impl": os.environ.get("NOSTRADAMUS_QRAM_IMPL", "auto"),
        "blackburn_backend": os.environ.get("NOSTRADAMUS_BLACKBURN_BACKEND", "legacy"),
        "python": platform.python_version(), "platform": platform.platform(),
        "logical_cpus": os.cpu_count(),
    }


def full_hashes(forged_hex: str) -> dict:
    def calculate(bits: int) -> str:
        if cpp_core_available():
            return _run(["hash", forged_hex, str(bits)])[0]
        return HashCalculator("1" if bits == 512 else "0", "hex", forged_hex).run()
    return {"full_gost512": calculate(512), "full_gost256": calculate(256),
            "full_hash_representation": "canonical RFC6986 vector; rightmost block first"}


def build_to_path(adapter: BackendAdapter, params: dict, method: str, seed: int | None,
                  output: Path, log: Callable[[str], None], threads: int = 0) -> BuildResult:
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="building-", dir=output.parent) as staging:
        request = BuildRequest(
            search_method(method).storage_id,
            int(params["k"]), int(params.get("n", params.get("t"))), int(params.get("prefix_blocks", 1)),
            int(params.get("rounds", 12)), int(params.get("trials_limit", 1_000_000_000)),
            Path(staging), int(params.get("sigma_bits", 0)),
            int(params.get("sigma_seed", seed if seed is not None else 0)), seed, threads,
            parameter_strategy=str(params.get("parameter_strategy", "theoretical")),
            target_probability=float(params.get("target_probability", 0.95)),
            bbht_options=BBHTOptions(**params["bbht_options"]) if params.get("bbht_options") else None,
        )
        result = adapter.build_diamond(request, log)
        result.path.replace(output)
        return BuildResult(result.data, output, result.elapsed_seconds)


@dataclass(frozen=True)
class CampaignTask:
    task_id: str
    group: str
    stage: str
    method: str
    params: dict
    repetition: int
    seed: int
    output: Path
    diamond_task: str | None = None
    diamond_path: Path | None = None


def expand_tasks(config: dict, output_root: Path) -> list[CampaignTask]:
    tasks = []
    defaults = config.get("defaults", {})
    master_seed = int(config.get("seed", 12345))
    for group in config["groups"]:
        name = group["name"]
        if not name or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in name):
            raise ValueError("Campaign group name must use letters, digits, '-' or '_'.")
        grid = group.get("grid", {})
        keys = list(grid)
        combinations = [dict(zip(keys, values)) for values in itertools.product(*(grid[key] for key in keys))]
        if "cases" in group:
            combinations = group["cases"]
        for combination_index, values in enumerate(combinations):
            params = defaults | group.get("parameters", {}) | values
            if "n" in params:
                params["t"] = params.pop("n")
            repetitions = group.get("repetitions", 1)
            if isinstance(repetitions, dict):
                repetitions = repetitions[str(params["t"])]
            methods = group.get("methods", ["classical", "quantum"])
            builds = []
            for method in methods:
                for repetition in range(int(repetitions)):
                    task_id = f"{name}-{combination_index:03d}-{method}-diamond-{repetition:03d}"
                    seed = int.from_bytes(hashlib.sha256(f"{master_seed}:{task_id}".encode()).digest()[:8], "big")
                    output = output_root / "diamonds" / f"{task_id}.json"
                    task = CampaignTask(task_id, name, "diamond", method, params, repetition, seed, output)
                    tasks.append(task)
                    builds.append(task)
            link_count = int(group.get("linking_repetitions", 0))
            selected = builds if group.get("linking_each_diamond", False) else builds[:1]
            for build in selected:
                for method in group.get("linking_methods", ("classical", "quantum")):
                    for repetition in range(link_count):
                        task_id = f"{build.task_id}-{method}-link-{repetition:03d}"
                        seed = int.from_bytes(hashlib.sha256(f"{master_seed}:{task_id}".encode()).digest()[:8], "big")
                        tasks.append(CampaignTask(task_id, name, "herding", method, params,
                                                  repetition, seed, output_root / "attacks" / f"{task_id}.json",
                                                  build.task_id, build.output))
    return tasks


def run_campaign(config_path: Path, *, resume: bool = False, log: Callable[[str], None] = print,
                 database: Path | None = None) -> dict:
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    choices = {"rng": ("mt19937", "xoshiro256ss"), "qram_impl": ("auto", "generic", "u64"),
               "blackburn_backend": ("legacy", "cpp-layer")}
    settings = {}
    for key, allowed in choices.items():
        value = config.get(key, allowed[0])
        if value not in allowed:
            raise ValueError(f"Invalid {key}: {value}")
        settings["NOSTRADAMUS_" + key.upper()] = value
    previous = {key: os.environ.get(key) for key in settings}
    try:
        os.environ.update(settings)
        return _run_campaign(config_path, resume=resume, log=log, database=database)
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _run_campaign(config_path: Path, *, resume: bool = False, log: Callable[[str], None] = print,
                 database: Path | None = None) -> dict:
    config_path = Path(config_path).resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    name = config["name"]
    if not name or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in name):
        raise ValueError("Invalid campaign name")
    output_root = Path(config.get("runs_directory", ROOT / "experiments" / "runs" / name))
    store = ExperimentStore(None, database or ROOT / config.get("database", "experiments/thesis_statevector.json"))
    if config.get('model_revision', MODEL_REVISION) != MODEL_REVISION:
        raise ValueError('Конфигурация относится к другой версии модели.')
    if any(entry.record.measurement_version != MODEL_REVISION for entry in store.entries):
        raise ValueError('База содержит предыдущую версию измерений; используйте отдельную новую базу.')
    tasks = expand_tasks(config, output_root)
    revision = code_fingerprint()
    config_hash = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
    existing = [entry for entry in store.entries if entry.metadata.get("campaign") == name]
    if existing and not resume:
        raise ValueError("Campaign already has records. Use --resume or a new campaign name.")
    completed = {entry.metadata.get("task_id") for entry in existing if entry.metadata.get("terminal", True)}
    if any(entry.metadata.get("config_sha256") != config_hash for entry in existing):
        raise ValueError("Campaign config changed; use a new campaign name/database.")
    if any(entry.metadata.get("code_sha256") != revision for entry in existing) and any(task.task_id not in completed for task in tasks):
        raise ValueError("Algorithm version changed; cannot mix unfinished campaign versions.")
    successes = {entry.metadata.get("task_id") for entry in existing if entry.record.status == "Завершено"}
    adapter = BackendAdapter()
    threads = int(config.get("threads", 0))
    env = environment(None, threads)
    cache: dict[Path, dict] = {}
    executed = failed = skipped = 0
    for index, task in enumerate(tasks, 1):
        if task.task_id in completed:
            continue
        meta = env | {"seed": task.seed, "campaign": name, "group": task.group,
                      "task_id": task.task_id, "repetition": task.repetition,
                      "parameters": task.params, "config_sha256": config_hash,
                      "terminal": True, "classical_threads": threads or None,
                      "builder": task.method, "diamond_task": task.diamond_task,
                      "statevector_simulation": search_method(task.method).is_quantum}
        log(f"[{index}/{len(tasks)}] {task.task_id}")
        started = time.perf_counter()
        try:
            if task.method == 'quantum':
                if task.stage == 'diamond':
                    estimates = [check_layer_resources(p.table_messages, p.search_messages, p.vertex_count, bits)
                                 for bits in range(task.params['k'], 0, -1)
                                 for p in [algorithm2_parameters(task.params['t'], bits)]]
                else:
                    states = 1 << (task.params['t'] - task.params['k'])
                    estimates = [check_resources(states, optimal_grover_iterations(states, 1), 262144 + (1 << task.params['k']) * 256)]
                meta['statevector_resource_estimates'] = estimates
            if task.stage == "diamond":
                result = build_to_path(adapter, task.params, task.method, task.seed, task.output,
                                       log if config.get("verbose", False) else lambda _: None, threads)
                store.add_completed(result.data, result.elapsed_seconds, result.path, meta)
                cache[result.path] = result.data
            else:
                if task.diamond_task not in successes:
                    raise FileNotFoundError("Dependent diamond build did not succeed; linking was not executed.")
                data = cache.get(task.diamond_path)
                if data is None:
                    data = adapter.load_json(task.diamond_path)
                    cache[task.diamond_path] = data
                event = f"успешен {task.repetition}"
                limit = int(task.params.get("link_trials_limit", 50_000_000))
                result = adapter.run_attack(data, "Эксперимент ", event, limit,
                                            task.method, task.seed, threads)
                payload = asdict(result.result) | full_hashes(result.result.forged_hex)
                task.output.parent.mkdir(parents=True, exist_ok=True)
                task.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                meta |= {"attack_result": str(task.output), "link_attempts": result.result.link_attempts,
                         "marked_elements": result.result.link_marked_count,
                         "statevector_simulation": search_method(task.method).is_quantum,
                         "statevector_elements_processed": result.result.link_statevector_elements_processed,
                         "statevector_norm_error_max": result.result.link_statevector_norm_error_max,
                         "full_gost512": payload["full_gost512"], "full_gost256": payload["full_gost256"]}
                store.add_attack(data, result.result, result.elapsed_seconds, task.diamond_path, limit, meta)
            successes.add(task.task_id)
            executed += 1
        except BaseException as exc:
            interrupted = isinstance(exc, KeyboardInterrupt)
            blocked = isinstance(exc, FileNotFoundError) and task.stage == "herding"
            if not isinstance(exc, (Exception, KeyboardInterrupt)):
                raise
            resource_refusal = isinstance(exc, ValueError) and any(word in str(exc) for word in ('лимит', 'бюджет'))
            if resource_refusal: blocked = True
            elapsed = None if blocked else time.perf_counter() - started
            if hasattr(exc, 'experiment_stats'):
                meta['partial_stats'] = exc.experiment_stats
            meta['resource_refusal'] = resource_refusal
            meta |= {"error": str(exc) or "Interrupted by Ctrl+C", "terminal": not interrupted,
                     "interrupted": interrupted, "not_executed": blocked}
            partial = getattr(exc, 'experiment_stats', {})
            prefix = 'quantum_' if task.stage == 'diamond' else 'quantum_link_'
            measured_fields = {}
            if task.method == 'quantum':
                for field, source in (('quantum_oracle_queries', 'oracle_queries'), ('quantum_simulator_hash_evaluations', 'simulator_hash_evaluations'),
                                      ('statevector_elements_processed', 'statevector_elements_processed'), ('statevector_norm_error_max', 'statevector_norm_error_max'),
                                      ('statevector_seconds', 'statevector_seconds'), ('success_probability_sum', 'success_probability_sum')):
                    measured_fields[field] = partial.get(prefix + source)
                measured_fields['grover_attempts'] = partial.get('quantum_grover_attempts' if task.stage == 'diamond' else 'quantum_link_attempts')
                measured_fields['quantum_grover_successes'] = partial.get('quantum_grover_successes', 0 if partial else None)
                measured_fields['quantum_layer_attempts'] = partial.get('quantum_layer_attempts')
                measured_fields['matching_successes'] = partial.get('quantum_matching_successes')
            meta['partial_stats_are_lower_bounds'] = bool(partial)
            record = ExperimentRecord(
                search_method(task.method).storage_id,
                task.params["t"], task.params["k"], task.params.get("prefix_blocks", 1),
                task.params.get("rounds", 12), elapsed,
                "Остановлено" if interrupted else "Пропущено" if blocked else "Ошибка",
                sigma_bits=task.params.get("sigma_bits", 0), experiment_type=task.stage,
                measurement_version=MODEL_REVISION, **measured_fields,
            )
            store.add_failure(record, meta)
            if blocked:
                skipped += 1
            else:
                executed += 1
                failed += 1
            log(f"  ERROR: {exc}")
            if interrupted:
                raise
        completed.add(task.task_id)
    campaign_entries=[e for e in store.entries if e.metadata.get("campaign")==name]
    failed_total=sum(e.record.status=="Ошибка" for e in campaign_entries)
    skipped_total=sum(e.record.status=="Пропущено" for e in campaign_entries)
    return {"status": "COMPLETE_WITH_ERRORS" if failed_total or skipped_total else "COMPLETE",
            "failed_campaign": failed_total, "skipped_campaign": skipped_total,
            "campaign": name, "planned": len(tasks), "executed_this_run": executed,
            "failed_this_run": failed, "skipped_dependencies": skipped,
            "database": str(store.local_path), "recorded_campaign": len([e for e in store.entries if e.metadata.get('campaign') == name])}
