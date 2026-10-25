"""Завершает нативный дочерний процесс при уничтожении управляющего Python-процесса."""

import os
import signal
import subprocess

_parent_job = None


def guard_current_process():
    """Привязывает дерево рабочего Python-процесса к группе до запуска первого вычислителя."""
    global _parent_job
    if os.name == "nt" and _parent_job is None:
        import ctypes
        current = ctypes.windll.kernel32.GetCurrentProcess
        current.restype = ctypes.c_void_p
        _parent_job = _windows_job(current())


class NativeProcess(subprocess.Popen):
    def __init__(self, *args, **kwargs):
        self._job = None
        if os.name=='nt':kwargs['creationflags']=kwargs.get('creationflags',0)|subprocess.CREATE_NO_WINDOW
        if os.name == "nt" and _parent_job is None:
            guard_current_process()
        if os.name != "nt":
            kwargs["preexec_fn"] = _parent_death_signal
        super().__init__(*args, **kwargs)

    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close_job()

    def close_job(self):
        if self._job is not None:
            import ctypes
            close = ctypes.windll.kernel32.CloseHandle
            close.argtypes = [ctypes.c_void_p]
            close(self._job)
            self._job = None


def _parent_death_signal():
    """Останавливает вычислитель Linux при смерти родителя даже во время запуска."""
    import ctypes
    parent = os.getppid()
    if ctypes.CDLL(None).prctl(1, signal.SIGKILL) != 0:
        raise OSError("Не удалось привязать время жизни нативного процесса к родителю.")
    if parent == 1 or os.getppid() != parent:
        os.kill(os.getpid(), signal.SIGKILL)


def _windows_job(process_handle):
    """Помещает вычислитель Windows в группу с завершением при закрытии последнего дескриптора."""
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)

    class Basic(ctypes.Structure):
        _fields_ = [("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64),
                    ("flags", wintypes.DWORD), ("min_working", ctypes.c_size_t),
                    ("max_working", ctypes.c_size_t), ("active", wintypes.DWORD),
                    ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD),
                    ("scheduling", wintypes.DWORD)]

    class Extended(ctypes.Structure):
        _fields_ = [("basic", Basic), ("io", ctypes.c_uint64 * 6),
                    ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                    ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]

    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateJobObjectW(None, None)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    info = Extended()
    info.basic.flags = 0x2000
    if not kernel.SetInformationJobObject(handle, 9, ctypes.byref(info), ctypes.sizeof(info)) or not kernel.AssignProcessToJobObject(handle, int(process_handle)):
        error = ctypes.get_last_error()
        kernel.CloseHandle(handle)
        raise ctypes.WinError(error)
    return handle


def run_native(command, *, input=None, timeout=None, **kwargs):
    """Повторяет subprocess.run с гарантированным завершением дочернего вычислителя."""
    with NativeProcess(command, stdin=subprocess.PIPE if input is not None else None,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs) as process:
        try:
            stdout, stderr = process.communicate(input, timeout=timeout)
        except BaseException:
            process.kill()
            process.communicate()
            raise
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
