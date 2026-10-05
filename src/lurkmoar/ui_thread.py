"""Thread reader: virtualised posts, rich body via QTextDocument built from whitelisted spans."""
import html as _html
import time
from collections import OrderedDict
from dataclasses import dataclass

from PySide6.QtCore import (QAbstractListModel, QEvent, QModelIndex, QPoint, QPointF, QRect, QRectF,
                            QSize, Qt, QTimer, Signal)
from PySide6.QtGui import (QAbstractTextDocumentLayout, QColor, QFont, QFontMetrics, QKeyEvent,
                           QPainter, QPalette, QTextDocument)
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QHBoxLayout, QLabel, QListView,
                               QMenu, QPushButton, QStyle, QStyledItemDelegate, QVBoxLayout, QWidget)

from .parse import quote_target
from .ui_media import is_video

PAD = 12


@dataclass
class Divider:
    count: int


class ThreadModel(QAbstractListModel):
    def __init__(self):
        super().__init__()
        self.items: list = []
        self.numbers: set = set()
        self.replies_to: dict = {}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.items)

    def data(self, index, role=Qt.DisplayRole):
        if role == Qt.UserRole and index.isValid():
            return self.items[index.row()]
        return None

    def flags(self, index):
        if index.isValid() and isinstance(self.items[index.row()], Divider):
            return Qt.ItemIsEnabled
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def _track(self, posts):
        for p in posts:
            self.numbers.add(p.number)
            for r in p.references:
                self.replies_to.setdefault(r, []).append(p.number)

    def load(self, posts):
        self.beginResetModel()
        self.items = list(posts)
        self.numbers, self.replies_to = set(), {}
        self._track(posts)
        self.endResetModel()

    def merge(self, posts):
        new = [p for p in posts if p.number not in self.numbers]
        if not new:
            return 0
        for r, it in enumerate(self.items):
            if isinstance(it, Divider):
                self.beginRemoveRows(QModelIndex(), r, r)
                del self.items[r]
                self.endRemoveRows()
                break
        start = len(self.items)
        self.beginInsertRows(QModelIndex(), start, start + len(new))
        self.items.extend([Divider(len(new))] + new)
        self._track(new)
        self.endInsertRows()
        return len(new)

    def post_at(self, row):
        it = self.items[row] if 0 <= row < len(self.items) else None
        return it if it is not None and not isinstance(it, Divider) else None

    def row_of(self, number):
        return next((i for i, x in enumerate(self.items)
                     if not isinstance(x, Divider) and x.number == number), -1)

    def post_count(self):
        return len(self.numbers)


def spans_html(spans, th, revealed):
    out = []
    for i, s in enumerate(spans):
        t = _html.escape(s.text, quote=False).replace("\n", "<br>")
        st = s.styles
        if "code" in st:
            t = f"<span style='font-family:monospace; white-space:pre-wrap'>{t}</span>"
        if "b" in st: t = f"<b>{t}</b>"
        if "i" in st: t = f"<i>{t}</i>"
        if "u" in st: t = f"<u>{t}</u>"
        if "greentext" in st: t = f"<span style='color:{th.quote}'>{t}</span>"
        if "quote" in st and s.target:
            t = f'<a href="q:{_html.escape(s.target)}">{t}</a>'
        elif "link" in st and s.target:
            t = f'<a href="l:{_html.escape(s.target)}">{t}</a>'
        if "spoiler" in st and i not in revealed:
            t = (f'<a href="s:{i}" style="color:{th.spoiler}; background-color:{th.spoiler}; '
                 f'text-decoration:none">{t}</a>')
        out.append(t)
    return "".join(out)


class ThreadDelegate(QStyledItemDelegate):
    """Paints a post and answers hit-tests from the same cached geometry."""

    def __init__(self, theme, cfg, thumb_fn, failed_fn):
        super().__init__()
        self.t, self.cfg, self.thumb_fn, self.failed_fn = theme, cfg, thumb_fn, failed_fn
        self.view_width = 700
        self.board = ""
        self.replies_to: dict = {}
        self.revealed_files: set = set()
        self.revealed_text: dict = {}
        self.flash_no = 0
        self._docs: OrderedDict = OrderedDict()
        self._geo: dict = {}
        self._rev = 0
        self.body = QFont()
        self.body.setPointSize(cfg.font_size)
        self.bold = QFont(self.body)
        self.bold.setBold(True)
        self.mono = QFont("monospace")
        self.mono.setStyleHint(QFont.Monospace)
        self.mono.setPointSize(max(8, cfg.font_size - 2))
        self.mfm, self.bfm = QFontMetrics(self.mono), QFontMetrics(self.bold)

    def invalidate(self, post_no=None):
        self._rev += 1                      # cache keys include the revision
        self._docs.clear()
        if post_no is None:
            self._geo.clear()
        else:
            self._geo = {k: v for k, v in self._geo.items() if k[0] != post_no}

    # ---- geometry
    def _box(self, post):
        a = post.attachment
        return self.cfg.thumb_size if a and not a.deleted else 0

    def _doc(self, post):
        key = (post.number, self.view_width, self._rev)
        doc = self._docs.get(key)
        if doc is not None:
            self._docs.move_to_end(key)
            return doc
        body = spans_html(post.spans, self.t, self.revealed_text.get(post.number, set()))
        back = self.replies_to.get(post.number)
        if back:
            links = " ".join(f'<a href="q:#p{n}">&gt;&gt;{n}</a>' for n in back)
            body += f'<br><span style="color:{self.t.foreground_muted}">Replies: {links}</span>'
        doc = QTextDocument()
        doc.setDocumentMargin(0)
        doc.setDefaultFont(self.body)
        doc.setDefaultStyleSheet(f"a {{ color: {self.t.link}; }}")
        doc.setHtml(body)
        box = self._box(post)
        doc.setTextWidth(max(120, self.view_width - 2 * PAD - (box + PAD if box else 0)))
        self._docs[key] = doc
        while len(self._docs) > 80:
            self._docs.popitem(last=False)
        return doc

    def geo(self, post):
        key = (post.number, self.view_width, self._rev)
        g = self._geo.get(key)
        if g is None:
            top = PAD + self.mfm.height() + 2
            if post.subject:
                top += self.bfm.height() + 2
            if post.attachment:
                top += self.mfm.height() + 2
            box = self._box(post)
            body_x = PAD + (box + PAD if box else 0)
            body_h = self._doc(post).size().height()
            g = dict(top=top + 4, box=box, body_x=body_x, body_h=body_h,
                     body_w=max(120, self.view_width - body_x - PAD),
                     height=int(top + 4 + max(body_h, box) + PAD + 1))
            self._geo[key] = g
        return g

    def sizeHint(self, option, index):
        item = index.data(Qt.UserRole)
        if isinstance(item, Divider):
            return QSize(self.view_width, 30)
        return QSize(self.view_width, self.geo(item)["height"])

    # ---- painting
    def caption(self, post):
        a = post.attachment
        if a is None:
            return ""
        live = [x for x in post.attachments if not x.deleted]
        if a.deleted:
            cap = "File deleted"
        else:
            cap = (f"{a.filename}{a.extension} · {a.width}×{a.height} · {a.size / 1024:.0f} KB"
                   + (" · spoiler" if a.spoiler and a.id not in self.revealed_files else ""))
        if len(live) > 1:
            cap += f" · +{len(live) - 1} more files"
        return cap

    def paint(self, p, opt, idx):
        item, th, r = idx.data(Qt.UserRole), self.t, opt.rect
        p.save()
        if isinstance(item, Divider):
            label = f"{item.count} NEW POST{'S' * (item.count != 1)}"
            p.fillRect(r, QColor(th.background))
            p.setFont(self.bold)
            p.setPen(QColor(th.new_post))
            w = QFontMetrics(self.bold).horizontalAdvance(label) + 24
            cx, cy = r.center().x(), r.center().y()
            p.drawLine(r.left() + PAD, cy, cx - w // 2, cy)
            p.drawLine(cx + w // 2, cy, r.right() - PAD, cy)
            p.drawText(QRect(cx - w // 2, r.y(), w, r.height()), Qt.AlignCenter, label)
            p.restore()
            return
        post, g = item, self.geo(item)
        sel = bool(opt.state & QStyle.State_Selected)
        is_op = post.number == post.thread_number
        bg = (th.surface_selected if sel else th.accent_muted if post.number == self.flash_no
              else th.surface if is_op else th.background)
        p.fillRect(r, QColor(bg))
        if sel:
            p.fillRect(QRect(r.x(), r.y(), 3, r.height()), QColor(th.accent))
        p.setPen(QColor(th.border))
        p.drawLine(r.left(), r.bottom(), r.right(), r.bottom())
        x, y = r.x() + PAD, r.y() + PAD
        # header: name  badge  No.  time
        p.setFont(self.bold)
        p.setPen(QColor(th.foreground))
        p.drawText(x, y + self.bfm.ascent(), post.name)
        x += self.bfm.horizontalAdvance(post.name) + 10
        p.setFont(self.mono)
        for text, col in ((("OP" if is_op else ""), th.accent),
                          ((f"## {post.capcode.upper()}" if post.capcode else ""), th.warning),
                          (f"No.{post.number}", th.foreground_muted),
                          (time.strftime("%Y-%m-%d %H:%M", time.localtime(post.timestamp)), th.foreground_muted)):
            if text:
                p.setPen(QColor(col))
                p.drawText(x, y + self.mfm.ascent(), text)
                x += self.mfm.horizontalAdvance(text) + 10
        y += self.mfm.height() + 2
        if post.subject:
            p.setFont(self.bold)
            p.setPen(QColor(th.accent))
            p.drawText(r.x() + PAD, y + self.bfm.ascent(), post.subject)
            y += self.bfm.height() + 2
        a = post.attachment
        if a:
            p.setFont(self.mono)
            p.setPen(QColor(th.foreground_muted))
            p.drawText(r.x() + PAD, y + self.mfm.ascent(), self.caption(post))
        y0 = r.y() + g["top"]
        if g["box"]:
            self._paint_thumb(p, QRect(r.x() + PAD, y0, g["box"], g["box"]), post)
        p.translate(r.x() + g["body_x"], y0)
        ctx = QAbstractTextDocumentLayout.PaintContext()
        ctx.palette.setColor(QPalette.Text, QColor(th.foreground))
        p.setClipRect(QRectF(0, 0, g["body_w"], g["body_h"]))
        self._doc(post).documentLayout().draw(p, ctx)
        p.restore()

    def _paint_thumb(self, p, box, post):
        th, a = self.t, post.attachment
        p.setPen(QColor(th.accent_muted))
        p.setBrush(QColor(th.surface))
        p.drawRect(box.adjusted(0, 0, -1, -1))
        p.setFont(self.mono)
        covered = a.spoiler and a.id not in self.revealed_files and not self.cfg.reveal_spoilers
        if covered:
            p.fillRect(box.adjusted(1, 1, -1, -1), QColor(th.spoiler))
            p.setPen(QColor(th.foreground))
            p.drawText(box.adjusted(4, 4, -4, -4), Qt.AlignCenter | Qt.TextWordWrap,
                       "SPOILER\nClick or Space to reveal")
            return
        img = self.thumb_fn(a)
        p.setPen(QColor(th.foreground_muted))
        if img is None:
            p.drawText(box.adjusted(4, 4, -4, -4), Qt.AlignCenter | Qt.TextWordWrap,
                       "Attachment unavailable" if self.failed_fn(a) else "…")
            return
        s = img.size().scaled(box.size(), Qt.KeepAspectRatio)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.drawImage(QRect(box.x() + (box.width() - s.width()) // 2,
                          box.y() + (box.height() - s.height()) // 2, s.width(), s.height()), img)
        if is_video(a.extension):
            p.fillRect(QRect(box.x(), box.bottom() - 16, 62, 16), QColor(0, 0, 0, 170))
            p.setPen(QColor("#ffffff"))
            p.drawText(QRect(box.x() + 4, box.bottom() - 16, 58, 16), Qt.AlignVCenter,
                       "▶ " + a.extension[1:].upper())

    # ---- hit testing (same geometry as paint)
    def hit(self, idx, rect, pos):
        post = idx.data(Qt.UserRole)
        if post is None or isinstance(post, Divider):
            return None
        g = self.geo(post)
        y0 = rect.y() + g["top"]
        if g["box"] and QRect(rect.x() + PAD, y0, g["box"], g["box"]).contains(pos):
            return ("media", post)
        pt = QPointF(pos.x() - (rect.x() + g["body_x"]), pos.y() - y0)
        if 0 <= pt.x() <= g["body_w"] and 0 <= pt.y() <= g["body_h"]:
            href = self._doc(post).documentLayout().anchorAt(pt)
            if href:
                return ("anchor", href)
        return None


class ThreadList(QListView):
    def __init__(self, delegate, on_hit):
        super().__init__()
        self._delegate, self._on_hit = delegate, on_hit
        self.setItemDelegate(delegate)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setMouseTracking(True)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        w = self.viewport().width()
        if w != self._delegate.view_width:
            self._delegate.view_width = w
            self._delegate.invalidate()
            self.scheduleDelayedItemsLayout()

    def _hit_at(self, pos):
        idx = self.indexAt(pos)
        return (idx, self._delegate.hit(idx, self.visualRect(idx), pos)) if idx.isValid() else (idx, None)

    def mouseMoveEvent(self, e):
        super().mouseMoveEvent(e)
        self.viewport().setCursor(Qt.PointingHandCursor if self._hit_at(e.position().toPoint())[1]
                                  else Qt.ArrowCursor)

    def mouseReleaseEvent(self, e):
        super().mouseReleaseEvent(e)
        if e.button() == Qt.LeftButton:
            idx, hit = self._hit_at(e.position().toPoint())
            if hit:
                self._on_hit(idx, hit)


class ThreadView(QWidget):
    back_requested = Signal()
    refresh_requested = Signal()
    bookmark_toggled = Signal()
    media_requested = Signal(str, str, object)
    link_requested = Signal(str)
    cross_requested = Signal(str, int, int)
    message = Signal(str)

    def __init__(self, theme, cfg, repo, db):
        super().__init__()
        self.t, self.cfg, self.repo, self.db = theme, cfg, repo, db
        self.site, self.board, self.number, self.subject = "4chan", "", 0, ""
        self.loaded, self.following, self.jumps, self._new = False, False, [], 0
        self.model = ThreadModel()
        self.delegate = ThreadDelegate(theme, cfg, lambda a: repo.thumb_image(self.site, self.board, a),
                                       lambda a: repo.thumb_failed(self.site, self.board, a))
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        head = QWidget()
        hv = QVBoxLayout(head)
        hv.setContentsMargins(10, 8, 10, 6)
        r1, r3 = QHBoxLayout(), QHBoxLayout()
        self.back_btn = QPushButton("← Back")
        self.back_btn.setToolTip("Back to the catalog (Esc)")
        self.back_btn.clicked.connect(self.back_requested)
        self.num_lbl = QLabel("")
        mono = QFont("monospace")
        mono.setStyleHint(QFont.Monospace)
        self.num_lbl.setFont(mono)
        self.follow_lbl = QLabel("")
        self.bm_btn = QPushButton("☆ Bookmark")
        self.bm_btn.setToolTip("Bookmark this thread (F)")
        self.bm_btn.clicked.connect(self.bookmark_toggled)
        refresh = QPushButton("↻ Refresh")
        refresh.setToolTip("Refresh (R)")
        refresh.clicked.connect(self.refresh_requested)
        web = QPushButton("Open in browser")
        web.setToolTip("Open the official page (O)")
        web.clicked.connect(lambda: self.link_requested.emit(self.current_ref()["url"] if self.current_ref() else ""))
        for w in (self.back_btn, self.num_lbl):
            r1.addWidget(w)
        r1.addStretch(1)
        for w in (self.follow_lbl, self.bm_btn, refresh, web):
            r1.addWidget(w)
        self.subj_lbl = QLabel("")
        f = QFont(self.subj_lbl.font())
        f.setBold(True)
        f.setPointSize(f.pointSize() + 2)
        self.subj_lbl.setFont(f)
        self.stats = QLabel("")
        self.stats.setObjectName("muted")
        self.jump_btn = QPushButton("↩ Back to previous position")
        self.jump_btn.clicked.connect(self.pop_jump)
        self.jump_btn.hide()
        r3.addWidget(self.stats)
        r3.addStretch(1)
        r3.addWidget(self.jump_btn)
        hv.addLayout(r1)
        hv.addWidget(self.subj_lbl)
        hv.addLayout(r3)
        self.list = ThreadList(self.delegate, self._on_hit)
        self.list.setModel(self.model)
        self.list.verticalScrollBar().valueChanged.connect(self._on_scroll)
        v.addWidget(head)
        v.addWidget(self.list, 1)

    # ---- lifecycle
    def begin(self, site, board, number, subject, bookmarked):
        self.site, self.board, self.number, self.subject = site, board, number, subject
        self.loaded, self.following, self._new = False, False, 0
        self.jumps.clear()
        self.model.load([])
        self.delegate.board = board
        self.delegate.invalidate()
        self.set_bookmarked(bookmarked)
        self._header()

    def load(self, thread, anchor=0):
        self.subject = thread.subject or self.subject
        self.delegate.replies_to = self.model.replies_to
        self.model.load(thread.posts)
        self.delegate.replies_to = self.model.replies_to
        self.delegate.invalidate()
        self.loaded = True
        self.list.doItemsLayout()
        row = self.model.row_of(anchor) if anchor else 0
        row = max(row, 0)
        self.list.setCurrentIndex(self.model.index(row))
        self.list.scrollTo(self.model.index(row), QAbstractItemView.PositionAtTop)
        self._header()

    def apply(self, thread, anchor=0):
        if not self.loaded:
            self.load(thread, anchor)
            return None
        top = self._top_post_and_y()
        had_backrefs = {k: len(v) for k, v in self.model.replies_to.items()}
        n = self.model.merge(thread.posts)
        if n:
            for k, v in self.model.replies_to.items():
                if len(v) != had_backrefs.get(k, 0):
                    self.delegate.invalidate(k)
            self.list.doItemsLayout()
            if top:
                no, old_y = top
                row = self.model.row_of(no)
                if row >= 0:
                    new_y = self.list.visualRect(self.model.index(row)).y()
                    sb = self.list.verticalScrollBar()
                    sb.setValue(sb.value() + new_y - old_y)
            if self.following:
                self.list.scrollToBottom()
            self._new = n
        self._header()
        return n

    def _top_post_and_y(self):
        idx = self.list.indexAt(QPoint(5, 5))
        while idx.isValid():
            post = self.model.post_at(idx.row())
            if post:
                return post.number, self.list.visualRect(idx).y()
            idx = self.model.index(idx.row() + 1)
        return None

    def anchor(self):
        top = self._top_post_and_y()
        return top[0] if top else 0

    def replies(self): return max(0, self.model.post_count() - 1)

    def images(self):
        return sum(1 for r in range(self.model.rowCount()) if (p := self.model.post_at(r))
                   for a in p.attachments if not a.deleted)

    def _header(self):
        self.num_lbl.setText(f"No.{self.number}")
        self.subj_lbl.setText(self.subject or "(no subject)")
        s = f"{self.replies()} replies · {self.images()} images"
        self.stats.setText(s + (f" · {self._new} new" if self._new else ""))
        self._follow_label()

    def _follow_label(self):
        if not self.cfg.auto_refresh:
            self.follow_lbl.setText("")
        else:
            self.follow_lbl.setText("● Following new posts" if self.following else "○ Follow paused")

    def _on_scroll(self, value):
        sb = self.list.verticalScrollBar()
        self.following = sb.maximum() > 0 and value >= sb.maximum() - 4
        self._follow_label()

    def set_bookmarked(self, on):
        self.bm_btn.setText("★ Bookmarked" if on else "☆ Bookmark")

    def on_bookmarks_changed(self):
        self.set_bookmarked(self.db.bookmark_has(self.site, self.board, self.number))

    # ---- quotes and jumps
    def current_post(self):
        return self.model.post_at(self.list.currentIndex().row())

    def _goto(self, no):
        row = self.model.row_of(no)
        idx = self.model.index(row)
        self.list.setCurrentIndex(idx)
        self.list.scrollTo(idx, QAbstractItemView.PositionAtTop)
        self.delegate.flash_no = no
        self.list.viewport().update()
        QTimer.singleShot(1200, self._unflash)

    def _unflash(self):
        self.delegate.flash_no = 0
        self.list.viewport().update()

    def follow_quote(self, href):
        q = quote_target(href)
        if q is None:
            return
        board, thread, post = q
        if board is not None:
            self.cross_requested.emit(board, thread, post)
            return
        if self.model.row_of(post) < 0:
            self.message.emit(f">>{post} isn't in this thread (deleted or not loaded)")
            return
        cur = self.current_post()
        self.jumps.append((self.list.verticalScrollBar().value(), cur.number if cur else 0))
        self.jump_btn.show()
        self._goto(post)

    def pop_jump(self):
        if not self.jumps:
            return False
        value, no = self.jumps.pop()
        if no and self.model.row_of(no) >= 0:
            self.list.setCurrentIndex(self.model.index(self.model.row_of(no)))
        self.list.verticalScrollBar().setValue(value)
        self.jump_btn.setVisible(bool(self.jumps))
        self.list.setFocus()
        return True

    # ---- clicks and keys
    def _on_hit(self, idx, hit):
        kind, val = hit
        self.list.setCurrentIndex(idx)
        if kind == "media":
            self.open_media(val)
            return
        tag, _, rest = val.partition(":")
        post = self.model.post_at(idx.row())
        if tag == "q":
            self.follow_quote(rest)
        elif tag == "l":
            self.link_requested.emit(rest)
        elif tag == "s" and post:
            self.delegate.revealed_text.setdefault(post.number, set()).add(int(rest))
            self.delegate.invalidate(post.number)
            self.list.viewport().update()

    def gallery(self):
        """Every live attachment in thread order, as (post number, Attachment)."""
        out = []
        for r in range(self.model.rowCount()):
            p = self.model.post_at(r)
            if p:
                out += [(p.number, a) for a in p.attachments if not a.deleted]
        return out

    def select_attachment(self, att_id):
        for r in range(self.model.rowCount()):
            p = self.model.post_at(r)
            if p and any(x.id == att_id for x in p.attachments):
                idx = self.model.index(r)
                self.list.setCurrentIndex(idx)
                self.list.scrollTo(idx, QAbstractItemView.EnsureVisible)
                return

    def open_media(self, post):
        a = post.attachment
        if not a or a.deleted:
            self.message.emit("Attachment unavailable")
            return
        if a.spoiler and a.id not in self.delegate.revealed_files and not self.cfg.reveal_spoilers:
            self.delegate.revealed_files.add(a.id)
            self.list.viewport().update()
            return
        self.media_requested.emit(self.site, self.board, a)

    def focus_list(self):
        self.list.setFocus()

    def key_action(self, name):
        post = self.current_post()
        if name == "back":
            return self.pop_jump()
        if name in ("down", "up"):
            key = Qt.Key_Down if name == "down" else Qt.Key_Up
            QApplication.sendEvent(self.list, QKeyEvent(QEvent.KeyPress, key, Qt.NoModifier))
            return True
        if post is None:
            return False
        if name == "reveal":
            a = post.attachment
            if a and a.spoiler and a.id not in self.delegate.revealed_files:
                self.delegate.revealed_files.add(a.id)
                self.list.viewport().update()
                return True
            return False
        if name == "media":
            self.open_media(post)
            return True
        if name == "open":
            refs = [r for r in post.references if self.model.row_of(r) >= 0]
            if len(refs) == 1:
                self.follow_quote(f"#p{refs[0]}")
            elif refs:
                menu = QMenu(self)
                for r in refs:
                    menu.addAction(f">>{r}", lambda r=r: self.follow_quote(f"#p{r}"))
                menu.exec(self.list.viewport().mapToGlobal(self.list.visualRect(self.list.currentIndex()).center()))
            elif post.attachment and not post.attachment.deleted:
                self.open_media(post)
            else:
                self.message.emit("Nothing to open in this post")
            return True
        return False

    def current_ref(self):
        if not self.number:
            return None
        post = self.current_post()
        url = self.repo.sites[self.site].page_url(self.board, self.number, post.number if post else None)
        return dict(site=self.site, board=self.board, number=self.number, subject=self.subject or f"No.{self.number}",
                    replies=self.replies(), url=url)
