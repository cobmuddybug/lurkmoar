"""Catalog: virtualised thread rows with sort and local filter."""
import time

from PySide6.QtCore import (QAbstractListModel, QEvent, QModelIndex, QPoint, QRect, QRectF, QSize,
                            Qt, Signal)
from PySide6.QtGui import QColor, QFont, QFontMetrics, QKeyEvent, QPainter
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QHBoxLayout, QLabel,
                               QLineEdit, QListView, QPushButton, QStyle, QStyledItemDelegate,
                               QVBoxLayout, QWidget)

from .ui_media import is_video
from .ui_misc import ago

PAD = 10
SORTS = {"activity": "Activity", "replies": "Replies", "images": "Images", "created": "Newest"}
_KEYS = {"replies": lambda t: -t.replies, "images": lambda t: -t.images,
         "created": lambda t: -t.created_at}


def arrange(threads, sort, text):
    q = text.strip().lower()
    out = [t for t in threads
           if not q or q in t.subject.lower() or q in t.comment.lower() or q in str(t.number)]
    return out if sort == "activity" else sorted(out, key=_KEYS[sort])


class CatalogModel(QAbstractListModel):
    def __init__(self):
        super().__init__()
        self._all, self._rows = [], []
        self.sort, self.text = "activity", ""

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index, role=Qt.DisplayRole):
        if role == Qt.UserRole and index.isValid():
            return self._rows[index.row()]
        return None

    def _rebuild(self):
        self.beginResetModel()
        self._rows = arrange(self._all, self.sort, self.text)
        self.endResetModel()

    def set_threads(self, threads):
        old = {t.number for t in self._all}
        self._all = list(threads)
        new = sum(t.number not in old for t in self._all) if old else None
        self._rebuild()
        return new

    def set_sort(self, key):
        self.sort = key
        self._rebuild()

    def set_filter(self, text):
        self.text = text
        self._rebuild()

    def thread_at(self, row):
        return self._rows[row] if 0 <= row < len(self._rows) else None

    def number_at(self, row):
        t = self.thread_at(row)
        return t.number if t else 0

    def row_of(self, number):
        return next((i for i, t in enumerate(self._rows) if t.number == number), -1)

    def counts(self):
        return len(self._rows), len(self._all)


class CatalogDelegate(QStyledItemDelegate):
    def __init__(self, theme, cfg, thumb_fn, failed_fn):
        super().__init__()
        self.t, self.cfg, self.thumb_fn, self.failed_fn = theme, cfg, thumb_fn, failed_fn
        self.bookmarked: set = set()
        self.bold = QFont()
        self.bold.setBold(True)
        self.bold.setPointSize(cfg.font_size + 1)
        self.body = QFont()
        self.body.setPointSize(cfg.font_size)
        self.mono = QFont("monospace")
        self.mono.setStyleHint(QFont.Monospace)
        self.mono.setPointSize(max(8, cfg.font_size - 2))

    def sizeHint(self, option, index):
        return QSize(100, self.cfg.thumb_size + 2 * PAD)

    def _thumb(self, p, box, t):
        th, att = self.t, t.thumbnail
        p.setPen(QColor(th.border))
        p.setBrush(QColor(th.surface))
        p.drawRect(box.adjusted(0, 0, -1, -1))
        p.setFont(self.mono)
        p.setPen(QColor(th.foreground_muted))
        if att is None:
            p.drawText(box, Qt.AlignCenter, "no image")
            return
        if att.spoiler and not self.cfg.reveal_spoilers:
            p.fillRect(box.adjusted(1, 1, -1, -1), QColor(th.spoiler))
            p.setPen(QColor(th.foreground))
            p.drawText(box, Qt.AlignCenter | Qt.TextWordWrap, "SPOILER")
            return
        img = self.thumb_fn(t.site, t.board, att)
        if img is None:
            p.drawText(box, Qt.AlignCenter | Qt.TextWordWrap,
                       "Attachment unavailable" if self.failed_fn(t.site, t.board, att) else "…")
            return
        s = img.size().scaled(box.size(), Qt.KeepAspectRatio)
        target = QRect(box.x() + (box.width() - s.width()) // 2,
                       box.y() + (box.height() - s.height()) // 2, s.width(), s.height())
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.drawImage(target, img)
        if is_video(att.extension):
            p.fillRect(QRect(box.x(), box.bottom() - 16, 60, 16), QColor(0, 0, 0, 170))
            p.setPen(QColor("#ffffff"))
            p.drawText(QRect(box.x() + 4, box.bottom() - 16, 56, 16), Qt.AlignVCenter,
                       "▶ " + att.extension[1:].upper())

    def paint(self, p, opt, idx):
        t, th, r = idx.data(Qt.UserRole), self.t, opt.rect
        sel, hov = bool(opt.state & QStyle.State_Selected), bool(opt.state & QStyle.State_MouseOver)
        p.save()
        p.fillRect(r, QColor(th.surface_selected if sel else th.surface_hover if hov else th.background))
        if sel:
            p.fillRect(QRect(r.x(), r.y(), 3, r.height()), QColor(th.accent))
        p.setPen(QColor(th.border))
        p.drawLine(r.left(), r.bottom(), r.right(), r.bottom())
        box = self.cfg.thumb_size
        trect = QRect(r.x() + PAD + 4, r.y() + PAD, box, box)
        self._thumb(p, trect, t)
        x, w = trect.right() + PAD + 6, r.right() - trect.right() - 2 * PAD - 6
        y = r.y() + PAD
        # subject
        p.setFont(self.bold)
        p.setPen(QColor(th.foreground))
        fm = QFontMetrics(self.bold)
        star = "★ " if (t.site, t.board, t.number) in self.bookmarked else ""
        p.drawText(QRect(x, y, w, fm.height()), Qt.AlignVCenter,
                   fm.elidedText(star + (t.subject or "(no subject)"), Qt.ElideRight, w))
        y += fm.height() + 2
        # meta
        p.setFont(self.mono)
        p.setPen(QColor(th.foreground_muted))
        mfm = QFontMetrics(self.mono)
        p.drawText(QRect(x, y, w, mfm.height()), Qt.AlignVCenter, f"Anonymous · No.{t.number}")
        y += mfm.height() + 4
        # stats pinned to the bottom
        stats_y = r.bottom() - PAD - mfm.height()
        flags = ("   STICKY" if t.sticky else "") + ("   CLOSED" if t.closed else "")
        p.drawText(QRect(x, stats_y, w, mfm.height()), Qt.AlignVCenter,
                   f"{t.replies} replies · {t.images} images · active {ago(time.time() - t.modified_at)}{flags}")
        # excerpt
        p.setFont(self.body)
        p.setPen(QColor(th.foreground))
        text = t.comment.replace("\n", " ")
        text = text[:220] + "…" if len(text) > 220 else text
        p.drawText(QRect(x, y, w, max(0, stats_y - y - 2)), Qt.AlignTop | Qt.TextWordWrap, text)
        p.restore()


class CatalogView(QWidget):
    open_thread = Signal(str, str, int)
    refresh_requested = Signal()
    favourite_board = Signal()

    def __init__(self, theme, cfg, repo, db):
        super().__init__()
        self.t, self.cfg, self.db, self.repo = theme, cfg, db, repo
        self.site, self.board = "4chan", ""
        self.model = CatalogModel()
        self.delegate = CatalogDelegate(theme, cfg, repo.thumb_image, repo.thumb_failed)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        bar = QWidget()
        h = QHBoxLayout(bar)
        h.setContentsMargins(10, 8, 10, 8)
        self.title = QLabel("")
        f = QFont(self.title.font())
        f.setBold(True)
        self.title.setFont(f)
        self.fav_btn = QPushButton("☆ Favourite board")
        self.fav_btn.setToolTip("Add or remove this board in the left rail (Shift+F)")
        self.fav_btn.clicked.connect(self.favourite_board)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter catalog…   ( / )")
        self.filter.setClearButtonEnabled(True)
        self.filter.textChanged.connect(self._on_filter)
        self.count = QLabel("")
        self.count.setObjectName("muted")
        self.sort = QComboBox()
        for k, label in SORTS.items():
            self.sort.addItem(f"Sort: {label}", k)
        self.sort.currentIndexChanged.connect(self._on_sort)
        refresh = QPushButton("↻")
        refresh.setToolTip("Refresh (R)")
        refresh.clicked.connect(self.refresh_requested)
        h.addWidget(self.title)
        h.addWidget(self.fav_btn)
        h.addWidget(self.filter, 1)
        h.addWidget(self.count)
        h.addWidget(self.sort)
        h.addWidget(refresh)
        self.note = QLabel("")
        self.note.setObjectName("muted")
        self.note.setAlignment(Qt.AlignCenter)
        self.note.hide()
        self.list = QListView()
        self.list.setModel(self.model)
        self.list.setItemDelegate(self.delegate)
        self.list.setUniformItemSizes(True)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.list.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.list.setMouseTracking(True)
        self.list.viewport().setCursor(Qt.PointingHandCursor)
        self.list.clicked.connect(lambda i: self._open(i.row()))
        v.addWidget(bar)
        v.addWidget(self.note)
        v.addWidget(self.list, 1)

    # ---- board / data
    def set_board(self, site, code, board=None):
        self.site, self.board = site, code
        prefix = "" if site == "4chan" else self.repo.sites[site].name + " "
        self.title.setText(f"{prefix}/{code}/ {board.title}" if board and board.title else f"{prefix}/{code}/")
        self.filter.blockSignals(True)
        self.filter.clear()
        self.filter.blockSignals(False)
        self.model.text = ""
        self.model.set_threads([])
        self.on_bookmarks_changed()
        self._update_count()

    def set_favourite(self, on):
        self.fav_btn.setText("★ Favourite board" if on else "☆ Favourite board")

    def show_loading(self, code):
        self.note.setText(f"Loading /{code}/…")
        self.note.show()

    def show_threads(self, threads):
        sb = self.list.verticalScrollBar()
        value, sel = sb.value(), self.current_number()
        new = self.model.set_threads(threads)
        self.list.doItemsLayout()
        sb.setValue(value)
        row = self.model.row_of(sel) if sel else -1
        if self.model.rowCount():
            self.list.setCurrentIndex(self.model.index(max(row, 0)))
        self._update_count()
        return new

    def _update_count(self):
        shown, total = self.model.counts()
        self.count.setText(f"{total} threads" if not self.model.text.strip()
                           else f"{shown} of {total} threads")
        if total and not shown:
            self.note.setText("No threads match this filter.")
            self.note.show()
        elif total:
            self.note.hide()

    # ---- position
    def anchor(self):
        idx = self.list.indexAt(QPoint(5, 5))
        return self.model.number_at(idx.row()) if idx.isValid() else 0

    def current_number(self):
        return self.model.number_at(self.list.currentIndex().row())

    def restore(self, anchor, select):
        self.list.doItemsLayout()
        row = self.model.row_of(anchor) if anchor else -1
        if row >= 0:
            self.list.scrollTo(self.model.index(row), QAbstractItemView.PositionAtTop)
        if select:
            self.select(select)

    def select(self, number):
        row = self.model.row_of(number)
        if row >= 0:
            self.list.setCurrentIndex(self.model.index(row))
            self.list.scrollTo(self.model.index(row), QAbstractItemView.EnsureVisible)

    # ---- filter / sort
    def _on_filter(self, text):
        self.model.set_filter(text)
        self._update_count()
        if self.model.rowCount():
            self.list.setCurrentIndex(self.model.index(0))
            self.list.scrollToTop()

    def _on_sort(self, _):
        self.model.set_sort(self.sort.currentData())
        if self.model.rowCount():
            self.list.setCurrentIndex(self.model.index(0))
            self.list.scrollToTop()

    def clear_filter(self):
        if self.filter.text() or self.filter.hasFocus():
            self.filter.clear()
            self.list.setFocus()
            return True
        return False

    # ---- page protocol
    def _open(self, row):
        t = self.model.thread_at(row)
        if t:
            self.open_thread.emit(t.site, t.board, t.number)
        return t is not None

    def focus_list(self):
        self.list.setFocus()

    def key_action(self, name):
        if name == "open":
            return self._open(self.list.currentIndex().row())
        if name == "filter":
            self.filter.setFocus()
            self.filter.selectAll()
            return True
        if name == "sort":
            self.sort.setCurrentIndex((self.sort.currentIndex() + 1) % self.sort.count())
            return True
        if name in ("down", "up"):
            key = Qt.Key_Down if name == "down" else Qt.Key_Up
            QApplication.sendEvent(self.list, QKeyEvent(QEvent.KeyPress, key, Qt.NoModifier))
            return True
        if name == "back":
            return self.clear_filter()
        return False

    def current_ref(self):
        t = self.model.thread_at(self.list.currentIndex().row())
        if not t:
            return None
        return dict(site=t.site, board=t.board, number=t.number, replies=t.replies,
                    subject=t.subject or t.comment[:60] or f"No.{t.number}",
                    url=self.repo.sites[t.site].page_url(t.board, t.number))

    def on_bookmarks_changed(self):
        self.delegate.bookmarked = {(b.site, b.board, b.thread_id) for b in self.db.bookmarks()}
        self.list.viewport().update()
