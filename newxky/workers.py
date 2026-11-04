from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class WorkerSignals(QObject):
    result = Signal(object)
    error = Signal(str)
    progress = Signal(int, int, str)
    finished = Signal()


class Worker(QRunnable):
    def __init__(self, function):
        super().__init__()
        self.function = function
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        try:
            self.signals.result.emit(self.function(self.signals.progress.emit))
        except Exception as error:
            self.signals.error.emit(f"{type(error).__name__}：{error}")
        finally:
            self.signals.finished.emit()
