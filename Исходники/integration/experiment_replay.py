"""Восстанавливает параметры повторного запуска из записи и исходных результатов."""

from dataclasses import dataclass,fields
import json
from pathlib import Path
from uuid import uuid4

from algorithms.search_methods import BBHTOptions,SearchMethod,search_method
from algorithms.diamond import diamond_to_json_dict,validate_diamond_data
from .backend_adapter import BuildRequest
from .experiment_store import PROJECT_ROOT, diamond_digest
from .project_paths import resolve_project_input,DATA_ROOT


def resolve_source(name):
    path = resolve_project_input(name)
    if path.is_file():
        return path
    for folder in ("experiments", "data"):
        if folder in path.parts:
            for root in (DATA_ROOT,PROJECT_ROOT):
                candidate = root.joinpath(*path.parts[path.parts.index(folder):])
                if candidate.is_file():return candidate
    return None


@dataclass
class ReplayPlan:
    entry: object
    request: BuildRequest | None
    attack: dict | None
    data: dict | None
    source: Path | None


def _report_run(entry,source):
    """Находит исходный запуск в JSONL по сохранённой контрольной сумме записи."""
    expected=entry.metadata.get('source_record_sha256')
    with source.open(encoding='utf-8-sig') as stream:
        for line_number,line in enumerate(stream,1):
            try:raw=json.loads(line)
            except json.JSONDecodeError:continue
            if raw.get('record_type') not in (None,'run_result'):continue
            normalized={key:value for key,value in raw.items() if key not in ('source','source_path','recorded_at')}
            if expected and diamond_digest(normalized)==expected:return raw
            if not expected and line_number==entry.metadata.get('source_line'):
                data=raw.get('aggregate',raw)
                if (data.get('n'),data.get('k'))==(entry.record.n,entry.record.k):return raw
    raise ValueError('Исходная запись эксперимента не найдена в журнале JSONL.')


def _report_diamond(raw,record):
    schedule=raw.get('sigma_schedule',[])
    if len(schedule)!=record.k+1 or len(raw.get('layers',[]))!=record.k:
        raise ValueError('В журнале нет завершённой алмазной структуры для повторного поиска.')
    stats={'sigma_bits':record.sigma_bits,'leaf_sigma':schedule[0]}
    stats.update((f'sigma_level_{i}',value) for i,value in enumerate(schedule[1:],1))
    structure=[[(edge['h_left'],edge['h_right'],edge['m_link_left'],edge['m_link_right'],edge['h_common'])
                for edge in layer['matched_edges']] for layer in raw['layers']]
    data=diamond_to_json_dict([('',h) for h in raw['leaves']],structure,record.n,record.k,
                             record.rounds,record.prefix_blocks,stats,record.sigma_bits)
    method=search_method(record.build_method or record.method);data['seed']=raw.get('seed')
    if method.is_quantum:data['builder']=method.storage_id
    validate_diamond_data(data)
    return data


def _bbht_options(record,parameters):
    if search_method(record.method) is not SearchMethod.GROVER_BBHT:return None
    values=dict(parameters);values.update(json.loads(record.search_configuration) if record.search_configuration else {})
    for old,new in (('max_queries','max_oracle_queries'),('dense_max_S','dense_max_states'),('stage_timeout','max_stage_seconds')):
        if new not in values and old in values:values[new]=values[old]
    return BBHTOptions(**{f.name:values[f.name] for f in fields(BBHTOptions) if values.get(f.name) is not None})


def prepare_replay(entry, store, adapter):
    record, metadata = entry.record, entry.metadata
    parameters = metadata.get("parameters", {})
    source = resolve_source(entry.source)
    data = None
    report=_report_run(entry,source) if source and source.suffix.lower()=='.jsonl' else None
    if source and report is None:
        loaded = adapter.load_json(source)
        if not entry.source_digest or diamond_digest(loaded) == entry.source_digest:
            data = loaded
    options = _bbht_options(record,parameters)
    seed = metadata.get("seed")
    threads = int(metadata.get("threads") or 0)
    if report is not None and record.experiment_type=='herding':
        data=_report_diamond(report,record)
        source=store.local_path.parent/'repeats'/uuid4().hex/'diamond.json'
        source.parent.mkdir(parents=True,exist_ok=True)
        source.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    if record.experiment_type in ('diamond','full'):
        original = metadata.get("build_request", {})
        request = BuildRequest(
            original.get("method",record.method), record.k, record.n, record.prefix_blocks, record.rounds,
            int(original.get("trials_limit", parameters.get("trials_limit", 1_000_000_000))),
            store.local_path.parent / "repeats" / uuid4().hex,
            sigma_bits=record.sigma_bits,
            sigma_seed=int(original.get("sigma_seed", parameters.get("sigma_seed", seed if metadata.get("campaign") and seed is not None else 0))),
            seed=original.get("seed", data.get("seed", seed) if data else seed),
            threads=int(original.get("threads", threads)), use_cpp=original.get("use_cpp"),
            parameter_strategy=record.parameter_strategy,
            target_probability=record.target_probability if record.target_probability is not None else .95,
            bbht_options=options,
        )
        adapter.validate_request(request)
        attack=None
        if record.experiment_type=='full':
            saved=metadata.get('replay_attack',{})
            text=saved.get('description',parameters.get('prefix_text'))
            if text is None:raise ValueError('В журнале не сохранён текст префикса полной атаки.')
            attack=dict(operation='attack',description=text,event_result=saved.get('event_result',''),
                        trials_limit=int(record.attack_trials_limit or parameters.get('link_trials_limit',request.trials_limit)),
                        method=record.method,seed=saved.get('seed') if saved.get('seed') is not None else seed,
                        threads=threads,bbht_options=options.__dict__ if options else None)
        return ReplayPlan(entry, request, attack, data, source)
    if data is None:
        for candidate in store.entries:
            if candidate.source_digest == entry.source_digest:
                candidate_path = resolve_source(candidate.source)
                if candidate_path and candidate_path.suffix.lower()!='.jsonl':
                    loaded = adapter.load_json(candidate_path)
                    if diamond_digest(loaded) == entry.source_digest:
                        source, data = candidate_path, loaded
                        break
    if data is None:
        raise ValueError("Для повтора атаки не найдена исходная алмазная структура с совпадающей контрольной суммой файла.")
    payload = metadata.get("replay_attack")
    if payload is None and report is not None and parameters.get('prefix_text') is not None:
        payload=dict(description=parameters['prefix_text'],event_result='',seed=seed)
    if payload is None:
        attack_path = resolve_source(metadata.get("attack_result", ""))
        if attack_path:
            payload = json.loads(attack_path.read_text(encoding="utf-8"))
    if payload is None or not all(key in payload for key in ("description", "event_result")):
        raise ValueError("В старой записи не сохранён текст префикса и события; точный повтор этой атаки невозможен.")
    limit = record.attack_trials_limit or parameters.get("link_trials_limit") or (1_000_000_000 if report is not None else None)
    if limit is None:
        raise ValueError("В записи не сохранён лимит поиска связующего блока.")
    replay_seed=next((value for value in (payload.get("seed"),payload.get("link_seed"),seed) if value is not None),None)
    attack = dict(operation="attack", data=data, description=payload["description"], event_result=payload["event_result"],
                  trials_limit=int(limit), method=record.method, seed=replay_seed, threads=threads,
                  bbht_options=options.__dict__ if options else None)
    return ReplayPlan(entry, None, attack, data, source)
