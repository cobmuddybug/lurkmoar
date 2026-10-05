"""LurkMoar main window: header, rail, page stack, banner, status line, global keys."""
import sys
import time

from PySide6.QtCore import QByteArray, QEvent, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QAbstractButton, QApplication, QHBoxLayout, QLineEdit, QMainWindow,
                               QMessageBox, QStackedWidget, QVBoxLayout, QWidget)

from .ui_catalog import CatalogView
from .ui_media import MediaViewer, open_url
from .ui_thread import ThreadView
from .ui_misc import (Banner, BoardPicker, BookmarksView, HelpDialog, Header, Sidebar, StatusLine,
                      Welcome, ago)


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
        self.thread = ThreadView(theme, cfg, repo, db)
        self.add_page("thread", self.thread)
        self.thread_ref = None
        self.thread_gone = False
        self.thread.back_requested.connect(self.leave_thread)
        self.thread.refresh_requested.connect(self.refresh)
        self.thread.bookmark_toggled.connect(self.toggle_bookmark)
        self.thread.link_requested.connect(self._open_link)
        self.thread.message.connect(self.status.message)
        self.thread.cross_requested.connect(self._cross_thread)
        self.repo.thread_ready.connect(self._on_thread)
        self._thread_timer = QTimer(self)
        self._thread_timer.timeout.connect(self._auto_refresh)
        self.viewer = MediaViewer(root, theme, cfg, repo)
        self.viewer.message.connect(self.status.message)
        self.viewer.closed.connect(lambda att_id: att_id and self.thread.select_attachment(att_id))
        self.thread.media_requested.connect(self.open_media)
        self.bookmarks = BookmarksView(db)
        self.add_page("bookmarks", self.bookmarks)
        self.bookmarks.open_thread.connect(lambda b, n: self.open_thread(b, n))
        self.header.toggle_rail.connect(self._toggle_rail)
        self.header.choose_board.connect(self.open_picker)
        self.header.refresh.connect(self.refresh)
        self.header.help.connect(self.show_help)
        self.sidebar.board_chosen.connect(self._rail_chose)
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
        self._restore()

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
        if self.mode == "thread":
            self.leave_thread()
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

    def _rail_chose(self, code):
        self.open_board(code)
        self.page().focus_list()

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

    def show_bookmarks(self):
        self.bookmarks.reload()
        self.banner.hide()
        self.show_mode("bookmarks")

    def _refresh_bookmarks(self):
        boards = sorted({b.board for b in self.db.bookmarks()})
        if not boards:
            self.status.message("No bookmarks yet. Press F on a thread.")
            return
        self.status.message("Checking bookmarks…")
        for b in boards:
            self.repo.request_catalog(b)

    def _restore(self):
        last = self.db.kv_get("last_board")
        if not last or not self.cfg.start_on_last_board:
            return
        view = self.db.kv_get("last_view", "")      # read first: open_board resets it to "catalog"
        self.open_board(last)
        if self.cfg.restore_thread and view.startswith("thread:"):
            try:
                _, b, n = view.split(":")
                if b == last:
                    self.open_thread(b, int(n))
            except ValueError:
                pass

    def open_media(self, board, att):
        self.viewer.show_attachment(board, att, [a for _, a in self.thread.gallery()])

    def _open_link(self, url):
        if url:
            open_url(url)
            self.status.message(f"Opened in browser: {url}")

    def _cross_thread(self, board, thread, post):
        box = QMessageBox(self)
        box.setWindowTitle("Open another thread?")
        box.setText(f"This quote points to /{board}/ No.{thread}.")
        a = box.addButton("Open here", QMessageBox.AcceptRole)
        w = box.addButton("Open on 4chan.org", QMessageBox.ActionRole)
        box.addButton("Cancel", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is a:
            self.open_thread(board, thread)
        elif box.clickedButton() is w:
            self._open_link(f"https://boards.4chan.org/{board}/thread/{thread}#p{post}")

    def open_thread(self, board, no, announce=True):
        if board != self.board:
            self.open_board(board)
        elif self.mode == "thread":
            self._save_thread_state()
        nav = self.db.nav_get(board)
        bm = next((b for b in self.db.bookmarks() if b.board == board and b.thread_id == no), None)
        anchor = nav.thread_anchor if nav.thread_no == no else (bm.last_opened_post if bm else 0)
        sel = self.catalog.model.row_of(no)
        summary = self.catalog.model.thread_at(sel) if sel >= 0 else None
        subject = (summary.subject or summary.comment[:60]) if summary else (bm.subject if bm else "")
        self.db.nav_set(board, catalog_anchor=self.catalog.anchor(), thread_no=no)
        self.db.recent_add(board, no, subject or f"No.{no}")
        self.db.kv_set("last_view", f"thread:{board}:{no}")
        self.thread_ref, self.thread_gone, self._anchor = (board, no), False, anchor
        self.banner.hide()
        self.thread.begin(board, no, subject, self.db.bookmark_has(board, no))
        cached = self.repo.cached_thread(board, no)
        if cached.data is not None:
            self.thread.load(cached.data, anchor)
            self.fetched_at, self.cached_flag = cached.fetched_at, False
        else:
            self.fetched_at = None
        self.show_mode("thread")
        if announce:
            self.status.message(f"Loading thread {no}…")
        self.refreshing = True
        self.repo.request_thread(board, no)
        if self.cfg.auto_refresh:
            self._thread_timer.start(self.cfg.refresh_seconds * 1000)

    def _refresh_thread(self):
        if self.thread_ref and not self.thread_gone:
            self.refreshing = True
            if self.repo.request_thread(*self.thread_ref):
                self.status.message(f"Refreshing thread {self.thread_ref[1]}…")
            else:
                self.status.message("Already refreshing…")

    def _auto_refresh(self):
        if self.mode == "thread" and not self.thread_gone and self.isActiveWindow():
            self.refreshing = True
            self.repo.request_thread(*self.thread_ref)

    def _on_thread(self, board, no, res):
        for pg in self.pages.values():
            getattr(pg, "on_bookmarks_changed", lambda: None)()
        if self.thread_ref != (board, no):
            return
        self.refreshing = False
        label = f"thread {no}"
        if res.gone:
            self.thread_gone = True
            self._thread_timer.stop()
            self.fetched_at = res.fetched_at
            back = ("Back to /%s/" % board, self.leave_thread)
            if self.thread.loaded:
                self.banner.show_message("This thread is no longer available.\nYou're reading a cached copy.", [back])
            else:
                self.banner.show_message("This thread is no longer available.\nNo cached copy.", [back])
            return
        if res.data is None:
            self.note_result(res, label, self._refresh_thread)
            return
        new = self.thread.apply(res.data, self._anchor)
        self.note_result(res, label, self._refresh_thread)
        if new:
            self.status.message(f"Thread updated · {new} new post{'s' * (new != 1)}")
        elif new is None and not res.from_cache:
            self.status.message(f"Thread {no} loaded")

    def _save_thread_state(self):
        if not self.thread_ref:
            return
        b, n = self.thread_ref
        a = self.thread.anchor()
        self.db.nav_set(b, thread_no=n, thread_anchor=a)
        if self.thread.loaded:
            self.db.bookmark_seen(b, n, self.thread.replies(), a)

    def leave_thread(self):
        if not self.thread_ref:
            return
        self._save_thread_state()
        n = self.thread_ref[1]
        self._thread_timer.stop()
        self.banner.hide()
        self.db.kv_set("last_view", "catalog")
        self.thread.jumps.clear()
        self.show_mode("catalog")
        self.catalog.select(n)
        self.refreshing = False
        self.thread_ref = None

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
        focus = self.focusWidget() or QApplication.focusWidget()   # this window's own focus first (app-level can lag)
        page = self.page()
        if k == Qt.Key_Backspace and (mods or isinstance(focus, QLineEdit)):
            return False                            # text editing, and Ctrl+Backspace, stay untouched
        if k in (Qt.Key_Escape, Qt.Key_Backspace):  # Backspace does everything Esc does
            if self.sidebar.has_focus() and not (self.viewer is not None and self.viewer.isVisible()):
                if page:
                    page.focus_list()
                return True
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
        if self.sidebar.has_focus():
            if k == Qt.Key_Right:
                if page:
                    page.focus_list()
                return True
            if k == Qt.Key_Left:
                return True
            if k in (Qt.Key_Up, Qt.Key_Down):
                return self.sidebar.nav(k)
            if k in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
                self.sidebar.activate()
                return True
        elif k == Qt.Key_Left and self.mode != "welcome":
            self._focus_rail()
            return True
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

    def _focus_rail(self):
        self._rail_wanted = True
        self.sidebar.setVisible(True)
        if not self.sidebar.isVisible():
            self.status.message("Window too narrow for the board list")
            return
        self.sidebar.enter()

    def _toggle_rail(self):
        self._rail_wanted = not self._rail_wanted
        self.sidebar.setVisible(self._rail_wanted)

    def _restore_geometry(self):
        g = self.db.kv_get("geometry")
        if g:
            self.restoreGeometry(QByteArray.fromBase64(g.encode()))

    def closeEvent(self, e):
        self.db.kv_set("geometry", bytes(self.saveGeometry().toBase64()).decode())
        if self.mode == "thread":
            self._save_thread_state()
        if self.board:
            self.db.nav_set(self.board, catalog_anchor=self.catalog.anchor())
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
