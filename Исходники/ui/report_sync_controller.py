"""Наблюдает за каталогом отчётов и синхронизирует базу вне основного потока Qt."""

from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QObject, QThread, QTimer, Signal

from integration.report_sync import ReportSynchronizer


class SyncWorker(QThread):
    completed=Signal(object)

    def __init__(self, store, root, force, parent=None):
        super().__init__(parent)
        self.store,self.root,self.force=store,root,force

    def run(self):
        try:
            result=ReportSynchronizer(self.store,self.root).sync(self.force,self.isInterruptionRequested)
        except Exception as exc:
            result=dict(error=str(exc),files=0,added=0,reports=[])
        self.completed.emit(result)


class ReportSyncController(QObject):
    completed=Signal(object)
    busy_changed=Signal(bool)

    def __init__(self, store, root, parent=None):
        super().__init__(parent)
        self.store,self.root=store,Path(root)
        self.worker=None;self.pending=False;self.force=False;self.stopping=False
        self.watcher=QFileSystemWatcher(self)
        self.watcher.directoryChanged.connect(lambda *_:self.schedule())
        self.watcher.fileChanged.connect(lambda *_:self.schedule())
        self.debounce=QTimer(self);self.debounce.setSingleShot(True);self.debounce.setInterval(400)
        self.debounce.timeout.connect(self.synchronize)
        self.timer=QTimer(self);self.timer.setInterval(30000);self.timer.timeout.connect(self.synchronize);self.timer.start()
        QTimer.singleShot(0,self.synchronize)

    def _watch(self):
        paths={str(self.root)} if self.root.exists() else {str(self.root.parent)}
        if self.root.exists():
            paths.update(str(p) for p in self.root.rglob('*') if p.is_dir() or p.suffix=='.jsonl')
        current=set(self.watcher.directories()+self.watcher.files())
        if current-paths:self.watcher.removePaths(list(current-paths))
        if paths-current:self.watcher.addPaths(sorted(paths-current))

    def schedule(self):
        if not self.stopping:self.debounce.start()

    def synchronize(self, force=False):
        if self.stopping:return
        if self.worker:
            self.pending=True;self.force=self.force or force;return
        self._watch()
        self.worker=SyncWorker(self.store,self.root,force,self)
        self.worker.completed.connect(self.completed)
        self.worker.finished.connect(self._finished)
        self.busy_changed.emit(True);self.worker.start()

    def _finished(self):
        worker=self.worker;self.worker=None;worker.deleteLater()
        self.busy_changed.emit(False)
        self._watch()
        if self.pending and not self.stopping:
            force=self.force;self.pending=self.force=False
            self.synchronize(force)

    def stop(self):
        self.stopping=True;self.timer.stop();self.debounce.stop()
        if self.worker:self.worker.requestInterruption()
        return self.worker is None
