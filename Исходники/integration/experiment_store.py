"""Хранит переносимые записи сравнения на основе проверенных экспериментальных данных."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
from functools import wraps
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .backend_adapter import BackendAdapter
from .result_adapter import ExperimentRecord, QuantumLayerRecord, record_from_attack, record_from_data


from algorithms.statevector_limits import MODEL_REVISION

FORMAT = "herdinglab-experiments-v1"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_PATH = PROJECT_ROOT / "experiments" / "search_policy_v1.json"
if (PROJECT_ROOT/'experiments/minimal.json').is_file():EXAMPLES_PATH=PROJECT_ROOT/'experiments/minimal.json'
if not EXAMPLES_PATH.exists():
    EXAMPLES_PATH = PROJECT_ROOT / 'experiments' / 'thesis_statevector.json'
if not EXAMPLES_PATH.exists():
    EXAMPLES_PATH = PROJECT_ROOT / "experiments" / "examples.json"


def synchronized(method):
    """Последовательно выполняет изменения базы из потоков интерфейса и импорта."""
    @wraps(method)
    def locked(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return locked


def default_local_path() -> Path:
    if os.environ.get('HERDINGLAB_DATA_DIR'):return Path(os.environ['HERDINGLAB_DATA_DIR'])/'experiments.json'
    if getattr(sys,'frozen',False):return Path(sys.executable).resolve().parent/'experiments.json'
    base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / ".local" / "share"))
    return base / "HerdingLab" / "experiments.json"


def diamond_digest(data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class StoredExperiment:
    identity: str
    record: ExperimentRecord
    source: str
    source_digest: str | None = None
    recorded_at: str | None = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.identity,
            "record": self.record.to_storage_dict(),
            "source": self.source,
            "source_sha256": self.source_digest,
            "recorded_at": self.recorded_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, value: dict) -> "StoredExperiment":
        if not isinstance(value, dict) or not isinstance(value.get("record"), dict):
            raise ValueError("Запись базы экспериментов повреждена.")
        raw = dict(value["record"])
        raw["sigma_schedule"] = tuple(raw.get("sigma_schedule", ()))
        raw["quantum_layers"] = tuple(QuantumLayerRecord(**layer) for layer in raw.get("quantum_layers", ()))
        raw["n"] = raw.pop("t") if "t" in raw else raw["n"]
        record = ExperimentRecord(**raw)
        identity = value.get("id")
        if not isinstance(identity, str) or not identity:
            raise ValueError("У записи эксперимента нет идентификатора.")
        if record.n < 1 or record.k < 1 or record.elapsed_seconds is not None and record.elapsed_seconds < 0:
            raise ValueError("В базе есть недопустимые параметры эксперимента.")
        return cls(identity, record, str(value.get("source", "")), value.get("source_sha256"), value.get("recorded_at"), dict(value.get("metadata", {})))


def read_database(path: Path) -> list[StoredExperiment]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("format") != FORMAT or not isinstance(payload.get("entries"), list):
        raise ValueError("Файл не является базой экспериментов HerdingLab.")
    return [StoredExperiment.from_dict(item) for item in payload["entries"]]


class ExperimentStore:
    def __init__(self, examples_path: Path | None = EXAMPLES_PATH, local_path: Path | None = None, *, active_only: bool | None = None) -> None:
        self._lock = threading.RLock()
        self.sync_sources = {}
        self.active_only = False if active_only is None else active_only
        self.examples_path = Path(examples_path) if examples_path is not None else None
        self.local_path = Path(local_path) if local_path is not None else default_local_path()
        self.entries: list[StoredExperiment] = []
        self._local_entries: list[StoredExperiment] = []
        self._ids: set[str] = set()
        self._deleted_ids: set[str] = set()
        self.load_errors: list[str] = []
        self._local_error = None
        if self.examples_path is not None and self.examples_path.exists():
            try:
                for entry in read_database(self.examples_path):
                    self._add(entry)
            except (ValueError,TypeError,KeyError,OSError) as exc:
                self.load_errors.append(f"{self.examples_path.name}: {exc}")
        if self.local_path.exists():
            try:
                incoming=read_database(self.local_path)
                self.sync_sources = json.loads(self.local_path.read_text(encoding="utf-8")).get("sync_sources", {})
                self._deleted_ids = set(json.loads(self.local_path.read_text(encoding="utf-8")).get("deleted_ids", []))
                self.entries = [entry for entry in self.entries if entry.identity not in self._deleted_ids]
                for entry in incoming:
                    if entry.identity in self._deleted_ids:
                        continue
                    self._add(entry)
                    self._local_entries.append(entry)
            except (ValueError,TypeError,KeyError,OSError) as exc:
                self._local_error=f"Повреждена личная база {self.local_path}: {exc}"
                self.load_errors.append(self._local_error)

    @property
    def records(self) -> list[ExperimentRecord]:
        return [entry.record for entry in self.entries]

    def _add(self, entry: StoredExperiment) -> bool:
        if entry.identity in self._deleted_ids:
            return False
        if self.active_only and entry.record.measurement_version != MODEL_REVISION:
            self._ids.add(entry.identity)
            return False
        if entry.identity in self._ids:
            return False
        self._ids.add(entry.identity)
        self.entries.append(entry)
        return True

    def _save_local(self) -> None:
        if self._local_error:
            raise ValueError(self._local_error+". Исходный файл не перезаписан.")
        self.local_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"format": FORMAT, "entries": [entry.to_dict() for entry in self._local_entries], "deleted_ids": sorted(self._deleted_ids), "sync_sources": self.sync_sources}
        temporary = self.local_path.with_name(self.local_path.name + f".{os.getpid()}.tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.local_path)

    @synchronized
    def _persist(self, entry: StoredExperiment) -> bool:
        if not self._add(entry):
            return False
        self._local_entries.append(entry)
        try:
            self._save_local()
        except Exception:
            self._local_entries.pop()
            self.entries.pop()
            self._ids.remove(entry.identity)
            raise
        return True

    def find_record(self, record: ExperimentRecord) -> StoredExperiment | None:
        return next((entry for entry in self.entries if entry.record is record), None)

    @synchronized
    def remove_record(self, record: ExperimentRecord) -> None:
        """Удаляет запись из личной базы, сохраняя исходные исторические файлы."""
        entry = self.find_record(record)
        if entry is None:
            raise ValueError("Эксперимент отсутствует в базе.")
        before = (self.entries[:], self._local_entries[:], self._ids.copy(), self._deleted_ids.copy())
        self.entries = [item for item in self.entries if item.identity != entry.identity]
        self._local_entries = [item for item in self._local_entries if item.identity != entry.identity]
        self._ids.discard(entry.identity)
        self._deleted_ids.add(entry.identity)
        try:
            self._save_local()
        except Exception:
            self.entries, self._local_entries, self._ids, self._deleted_ids = before
            raise

    def add_completed(self, data: dict, elapsed_seconds: float, source: Path,
                      metadata: dict | None = None, identity: str | None = None) -> StoredExperiment:
        record = record_from_data(data, elapsed_seconds, "Завершено")
        if record.measurement_version == MODEL_REVISION:
            metadata = self._measurement_metadata(data.get('seed'), record.is_quantum, metadata)
        entry = StoredExperiment(
            identity or f"run:{uuid4().hex}", record, str(source), diamond_digest(data),
            datetime.now(timezone.utc).isoformat(), metadata or {},
        )
        self._persist(entry)
        return entry

    def add_attack(self, data: dict, result: object, elapsed_seconds: float,
                   source: Path | None, trials_limit: int | None = None,
                   metadata: dict | None = None, identity: str | None = None) -> StoredExperiment:
        digest = diamond_digest(data)
        record = record_from_attack(data, result, elapsed_seconds, digest, trials_limit)
        metadata = self._measurement_metadata(getattr(result, 'link_seed', None), record.is_quantum, metadata)
        metadata.update(build_method=record.build_method, link_method=record.link_method)
        metadata["replay_attack"] = {"description": result.description, "event_result": result.event_result,
                                     "seed": getattr(result, "link_seed", None) if getattr(result, "link_seed", None) is not None else metadata.get("seed")}
        entry = StoredExperiment(
            identity or f"run:{uuid4().hex}", record, str(source) if source else "Алмаз текущей сессии",
            digest, datetime.now(timezone.utc).isoformat(), metadata or {},
        )
        self._persist(entry)
        return entry

    def add_full(self,build,attack,trials_limit,metadata=None):
        """Сохраняет полный повтор после успешного завершения обоих этапов."""
        from .comparison_analysis import metric_value
        digest=diamond_digest(build.data)
        first=record_from_data(build.data,build.elapsed_seconds,'Завершено')
        second=record_from_attack(build.data,attack.result,attack.elapsed_seconds,digest,trials_limit)
        totals={}
        stages={}
        for stage,record in (('diamond',first),('herding',second)):
            stages[stage]={key:metric_value(record,metric) for key,metric in
                           (('queries','queries'),('evaluations','evaluations'),('seconds','runtime'))}
        for key in stages['diamond']:
            values=[stages[stage][key] for stage in ('diamond','herding')]
            totals[key]=sum(values) if all(v is not None for v in values) else None
        record=replace(second,experiment_type='full',elapsed_seconds=totals['seconds'],
                       collision_queries=totals['queries'] if not second.is_quantum else None,
                       quantum_oracle_queries=totals['queries'] if second.is_quantum else None,
                       compression_calls=totals['evaluations'] if not second.is_quantum else None,
                       quantum_simulator_hash_evaluations=totals['evaluations'] if second.is_quantum else None)
        meta=self._measurement_metadata(build.data.get('seed'),record.is_quantum,metadata)
        meta.update(stages=stages|{'full':totals},replay_attack=dict(description=attack.result.description,
                    event_result=attack.result.event_result,
                    seed=attack.result.link_seed if attack.result.link_seed is not None else meta.get('seed')))
        entry=StoredExperiment(f'run:{uuid4().hex}',record,str(build.path),digest,
                               datetime.now(timezone.utc).isoformat(),meta)
        self._persist(entry)
        return entry

    @staticmethod
    def _measurement_metadata(seed, quantum, supplied):
        """Записывает версию, seed и исходники нового измерения вместе с данными backend."""
        metadata = dict(supplied or {})
        if not all(key in metadata for key in ('backend', 'code_sha256', 'model_revision')):
            from .campaign_runner import environment
            metadata = environment(seed) | metadata
        if metadata.get('seed') is None and seed is not None:
            metadata['seed'] = seed
        metadata['statevector_simulation'] = quantum
        from .campaign_runner import MODEL_REVISION as measurement_revision
        metadata['measurement_version'] = measurement_revision
        return metadata

    def add_failure(self, record: ExperimentRecord, metadata: dict,
                    identity: str | None = None) -> StoredExperiment:
        entry = StoredExperiment(identity or f"run:{uuid4().hex}", record, "",
                                 recorded_at=datetime.now(timezone.utc).isoformat(), metadata=metadata)
        self._persist(entry)
        return entry

    def import_diamond(self, path: Path, adapter: BackendAdapter | None = None) -> bool:
        data = (adapter or BackendAdapter()).load_json(path)
        digest = diamond_digest(data)
        if any(entry.record.experiment_type == "diamond" and entry.source_digest == digest
               for entry in self.entries):
            return False
        entry = StoredExperiment(f"diamond:{digest}", record_from_data(data, None, "Загружено"), str(path), digest)
        return self._persist(entry)

    @synchronized
    def import_database(self, path: Path) -> int:
        incoming = read_database(Path(path))
        before = (self.entries[:], self._local_entries[:], self._ids.copy())
        added = 0
        try:
            for entry in incoming:
                if self._add(entry):
                    self._local_entries.append(entry)
                    added += 1
            if added:
                self._save_local()
        except Exception:
            self.entries, self._local_entries, self._ids = before
            raise
        return added

    @synchronized
    def merge_reports(self, incoming, sources):
        """Атомарно сохраняет пакет новых записей и контрольные позиции журналов."""
        before = (self.entries[:], self._local_entries[:], self._ids.copy(), self.sync_sources)
        added = 0
        try:
            for entry in incoming:
                if self._add(entry):
                    self._local_entries.append(entry)
                    added += 1
            self.sync_sources = sources
            self._save_local()
        except Exception:
            self.entries, self._local_entries, self._ids, self.sync_sources = before
            raise
        return added

    @synchronized
    def snapshot(self):
        """Возвращает согласованный снимок списка экспериментов."""
        return list(self.entries)

    def import_file(self, path: Path, adapter: BackendAdapter | None = None) -> int:
        """Импортирует переносимую базу экспериментов или одну алмазную структуру JSON."""
        path = Path(path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and payload.get("format") == FORMAT:
            return self.import_database(path)
        return int(self.import_diamond(path, adapter))
