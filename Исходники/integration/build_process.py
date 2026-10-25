"""Запуск неизменённого построения в отдельном процессе для безопасной отмены из UI."""

from __future__ import annotations

from dataclasses import asdict
import json
import sys
import traceback
from pathlib import Path

from .backend_adapter import BackendAdapter, BuildRequest
from algorithms.search_methods import BBHTOptions
from .native_process import guard_current_process


def emit(kind: str, **payload: object) -> None:
    line = "HERDINGLAB:" + json.dumps({"type": kind, **payload}, ensure_ascii=False) + "\n"
    sys.stdout.buffer.write(line.encode("utf-8"))
    sys.stdout.buffer.flush()


def main() -> int:
    try:
        guard_current_process()
        values = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        operation = values.pop("operation", "build")
        if values.get("bbht_options") is not None:
            values["bbht_options"] = BBHTOptions(**values["bbht_options"])
        if operation == "attack":
            result = BackendAdapter().run_attack(**values)
            emit("result", attack=asdict(result.result), elapsed_seconds=result.elapsed_seconds)
            return 0
        values["output_directory"] = Path(values["output_directory"])
        request = BuildRequest(**values)
        result = BackendAdapter().build_diamond(request, lambda message: emit("log", message=message),
                                                 progress=lambda data: emit("level", data=data))
        emit("result", path=str(result.path), elapsed_seconds=result.elapsed_seconds)
        return 0
    except Exception as exc:
        emit("error", message=str(exc), trace=traceback.format_exc())
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
