import json
import re
import time

from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest

from lurkmoar.api import ApiError, NotFound, Response
from lurkmoar.config import load_config, paths
from lurkmoar.db import DB
from lurkmoar.repo import Repo
from lurkmoar.theme import DEFAULT, stylesheet
from samples import BOARDS, CATALOG, THREAD
from samples_vichan import FILES_CATALOG, FILES_THREAD, VICHAN_CATALOG, VICHAN_THREAD


def ok(obj, lm="Mon"):
    return Response(200, json.dumps(obj).encode(), lm)


def png_bytes(w=40, h=30):
    img = QImage(w, h, QImage.Format_RGB32)
    img.fill(QColor("#336699"))
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return bytes(ba)


class FakeApi:
    def __init__(self):
        self.catalog, self.thread = CATALOG, THREAD
        self.vichan_catalog, self.vichan_thread = VICHAN_CATALOG, VICHAN_THREAD
        self.files_catalog, self.files_thread = FILES_CATALOG, FILES_THREAD
        self.fail, self.gone, self.calls, self.fail_hosts = False, set(), [], set()

    def get(self, url, last_modified=None):
        self.calls.append(url)
        host = url.split("/")[2]
        if self.fail or host in self.fail_hosts:
            raise ApiError("network: down")
        if host != "a.4cdn.org":
            if url.endswith("catalog.json"):
                return ok(self.files_catalog if "leftypol" in host else self.vichan_catalog)
            m = re.search(r"/res/(\d+)\.json$", url)
            if m:
                if int(m.group(1)) in self.gone:
                    raise NotFound("nf", 404)
                return ok(self.files_thread if "leftypol" in host else self.vichan_thread)
            raise NotFound("nf", 404)
        if url.endswith("boards.json"):
            return ok(BOARDS)
        if url.endswith("catalog.json"):
            return ok(self.catalog)
        m = re.search(r"/(\w+)/thread/(\d+)\.json", url)
        if m:
            if int(m.group(2)) in self.gone:
                raise NotFound("nf", 404)
            return ok(self.thread)
        raise NotFound("nf", 404)


class FakeCdn:
    def get(self, url, last_modified=None):
        return Response(200, png_bytes(), None)


WINDOWS = []


def cleanup():
    """Close test windows and drop their app-level key filters so tests cannot leak into each other."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    while WINDOWS:
        w = WINDOWS.pop()
        app.removeEventFilter(w)
        w.close()
        w.deleteLater()


def make_window(qapp, api=None, db=None, theme_path=None):
    from lurkmoar.main import MainWindow
    p = paths()
    cfg = load_config(p)
    cfg.auto_refresh = False
    api = api or FakeApi()
    db = db or DB(":memory:")
    repo = Repo(db, api, FakeCdn(), p, cfg)
    qapp.setStyleSheet(stylesheet(DEFAULT, cfg.font_size))
    from lurkmoar.theme import read_theme
    theme_path = theme_path or (p.config / "no-omarchy" / "theme" / "colors.toml")   # tests never watch the real theme
    win = MainWindow(cfg, db, repo, read_theme(theme_path) or DEFAULT, p, theme_path=theme_path)
    win.isActiveWindow = lambda: True  # offscreen platform never reports active
    win.show()
    WINDOWS.append(win)
    return win, api, repo, db


def pump(qapp, cond, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        qapp.processEvents()
        if cond():
            return True
        time.sleep(0.01)
    return False


def press(win, key):
    QTest.keyClick(win, key)
