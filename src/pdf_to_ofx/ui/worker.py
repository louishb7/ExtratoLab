"""A single local worker; only immutable results cross into the GUI thread."""
from PySide6.QtCore import QThread, Signal


class AnalysisWorker(QThread):
    completed = Signal(int, object, object)

    def __init__(self, request_id, path, analyzer, parent=None):
        super().__init__(parent)
        self.request_id, self.path, self.analyzer = request_id, path, analyzer

    def run(self):
        try:
            result = self.analyzer(self.path)
        except Exception as error:
            # Never pass exception strings/tracebacks containing document data.
            self.completed.emit(self.request_id, None, type(error))
        else:
            self.completed.emit(self.request_id, result, None)
