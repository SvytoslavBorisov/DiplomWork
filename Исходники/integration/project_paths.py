"""Задаёт пути проекта независимо от текущего рабочего каталога."""

from datetime import datetime
from functools import lru_cache
import hashlib
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT=Path(__file__).resolve().parents[1]
DATA_ROOT=Path(os.environ['HERDINGLAB_DATA_DIR']) if os.environ.get('HERDINGLAB_DATA_DIR') else Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else PROJECT_ROOT
BUILD_DIR=PROJECT_ROOT/"build"
DIAMONDS_DIR=DATA_ROOT/"data"/"diamonds"
RESOURCE_DIR=PROJECT_ROOT/"ui"/"resources"


def _unique_label():
    return datetime.now().strftime("%Y%m%d_%H%M%S")+"_"+uuid4().hex[:8]


def new_experiment_directory(name):
    """Выделяет отдельный путь для результатов нового экспериментального запуска."""
    return DATA_ROOT/"experiments"/"runs"/name/_unique_label()


def new_diamond_directory():
    """Отделяет новые построения интерфейса от сохранённых алмазных структур."""
    return DIAMONDS_DIR/"generated"/_unique_label()


@lru_cache(maxsize=1)
def _diamond_migrations():
    return json.loads((PROJECT_ROOT/"data/diamond_path_migrations.json").read_text(encoding="utf8"))


def resolve_project_input(name):
    """Восстанавливает прежние пути перенесённых структур без изменения сохранённых баз."""
    path=Path(name)
    if path.is_file():return path
    if not path.name.startswith("diamond_v3_") or path.suffix!=".json":return path
    if len(path.parts)>1 and path.parent.resolve()!=PROJECT_ROOT and path.parent.name!=PROJECT_ROOT.name:return path
    entry=_diamond_migrations().get(path.name)
    if not entry:return path
    candidate=PROJECT_ROOT/entry["target"]
    if not candidate.is_file():return path
    if hashlib.sha256(candidate.read_bytes()).hexdigest()!=entry["sha256"]:
        raise ValueError("Перенесённая структура отличается от сохранённой контрольной суммы.")
    return candidate
