"""Проверяет память, объём работы и время непосредственного моделирования амплитуд."""

from contextvars import ContextVar
from functools import wraps
import math
import inspect
import os
import time

MODEL_REVISION = 'grover-statevector-v2'
MODEL_LABEL = 'Моделирование вектора амплитуд'
MAX_STATES = 1048576
MAX_WORK = 200000000
MAX_MEMORY_BYTES = 536870912
SIMULATION_TIMEOUT = 30.0
EXPERIMENT_TIMEOUT = 300.0
DENSE_MAX_STATES = 8192
NATIVE_BATCH_STATES = 4096
_deadline = ContextVar('statevector_experiment_deadline', default=None)


def limits():
    """Возвращает обязательные верхние границы с возможностью только уменьшить их."""
    result = {}
    for key, maximum in (('GROVER_MAX_STATES', MAX_STATES), ('GROVER_MAX_WORK', MAX_WORK), ('GROVER_MAX_MEMORY_BYTES', MAX_MEMORY_BYTES)):
        value = int(os.environ.get(key, maximum))
        if value <= 0:
            raise ValueError('Лимиты ресурсов должны быть положительными.')
        result[key] = min(value, maximum)
    return result


def available_memory():
    """Определяет доступную физическую память Windows без изменения системных настроек."""
    if os.name != 'nt':
        return None
    import ctypes
    class MemoryStatus(ctypes.Structure):
        _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [(key, ctypes.c_ulonglong) for key in ('total_phys', 'avail_phys', 'total_page', 'avail_page', 'total_virtual', 'avail_virtual', 'avail_extended')]
    status = MemoryStatus()
    status.length = ctypes.sizeof(status)
    return int(status.avail_phys) if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)) else None


def check_resources(states, iterations, other_bytes=0, *, python=False):
    """Отказывает до выделения памяти при превышении размера, работы или оценки памяти."""
    policy = limits()
    if states <= 0 or iterations < 0:
        raise ValueError('Размер пространства должен быть положительным, а число итераций неотрицательным.')
    memory = other_bytes + states * (96 if python else 9)
    work = states * iterations
    if states > policy['GROVER_MAX_STATES']:
        raise ValueError(f"Вектор амплитуд S={states} превышает лимит {policy['GROVER_MAX_STATES']} состояний.")
    if work > policy['GROVER_MAX_WORK']:
        raise ValueError(f"Объём симуляции S × iterations={work} превышает лимит {policy['GROVER_MAX_WORK']}.")
    available = available_memory()
    budget = min(policy['GROVER_MAX_MEMORY_BYTES'], int(available * .2)) if available is not None else policy['GROVER_MAX_MEMORY_BYTES']
    if memory > budget:
        raise ValueError(f'Оценка памяти {memory / 1024**2:.1f} МиБ превышает доступный лимит {budget / 1024**2:.1f} МиБ.')
    check_deadline()
    return dict(search_messages=states, iterations=iterations, estimated_bytes=memory, iteration_work=work)


def check_native_resources(states, iterations, other_bytes=0, *, dense_max_states=DENSE_MAX_STATES):
    """Оценивает плотный или двухамплитудный C++-поиск с пакетным вычислением кандидатов."""
    if states <= dense_max_states:
        return check_resources(states, iterations, other_bytes)
    if not 0 < states < 2**64 or iterations < 0:
        raise ValueError('Пространство кандидатов превышает лимит адресации C++.')
    policy = limits()
    memory = other_bytes + 65536
    work = 2 * iterations
    available = available_memory()
    budget = min(policy['GROVER_MAX_MEMORY_BYTES'], int(available * .2)) if available is not None else policy['GROVER_MAX_MEMORY_BYTES']
    if memory > budget:
        raise ValueError(f'Оценка памяти {memory / 1024**2:.1f} МиБ превышает доступный лимит {budget / 1024**2:.1f} МиБ.')
    if work > policy['GROVER_MAX_WORK']:
        raise ValueError(f"Объём численного моделирования превышает лимит {policy['GROVER_MAX_WORK']}.")
    check_deadline()
    return dict(search_messages=states, iterations=iterations, estimated_bytes=memory,
                iteration_work=work, amplitude_backend='symmetric', candidate_evaluations=states)


def layer_other_bytes(table_messages, states, vertex_count, *, python=False, dense_max_states=DENSE_MAX_STATES):
    """Возвращает оценку qRAM и одновременно живущих буферов слоя."""
    buffer_states = states if python or states <= dense_max_states else NATIVE_BATCH_STATES
    return 128 * max(table_messages, buffer_states) + 256 * table_messages * vertex_count + 256 * vertex_count


def check_layer_resources(table_messages, states, vertex_count, layer_bits, *, python=False, dense_max_states=DENSE_MAX_STATES):
    """Оценивает рабочие буферы, qRAM и множество кандидатов выбранного backend."""
    from .grover import optimal_grover_iterations
    other = layer_other_bytes(table_messages, states, vertex_count, python=python, dense_max_states=dense_max_states)
    if python:
        other += 256 * states * vertex_count * layer_bits
        return check_resources(states, optimal_grover_iterations(states, 1), other, python=True)
    return check_native_resources(states, optimal_grover_iterations(states, 1), other, dense_max_states=dense_max_states)


def check_deadline():
    """Проверяет общее время текущего эксперимента."""
    deadline = _deadline.get()
    if deadline is not None and time.perf_counter() >= deadline:
        raise TimeoutError('Превышен лимит времени отдельного эксперимента.')


def remaining_seconds():
    """Возвращает оставшееся время эксперимента для завершения дочернего процесса."""
    check_deadline()
    deadline = _deadline.get()
    return None if deadline is None else max(.001, deadline - time.perf_counter())


def bounded_experiment(function):
    """Сохраняет явный тайм-аут и снимает стандартный тайм-аут больших нативных квантовых задач."""
    signature = inspect.signature(function)
    @wraps(function)
    def wrapped(*args, **kwargs):
        bound = signature.bind(*args, **kwargs).arguments
        request = bound.get('request')
        data = bound.get('data', {})
        n = getattr(request, 'truncate_bits', data.get('trunc_bits', 0))
        method = getattr(request, 'method', bound.get('method') or bound.get('quantum', False))
        from .search_methods import search_method
        from CppCore import cpp_core_available
        native = getattr(request, 'use_cpp', bound.get('use_cpp'))
        scalable = n >= 36 and search_method(method).is_quantum and native is not False and (native or cpp_core_available())
        raw_timeout = os.environ.get('HERDING_EXPERIMENT_TIMEOUT_SECONDS')
        seconds = float(raw_timeout if raw_timeout is not None else EXPERIMENT_TIMEOUT)
        if not math.isfinite(seconds) or seconds <= 0:
            raise ValueError('Лимит времени эксперимента должен быть положительным.')
        existing = _deadline.get()
        deadline = None if scalable and raw_timeout is None else time.perf_counter() + seconds
        if existing is not None:
            deadline = existing if deadline is None else min(existing, deadline)
        token = _deadline.set(deadline)
        try:
            return function(*args, **kwargs)
        finally:
            _deadline.reset(token)
    return wrapped
