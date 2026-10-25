"""Импортирует завершённые записи JSONL с сохранением происхождения и этапов затрат."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

from algorithms.search_methods import search_method
from .experiment_store import StoredExperiment, diamond_digest
from .result_adapter import ExperimentRecord


def numeric(value):
    """Отклоняет отрицательные, бесконечные и нечисловые измерения."""
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0 else None


def stats_sum(items, name):
    values = [numeric(item.get(name)) for item in items]
    return sum(values) if values and all(value is not None for value in values) else None


def normalize_report(raw, header, source, line, digest):
    """Преобразует один реальный запуск в совместимые записи измеренных этапов."""
    kind = raw.get('record_type')
    if kind in ('campaign', 'run_started'):
        return []
    if 'record' in raw and 'id' in raw:
        return [StoredExperiment.from_dict(raw)]
    if kind not in (None, 'run_result', 'run_interrupted'):
        return []
    data = raw.get('aggregate', raw)
    if not isinstance(data, dict) or not all(key in data for key in ('method', 'n', 'k')):
        return []
    alias = {'bbht':'grover_bbht', 'fixed_single':'grover_fixed', 'fixed_repeated':'grover_fixed'}
    method = search_method(alias.get(data['method'], data['method'])).value
    profile = header.get('profile', {})
    configuration = profile.get('configuration', {})
    protocol = data.get('search_protocol', raw.get('search_protocol', profile.get('search_protocol', 'legacy-v0')))
    policy = data.get('attempt_policy', data['method'] if data['method'] in ('fixed_single','fixed_repeated') else None)
    if not policy:
        policies = {d.get('attempt_policy') for layer in raw.get('layers', []) for attempt in layer.get('attempts', []) for d in attempt.get('search_diagnostics', []) if d.get('attempt_policy')}
        if len(policies) > 1:
            raise ValueError('В одном запуске смешаны политики поиска.')
        policy = next(iter(policies), 'classical' if method == 'classical' else 'bbht_auto' if method == 'grover_bbht' else 'fixed_single' if 'single' in protocol else 'fixed_repeated' if 'repeated' in protocol else 'unknown')
    campaign = header.get('profile_sha256') or (diamond_digest(profile) if profile else raw.get('campaign', 'unlabelled'))
    normalized = {key: value for key, value in raw.items() if key not in ('source', 'source_path', 'recorded_at')}
    explicit = raw.get('run_id') or raw.get('task_id')
    run_id = diamond_digest({'campaign': campaign, 'run_id': explicit}) if explicit else diamond_digest({'campaign': campaign, 'run': normalized})
    interrupted = kind == 'run_interrupted'
    success = data.get('status') in ('success', 'Завершено') and raw.get('verified', True) is not False
    complete = data.get('query_accounting_complete', raw.get('query_accounting_complete', not interrupted)) is True
    layers = raw.get('layers', [])
    attempts = [attempt.get('stats', {}) for layer in layers for attempt in layer.get('attempts', [])]
    searches = [search.get('stats', {}) for search in raw.get('searches', [])]
    stages = {}
    for name, items in (('diamond', attempts), ('herding', searches)):
        stages[name] = dict(queries=stats_sum(items, 'oracle_queries'), evaluations=stats_sum(items, 'classical_gost_evaluations'),
                            seconds=numeric(data.get('build_seconds' if name == 'diamond' else 'link_seconds')),
                            attempts=len(items) if items else None)
    stages['full'] = dict(queries=numeric(data.get('oracle_queries')), evaluations=numeric(data.get('classical_gost_evaluations')),
                          seconds=numeric(data.get('elapsed_seconds', data.get('wall_seconds'))))
    warnings = []
    for metric in ('queries', 'evaluations'):
        a, b, total = (stages[stage][metric] for stage in ('diamond', 'herding', 'full'))
        if a is not None and b is not None:
            if total is not None and total != a + b:
                warnings.append(f'Несогласованные суммарные затраты: {metric}.')
                stages['full'][metric] = None
            elif total is None and complete:
                stages['full'][metric] = a + b
    if not complete:
        stages['full']['queries'] = stages['full']['evaluations'] = None
    meta = dict(campaign=str(campaign), group='jsonl', run_id=run_id, seed=data.get('seed', raw.get('seed', profile.get('seed'))),
                trial=data.get('trial', raw.get('trial')), execution_attempt=raw.get('execution_attempt'),
                protocol=protocol, attempt_policy=policy, query_accounting_complete=complete,
                verified=raw.get('verified'), failure_reason=data.get('failure_reason', raw.get('reason')),
                stages=stages, import_warnings=warnings, parameters=configuration,
                threads=profile.get('threads', configuration.get('threads')), model_revision=raw.get('model'),
                code_sha256=diamond_digest(profile.get('sources', {})) if profile.get('sources') else None,
                source_line=line, source_record_sha256=diamond_digest(normalized),
                independent_replay_evaluations=numeric(data.get('independent_replay_evaluations')),
                depth_policy=data.get('depth_policy', raw.get('depth_policy', configuration.get('depth_policy'))),
                total_classical_evaluations_with_replay=numeric(data.get('total_classical_evaluations_with_replay')))
    entries = []
    for stage in ('diamond', 'herding', 'full'):
        if stage != 'full' and not (attempts if stage == 'diamond' else searches):
            continue
        costs = stages[stage]
        built = len(layers) == int(data['k']) and bool(layers) and bool(layers[-1].get('matched_edges'))
        stage_success = success if stage == 'full' else built if stage == 'diamond' else bool(data.get('link_success', success))
        status = 'Остановлено' if interrupted else 'Завершено' if stage_success else 'Ошибка'
        n, k = int(data['n']), int(data['k'])
        if n < 1 or k < 1:
            raise ValueError('Параметры n и k должны быть положительными.')
        record = ExperimentRecord(method, n, k, int(data.get('prefix_blocks', configuration.get('prefix_blocks', 1))),
                    int(data.get('rounds', configuration.get('rounds', 12))), costs['seconds'], status,
                    collision_queries=costs['queries'] if method == 'classical' else None,
                    quantum_oracle_queries=costs['queries'] if method != 'classical' else None,
                    compression_calls=costs['evaluations'] if method == 'classical' else None,
                    quantum_simulator_hash_evaluations=costs['evaluations'] if method != 'classical' else None,
                    sigma_bits=int(data.get('s', raw.get('s', configuration.get('s', 0)))),
                    experiment_type=stage, model=raw.get('model', ''), measurement_version=protocol,
                    search_protocol=protocol, search_configuration=json.dumps({key: configuration[key] for key in ('growth', 'max_attempts', 'max_queries', 'L_scale', 'S_scale', 'max_link_S', 'max_layer_attempts', 'max_link_batches') if key in configuration}, sort_keys=True),
                    amplitude_backend=data.get('amplitude_backend', 'unknown'),
                    link_N=raw.get('link_N'), first_level_N=raw.get('first_level_N'),
                    build_method=method, link_method=method, link_attempts=data.get('link_batches'))
        entries.append(StoredExperiment(f'jsonl:{run_id}:{stage}', record, str(source), digest,
                        metadata=meta | {'stage_attempts': costs.get('attempts')}))
    return entries


class ReportSynchronizer:
    def __init__(self, store, root):
        self.store, self.root = store, Path(root)

    def sync(self, force=False, cancelled=lambda: False):
        sources = deepcopy(self.store.sync_sources)
        incoming = []
        existing = {entry.identity for entry in self.store.snapshot()} | self.store._deleted_ids
        now = datetime.now(timezone.utc).isoformat()
        reports = []
        for path in sorted(self.root.rglob('*.jsonl')) if self.root.exists() else []:
            if cancelled():
                return dict(cancelled=True, files=0, added=0, reports=[])
            name = str(path.resolve())
            previous = sources.get(name, {})
            try:
                stat = path.stat()
                if not force and previous.get('size') == stat.st_size and previous.get('mtime_ns') == stat.st_mtime_ns:
                    reports.append(previous | {'unchanged': True})
                    continue
                content = path.read_bytes()
                digest = hashlib.sha256(content).hexdigest()
                offset = 0 if force else previous.get('offset', 0)
                if offset > len(content) or hashlib.sha256(content[:offset]).hexdigest() != previous.get('prefix_sha256'):
                    offset = 0
                header = previous.get('header', {}) if offset else {}
                line_number = previous.get('line', 0) if offset else 0
                report = dict(path=name, size=len(content), mtime_ns=stat.st_mtime_ns, sha256=digest,
                              imported=0, duplicates=0, ignored=0, warnings=[], records=list(previous.get('records', [])), synced_at=now)
                tail = content[offset:]
                for encoded in tail.splitlines(keepends=True):
                    if not encoded.endswith(b'\n'):
                        report['warnings'].append('Последняя строка не завершена; ожидается продолжение записи.')
                        break
                    line_number += 1
                    offset += len(encoded)
                    if cancelled():
                        return dict(cancelled=True, files=0, added=0, reports=[])
                    try:
                        raw = json.loads(encoded.decode('utf-8-sig'))
                        if not isinstance(raw, dict):
                            raise ValueError('Строка не является объектом JSON.')
                        if raw.get('record_type') == 'campaign':
                            header = raw
                            continue
                        entries = normalize_report(raw, header, path, line_number, digest)
                        if not entries:
                            report['ignored'] += 1
                        for entry in entries:
                            if entry.identity in existing:
                                report['duplicates'] += 1
                            else:
                                existing.add(entry.identity)
                                incoming.append(entry)
                                report['imported'] += 1
                            if entry.identity not in report['records']:
                                report['records'].append(entry.identity)
                        report['warnings'].extend(f'Строка {line_number}: {message}' for message in (entries[0].metadata.get('import_warnings', []) if entries else []))
                    except (ValueError, TypeError, KeyError, OverflowError) as exc:
                        report['warnings'].append(f'Строка {line_number}: {exc}')
                report.update(offset=offset, prefix_sha256=hashlib.sha256(content[:offset]).hexdigest(), header=header, line=line_number)
                sources[name] = report
                reports.append(report)
            except OSError as exc:
                reports.append(dict(path=name, imported=0, duplicates=0, warnings=[str(exc)]))
        added = self.store.merge_reports(incoming, sources) if incoming or sources != self.store.sync_sources else 0
        return dict(files=len(reports), added=added, runs=len({entry.metadata.get('run_id', entry.identity) for entry in incoming}),
                    synced_at=now, root=str(self.root.resolve()), reports=reports)
