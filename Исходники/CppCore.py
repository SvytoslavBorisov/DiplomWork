from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Tuple

_STATEVECTOR_CORES = set()


ROOT = Path(__file__).resolve().parent

class BlackburnLayerSession:
    """Пул C++ обслуживает один уровень, а расширением списков и паросочетанием управляет Python."""
    def __init__(self,states,N,n,rounds,threads,*,sigma_bits=0,current_sigma=0,target_sigma=0):
        self.states=list(states)
        self.args=['blackburn-layer',str(len(self.states)),str(N),str(n),str(rounds),str(threads),str(sigma_bits),str(current_sigma),str(target_sigma)]
        self.process=None
    def _send(self,text):
        self.process.stdin.write(text+'\n')
        self.process.stdin.flush()
    def _reply(self):
        line=self.process.stdout.readline()
        if not line:
            detail=self.process.stderr.read()
            raise RuntimeError(f'Blackburn layer process ended: {detail}')
        parts=line.split()
        if not parts or parts[0]!='OK':
            raise RuntimeError(f'Invalid Blackburn reply: {line!r}')
        return parts[1:]
    def __enter__(self):
        executable=core_path()
        if executable is None:raise FileNotFoundError('C++ backend unavailable')
        from integration.native_process import NativeProcess
        self.process=NativeProcess([str(executable),*self.args],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
        try:
            self._send('\n'.join(self.states))
            if self._reply()!=['READY']:raise RuntimeError('Blackburn session not ready')
        except BaseException:
            self.__exit__(RuntimeError,None,None)
            raise
        return self
    def grow(self,count,seed):
        self._send(f'GROW {count} {int(seed is not None)} {seed or 0}')
        parts=self._reply()
        if len(parts)<2:raise RuntimeError('Missing Blackburn counters')
        queries,edge_count=map(int,parts[:2])
        if queries!=len(self.states)*count or len(parts)!=2+6*edge_count:raise RuntimeError('Incomplete Blackburn result')
        edges=[]
        for offset in range(2,len(parts),6):
            left,right,lm,rm,common,sigma=parts[offset:offset+6]
            edges.append((int(left),int(right),lm,rm,common,int(sigma)))
        return edges,queries
    def drop_edges(self,edges):
        self._send('DROP '+str(len(edges))+' '+ ' '.join(f'{a} {b}' for a,b in edges))
        if self._reply()!=['DROP']:raise RuntimeError('Blackburn DROP failed')
    def __exit__(self,exc_type,exc_value,traceback):
        if self.process is None:return False
        process=self.process
        try:
            if process.poll() is None:
                if exc_type is None:
                    self._send('DONE')
                    if self._reply()!=['DONE']:raise RuntimeError('Blackburn shutdown failed')
                else:process.terminate()
            process.wait(timeout=5)
            if exc_type is None and process.returncode:raise RuntimeError(f'Blackburn exit {process.returncode}')
        finally:
            if process.poll() is None:
                process.kill();process.wait()
            process.close_job()
            for stream in (process.stdin,process.stdout,process.stderr):
                stream.close()
        return False


@dataclass(frozen=True)
class CppQuantumLayerResult:
    edges: list[tuple[int, int, str, str, str]]
    oracle_queries: int
    simulator_evaluations: int
    qram_entries: int
    grover_successes: int
    statevector_elements_processed: int = 0
    statevector_iterations: int = 0
    grover_attempts: int = 0
    marked_elements: int = 0
    verification_evaluations: int = 0
    success_probability_sum: float = 0.0
    statevector_norm_error_max: float = 0.0
    statevector_seconds: float = 0.0
    phase_oracle_queries: int | None = None
    verification_queries: int | None = None
    failed_attempts: int = 0
    search_attempts: int = 0
    amplitude_backend: str = "dense"
    search_protocol: str = "legacy-v0"
    attempt_policy: str = ""
    search_diagnostics: tuple[dict, ...] = ()


@dataclass(frozen=True)
class CppQuantumLinkResult:
    block: Optional[str]
    target_state: Optional[str]
    oracle_queries: int
    simulator_evaluations: int
    marked_count: int
    success_probability: float
    norm_error: float
    statevector_elements_processed: int = 0
    statevector_iterations: int = 0
    verification_evaluations: int = 0
    statevector_seconds: float = 0.0
    phase_oracle_queries: int | None = None
    verification_queries: int | None = None
    failed_attempts: int = 0
    search_attempts: int = 0
    amplitude_backend: str = "dense"
    search_protocol: str = "legacy-v0"
    attempt_policy: str = ""
    search_diagnostics: tuple[dict, ...] = ()


def _search_diagnostics(parts):
    """Читает версию политики и фактические причины остановки каждого нативного поиска."""
    if 'SEARCH' not in parts:
        return parts, {}
    marker = parts.index('SEARCH')
    values = parts[marker + 1:]
    if len(values) < 2:
        raise RuntimeError('Отсутствует заголовок политики поиска.')
    count = int(values[1])
    if count < 1 or len(values) != 2 + 7 * count:
        raise RuntimeError('Неполная диагностика попыток поиска.')
    searches = []
    for offset in range(2, len(values), 7):
        policy, states, growth, maximum, attempts, failures, reason = values[offset:offset + 7]
        searches.append(dict(attempt_policy=policy, search_messages=int(states), growth=float(growth),
            effective_max_attempts=int(maximum), attempts=int(attempts), failures=int(failures), stop_reason=reason))
    return parts[:marker], dict(search_protocol=values[0], attempt_policy=searches[0]['attempt_policy'],
                               search_diagnostics=tuple(searches))


def _candidate_paths() -> list[Path]:
    names = ["gost_core.exe"] if os.name == "nt" else ["gost_core"]
    paths: list[Path] = []
    env = os.environ.get("NOSTRADAMUS_CPP_CORE")
    if env:
        paths.append(Path(env))
    for name in names:
        paths.append(ROOT / "bin" / name)
        paths.append(ROOT / "build" / "cpp_core" / "Release" / name)
        paths.append(ROOT / "build" / "cpp_core" / name)
        paths.append(ROOT / "cpp_core" / "build" / "Release" / name)
        paths.append(ROOT / "cpp_core" / "build" / name)
        paths.append(ROOT / name)
    return paths


def core_path() -> Optional[Path]:
    for path in _candidate_paths():
        if path.is_file():
            return path
    return None


def cpp_core_available() -> bool:
    return core_path() is not None


def _run(
    args: list[str],
    timeout: Optional[float] = None,
    input_text: Optional[str] = None,
) -> list[str]:
    from algorithms.statevector_limits import remaining_seconds
    exe = core_path()
    if exe is None:
        raise FileNotFoundError(
            "C++ ядро не найдено. Запустите build_windows.bat (Windows) "
            "или build_linux.sh (Linux)."
        )
    remaining = remaining_seconds()
    if remaining is not None:
        timeout = remaining if timeout is None else min(timeout, remaining)
    environment = dict(os.environ)
    if remaining is not None:
        environment['GROVER_TIMEOUT_SECONDS'] = str(min(float(environment.get('GROVER_TIMEOUT_SECONDS', remaining)), remaining))
    if args[0].startswith(('quantum-', 'grover-')):
        stamp = (str(exe.resolve()), exe.stat().st_mtime_ns, exe.stat().st_size)
        if stamp not in _STATEVECTOR_CORES:
            version = subprocess.run([str(exe), 'version'], capture_output=True, text=True, encoding='utf-8', timeout=min(timeout or 5, 5), creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            if version.returncode or version.stdout.strip() != 'OK gost_core_v13_statevector_v2':
                raise RuntimeError('C++-ядро не поддерживает моделирование вектора амплитуд; выполните build_windows.bat или build_linux.sh.')
            _STATEVECTOR_CORES.add(stamp)
    from integration.native_process import run_native
    proc = run_native(
        [str(exe), *args],
        text=True,
        encoding="utf-8",
        env=environment,
        input=input_text,
        timeout=timeout,
    )
    out = proc.stdout.strip()
    if proc.returncode != 0:
        detail = proc.stderr.strip() or out or f"exit code {proc.returncode}"
        raise RuntimeError(f"Ошибка C++ ядра: {detail}")
    parts = out.split()
    if not parts or parts[0] != "OK":
        raise RuntimeError(f"Некорректный ответ C++ ядра: {out!r}")
    return parts[1:]


def cpp_compress(m: str, h: str, N: int, rounds: int) -> str:
    parts = _run(["compress", m, h, str(N), str(rounds)])
    if len(parts) != 1:
        raise RuntimeError("Некорректный ответ команды compress.")
    return parts[0]


def cpp_reduced(m: str, state: str, N: int, rounds: int, truncate_bits: int) -> str:
    parts = _run([
        "reduced", m, state, str(N), str(rounds), str(truncate_bits)
    ])
    if len(parts) != 1:
        raise RuntimeError("Некорректный ответ команды reduced.")
    return parts[0]


def cpp_find_collision(
    h1: str,
    h2: str,
    N: int,
    truncate_bits: int,
    rounds: int,
    trials_limit: int,
    threads: int = 0,
    *,
    sigma_bits: int = 0,
    left_sigma: int = 0,
    right_sigma: int = 0,
    target_sigma: int = 0,
    seed: int | None = None,
) -> Tuple[str, str, str, int]:
    if sigma_bits:
        args = [
            "collision-sigma", h1, h2, str(N), str(truncate_bits), str(rounds),
            str(trials_limit), str(threads), str(sigma_bits), str(left_sigma),
            str(right_sigma), str(target_sigma),
        ]
    else:
        args = [
            "collision", h1, h2, str(N), str(truncate_bits), str(rounds),
            str(trials_limit), str(threads),
        ]
    if seed is not None:
        args += ["--seed", str(seed)]
    parts = _run(args)
    if len(parts) != 4:
        raise RuntimeError("Некорректный ответ команды collision.")
    m1, m2, common, queries = parts
    return m1, m2, common, int(queries)


def cpp_find_link(
    prefix_state: str,
    target_states: Iterable[str],
    N: int,
    truncate_bits: int,
    rounds: int,
    trials_limit: int,
    threads: int = 0,
    *,
    sigma_bits: int = 0,
    current_sigma: int = 0,
    target_sigma: int = 0,
    seed: int | None = None,
) -> Tuple[str, str, int]:
    targets = list(dict.fromkeys(target_states))
    if not targets:
        raise ValueError("Список целевых состояний пуст.")
    if sigma_bits:
        args = [
            "link-sigma-stdin", prefix_state, str(N), str(truncate_bits), str(rounds),
            str(trials_limit), str(threads), str(len(targets)), str(sigma_bits),
            str(current_sigma), str(target_sigma),
        ]
    else:
        args = [
            "link-stdin", prefix_state, str(N), str(truncate_bits), str(rounds),
            str(trials_limit), str(threads), str(len(targets)),
        ]
    if seed is not None:
        args += ["--seed", str(seed)]
    parts = _run(args, input_text="\n".join(targets))
    if len(parts) != 3:
        raise RuntimeError("Некорректный ответ команды link.")
    block, state, queries = parts
    return block, state, int(queries)


def cpp_sample_transitions(
    states: Iterable[str],
    samples_per_state: int,
    N: int,
    truncate_bits: int,
    rounds: int,
    threads: int = 0,
    *,
    sigma_bits: int = 0,
    current_sigma: int = 0,
    target_sigma: int = 0,
    seed: int | None = None,
) -> list[list[tuple[str, str]]]:
    states = list(states)
    if not states:
        raise ValueError("Список состояний пуст.")
    if samples_per_state <= 0:
        raise ValueError("samples_per_state должен быть положительным.")
    if sigma_bits:
        args = [
            "sample-sigma-stdin", str(len(states)), str(samples_per_state), str(N),
            str(truncate_bits), str(rounds), str(threads), str(sigma_bits),
            str(current_sigma), str(target_sigma),
        ]
    else:
        args = [
            "sample-stdin", str(len(states)), str(samples_per_state), str(N),
            str(truncate_bits), str(rounds), str(threads),
        ]
    if seed is not None:
        args += ["--seed", str(seed)]
    parts = _run(args, input_text="\n".join(states))
    expected = len(states) * samples_per_state * 2
    if len(parts) != expected:
        raise RuntimeError(
            "Некорректный ответ команды sample: "
            f"ожидалось {expected} значений, получено {len(parts)}."
        )
    result: list[list[tuple[str, str]]] = []
    cursor = 0
    for _ in states:
        vertex_samples = []
        for _ in range(samples_per_state):
            vertex_samples.append((parts[cursor], parts[cursor + 1]))
            cursor += 2
        result.append(vertex_samples)
    return result


def cpp_quantum_layer(
    states: Iterable[str],
    table_messages: int,
    search_messages: int,
    layer_bits: int,
    N: int,
    truncate_bits: int,
    rounds: int,
    seed: int,
    threads: int = 0,
    *,
    sigma_bits: int = 0,
    current_sigma: int = 0,
    target_sigma: int = 0,
    method="grover_fixed",
    bbht_options=None,
) -> CppQuantumLayerResult:
    states = list(states)
    if not states:
        raise ValueError("Список состояний пуст.")
    if sigma_bits:
        args = [
            "quantum-layer-sigma-stdin", str(len(states)), str(table_messages),
            str(search_messages), str(layer_bits), str(N), str(truncate_bits),
            str(rounds), str(seed), str(threads), str(sigma_bits),
            str(current_sigma), str(target_sigma),
        ]
    else:
        args = [
            "quantum-layer-stdin", str(len(states)), str(table_messages),
            str(search_messages), str(layer_bits), str(N), str(truncate_bits),
            str(rounds), str(seed), str(threads),
        ]
    from algorithms.search_methods import BBHTOptions, SearchMethod, search_method
    selected = search_method(method)
    if selected is SearchMethod.CLASSICAL:
        raise ValueError("Квантовый вызов требует фиксированного Гровера или BBHT.")
    if selected is SearchMethod.GROVER_BBHT:
        options = bbht_options or BBHTOptions()
        options.validate()
        args = ["bbht-layer-stdin", str(len(states)), str(table_messages), str(search_messages),
                str(layer_bits), str(N), str(truncate_bits), str(rounds), str(seed), str(threads),
                str(sigma_bits), str(current_sigma), str(target_sigma)]
        args += [str(options.growth), str(options.max_attempts), str(options.max_oracle_queries),
                 str(options.dense_max_states), str(options.max_stage_seconds)]
    parts = _run(args, input_text="\n".join(states))
    parts, adaptive = _search_diagnostics(parts)
    if 'AMP' in parts:
        marker = parts.index('AMP')
        if len(parts) != marker + 2 or parts[-1] not in ('dense', 'symmetric'):
            raise RuntimeError('Некорректный тип моделирования амплитуд.')
        adaptive['amplitude_backend'] = parts[-1]
        parts = parts[:marker]
    if 'BBHT' in parts:
        marker = parts.index('BBHT')
        values = parts[marker + 1:]
        if len(values) != 5:
            raise RuntimeError('Некорректная статистика BBHT.')
        adaptive.update(phase_oracle_queries=int(values[0]), verification_queries=int(values[1]),
                        failed_attempts=int(values[2]), search_attempts=int(values[3]), amplitude_backend=values[4])
        parts = parts[:marker]

    if len(parts) < 5:
        raise RuntimeError("Некорректный заголовок ответа quantum-layer.")
    oracle_queries, simulator_evaluations, qram_entries, successes, edge_count = (
        int(value) for value in parts[:5]
    )
    payload = parts[5:]
    if 'SV' not in payload:
        raise RuntimeError('C++-ядро не вернуло статистику вектора амплитуд.')
    marker = payload.index('SV')
    extra = payload[marker + 1:]
    payload = payload[:marker]
    if len(extra) != 8:
        raise RuntimeError('Некорректная статистика quantum-layer statevector.')
    if len(payload) != edge_count * 5:
        raise RuntimeError(
            "Некорректный ответ quantum-layer: "
            f"ожидалось {edge_count * 5} полей рёбер, получено {len(payload)}."
        )
    edges = []
    for offset in range(0, len(payload), 5):
        left, right, left_block, right_block, common = payload[offset:offset + 5]
        edges.append((int(left), int(right), left_block, right_block, common))
    adaptive.setdefault('phase_oracle_queries', int(extra[1]))
    adaptive.setdefault('verification_queries', int(extra[4]))
    adaptive.setdefault('failed_attempts', int(extra[2]) - successes)
    adaptive.setdefault('search_attempts', int(extra[2]))
    return CppQuantumLayerResult(
        **adaptive,
        edges=edges,
        oracle_queries=oracle_queries,
        simulator_evaluations=simulator_evaluations,
        qram_entries=qram_entries,
        grover_successes=successes,
        statevector_elements_processed=int(extra[0]), statevector_iterations=int(extra[1]),
        grover_attempts=int(extra[2]), marked_elements=int(extra[3]), verification_evaluations=int(extra[4]),
        success_probability_sum=float(extra[5]), statevector_norm_error_max=float(extra[6]), statevector_seconds=float(extra[7]),
    )


def cpp_quantum_link(
    prefix_state: str,
    target_states: Iterable[str],
    search_messages: int,
    N: int,
    truncate_bits: int,
    rounds: int,
    seed: int,
    threads: int = 0,
    *,
    sigma_bits: int = 0,
    current_sigma: int = 0,
    target_sigma: int = 0,
    method="grover_fixed",
    bbht_options=None,
) -> CppQuantumLinkResult:
    targets = list(dict.fromkeys(target_states))
    if not targets:
        raise ValueError("Список целевых состояний пуст.")
    if sigma_bits:
        args = [
            "quantum-link-sigma-stdin", prefix_state, str(len(targets)),
            str(search_messages), str(N), str(truncate_bits), str(rounds),
            str(seed), str(threads), str(sigma_bits), str(current_sigma),
            str(target_sigma),
        ]
    else:
        args = [
            "quantum-link-stdin", prefix_state, str(len(targets)),
            str(search_messages), str(N), str(truncate_bits), str(rounds),
            str(seed), str(threads),
        ]
    from algorithms.search_methods import BBHTOptions, SearchMethod, search_method
    selected = search_method(method)
    if selected is SearchMethod.CLASSICAL:
        raise ValueError("Квантовый вызов требует фиксированного Гровера или BBHT.")
    if selected is SearchMethod.GROVER_BBHT:
        options = bbht_options or BBHTOptions()
        options.validate()
        args = ["bbht-link-stdin", prefix_state, str(len(targets)), str(search_messages), str(N),
                str(truncate_bits), str(rounds), str(seed), str(threads), str(sigma_bits),
                str(current_sigma), str(target_sigma)]
        args += [str(options.growth), str(options.max_attempts), str(options.max_oracle_queries),
                 str(options.dense_max_states), str(options.max_stage_seconds)]
    parts = _run(args, input_text="\n".join(targets))
    parts, adaptive = _search_diagnostics(parts)
    if 'AMP' in parts:
        marker = parts.index('AMP')
        if len(parts) != marker + 2 or parts[-1] not in ('dense', 'symmetric'):
            raise RuntimeError('Некорректный тип моделирования амплитуд.')
        adaptive['amplitude_backend'] = parts[-1]
        parts = parts[:marker]
    if 'BBHT' in parts:
        marker = parts.index('BBHT')
        values = parts[marker + 1:]
        if len(values) != 5:
            raise RuntimeError('Некорректная статистика BBHT.')
        adaptive.update(phase_oracle_queries=int(values[0]), verification_queries=int(values[1]),
                        failed_attempts=int(values[2]), search_attempts=int(values[3]), amplitude_backend=values[4])
        parts = parts[:marker]

    if 'SV' not in parts:
        raise RuntimeError('C++-ядро не вернуло статистику вектора амплитуд.')
    marker = parts.index('SV')
    extra = parts[marker + 1:]
    parts = parts[:marker]
    if len(extra) != 4:
        raise RuntimeError('Некорректная статистика quantum-link statevector.')
    if len(parts) not in (6, 8):
        raise RuntimeError("Некорректный ответ команды quantum-link.")
    found = parts[0] == "1"
    if found != (len(parts) == 8):
        raise RuntimeError("Флаг и payload команды quantum-link не согласованы.")
    adaptive.setdefault('phase_oracle_queries', int(extra[1]))
    adaptive.setdefault('verification_queries', int(extra[2]))
    adaptive.setdefault('failed_attempts', 0 if found else 1)
    adaptive.setdefault('search_attempts', 1)
    return CppQuantumLinkResult(
        **adaptive,
        block=parts[6] if found else None,
        target_state=parts[7] if found else None,
        oracle_queries=int(parts[1]),
        simulator_evaluations=int(parts[2]),
        marked_count=int(parts[3]),
        success_probability=float(parts[4]),
        norm_error=float(parts[5]),
        statevector_elements_processed=int(extra[0]), statevector_iterations=int(extra[1]),
        verification_evaluations=int(extra[2]), statevector_seconds=float(extra[3]),
    )
