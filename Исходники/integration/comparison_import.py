"""Импортирует файлы экспериментов в рабочем потоке без блокировки цикла Qt."""

from pathlib import Path

from PySide6.QtCore import QThread,Signal


class ComparisonImport(QThread):
    completed=Signal(int,object)

    def __init__(self,store,paths,adapter,parent=None):
        super().__init__(parent)
        self.store,self.paths,self.adapter=store,paths,adapter

    def run(self):
        added=0;errors=[]
        for name in self.paths:
            try:added+=self.store.import_file(Path(name),self.adapter)
            except Exception as exc:errors.append(f"{Path(name).name}: {exc}")
        self.completed.emit(added,errors)
