"""Связующий слой между неизменяемой практической частью и PySide6 UI."""

from .backend_adapter import BackendAdapter, BuildRequest, BuildResult
from .result_adapter import DiamondGraph, ExperimentRecord, build_diamond_graph

__all__ = [
    "BackendAdapter",
    "BuildRequest",
    "BuildResult",
    "DiamondGraph",
    "ExperimentRecord",
    "build_diamond_graph",
]
