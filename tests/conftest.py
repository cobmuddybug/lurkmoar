import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("LURKMOAR_HOME", str(tmp_path / "lm"))
    return tmp_path / "lm"


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _close_windows():
    yield
    try:
        import helpers
    except ImportError:
        return
    helpers.cleanup()
