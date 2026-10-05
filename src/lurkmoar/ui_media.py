"""External-open helpers and the in-app image viewer."""
import shlex
import subprocess

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
                               QWidget)

VIDEO_EXT = {".webm", ".mp4"}


def is_video(ext: str) -> bool:
    return ext.lower() in VIDEO_EXT


def _spawn(argv):
    subprocess.Popen(argv, start_new_session=True, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def open_url(url: str):
    _spawn(["xdg-open", url])


def play_video(command: str, url: str):
    _spawn(shlex.split(command or "mpv") + [url])


class Canvas(QWidget):
    def __init__(self):
        super().__init__()
        self.img, self.note = None, ""
        self.scale, self.off, self.fitted = 1.0, QPointF(0, 0), True
        self._drag = None
        self.bg = "#000000"
        self.fg = "#ffffff"

    def set_image(self, img):
        self.img, self.note = img, ""
        self.fit()

    def set_note(self, text):
        self.img, self.note = None, text
        self.update()

    def fit(self):
        self.fitted, self.off = True, QPointF(0, 0)
        if self.img is not None and self.img.width() and self.img.height():
            self.scale = min(self.width() / self.img.width(), self.height() / self.img.height())
        self.update()

    def actual(self):
        self.fitted, self.scale, self.off = False, 1.0, QPointF(0, 0)
        self.update()

    def zoom(self, factor, anchor=None):
        self.fitted = False
        old = self.scale
        self.scale = max(0.02, min(32.0, self.scale * factor))
        if anchor is not None:
            c = QPointF(anchor) - QPointF(self.width() / 2, self.height() / 2)
            self.off = c - (c - self.off) * (self.scale / old)
        self.update()

    def resizeEvent(self, e):
        if self.fitted:
            self.fit()

    def wheelEvent(self, e):
        self.zoom(1.15 ** (e.angleDelta().y() / 120), e.position())

    def mousePressEvent(self, e):
        self._drag = e.position()
        self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, e):
        if self._drag is not None:
            self.off += e.position() - self._drag
            self._drag = e.position()
            self.fitted = False
            self.update()

    def mouseReleaseEvent(self, e):
        self._drag = None
        self.setCursor(Qt.OpenHandCursor)

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(self.bg))
        if self.img is None:
            p.setPen(QColor(self.fg))
            p.drawText(self.rect(), Qt.AlignCenter | Qt.TextWordWrap, self.note)
            return
        w, h = self.img.width() * self.scale, self.img.height() * self.scale
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.drawImage(QRectF(self.width() / 2 - w / 2 + self.off.x(),
                           self.height() / 2 - h / 2 + self.off.y(), w, h), self.img)


def _size(n):
    return f"{n / 1024:.0f} KB" if n < 1024 * 1024 else f"{n / 1024 / 1024:.1f} MB"


class MediaViewer(QFrame):
    message = Signal(str)

    def __init__(self, parent, theme, cfg, repo):
        super().__init__(parent)
        self.cfg, self.repo, self.att, self.board = cfg, repo, None, ""
        self.setObjectName("viewer")
        self.setStyleSheet(f"#viewer {{ background: {theme.background}; }}")
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.canvas = Canvas()
        self.canvas.bg, self.canvas.fg = theme.background, theme.foreground
        self.canvas.setCursor(Qt.OpenHandCursor)
        bar = QFrame()
        bar.setObjectName("statusline")
        h = QHBoxLayout(bar)
        h.setContentsMargins(10, 6, 10, 6)
        self.info = QLabel("")
        self.info.setObjectName("muted")
        hint = QLabel("+ / − zoom   0 fit   1 actual size   wheel zoom · drag pan")
        hint.setObjectName("muted")
        open_btn = QPushButton("Open original  O")
        open_btn.clicked.connect(self._open_original)
        copy_btn = QPushButton("Copy URL  C")
        copy_btn.clicked.connect(self._copy)
        close_btn = QPushButton("Close  Esc")
        close_btn.clicked.connect(self.close_)
        h.addWidget(self.info)
        h.addWidget(hint, 1)
        for b in (open_btn, copy_btn, close_btn):
            h.addWidget(b)
        v.addWidget(self.canvas, 1)
        v.addWidget(bar)
        repo.media_ready.connect(self.on_media)
        self.hide()

    def show_attachment(self, board, att):
        self.board, self.att = board, att
        self.info.setText(f"{att.width}×{att.height} · {att.extension[1:].upper()} · {_size(att.size)}")
        self.canvas.set_note("Loading image…")
        self.setGeometry(self.parentWidget().rect())
        self.show()
        self.raise_()
        self.canvas.setFocus()
        self.repo.request_media(board, att)

    def on_media(self, url, img, error):
        if self.att is None or url != self.att.original_url or not self.isVisible():
            return
        if img is None:
            self.canvas.set_note(f"Couldn't load this image ({error}).\nPress O to open the original.")
        else:
            self.canvas.set_image(img)

    def close_(self):
        self.hide()
        self.att = None
        self.parentWidget().window().activateWindow()

    def _open_original(self):
        if self.att:
            open_url(self.att.original_url)
            self.message.emit("Opened original in your default app")

    def _copy(self):
        if self.att:
            QApplication.clipboard().setText(self.att.original_url)
            self.message.emit(f"Copied {self.att.original_url}")

    def key(self, k, ch):
        if ch in ("+", "="): self.canvas.zoom(1.25)
        elif ch in ("-", "_"): self.canvas.zoom(0.8)
        elif ch == "0": self.canvas.fit()
        elif ch == "1": self.canvas.actual()
        elif ch.lower() == "o": self._open_original()
        elif ch.lower() == "c": self._copy()
        return True
