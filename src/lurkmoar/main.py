"""LurkMoar main window: header, rail, page stack, banner, status line, global keys."""
import sys
import time

from PySide6.QtCore import QByteArray, QEvent, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QAbstractButton, QApplication, QHBoxLayout, QLineEdit, QMainWindow,
                               QStackedWidget, QVBoxLayout, QWidget)

from .ui_catalog import CatalogView
from .ui_media import open_url
from .ui_misc import (Banner, BoardPicker, HelpDialog, Header, Sidebar, StatusLine, Welcome, ago)


class MainWindow(QMainWindow):
    def __init__(self, cfg, db, repo, theme, paths):
        super().__init__()
        self.cfg, self.db, self.repo, self.theme, self.paths = cfg, db, repo, theme, paths
        self.mode = self.prev_mode = "welcome"
        self.board = None
        self.boards = {}
        self.pages = {}
        self.viewer = None
        self.fetched_at = None
        self.cached_flag = self.refreshing = False
        self._picker = self._help = None
        self._rail_wanted = True
        self.setWindowTitle("LurkMoar")
        self.resize(1100, 760)

        root = QWidget()
        self.setCentralWidget(root)
        col = QVBoxLayout(root)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        self.header, self.banner, self.sidebar = Header(), Banner(), Sidebar()
        self.stack, self.status = QStackedWidget(), StatusLine()
        body = QHBoxLayout()
        body.setSpacing(0)
        body.addWidget(self.sidebar)
        body.addWidget(self.stack, 1)
        col.addWidget(self.header)
        col.addWidget(self.banner)
        col.addLayout(body, 1)
        col.addWidget(self.status)

        self.welcome = Welcome()
        self.add_page("welcome", self.welcome)
        self.welcome.choose.connect(self.open_picker)
        self.catalog = CatalogView(theme, cfg, repo, db)
        self.add_page("catalog", self.catalog)
        self.catalog.open_thread.connect(lambda b, n: self.open_thread(b, n))
        self.catalog.refresh_requested.connect(self.refresh)
        self.catalog.favourite_board.connect(self.toggle_board_favourite)
        self.repo.catalog_ready.connect(self._on_catalog)
        self.repo.thumbs_changed.connect(lambda: self._repaint.start())
        self._repaint = QTimer(self)
        self._repaint.setSingleShot(True)
        self._repaint.setInterval(120)
        self._repaint.timeout.connect(self._repaint_lists)
        self.header.toggle_rail.connect(self._toggle_rail)
        self.header.choose_board.connect(self.open_picker)
        self.header.refresh.connect(self.refresh)
        self.header.help.connect(self.show_help)
        self.sidebar.board_chosen.connect(lambda c: self.open_board(c))
        self.sidebar.all_boards.connect(self.open_picker)
        self.sidebar.bookmarks.connect(lambda: self.show_bookmarks())

        self.repo.boards_ready.connect(self._on_boards)
        cached = self.repo.cached_boards()
        if cached.data:
            self._set_boards(cached.data)
        self.repo.request_boards()
        self.sidebar.set_boards(self.db.fav_boards(), None)

        QApplication.instance().installEventFilter(self)
        self._ticker = QTimer(self)
        self._ticker.timeout.connect(self._tick)
        self._ticker.start(1000)
        self._restore_geometry()
        self.show_mode("welcome")

    # ---- pages and modes
    def add_page(self, mode, widget):
        self.pages[mode] = widget
        self.stack.addWidget(widget)

    def page(self):
        return self.pages.get(self.mode)

    def show_mode(self, mode):
        if mode == "bookmarks" and self.mode != "bookmarks":
            self.prev_mode = self.mode
        self.mode = mode
        self.stack.setCurrentWidget(self.pages[mode])
        self.status.set_hint(mode)
        self._update_where()
        self.page().focus_list()

    def _update_where(self):
        t = {"welcome": "Choose a board  (B)", "bookmarks": "Bookmarks"}.get(self.mode)
        if t is None and self.board:
            b = self.boards.get(self.board)
            t = f"/{self.board}/ {b.title}" if b else f"/{self.board}/"
            if self.mode == "thread":
                t = f"/{self.board}/ › No.{getattr(self.pages['thread'], 'number', '')}"
        self.header.where.setText(t or "Choose a board  (B)")

    def refresh(self):
        fn = getattr(self, f"_refresh_{self.mode}", None)
        if fn:
            fn()

    def back(self):
        if self.viewer is not None and self.viewer.isVisible():
            self.viewer.close_()
            return True
        page = self.page()
        if page is not None and page.key_action("back"):
            return True
        if self.mode == "bookmarks":
            self.show_mode(self.prev_mode)
            return True
        return False

    # ---- boards
    def _on_boards(self, res):
        if res.data:
            self._set_boards(res.data)

    def _set_boards(self, boards):
        self.boards = {b.code: b for b in boards}
        if self._picker is not None and self._picker.isVisible():
            self._picker.set_boards(boards, self.db.fav_boards())
        self._update_where()

    def open_picker(self):
        if self._picker is not None and self._picker.isVisible():
            return
        if not self.boards:
            self.repo.request_boards()
        p = BoardPicker(self, list(self.boards.values()), self.db.fav_boards())
        p.chosen.connect(lambda c: self.open_board(c))
        p.favourite_toggled.connect(self._toggle_fav)
        self._picker = p
        p.open()

    def _toggle_fav(self, code):
        on = self.db.fav_toggle(code)
        self.sidebar.set_boards(self.db.fav_boards(), self.board)
        self.catalog.set_favourite(self.board in self.db.fav_boards())
        if self._picker is not None:
            self._picker.set_favs(self.db.fav_boards())
        self.status.message(f"/{code}/ {'added to' if on else 'removed from'} favourites")

    def toggle_board_favourite(self):
        if self.board:
            self._toggle_fav(self.board)
        else:
            self.status.message("Choose a board first")

    def show_help(self):
        self._help = HelpDialog(self)
        self._help.open()

    def _repaint_lists(self):
        for pg in self.pages.values():
            lst = getattr(pg, "list", None)
            if lst is not None and pg.isVisible():
                lst.viewport().update()

    def open_board(self, code):
        code = code.lower()
        if self.mode == "thread":
            self._save_thread_state()
        self.board = code
        self.db.kv_set("last_board", code)
        self.db.kv_set("last_view", "catalog")
        self.banner.hide()
        self.catalog.set_board(code, self.boards.get(code))
        self.catalog.set_favourite(code in self.db.fav_boards())
        self.sidebar.set_boards(self.db.fav_boards(), code)
        cached, nav = self.repo.cached_catalog(code), self.db.nav_get(code)
        if cached.data is not None:
            self.catalog.show_threads(cached.data)
            self.catalog.restore(nav.catalog_anchor, nav.thread_no)
            self.fetched_at, self.cached_flag = cached.fetched_at, False
        else:
            self.catalog.show_loading(code)
            self.fetched_at = None
        self.show_mode("catalog")
        self._refresh_catalog(announce=False)

    def _refresh_catalog(self, announce=True):
        if not self.board:
            return
        self.refreshing = True
        if self.repo.request_catalog(self.board):
            if announce:
                self.status.message(f"Refreshing /{self.board}/…")
        else:
            self.status.message("Already refreshing…")

    def _on_catalog(self, code, res):
        self.refreshing = False
        for pg in self.pages.values():
            getattr(pg, "on_bookmarks_changed", lambda: None)()
        if code != self.board:
            return
        new = self.catalog.show_threads(res.data) if res.data is not None else None
        if self.mode != "catalog":
            return
        self.note_result(res, f"/{code}/ catalog", self._refresh_catalog)
        if res.error is None and not res.from_cache:
            if new is None:
                msg = f"/{code}/ loaded · {len(res.data)} threads"
            else:
                msg = f"/{code}/ updated · " + (f"{new} new thread{'s' * (new != 1)}" if new else "no new threads")
            self.status.message(msg + " · just now")
        elif res.error is None:
            self.status.message(f"/{code}/ is up to date")

    # ---- shared feedback
    def note_result(self, res, label, retry):
        self.refreshing = False
        self.fetched_at = res.fetched_at
        self.cached_flag = bool(res.error)
        if res.error and not res.gone:
            if res.data is not None and res.fetched_at:
                when = time.strftime("%H:%M", time.localtime(res.fetched_at))
                text = f"Couldn't reach the server.\nShowing cached {label} from {when}."
            else:
                text = f"Couldn't reach the server.\nNothing is cached for {label} yet."
            self.banner.show_message(text, [("Retry", retry)])
        elif not res.gone:
            self.banner.hide()

    def _tick(self):
        if self.refreshing:
            txt = "Refreshing…"
        elif self.fetched_at:
            txt = f"Updated {ago(time.time() - self.fetched_at)}" + (" · cached" if self.cached_flag else "")
        else:
            txt = ""
        self.header.status.setText(txt)

    # ---- actions on the current page's object
    def _ref(self):
        p = self.page()
        return p.current_ref() if p else None

    def open_in_browser(self):
        ref = self._ref()
        if ref:
            open_url(ref["url"])
            self.status.message(f"Opened in browser: {ref['url']}")

    def copy_url(self):
        ref = self._ref()
        if ref:
            QApplication.clipboard().setText(ref["url"])
            self.status.message(f"Copied {ref['url']}")

    def toggle_bookmark(self):
        ref = self._ref()
        if not ref:
            self.status.message("Select a thread first")
            return
        b, n = ref["board"], ref["number"]
        if self.db.bookmark_has(b, n):
            self.db.bookmark_remove(b, n)
            self.status.message(f"Bookmark removed · /{b}/ No.{n}")
        else:
            self.db.bookmark_add(b, n, ref["subject"], ref["replies"])
            self.status.message(f"Bookmarked · /{b}/ No.{n}")
        for pg in self.pages.values():
            getattr(pg, "on_bookmarks_changed", lambda: None)()

    # ---- keys
    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.KeyPress and self.isActiveWindow():
            if self._on_key(ev):
                return True
        return super().eventFilter(obj, ev)

    def _on_key(self, ev):
        k, mods, ch = ev.key(), ev.modifiers(), ev.text()
        focus = QApplication.focusWidget()
        page = self.page()
        if k == Qt.Key_Escape:
            return self.back()
        if isinstance(focus, QLineEdit):
            if k in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Down) and page:
                page.focus_list()
                return True
            return False
        if mods & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier):
            return False
        if self.viewer is not None and self.viewer.isVisible():
            return self.viewer.key(k, ch)
        if isinstance(focus, QAbstractButton) and k in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            return False
        for key, name in ((Qt.Key_Return, "open"), (Qt.Key_Enter, "open"),
                          (Qt.Key_Space, "reveal"), (Qt.Key_Delete, "delete")):
            if k == key:
                return bool(page and page.key_action(name))
        simple = {"b": self.open_picker, "r": self.refresh, "?": self.show_help,
                  "o": self.open_in_browser, "c": self.copy_url, "f": self.toggle_bookmark,
                  "F": self.toggle_board_favourite}
        if ch in simple:
            simple[ch]()
            return True
        names = {"/": "filter", "s": "sort", "m": "media", "j": "down", "k": "up"}
        if ch in names:
            return bool(page and page.key_action(names[ch]))
        return False

    # ---- window state
    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.sidebar.setVisible(self._rail_wanted and self.width() >= 760)
        if self.viewer is not None:
            self.viewer.setGeometry(self.centralWidget().rect())

    def _toggle_rail(self):
        self._rail_wanted = not self._rail_wanted
        self.sidebar.setVisible(self._rail_wanted)

    def _restore_geometry(self):
        g = self.db.kv_get("geometry")
        if g:
            self.restoreGeometry(QByteArray.fromBase64(g.encode()))

    def closeEvent(self, e):
        self.db.kv_set("geometry", bytes(self.saveGeometry().toBase64()).decode())
        super().closeEvent(e)


def main():
    from .api import Client
    from .config import load_config, paths
    from .db import DB
    from .repo import Repo, evict
    from .theme import load_theme, stylesheet

    app = QApplication(sys.argv)
    app.setApplicationName("LurkMoar")
    app.setDesktopFileName("LurkMoar")
    app.setWindowIcon(QIcon.fromTheme("lurkmoar"))
    p = paths()
    cfg = load_config(p)
    theme = load_theme()
    app.setStyleSheet(stylesheet(theme, cfg.font_size))
    evict([p.thumbs, p.media], cfg.cache_mb * 1024 * 1024)
    repo = Repo(DB(p.db_file), Client(), Client(min_interval=0.05), p, cfg)
    win = MainWindow(cfg, repo.db, repo, theme, p)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
