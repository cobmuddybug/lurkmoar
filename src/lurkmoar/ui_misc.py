"""Small shared widgets: header, rail, banner, status line, picker, help."""
from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPushButton, QToolButton, QVBoxLayout, QWidget)

from .sites import key as site_key

KEYS = [
    ("B", "Choose board"),
    ("←", "Move to the board list (↑↓ choose, Enter open, → or Esc back)"),
    ("/", "Filter catalog"),
    ("S", "Cycle catalog sort"),
    ("R", "Refresh (on Bookmarks: check for updates)"),
    ("↑ ↓  or  K J", "Previous / next item"),
    ("PgUp PgDn Home End", "Scroll"),
    ("Enter", "Open selected thread; in a thread follow a quote or open media"),
    ("Esc  or  Backspace", "Back / close (undoes quote jumps first)"),
    ("M", "Open selected post's media"),
    ("← →", "Previous / next image or video in the thread (wraps around)"),
    ("S", "In the viewer: save the image or video to your download folder"),
    ("Space  M  [ ]  V", "In a video: pause, mute, seek 5 s back / forward, open in mpv"),
    ("Space", "Reveal spoilered image"),
    ("F", "Bookmark selected thread / open thread"),
    ("Shift+F", "Favourite current board"),
    ("O", "Open page in browser"),
    ("C", "Copy URL"),
    ("Delete", "Remove selected bookmark"),
    ("?", "This help"),
]
HINTS = {
    "welcome": "B choose board   ? help",
    "catalog": "B board   / filter   S sort   R refresh   ↑↓ navigate   Enter open   F bookmark   ? help",
    "thread": "Esc back   R refresh   ↑↓ navigate   Enter follow quote / media   M media   F bookmark   O browser   ? help",
    "bookmarks": "Esc back   R check for updates   ↑↓ navigate   Enter open   Delete remove   ? help",
}
ABOUT = ("LurkMoar is an independent read-only client.\n"
         "Content sourced from 4chan. Not affiliated with or endorsed by 4chan.")


def ago(seconds) -> str:
    s = max(0, int(seconds))
    if s < 5: return "just now"
    if s < 60: return f"{s}s ago"
    if s < 3600: return f"{s // 60} min ago"
    if s < 86400: return f"{s // 3600} h ago"
    return f"{s // 86400} d ago"


def filter_boards(boards, query, favs=()):
    q = query.strip().lower().strip("/")
    if not q:
        return sorted(boards, key=lambda b: (b.code not in favs, b.code))

    def score(b):
        c, t = b.code.lower(), b.title.lower()
        if c == q: return 0
        if c.startswith(q): return 1
        if any(w.startswith(q) for w in t.split()): return 2
        if q in t: return 3
        return None

    scored = [(score(b), b.code, b) for b in boards]
    return [b for s, _, b in sorted((x for x in scored if x[0] is not None), key=lambda x: x[:2])]


class Header(QFrame):
    toggle_rail = Signal()
    choose_board = Signal()
    refresh = Signal()
    help = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("header")
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 6, 10, 6)
        rail = QToolButton(text="☰")
        rail.setToolTip("Show / hide the board list")
        rail.clicked.connect(self.toggle_rail)
        brand = QLabel("LURKMOAR")
        brand.setObjectName("brand")
        self.where = QPushButton("Choose a board  (B)")
        self.where.setObjectName("where")
        self.where.setToolTip("Choose board (B)")
        self.where.clicked.connect(self.choose_board)
        self.status = QLabel("")
        self.status.setObjectName("muted")
        refresh = QToolButton(text="↻ Refresh")
        refresh.setToolTip("Refresh (R)")
        refresh.clicked.connect(self.refresh)
        helpb = QToolButton(text="?")
        helpb.setToolTip("Keyboard shortcuts and About (?)")
        helpb.clicked.connect(self.help)
        for w in (rail, brand, self.where):
            row.addWidget(w)
        row.addStretch(1)
        for w in (self.status, refresh, helpb):
            row.addWidget(w)


class Sidebar(QFrame):
    board_chosen = Signal(str)
    all_boards = Signal()
    bookmarks = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("rail")
        self.setFixedWidth(170)
        v = QVBoxLayout(self)
        v.setContentsMargins(8, 8, 8, 8)
        title = QLabel("BOARDS")
        title.setObjectName("muted")
        self.list = QListWidget()
        self.list.itemClicked.connect(lambda it: self.board_chosen.emit(it.data(Qt.UserRole)))
        self.all_btn = QPushButton("All boards…   B")
        self.all_btn.clicked.connect(self.all_boards)
        self.bm_btn = QPushButton("★ Bookmarks")
        self.bm_btn.clicked.connect(self.bookmarks)
        for w in (title, self.list, self.all_btn, self.bm_btn):
            v.addWidget(w)
        v.setStretch(1, 1)

    def _focused(self):
        # the window's focus widget: same as hasFocus() in a live session, and also right when the window is inactive
        fw = self.window().focusWidget()
        return fw if fw in (self.list, self.all_btn, self.bm_btn) else None

    def has_focus(self):
        return self._focused() is not None

    def enter(self):
        """Move keyboard focus into the rail with the current board highlighted."""
        if self.list.count() and self.list.currentRow() < 0:
            self.list.setCurrentRow(0)
        self.list.setFocus()

    def nav(self, key):
        """Up/Down walk list -> All boards -> Bookmarks; returns True when the key was consumed here."""
        chain = (self.list, self.all_btn, self.bm_btn)
        cur = next((i for i, w in enumerate(chain) if w is self._focused()), 0)
        if cur == 0:
            row, last = self.list.currentRow(), self.list.count() - 1
            if key == Qt.Key_Down:
                if row >= last:
                    self.all_btn.setFocus()
                else:
                    self.list.setCurrentRow(row + 1)
                return True
            if key == Qt.Key_Up:
                if row > 0:                              # top of the list: nothing above, stay put
                    self.list.setCurrentRow(row - 1)
                return True
            return False
        if key == Qt.Key_Down:
            chain[min(cur + 1, 2)].setFocus()
            return True
        if key == Qt.Key_Up:
            chain[cur - 1].setFocus()
            if cur == 1:
                self.list.setCurrentRow(self.list.count() - 1)
            return True
        return False

    def activate(self):
        """Enter on the focused widget: choose the board, or press the focused button."""
        fw = self._focused()
        if fw is self.list:
            self.choose_current()
        elif fw is not None:
            fw.click()

    def choose_current(self):
        it = self.list.currentItem()
        if it:
            self.board_chosen.emit(it.data(Qt.UserRole))

    def set_boards(self, favs, current):
        self.list.clear()
        codes = list(favs) + ([current] if current and current not in favs else [])
        for c in codes:
            it = QListWidgetItem(("★ " if c in favs else "   ") + f"/{c}/")
            it.setData(Qt.UserRole, c)
            self.list.addItem(it)
            if c == current:
                self.list.setCurrentItem(it)


class Banner(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("banner")
        h = QHBoxLayout(self)
        h.setContentsMargins(12, 6, 12, 6)
        self.label = QLabel("")
        self.label.setWordWrap(True)
        h.addWidget(self.label, 1)
        self._btns = []
        self.hide()

    def show_message(self, text, actions=()):
        for b in self._btns:
            self.layout().removeWidget(b)
            b.deleteLater()
        self._btns = []
        self.label.setText(text)
        for label, fn in actions:
            b = QPushButton(label)
            b.clicked.connect(lambda _=False, f=fn: f())
            self.layout().addWidget(b)
            self._btns.append(b)
        self.show()


class StatusLine(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("statusline")
        h = QHBoxLayout(self)
        h.setContentsMargins(10, 4, 10, 4)
        self.hint = QLabel("")
        self.hint.setObjectName("muted")
        self.msg = QLabel("")
        h.addWidget(self.hint, 1)
        h.addWidget(self.msg)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(lambda: self.msg.setText(""))

    def message(self, text, ms=5000):
        self.msg.setText(text)
        self._timer.start(ms)

    def set_hint(self, mode):
        self.hint.setText(HINTS.get(mode, ""))


class Welcome(QWidget):
    choose = Signal()

    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.addStretch(1)
        t = QLabel("Welcome to LurkMoar")
        f = QFont(t.font())
        f.setPointSize(f.pointSize() + 8)
        f.setBold(True)
        t.setFont(f)
        t.setAlignment(Qt.AlignCenter)
        s = QLabel("Choose a board to start browsing.")
        s.setAlignment(Qt.AlignCenter)
        b = QPushButton("B   Choose Board")
        b.clicked.connect(self.choose)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(b)
        row.addStretch(1)
        for w in (t, s):
            v.addWidget(w)
        v.addLayout(row)
        v.addStretch(2)

    def focus_list(self): pass
    def key_action(self, name): return False
    def current_ref(self): return None


class BoardPicker(QDialog):
    chosen = Signal(str)
    favourite_toggled = Signal(str)

    def __init__(self, parent, boards, favs):
        super().__init__(parent)
        self.setWindowTitle("Choose board")
        self.resize(480, 440)
        v = QVBoxLayout(self)
        v.addWidget(QLabel("Choose board"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Type to filter by code or name…")
        self.search.textChanged.connect(self.refill)
        self.search.returnPressed.connect(self._accept_current)
        self.search.installEventFilter(self)
        self.msg = QLabel("")
        self.msg.setObjectName("muted")
        self.list = QListWidget()
        mono = QFont("monospace")
        mono.setStyleHint(QFont.Monospace)
        self.list.setFont(mono)
        self.list.itemDoubleClicked.connect(self._accept_item)
        self.fav_btn = QPushButton("★ Toggle favourite")
        self.fav_btn.clicked.connect(self._fav)
        hint = QLabel("Enter Open    Esc Close")
        hint.setObjectName("muted")
        row = QHBoxLayout()
        row.addWidget(self.fav_btn)
        row.addStretch(1)
        row.addWidget(hint)
        for w in (self.search, self.msg, self.list):
            v.addWidget(w)
        v.addLayout(row)
        self.set_boards(boards, favs)
        self.search.setFocus()

    def eventFilter(self, o, e):
        if (o is self.search and e.type() == QEvent.KeyPress and e.key() == Qt.Key_Backspace
                and not self.search.text() and not e.modifiers()):
            self.reject()                           # nothing left to delete: Backspace backs out like Esc
            return True
        if o is self.search and e.type() == QEvent.KeyPress and e.key() in (Qt.Key_Up, Qt.Key_Down):
            step = 1 if e.key() == Qt.Key_Down else -1
            self.list.setCurrentRow(max(0, min(self.list.count() - 1, self.list.currentRow() + step)))
            return True
        return super().eventFilter(o, e)

    def set_boards(self, boards, favs):
        self.boards, self.favs = list(boards), set(favs)
        self.msg.setText("" if self.boards else "Loading boards…")
        self.refill()

    def set_favs(self, favs):
        self.favs = set(favs)
        self.refill()

    def refill(self):
        keep = self._current_code()
        self.list.clear()
        for b in filter_boards(self.boards, self.search.text(), self.favs):
            it = QListWidgetItem(f"{'★' if b.code in self.favs else ' '} /{b.code}/".ljust(9)
                                 + f" {b.title}" + ("" if b.worksafe else "   NSFW"))
            it.setData(Qt.UserRole, b.code)
            self.list.addItem(it)
            if b.code == keep:
                self.list.setCurrentItem(it)
        if self.list.count() and self.list.currentRow() < 0:
            self.list.setCurrentRow(0)

    def _current_code(self):
        it = self.list.currentItem()
        return it.data(Qt.UserRole) if it else None

    def _accept_item(self, it):
        self.chosen.emit(it.data(Qt.UserRole))
        self.accept()

    def _accept_current(self):
        if self.list.currentItem():
            self._accept_item(self.list.currentItem())

    def _fav(self):
        code = self._current_code()
        if code:
            self.favourite_toggled.emit(code)


class HelpDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("LurkMoar help")
        self.resize(560, 520)
        rows = "".join(f"<tr><td><b>{k}</b>&nbsp;&nbsp;</td><td>{d}</td></tr>" for k, d in KEYS)
        v = QVBoxLayout(self)
        body = QLabel(f"<h3>Keyboard shortcuts</h3><table>{rows}</table><h3>About</h3>"
                      f"<p>{ABOUT.replace(chr(10), '<br>')}</p>"
                      "<p><a href='https://www.4chan.org'>4chan.org</a></p>")
        body.setTextFormat(Qt.RichText)
        body.setOpenExternalLinks(True)
        body.setWordWrap(True)
        close = QPushButton("Close   Esc")
        close.clicked.connect(self.accept)
        v.addWidget(body, 1)
        v.addWidget(close)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Backspace and not e.modifiers():
            self.reject()
        else:
            super().keyPressEvent(e)


def bookmark_status(b, has_cache) -> str:
    if b.expired:
        return "Thread expired    " + ("cached copy available" if has_cache else "no cached copy")
    latest = b.latest_replies or b.last_known_reply_count
    if latest > b.last_known_reply_count:
        return f"{b.last_known_reply_count} → {latest} replies    +{latest - b.last_known_reply_count} new"
    return f"{latest} replies    unchanged"


class BookmarksView(QWidget):
    open_thread = Signal(str, str, int)

    def __init__(self, db, sites):
        super().__init__()
        self.db, self.sites = db, sites
        v = QVBoxLayout(self)
        v.setContentsMargins(10, 10, 10, 10)
        row = QHBoxLayout()
        title = QLabel("BOOKMARKS")
        title.setObjectName("brand")
        hint = QLabel("Saved on this computer only. Press R to check for new replies.")
        hint.setObjectName("muted")
        self.remove_btn = QPushButton("Remove bookmark   Del")
        self.remove_btn.clicked.connect(lambda: self.key_action("delete"))
        row.addWidget(title)
        row.addWidget(hint, 1)
        row.addWidget(self.remove_btn)
        self.empty = QLabel("No bookmarks yet.\nPress F on a thread in the catalog or while reading it.")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setObjectName("muted")
        self.list = QListWidget()
        mono = QFont("monospace")
        mono.setStyleHint(QFont.Monospace)
        self.list.setFont(mono)
        self.list.itemClicked.connect(lambda it: self._open(it))
        v.addLayout(row)
        v.addWidget(self.empty)
        v.addWidget(self.list, 1)
        self.reload()

    def _label(self, site, board, subject):
        if site == "4chan":
            return f"/{board}/  {subject}"
        name = self.sites[site].name if site in self.sites else site
        return f"{name} · /{board}/  {subject}"

    def _add(self, text, data=None, header=False):
        it = QListWidgetItem(text)
        if header:
            it.setFlags(Qt.NoItemFlags)
        else:
            it.setData(Qt.UserRole, data)
        self.list.addItem(it)

    def reload(self):
        cur = self.list.currentItem().data(Qt.UserRole) if self.list.currentItem() else None
        self.list.clear()
        bms = self.db.bookmarks()
        self.empty.setVisible(not bms)
        for b in bms:
            has = self.db.cache_get(site_key(b.site, "thread", b.board, b.thread_id)) is not None
            self._add(f"{self._label(b.site, b.board, b.subject)}\n      {bookmark_status(b, has)}",
                      ("bm", b.site, b.board, b.thread_id))
        marked = {(b.site, b.board, b.thread_id) for b in bms}
        recent = [r for r in self.db.recent() if (r[0], r[1], r[2]) not in marked]
        if recent:
            self._add("RECENTLY VISITED", header=True)
            for site, board, tid, subject in recent:
                self._add(self._label(site, board, subject), ("recent", site, board, tid))
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.UserRole) == cur and cur is not None:
                self.list.setCurrentRow(i)
                return
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.UserRole):
                self.list.setCurrentRow(i)
                return

    def on_bookmarks_changed(self):
        self.reload()

    def _selected(self):
        it = self.list.currentItem()
        return it.data(Qt.UserRole) if it else None

    def _open(self, it):
        d = it.data(Qt.UserRole)
        if d:
            self.open_thread.emit(d[1], d[2], d[3])

    def focus_list(self):
        self.list.setFocus()

    def key_action(self, name):
        d = self._selected()
        if name == "open":
            if d:
                self.open_thread.emit(d[1], d[2], d[3])
            return bool(d)
        if name == "delete":
            if d and d[0] == "bm":
                self.db.bookmark_remove(d[1], d[2], d[3])
                self.reload()
            return bool(d)
        if name in ("down", "up"):
            from PySide6.QtGui import QKeyEvent
            from PySide6.QtWidgets import QApplication
            QApplication.sendEvent(self.list, QKeyEvent(QEvent.KeyPress,
                                   Qt.Key_Down if name == "down" else Qt.Key_Up, Qt.NoModifier))
            return True
        return False

    def current_ref(self):
        d = self._selected()
        if not d:
            return None
        url = self.sites[d[1]].page_url(d[2], d[3]) if d[1] in self.sites else ""
        return dict(site=d[1], board=d[2], number=d[3], subject="", replies=0, url=url)
