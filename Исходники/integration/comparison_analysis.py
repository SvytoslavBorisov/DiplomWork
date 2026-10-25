"""Группирует измеренные эксперименты и вычисляет статистику научных графиков."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, replace
from functools import lru_cache
import hashlib
import json
import math
from statistics import mean, median, stdev
from typing import Any

from scipy.stats import t as student_t

from algorithms.search_methods import SearchMethod, search_method
from .experiment_store import StoredExperiment
from .result_adapter import ExperimentRecord


SUCCESS = frozenset(("Завершено", "Загружено"))
METHOD_NAMES = {SearchMethod.CLASSICAL: "Классический алгоритм", SearchMethod.GROVER_FIXED: "Фиксированный Гровер", SearchMethod.GROVER_BBHT: "BBHT"}
GRAPH_TITLES = {
    "queries_n": "Зависимость запросной сложности от размера части хэш-кода",
    "speedup": "Запросное квантовое ускорение от размера части хэш-кода",
    "evaluations_n": "Зависимость числа вычислений функции сжатия от размера части хэш-кода",
    "runtime_n": "Зависимость времени выполнения от размера части хэш-кода",
    "sigma": "Влияние размера части контрольной суммы на вычислительную сложность",
    "depth": "Зависимость вычислительной сложности от глубины алмазной структуры",
    "theory": "Теоретический порядок и экспериментальная запросная сложность",
}
METRIC_UNITS = {"queries": "Запросы Q", "evaluations": "Вычисления g", "runtime": "Время, с", "memory": "Пиковых записей qRAM"}
STAGES = {"diamond": "Построение алмазной структуры", "herding": "Поиск связующего блока", "full": "Полная herding-атака"}


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def finite_nonnegative(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def counter(record):
    return record.link_N if record.experiment_type in ("herding", "full") else record.first_level_N


def metric_value(record, metric):
    if metric == "queries":
        value = record.quantum_oracle_queries if record.is_quantum else record.algorithmic_queries
    elif metric == "evaluations":
        value = record.quantum_simulator_hash_evaluations if record.is_quantum else (
            record.compression_calls if record.compression_calls is not None else record.algorithmic_queries)
    elif metric == "runtime":
        value = record.elapsed_seconds
    else:
        value = record.quantum_qram_peak_entries if record.is_quantum else None
    return value if finite_nonnegative(value) else None


@dataclass(frozen=True)
class Summary:
    count: int = 0
    mean: float | None = None
    median: float | None = None
    minimum: float | None = None
    maximum: float | None = None
    stddev: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None


@lru_cache(maxsize=8192)
def summarize(values: tuple[float, ...]) -> Summary:
    if not values:
        return Summary()
    center = mean(values)
    deviation = stdev(values) if len(values) >= 2 else None
    margin = float(student_t.ppf(.975, len(values)-1)) * deviation / math.sqrt(len(values)) if deviation is not None else None
    return Summary(len(values), center, median(values), min(values), max(values), deviation,
                   center-margin if margin is not None else None, center+margin if margin is not None else None)


@dataclass(frozen=True)
class Observation:
    uid: str
    record: ExperimentRecord
    metadata: dict = field(compare=False, hash=False, default_factory=dict)
    sources: tuple[str, ...] = ()


@dataclass(frozen=True)
class AnalysisOptions:
    graph: str = "queries_n"
    metric: str = "queries"
    axis: str = "n"
    presentation: str = "complexity"
    aggregation: str = "mean"
    stage: str | None = "diamond"
    methods: tuple[str, ...] = tuple(method.value for method in SearchMethod)
    n_min: int = 1
    n_max: int = 512
    k_min: int = 1
    k_max: int = 20
    filters: tuple[tuple[str, str], ...] = ()
    comparable_only: bool = False
    logarithmic: bool = False
    uncertainty: str = "ci"
    theory_ratio: bool = False
    search: str = ""

    @property
    def effective_axis(self):
        if self.presentation=="speedup":return "n"
        return {"sigma": "s", "depth": "k"}.get(self.graph, self.axis if self.graph in ("theory","dispersion") else "n")

    @property
    def effective_metric(self):
        if self.presentation == "speedup" or self.graph == "theory":
            return "queries"
        return {"queries_n": "queries", "evaluations_n": "evaluations", "runtime_n": "runtime"}.get(self.graph, self.metric)


@dataclass
class Aggregate:
    identity: str
    method: SearchMethod
    x: int
    configuration: dict
    profile: dict
    summary: Summary
    observations: tuple[Observation, ...]
    values: tuple[float, ...]
    successful: int
    failed: int
    interrupted: int
    skipped: int
    missing: int
    common_key: str
    series_key: str
    value: float | None
    ci_low: float | None = None
    ci_high: float | None = None
    baseline: str | None = None
    theory: float | None = None
    theory_note: str = ""
    reference_ids: tuple[str, ...] = ()
    baseline_mean: float | None = None
    baseline_count: int = 0

    @property
    def total(self):
        return len(self.observations)

    @property
    def success_rate(self):
        return self.successful/self.total if self.total else None

    @property
    def source_ids(self):
        return tuple(dict.fromkeys([uid for item in self.observations for uid in (item.sources or (item.uid,))]+list(self.reference_ids)))


@dataclass
class AnalysisResult:
    options: AnalysisOptions
    groups: tuple[Aggregate, ...]
    observations: tuple[Observation, ...]
    notices: tuple[str, ...] = ()
    invalid: int = 0
    basis: tuple[Aggregate, ...] = ()

    @property
    def plotted(self):
        return tuple(group for group in self.groups if (group.summary.median if self.options.presentation=="dispersion" else group.value) is not None and (
            not self.options.logarithmic or (group.summary.median if self.options.presentation=="dispersion" else group.value) > 0))


def field_value(observation, key):
    record, metadata = observation.record, observation.metadata
    parameters = metadata.get("parameters") or metadata.get("build_request") or {}
    direct = {"n": record.n, "k": record.k, "s": record.sigma_bits, "N": counter(record),
              "rounds": record.rounds, "prefix_blocks": record.prefix_blocks, "stage": record.experiment_type,
              "model": record.model, "version": record.measurement_version,
              "strategy": record.parameter_strategy if record.is_quantum else None,
              "probability": record.target_probability if record.is_quantum else None,
              "profile": record.search_configuration if record.is_quantum else None,
              "protocol": record.search_protocol,
              "amplitude": record.amplitude_backend if record.is_quantum else None,
              "scenario": (str(metadata.get("campaign", "")) + "/" + str(metadata.get("group", ""))) if metadata.get("campaign") else "отдельный запуск",
              "threads": metadata.get("threads", parameters.get("threads")),
              "hardware": metadata.get("hardware", metadata.get("platform")),
              "limit": record.attack_trials_limit if record.experiment_type != "diamond" else parameters.get("trials_limit")}
    return direct[key]


def common_configuration(item, metric):
    record, meta = item.record, item.metadata
    config = {key: field_value(item, key) for key in ("n", "k", "s", "N", "rounds", "prefix_blocks", "stage", "model", "version", "scenario", "limit")}
    config.update(first_level_N=record.first_level_N, link_N=record.link_N,
                  code_revision=meta.get("code_sha256"), model_revision=meta.get("model_revision"), protocol=record.search_protocol)
    campaign = bool(meta.get("campaign") and meta.get("group"))
    if record.experiment_type in ("herding", "full"):
        config["input_policy"] = "campaign_ensemble" if campaign else "literal_input"
        if not campaign:
            config.update(diamond=record.attack_diamond_digest, prefix=record.attack_prefix_state,
                          message=record.attack_message_digest, sigma_schedule=record.sigma_schedule)
        elif record.experiment_type != "full":
            config["build_scenario"] = meta.get("builder", record.build_method)
    if metric == "runtime":
        config["execution"] = {key: meta.get(key) for key in (
            "platform", "hardware", "logical_cpus", "threads", "classical_threads", "backend", "python", "qram_impl", "blackburn_backend")}
    return config


def method_profile(item):
    record = item.record
    profile = {"build_method": record.build_method if record.experiment_type == "full" else "",
               "search_configuration": record.search_configuration,
               "attempt_policy": item.metadata.get("attempt_policy", "unknown"),
               "threads": field_value(item, "threads")}
    if record.is_quantum:
        profile.update(amplitude_backend=record.amplitude_backend, parameter_strategy=record.parameter_strategy,
                       target_probability=record.target_probability if record.parameter_strategy != "theoretical" else None)
    return profile


def compatible_profiles(classical, quantum):
    return classical.profile.get("threads") == quantum.profile.get("threads")


def theory_order(record):
    if record.sigma_bits:
        return None, "Для s > 0 обоснованная численная теоретическая линия отсутствует."
    if record.experiment_type == "full":
        return None, "Для полной атаки единый теоретический порядок не задан."
    if search_method(record.method) is SearchMethod.GROVER_BBHT:
        return None, "BBHT: порядок поиска не задаёт константы полной процедуры построения и повторов."
    if record.is_quantum and record.parameter_strategy!="theoretical":
        return None, "Для адаптивного подбора параметров отдельная теоретическая форма не обоснована."
    n, k = record.n, record.k
    if record.experiment_type == "diamond":
        if record.is_quantum and k>=n:return None,"Теорема для улучшенного построения требует k < n."
        value = math.sqrt(k)*2**((n+k)/2) if not record.is_quantum else k**(1/3)*2**((n+2*k)/3)
        expression = "√k · 2^((n+k)/2)" if not record.is_quantum else "k^(1/3) · 2^((n+2k)/3)"
    else:
        value = 2**((n-k)/(2 if record.is_quantum else 1))
        expression = "2^((n−k)/2)" if record.is_quantum else "2^(n−k)"
    return value, "Асимптотическая форма " + expression + "; множитель 1, не предсказание числа запросов."


class ComparisonAnalysis:
    def __init__(self):
        self.observations = ()
        self.entries = {}
        self.invalid = 0
        self._cache = {}
        self.generation = 0
        self._full_cache=None

    def set_entries(self, entries):
        observations = []
        self.invalid = 0
        self.entries = {}
        for entry in entries:
            record = entry.record
            try:
                search_method(record.method)
                valid = record.n > 0 and record.k > 0 and record.sigma_bits >= 0 and record.rounds > 0 and record.prefix_blocks > 0
            except (ValueError, TypeError):
                valid = False
            if not valid:
                self.invalid += 1
                continue
            self.entries[entry.identity] = entry
            observations.append(Observation(entry.identity, record, entry.metadata, (entry.identity,)))
        self.observations = tuple(observations)
        self.generation += 1
        self._cache.clear()
        self._full_cache=None

    def set_records(self, records):
        self.set_entries([StoredExperiment(f"session:{id(record)}", record, "") for record in records])

    def full_observations(self):
        if self._full_cache is not None:return self._full_cache
        builds = defaultdict(list)
        for item in self.observations:
            entry = self.entries[item.uid]
            if item.record.experiment_type == "diamond" and entry.source_digest:
                builds[entry.source_digest].append(item)
        combined = [item for item in self.observations if item.record.experiment_type == "full"]
        for attack in self.observations:
            record = attack.record
            if record.experiment_type != "herding" or not record.attack_diamond_digest:
                continue
            if attack.metadata.get("run_id") and any(item.metadata.get("run_id") == attack.metadata["run_id"] for item in combined):
                continue
            candidates = builds.get(record.attack_diamond_digest, [])
            task_id = attack.metadata.get("diamond_task")
            if task_id:
                candidates = [item for item in candidates if item.metadata.get("task_id") == task_id]
            if len(candidates) != 1:
                continue
            build = candidates[0]
            if (build.record.n,build.record.k,build.record.sigma_bits,build.record.rounds,build.record.prefix_blocks,build.record.model,build.record.measurement_version,build.record.first_level_N,build.record.link_N,build.record.sigma_schedule) != (
                record.n,record.k,record.sigma_bits,record.rounds,record.prefix_blocks,record.model,record.measurement_version,record.first_level_N,record.link_N,record.sigma_schedule):
                continue
            values = {}
            for metric, name in (("queries", "quantum_oracle_queries" if record.is_quantum else "collision_queries"),
                                 ("evaluations", "quantum_simulator_hash_evaluations" if record.is_quantum else "compression_calls"),
                                 ("runtime", "elapsed_seconds")):
                a,b=metric_value(build.record,metric),metric_value(record,metric)
                values[name]=a+b if a is not None and b is not None else None
            if build.record.is_quantum != record.is_quantum or search_method(build.record.method) != search_method(record.method):
                continue
            success=build.record.status in SUCCESS and record.status in SUCCESS
            full=replace(record,experiment_type="full",blackburn_transition_queries=None,
                         status="Завершено" if success else "Ошибка",**values)
            metadata=dict(attack.metadata,linked_build=build.uid,linked_attack=attack.uid,
                          cost_policy="construction_plus_link_per_attack")
            combined.append(Observation(f"full:{build.uid}:{attack.uid}",full,metadata,(build.uid,attack.uid)))
        self._full_cache=tuple(combined)
        return self._full_cache

    def suggested_cohort(self,options):
        axis,metric=options.effective_axis,options.effective_metric
        groups=defaultdict(list)
        items=self.full_observations() if options.stage=="full" else self.observations
        for item in items:
            record=item.record
            if record.experiment_type!=options.stage or search_method(record.method).value not in options.methods:continue
            if any(canonical(field_value(item,key)) != value for key,value in options.filters if key in ('protocol','scenario')):continue
            if not options.n_min<=record.n<=options.n_max or not options.k_min<=record.k<=options.k_max:continue
            if options.graph=="theory" and options.presentation!="speedup" and record.sigma_bits:continue
            config=common_configuration(item,metric);config.pop(axis,None)
            if axis in ("k","s"):config.pop("sigma_schedule",None)
            groups[canonical(config)].append(item)
        if not groups:return None
        members=max(groups.values(),key=lambda group:(len({field_value(item,axis) for item in group}),
                                                     len({search_method(item.record.method) for item in group}),len(group)))
        return members[0]

    def available_values(self, key, stage=None):
        items=self.full_observations() if stage=="full" else self.observations
        values={canonical(field_value(item,key)):field_value(item,key) for item in items if stage is None or item.record.experiment_type==stage}
        return tuple(sorted(values.values(),key=lambda value:(value is None,str(type(value)),value if isinstance(value,(int,float)) else str(value))))

    def analyze(self, options: AnalysisOptions):
        if options.theory_ratio and (options.graph!="theory" or options.presentation!="complexity"):
            options=replace(options,theory_ratio=False)
        if options in self._cache:
            return self._cache[options]
        axis, metric = options.effective_axis, options.effective_metric
        items = self.full_observations() if options.stage == "full" else self.observations
        selected=[]
        import re
        params=re.findall(r"([nksN]):\s*(\d+)",options.search)
        words=re.sub(r"[nksN]:\s*\d+","",options.search).casefold().split()
        for item in items:
            record=item.record
            if options.stage and record.experiment_type != options.stage:continue
            if search_method(record.method).value not in options.methods:continue
            if not options.n_min <= record.n <= options.n_max or not options.k_min <= record.k <= options.k_max:continue
            if any((key != axis or options.graph=='components') and not (key=='k' and options.graph=='optimal') and canonical(field_value(item,key)) != value for key,value in options.filters
                   if key not in ("strategy","probability","profile","amplitude") or record.is_quantum):continue
            if any(field_value(item,key)!=int(value) for key,value in params):continue
            text=f"{record.method_label} {record.stage_label} {record.status} {'Успешно' if record.status in SUCCESS else ''}".casefold()
            if any(word not in text for word in words):continue
            selected.append(item)
        grouped=defaultdict(list)
        configs={}
        for item in selected:
            config=common_configuration(item,metric)
            profile=method_profile(item)
            x=field_value(item,axis)
            series=dict(config)
            series.pop(axis,None)
            if axis=="k":
                series.pop("sigma_schedule",None)
            if axis=="s":
                series.pop("sigma_schedule",None)
            common=canonical(config)
            key=(canonical(series),search_method(item.record.method),canonical(profile),x,common)
            grouped[key].append(item);configs[key]=(config,profile)
        aggregates=[]
        for key,members in grouped.items():
            series,method,profile_json,x,common=key
            config,profile=configs[key]
            successful=[item for item in members if item.record.status in SUCCESS]
            values=tuple(value for item in successful if (value:=metric_value(item.record,metric)) is not None)
            summary=summarize(values)
            identity=hashlib.sha256(canonical(key).encode()).hexdigest()[:20]
            value=getattr(summary,options.aggregation)
            group=Aggregate(identity,method,x,config,profile,summary,tuple(members),values,len(successful),
                            sum(item.record.status not in SUCCESS and item.record.status not in ("Остановлено","Отменено","Пропущено") for item in members),
                            sum(item.record.status in ("Остановлено","Отменено") for item in members),
                            sum(item.record.status=="Пропущено" for item in members),len(successful)-len(values),common,
                            canonical((series,method.value,profile_json)),value)
            if options.aggregation=="mean":group.ci_low,group.ci_high=summary.ci_low,summary.ci_high
            if options.graph=="theory":
                group.theory,group.theory_note=theory_order(members[0].record)
                if options.theory_ratio:
                    group.value=value/group.theory if value is not None and group.theory else None
                    group.ci_low=group.ci_low/group.theory if group.ci_low is not None and group.theory else None
                    group.ci_high=group.ci_high/group.theory if group.ci_high is not None and group.theory else None
            aggregates.append(group)
        if options.comparable_only:
            aggregates=[group for group in aggregates if any(other.method!=group.method and other.common_key==group.common_key and compatible_profiles(group,other) for other in aggregates)]
            visible_ids={item.uid for group in aggregates for item in group.observations}
            selected=[item for item in selected if item.uid in visible_ids]
        notices=[]
        basis=tuple(aggregates)
        if options.presentation=="speedup":
            ratios=[]
            for group in aggregates:
                if group.method is SearchMethod.CLASSICAL:continue
                candidates=[base for base in aggregates if base.method is SearchMethod.CLASSICAL and base.common_key==group.common_key and compatible_profiles(base,group) and base.summary.mean is not None]
                if len(candidates)!=1 or group.summary.mean in (None,0):continue
                base=candidates[0]
                ratio=base.summary.mean/group.summary.mean
                low=high=None
                if base.summary.count>=2 and group.summary.count>=2 and base.summary.mean>0:
                    va=base.summary.stddev**2/base.summary.count/base.summary.mean**2
                    vb=group.summary.stddev**2/group.summary.count/group.summary.mean**2
                    denominator=va*va/(base.summary.count-1)+vb*vb/(group.summary.count-1)
                    df=(va+vb)**2/denominator if denominator else min(base.summary.count,group.summary.count)-1
                    radius=float(student_t.ppf(.975,df))*math.sqrt(va+vb)
                    low,high=ratio*math.exp(-radius),ratio*math.exp(radius)
                ratios.append(replace(group,identity=group.identity+":ratio",value=ratio,ci_low=low,ci_high=high,baseline=base.identity,
                                      reference_ids=base.source_ids,baseline_mean=base.summary.mean,baseline_count=base.summary.count,
                                      series_key=group.series_key+base.series_key))
            if not ratios:notices.append("Недостаточно сопоставимых данных: нужна единственная классическая база и ненулевое среднее Q квантового метода.")
            aggregates=ratios
        if options.graph=="theory":
            notices.extend(dict.fromkeys(group.theory_note for group in aggregates if group.theory is None))
            notices.append("Пунктир: асимптотическая форма с множителем 1; это не точное предсказание Q и не эмпирическая подгонка.")
        if any(item.record.is_quantum for item in selected):
            notices.append("Время квантовых методов — время классического симулятора; Q относится к запросной модели.")
        if any(item.record.status not in SUCCESS for item in selected):
            notices.append("Статистика условна по успешным завершениям; ошибки и прерывания показаны отдельно.")
        if metric=="runtime" and any(field_value(item,"threads") is None or field_value(item,"hardware") is None for item in selected):
            notices.append("Часть условий исполнения не записана; неизвестные и известные конфигурации не объединяются.")
        if any(group.ci_low is not None for group in aggregates):
            notices.append("95% ДИ предполагает независимые повторы; для медианы ДИ не рассчитывается.")
        if options.logarithmic and options.uncertainty=="ci" and any(group.ci_low is not None and group.ci_low<=0 for group in aggregates):
            notices.append("Интервалы, пересекающие ноль, не изображаются целиком в логарифмической шкале; границы сохранены в CSV.")
        result=AnalysisResult(options,tuple(sorted(aggregates,key=lambda group:(group.method.value,group.series_key,group.x))),tuple(selected),tuple(dict.fromkeys(notices)),self.invalid,basis)
        if len(self._cache)>=64:self._cache.pop(next(iter(self._cache)))
        self._cache[options]=result
        return result
