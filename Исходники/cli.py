"""Командный интерфейс HerdingLab с запуском графического интерфейса через main.py."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import traceback
from dataclasses import asdict
from pathlib import Path

from algorithms.search_methods import BBHTOptions, SearchMethod, search_method
from integration.backend_adapter import BackendAdapter
from integration.campaign_runner import ROOT, build_to_path, environment, full_hashes, run_campaign
from integration.experiment_store import ExperimentStore
from integration.result_adapter import ExperimentRecord
from algorithms.statevector_limits import MODEL_REVISION


def common(parser: argparse.ArgumentParser, suppress: bool = False) -> None:
    default = argparse.SUPPRESS if suppress else False
    flags = parser.add_mutually_exclusive_group()
    flags.add_argument("--quiet", action="store_true", default=default, help="Suppress progress")
    flags.add_argument("--verbose", action="store_true", default=default, help="Detailed logs and traceback")
    parser.add_argument("--json", action="store_true", default=default, help="Print final result as JSON")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="HerdingLab: reduced-GOST diamond/herding experiments")
    common(root)
    commands = root.add_subparsers(dest="command", required=True)
    for name, help_text in (("selftest", "Run every test suite"), ("validate-diamond", "Replay every edge"),
                            ("build-diamond", "Build a diamond"), ("attack", "Find a linking block and replay the path"),
                            ("campaign", "Run a reproducible experimental series"), ("analyze", "Create statistical reports and PNG charts")):
        command = commands.add_parser(name, help=help_text)
        common(command, True)
    commands.choices["validate-diamond"].add_argument("path", type=Path)
    build = commands.choices["build-diamond"]
    build.add_argument("--n", "--t", dest="n", required=True, type=int, help="Размер части хэш-кода n, бит")
    build.add_argument("--k", required=True, type=int, help="Глубина алмазной структуры k")
    build.add_argument("--prefix-blocks", type=int, default=1)
    build.add_argument("--rounds", type=int, default=12)
    build.add_argument("--sigma-bits", type=int, default=0)
    build.add_argument('--sigma-seed', type=int, default=0, help='Seed части контрольной суммы, как в GUI.')
    build.add_argument("--parameter-strategy", choices=("theoretical", "target_probability"), default="theoretical")
    build.add_argument("--target-probability", type=float, default=0.95)
    build.add_argument("--output", required=True, type=Path)
    attack = commands.choices["attack"]
    attack.add_argument("--diamond", required=True, type=Path)
    attack.add_argument("--description", default="Эксперимент ")
    attack.add_argument("--event-result", default="успешен")
    attack.add_argument("--output", type=Path, help="Save complete attack transcript")
    for item in (build, attack):
        item.add_argument("--method", choices=("classical", "quantum", "grover_fixed", "grover_bbht", "bbht", "blackburn", "quantum_algorithm_2_simulator"), required=True)
        item.add_argument("--bbht-growth", type=float, default=1.2, help="Коэффициент роста BBHT.")
        item.add_argument("--bbht-max-attempts", type=int, default=128, help="Максимум попыток BBHT; фактический лимит автоматически рассчитывается по S.")
        item.add_argument("--bbht-max-queries", type=int, default=100000, help="Модельных запросов на поиск BBHT.")
        item.add_argument("--bbht-dense-max-states", type=int, default=8192, help="Порог плотного вектора BBHT.")
        item.add_argument("--bbht-stage-seconds", type=float, default=0, help="Время этапа BBHT в секундах.")
        item.add_argument("--seed", type=int)
        item.add_argument("--threads", type=int, default=0)
        item.add_argument("--qram-impl", choices=("auto", "generic", "u64"), default="auto")
        item.add_argument("--rng", choices=("mt19937", "xoshiro256ss"), default="mt19937")
        item.add_argument("--blackburn-backend", choices=("legacy", "cpp-layer"), default="legacy")
        item.add_argument("--trials-limit", type=int, default=1_000_000_000)
        item.add_argument("--record-db", type=Path, default=ROOT / "experiments/search_policy_v1.json")
    campaign = commands.choices["campaign"]
    campaign.add_argument("--config", required=True, type=Path)
    campaign.add_argument("--resume", action="store_true")
    campaign.add_argument("--record-db", type=Path)
    analysis = commands.choices["analyze"]
    analysis.add_argument("--database", required=True, type=Path)
    analysis.add_argument("--output", required=True, type=Path)
    analysis.add_argument("--campaign", help="Analyze one campaign only")
    return root


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    args = parser().parse_args(argv)
    if hasattr(args,"qram_impl"):
        os.environ["NOSTRADAMUS_QRAM_IMPL"] = args.qram_impl
        os.environ["NOSTRADAMUS_RNG"] = args.rng
        os.environ["NOSTRADAMUS_BLACKBURN_BACKEND"] = args.blackburn_backend
    def log(text):
        if not args.quiet:
            cleaned = str(text).replace("state-vector, без реального квантового ускорения.", "классический симулятор.").replace(", без реального квантового ускорения.", "").replace("—", "–")
            print(cleaned, file=sys.stderr if args.json else sys.stdout, flush=True)
    started = time.perf_counter()
    store = None
    metadata = None
    failure_record = None
    try:
        adapter = BackendAdapter()
        if args.command == "selftest":
            results = []
            for command in ([sys.executable, "-m", "pytest", "-q"], *([sys.executable, "tests/" + name] for name in
                            ("selftest.py", "selftest_cpp.py", "test_diamond_builders.py", "test_quantum_algorithms.py", "test_sigma_aware.py"))):
                completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                           encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
                log(completed.stdout)
                if completed.stderr:
                    log(completed.stderr)
                results.append({"command": command[1:], "exit_code": completed.returncode})
                if completed.returncode:
                    raise RuntimeError(f"Test command failed: {command}")
            output = {"status": "PASS", "suites": results}
        elif args.command == "validate-diamond":
            data = adapter.load_json(args.path)
            output = {"status": "PASS", "path": str(args.path.resolve()), "leaves": len(data["leaves"]),
                      "edges": sum(len(layer) * 2 for layer in data["structure"]), "root": adapter.root(data)}
        elif args.command in ("build-diamond", "attack"):
            if args.seed is not None and not 0 <= args.seed < 2**64:
                raise ValueError("seed must be in 0..2^64-1")
            if args.threads < 0:
                raise ValueError("threads must be non-negative")
            selected = search_method(args.method)
            bbht_options = BBHTOptions(args.bbht_growth, args.bbht_max_attempts, args.bbht_max_queries,
                                       args.bbht_dense_max_states, args.bbht_stage_seconds)
            if selected is SearchMethod.GROVER_BBHT:
                bbht_options.validate()
            store = ExperimentStore(None, args.record_db)
            metadata = environment(args.seed, args.threads) | {"builder": args.method, "campaign": None, "repetition": None, "statevector_simulation": selected.is_quantum}
            if args.command == "build-diamond":
                params = {"t": args.n, "k": args.k, "prefix_blocks": args.prefix_blocks,
                          "rounds": args.rounds, "sigma_bits": args.sigma_bits, "trials_limit": args.trials_limit,
                          'sigma_seed': args.sigma_seed,
                          "parameter_strategy": args.parameter_strategy, "target_probability": args.target_probability,
                          "bbht_options": asdict(bbht_options) if selected is SearchMethod.GROVER_BBHT else None}
                metadata["parameters"] = params
                failure_record = ExperimentRecord(
                    selected.storage_id,
                    args.n, args.k, args.prefix_blocks, args.rounds, None, "Ошибка",
                    sigma_bits=args.sigma_bits, measurement_version=MODEL_REVISION)
                result = build_to_path(adapter, params, args.method, args.seed, args.output, log, args.threads)
                entry = store.add_completed(result.data, result.elapsed_seconds, result.path, metadata)
                output = {"status": "PASS", "path": str(result.path), "elapsed_seconds": result.elapsed_seconds,
                          "record": entry.record.to_storage_dict(), "record_id": entry.identity}
            else:
                data = adapter.load_json(args.diamond)
                metadata["parameters"] = {"t": data["trunc_bits"], "k": data["depth"],
                                          "prefix_blocks": data["prefix_blocks"], "rounds": data["rounds"],
                                          "sigma_bits": data.get("sigma_bits", 0), "trials_limit": args.trials_limit}
                failure_record = ExperimentRecord(
                    selected.storage_id,
                    data["trunc_bits"], data["depth"], data["prefix_blocks"], data["rounds"], None, "Ошибка",
                    sigma_bits=data.get("sigma_bits", 0), experiment_type="herding", measurement_version=MODEL_REVISION)
                result = adapter.run_attack(data, args.description, args.event_result, args.trials_limit,
                                            args.method, args.seed, args.threads,
                                            bbht_options=bbht_options if selected is SearchMethod.GROVER_BBHT else None)
                output = {"status": "PASS", "elapsed_seconds": result.elapsed_seconds,
                          "result": asdict(result.result)} | full_hashes(result.result.forged_hex)
                metadata |= {"full_gost512": output["full_gost512"], "full_gost256": output["full_gost256"]}
                entry = store.add_attack(data, result.result, result.elapsed_seconds, args.diamond,
                                         args.trials_limit, metadata)
                output["record_id"] = entry.identity
                if args.output:
                    args.output.parent.mkdir(parents=True, exist_ok=True)
                    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        elif args.command == "campaign":
            output = run_campaign(args.config, resume=args.resume, database=args.record_db, log=log)
        else:
            from integration.experiment_analysis import analyze_database
            output = analyze_database(args.database, args.output, args.campaign)
        if args.json:
            print(json.dumps(output, ensure_ascii=False), flush=True)
        elif not args.quiet:
            print(json.dumps(output, ensure_ascii=False, indent=2), flush=True)
        return 1 if args.command == "campaign" and (output.get("failed_campaign", 0) or output.get("skipped_campaign", 0)) else 0
    except (Exception, KeyboardInterrupt) as exc:
        interrupted = isinstance(exc, KeyboardInterrupt)
        message = str(exc) or "Interrupted by Ctrl+C"
        if store is not None and failure_record is not None and failure_record.n > 0 and failure_record.k > 0:
            from dataclasses import replace
            try:
                store.add_failure(replace(failure_record, elapsed_seconds=time.perf_counter() - started,
                                          status="Остановлено" if interrupted else "Ошибка"),
                                  (metadata or {}) | {"error": message, "interrupted": interrupted})
            except Exception as persistence_error:
                message += f"; cannot save failed attempt: {persistence_error}"
        if args.json:
            print(json.dumps({"status": "INTERRUPTED" if interrupted else "ERROR", "error": message}, ensure_ascii=False), flush=True)
        print(f"ERROR: {message}", file=sys.stderr, flush=True)
        if args.verbose and not interrupted:
            traceback.print_exc()
        return 130 if interrupted else 1


if __name__ == "__main__":
    raise SystemExit(main())
