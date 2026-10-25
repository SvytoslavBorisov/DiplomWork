"""Оценивает память симулятора квантового слоя C++ перед запуском из интерфейса."""

import ctypes
import sys

from algorithms.quantum_diamond import select_layer_parameters
from algorithms.statevector_limits import DENSE_MAX_STATES, layer_other_bytes


def available_physical_memory() -> int | None:
    if sys.platform != "win32":
        return None

    class MemoryStatus(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong),
                   ("total_phys", ctypes.c_ulonglong), ("avail_phys", ctypes.c_ulonglong),
                   ("total_page", ctypes.c_ulonglong), ("avail_page", ctypes.c_ulonglong),
                   ("total_virtual", ctypes.c_ulonglong), ("avail_virtual", ctypes.c_ulonglong),
                   ("avail_extended_virtual", ctypes.c_ulonglong)]

    status = MemoryStatus()
    status.length = ctypes.sizeof(status)
    return status.avail_phys if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)) else None


def quantum_layer_minimum_bytes(
    state_bits: int, depth: int, *, parameter_strategy: str = "theoretical",
    target_probability: float = 0.95,
    dense_max_states: int = DENSE_MAX_STATES,
) -> int:
    """Оценивает qRAM, пакеты кандидатов и выбранное представление амплитуд."""
    minimum = 0
    for bits in range(depth, 0, -1):
        params, _ = select_layer_parameters(
            state_bits, bits, parameter_strategy=parameter_strategy, target_probability=target_probability,
        )
        L, S, V = params.table_messages, params.search_messages, params.vertex_count
        memory = layer_other_bytes(L, S, V, dense_max_states=dense_max_states)
        memory += 9 * S if S <= dense_max_states else 65536
        minimum = max(minimum, memory)
    return minimum


def memory_warning(
    state_bits: int, depth: int, available: int | None, *,
    parameter_strategy: str = "theoretical", target_probability: float = 0.95,
    dense_max_states: int = DENSE_MAX_STATES,
) -> str | None:
    """Возвращает причину отказа до запуска дорогостоящего моделирования."""
    from algorithms.statevector_limits import check_layer_resources
    try:
        for bits in range(depth, 0, -1):
            params, _ = select_layer_parameters(
                state_bits, bits, parameter_strategy=parameter_strategy, target_probability=target_probability,
            )
            check_layer_resources(params.table_messages, params.search_messages, params.vertex_count, bits, dense_max_states=dense_max_states)
    except ValueError as exc:
        return str(exc)
    memory = quantum_layer_minimum_bytes(
        state_bits, depth, parameter_strategy=parameter_strategy, target_probability=target_probability,
        dense_max_states=dense_max_states,
    )
    if available is not None and memory > available * .2:
        return f'Для n = {state_bits}, k = {depth} требуется около {memory / 1024**2:.1f} МиБ; доступный бюджет составляет {available * .2 / 1024**2:.1f} МиБ.'
    return None
