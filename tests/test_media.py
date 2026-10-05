from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage

from helpers import make_window, press, pump
from lurkmoar.ui_media import Canvas
from samples import THREAD


def test_canvas_fit_zoom_actual(qapp):
    c = Canvas()
    c.resize(200, 100)
    img = QImage(400, 200, QImage.Format_RGB32)
    img.fill(QColor("red"))
    c.set_image(img)
    assert abs(c.scale - 0.5) < 1e-6                 # fit
    c.zoom(2.0)
    assert abs(c.scale - 1.0) < 1e-6
    c.zoom(0.5)
    c.actual()
    assert c.scale == 1.0
    c.fit()
    assert abs(c.scale - 0.5) < 1e-6


def open_thread_in(qapp):
    win, api, repo, db = make_window(qapp)
    win.open_board("4chan", "g")
    pump(qapp, lambda: win.catalog.model.rowCount() == 3)
    win.open_thread("4chan", "g", 100)
    assert pump(qapp, lambda: win.thread.loaded)
    return win, api, repo, db


def test_image_opens_in_overlay_and_thread_position_is_kept(qapp):
    win, *_ = open_thread_in(qapp)
    tv = win.thread
    tv.list.setCurrentIndex(tv.model.index(2))
    anchor, cur = tv.anchor(), tv.current_post().number
    att = tv.model.post_at(0).attachment
    win.open_media("4chan", "g", att)
    assert win.viewer.isVisible()
    assert pump(qapp, lambda: win.viewer.canvas.img is not None)
    assert "40×30" in win.viewer.info.text() or "800×600" in win.viewer.info.text()
    s0 = win.viewer.canvas.scale
    press(win, "+")
    assert win.viewer.canvas.scale > s0
    press(win, "1")
    assert win.viewer.canvas.scale == 1.0
    press(win, "0")
    press(win, Qt.Key_Escape)
    assert not win.viewer.isVisible()
    assert win.mode == "thread" and tv.anchor() == anchor and tv.current_post().number == cur


def test_keys_do_not_leak_to_thread_while_overlay_open(qapp):
    win, *_ = open_thread_in(qapp)
    att = win.thread.model.post_at(0).attachment
    win.thread.list.setCurrentIndex(win.thread.model.index(0))
    win.open_media("4chan", "g", att)
    press(win, "b")
    assert win._picker is None or not win._picker.isVisible()
    press(win, Qt.Key_Escape)


def test_media_error_is_shown_not_raised(qapp):
    win, api, repo, _ = open_thread_in(qapp)
    att = win.thread.model.post_at(0).attachment
    win.open_media("4chan", "g", att)
    win.viewer.on_media(att.original_url, None, "http 503")
    assert "Couldn't load" in win.viewer.canvas.note
    press(win, Qt.Key_Escape)


def test_video_opens_in_the_overlay_not_straight_in_mpv(qapp, monkeypatch):
    import lurkmoar.ui_media as um
    calls = []
    monkeypatch.setattr(um, "play_video", lambda cmd, url: calls.append((cmd, url)))
    win, *_ = open_thread_in(qapp)
    th = win.catalog.model.thread_at(2)                         # .webm thread
    win.open_media("4chan", "g", th.thumbnail)
    assert win.viewer.isVisible() and calls == []
