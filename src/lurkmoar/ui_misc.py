"""Small shared widgets: header, rail, banner, status line, picker, help."""
from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPushButton, QToolButton, QVBoxLayout, QWidget)

KEYS = [
    ("B", "Choose board"),
    ("/", "Filter catalog"),
    ("S", "Cycle catalog sort"),
    ("R", "Refresh (on Bookmarks: check for updates)"),
    ("↑ ↓  or  K J", "Previous / next item"),
    ("PgUp PgDn Home End", "Scroll"),
    ("Enter", "Open selected thread; in a thread follow a quote or open media"),
    ("Esc", "Back / close (undoes quote jumps first)"),
    ("M", "Open selected post's media"),
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
        all_btn = QPushButton("All boards…   B")
        all_btn.clicked.connect(self.all_boards)
        bm = QPushButton("★ Bookmarks")
        bm.clicked.connect(self.bookmarks)
        for w in (title, self.list, all_btn, bm):
            v.addWidget(w)
        v.setStretch(1, 1)

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
