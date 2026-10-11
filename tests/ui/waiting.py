from time import monotonic
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest


def wait_for_analysis(window, timeout=10):
    deadline = monotonic() + timeout
    while window._worker is not None or window._pending is not None:
        QApplication.processEvents()
        QTest.qWait(5)
        assert monotonic() < deadline, "Worker did not finish"
    QApplication.processEvents()
