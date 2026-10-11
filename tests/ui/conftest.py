"""Qt runs offscreen only for GUI tests; production selects its native platform."""

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication

from pdf_to_ofx.ui.main_window import MainWindow


@pytest.fixture(scope="session")
def qapp() -> Iterator[QApplication]:
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("QT_QPA_PLATFORM", "offscreen")
        app = QApplication.instance() or QApplication(["pdf-to-ofx-tests"])
        app.setQuitOnLastWindowClosed(False)
        yield app
        app.closeAllWindows()
        app.processEvents()


@pytest.fixture
def window(qapp: QApplication) -> Iterator[MainWindow]:
    window = MainWindow()
    window.show()
    qapp.processEvents()
    yield window
    window.close()
    window.deleteLater()
    # processEvents alone does not dispatch DeferredDelete without a running
    # outer event loop. Destroy GUI objects on their owning thread before the
    # next test starts a worker that may trigger Python garbage collection.
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()
