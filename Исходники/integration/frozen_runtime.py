"""Восстанавливает каналы вычислителя в оконной автономной сборке Windows."""

import os
import sys


def close_startup_splash():
    if not getattr(sys,'frozen',False):return
    import pyi_splash
    if pyi_splash.is_alive():pyi_splash.close()


def restore_worker_streams():
    if os.name!='nt':return
    import ctypes
    from ctypes import wintypes
    import msvcrt
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.GetStdHandle.argtypes=[wintypes.DWORD];kernel.GetStdHandle.restype=wintypes.HANDLE
    for name,number,mode,flags in (('stdin',-10,'r',os.O_RDONLY),('stdout',-11,'w',os.O_WRONLY),('stderr',-12,'w',os.O_WRONLY)):
        if getattr(sys,name) is None:
            handle=kernel.GetStdHandle(number)
            if handle and handle!=wintypes.HANDLE(-1).value:
                descriptor=msvcrt.open_osfhandle(handle,flags|os.O_BINARY)
                setattr(sys,name,os.fdopen(descriptor,mode,encoding='utf-8'))
