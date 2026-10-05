"""External-open helpers and the in-app image viewer."""
import shlex
import subprocess

from PySide6.QtCore import QPointF, QRectF, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QStackedWidget,
                               QVBoxLayout, QWidget)

from .models import is_video  # noqa: F401  (re-exported for the UI modules)


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
    """Full-window overlay: cycles through a gallery of images and videos."""
    message = Signal(str)
    closed = Signal(object)       # id of the attachment to select in the thread, or 0 if unchanged (ids exceed 32 bits)

    def __init__(self, parent, theme, cfg, repo):
        super().__init__(parent)
        self.cfg, self.repo, self.att, self.board = cfg, repo, None, ""
        self.items, self.index, self._start = [], 0, 0
        self.setObjectName("viewer")
        self.setStyleSheet(f"#viewer {{ background: {theme.background}; }}")
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.canvas = Canvas()
        self.canvas.bg, self.canvas.fg = theme.background, theme.foreground
        self.canvas.setCursor(Qt.OpenHandCursor)
        self.video = QVideoWidget()
        self.audio = QAudioOutput(self)
        self.audio.setMuted(cfg.video_start_muted)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video)
        self.player.setLoops(QMediaPlayer.Loops.Infinite)
        self.player.errorOccurred.connect(lambda _e, text: self.on_player_error(text))
        self.player.positionChanged.connect(lambda _p: self._video_status())
        self.player.playbackStateChanged.connect(lambda _s: self._video_status())
        self.stack = QStackedWidget()
        self.stack.addWidget(self.canvas)
        self.stack.addWidget(self.video)
        bar = QFrame()
        bar.setObjectName("statusline")
        h = QHBoxLayout(bar)
        h.setContentsMargins(10, 6, 10, 6)
        self.info = QLabel("")
        self.info.setObjectName("muted")
        self.vstatus = QLabel("")
        self.vstatus.setObjectName("muted")
        self.hint = QLabel("")
        self.hint.setObjectName("muted")
        prev_btn = QPushButton("◀")
        prev_btn.setToolTip("Previous (←)")
        prev_btn.clicked.connect(lambda: self.step(-1))
        next_btn = QPushButton("▶")
        next_btn.setToolTip("Next (→)")
        next_btn.clicked.connect(lambda: self.step(1))
        open_btn = QPushButton("Open original  O")
        open_btn.clicked.connect(self._open_original)
        copy_btn = QPushButton("Copy URL  C")
        copy_btn.clicked.connect(self._copy)
        close_btn = QPushButton("Close  Esc")
        close_btn.clicked.connect(self.close_)
        h.addWidget(prev_btn)
        h.addWidget(next_btn)
        h.addWidget(self.info)
        h.addWidget(self.vstatus)
        h.addWidget(self.hint, 1)
        for b in (open_btn, copy_btn, close_btn):
            h.addWidget(b)
        v.addWidget(self.stack, 1)
        v.addWidget(bar)
        repo.media_ready.connect(self.on_media)
        self.hide()

    # ---- showing things
    def show_attachment(self, board, att, gallery=None):
        items = list(gallery or [])
        idx = next((i for i, a in enumerate(items) if a.id == att.id), -1)
        if idx < 0:
            items, idx = [att], 0
        self.board, self.items, self.index, self._start = board, items, idx, idx
        self.setGeometry(self.parentWidget().rect())
        self.show()
        self.raise_()
        self.canvas.setFocus()
        self._show_current()

    def _stop_video(self):
        self.player.stop()
        self.player.setSource(QUrl())
        self.vstatus.setText("")

    def _show_current(self):
        self._stop_video()
        self.att = att = self.items[self.index]
        video = is_video(att.extension)
        counter = f"{self.index + 1} / {len(self.items)} · " if len(self.items) > 1 else ""
        self.info.setText(f"{counter}{att.width}×{att.height} · {att.extension[1:].upper()} · {_size(att.size)}")
        self.hint.setText("Space pause   M mute   [ ] seek   V open in "
                          + (self.cfg.video_command.split() or ["mpv"])[0] + "   ← → next" if video else
                          "+ / − zoom   0 fit   1 actual size   wheel zoom · drag pan   ← → previous / next")
        self.stack.setCurrentWidget(self.canvas)
        self.canvas.set_note("Loading video…" if video else "Loading image…")
        self.repo.request_media(self.board, att)

    def step(self, delta):
        if len(self.items) < 2:
            return
        self.index = (self.index + delta) % len(self.items)
        self._show_current()

    def on_media(self, url, data, error):
        if self.att is None or url != self.att.original_url or not self.isVisible():
            return
        kind = "video" if is_video(self.att.extension) else "image"
        if data is None:
            self.stack.setCurrentWidget(self.canvas)
            tail = "Press V to open it in the external player." if kind == "video" else "Press O to open the original."
            self.canvas.set_note(f"Couldn't load this {kind} ({error}).\n{tail}")
        elif isinstance(data, str):
            self.stack.setCurrentWidget(self.video)
            self.player.setSource(QUrl.fromLocalFile(data))
            self.player.play()
        else:
            self.stack.setCurrentWidget(self.canvas)
            self.canvas.set_image(data)

    def on_player_error(self, text):
        if self.att is None or not is_video(self.att.extension):
            return
        self.player.stop()
        self.stack.setCurrentWidget(self.canvas)
        name = (self.cfg.video_command.split() or ["mpv"])[0]
        self.canvas.set_note(f"Couldn't play this video ({text}).\nPress V to open it in {name}.")

    def _video_status(self):
        if self.att is None or not is_video(self.att.extension) or self.stack.currentWidget() is not self.video:
            return
        def clock(ms):
            return f"{ms // 60000}:{ms // 1000 % 60:02d}"
        state = "⏸" if self.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState else "▶"
        self.vstatus.setText(f"{state} {clock(self.player.position())} / {clock(self.player.duration())}"
                             + ("  · muted" if self.audio.isMuted() else ""))

    def close_(self):
        changed = self.att.id if self.att is not None and self.index != self._start else 0
        self._stop_video()
        self.hide()
        self.att, self.items = None, []
        self.parentWidget().window().activateWindow()
        self.closed.emit(changed)

    # ---- actions
    def _open_original(self):
        if self.att:
            open_url(self.att.original_url)
            self.message.emit("Opened original in your default app")

    def _copy(self):
        if self.att:
            QApplication.clipboard().setText(self.att.original_url)
            self.message.emit(f"Copied {self.att.original_url}")

    def _toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _toggle_mute(self):
        self.audio.setMuted(not self.audio.isMuted())
        self._video_status()

    def _seek(self, ms):
        self.player.setPosition(max(0, min(self.player.duration() or 0, self.player.position() + ms)))

    def _external(self):
        if not (self.att and is_video(self.att.extension)):
            return
        self.player.pause()
        name = (self.cfg.video_command.split() or ["mpv"])[0]
        try:
            play_video(self.cfg.video_command, self.att.original_url)
            self.message.emit(f"Playing in {name}…")
        except OSError:
            self.message.emit(f"Couldn't start {name}. Is it installed?")

    def key(self, k, ch):
        video = self.att is not None and is_video(self.att.extension)
        if k == Qt.Key_Right: self.step(1)
        elif k == Qt.Key_Left: self.step(-1)
        elif video and k == Qt.Key_Space: self._toggle_play()
        elif video and ch.lower() == "m": self._toggle_mute()
        elif video and ch == "[": self._seek(-5000)
        elif video and ch == "]": self._seek(5000)
        elif video and ch.lower() == "v": self._external()
        elif not video and ch in ("+", "="): self.canvas.zoom(1.25)
        elif not video and ch in ("-", "_"): self.canvas.zoom(0.8)
        elif not video and ch == "0": self.canvas.fit()
        elif not video and ch == "1": self.canvas.actual()
        elif ch.lower() == "o": self._open_original()
        elif ch.lower() == "c": self._copy()
        return True
