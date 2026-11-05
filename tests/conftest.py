"""Keep one Qt application alive until all windows/workers have shut down."""
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication,QEvent
from shiboken6 import isValid

_application = None


@pytest.fixture(scope="session",autouse=True)
def qt_application_lifetime():
    global _application
    _application = QApplication.instance() or QApplication([])
    _application.setQuitOnLastWindowClosed(False)
    yield _application
    windows = list(_application.topLevelWidgets())
    for window in windows:
        if isValid(window):
            window.close()
    deadline = time.monotonic()+15
    while time.monotonic()<deadline:
        _application.processEvents()
        if not any(isValid(window) and (getattr(window,"_jobs",None) or getattr(getattr(window,"auto",None),"busy",False)
                   or getattr(window,"personnel_worker",None)) for window in windows):
            break
        time.sleep(.01)
    _application.processEvents()
    for window in windows:
        if isValid(window):
            window.deleteLater()
    QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
    _application.processEvents()
