import os
import shutil
import subprocess

import pytest
from PySide6.QtCore import Qt

from helpers import make_window, press, pump
from lurkmoar.models import Attachment, is_video
from samples import THREAD

WEBM_POST = {"no": 104, "resto": 100, "name": "Anonymous", "time": 1040, "com": "clip",
             "tim": 1700000000004, "ext": ".webm", "filename": "clip", "w": 640, "h": 360, "fsize": 2048}


@pytest.fixture(scope="session")
def webm(tmp_path_factory):
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed: cannot generate a test clip")
    out = tmp_path_factory.mktemp("clip") / "t.webm"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=blue:s=64x48:d=0.5:r=10",
                    "-c:v", "libvpx", "-an", str(out)], check=True)
    return out.read_bytes()


class ClipCdn:
    """Serves the generated clip for .webm URLs and a PNG for everything else."""
    def __init__(self, clip): self.clip = clip

    def get(self, url, last_modified=None):
        from lurkmoar.api import Response
        from helpers import png_bytes
        return Response(200, self.clip if url.endswith(".webm") else png_bytes(), None)


def open_thread_with(qapp, extra=(), clip=None):
    win, api, repo, db = make_window(qapp)
    if clip is not None:
        repo._cdn = ClipCdn(clip)
    api.thread = {"posts": THREAD["posts"] + list(extra)}
    win.open_board("g")
    pump(qapp, lambda: win.catalog.model.rowCount() == 3)
    win.open_thread("g", 100)
    assert pump(qapp, lambda: win.thread.loaded)
    return win, api, repo, db


def test_is_video():
    assert is_video(".webm") and is_video(".MP4") and not is_video(".jpg") and not is_video(".gif")


def test_thread_gallery_lists_live_attachments_in_order(qapp):
    win, *_ = open_thread_with(qapp, [WEBM_POST])
    g = win.thread.gallery()
    assert [(p, a.extension) for p, a in g] == [(100, ".jpg"), (103, ".png"), (104, ".webm")]


def test_arrows_cycle_and_wrap_with_counter(qapp):
    win, *_ = open_thread_with(qapp)
    v = win.viewer
    win.open_media("g", win.thread.model.post_at(0).attachment)
    assert v.isVisible() and "1 / 2" in v.info.text()
    press(win, Qt.Key_Right)
    assert "2 / 2" in v.info.text() and v.att.id == 1700000000003
    press(win, Qt.Key_Right)
    assert "1 / 2" in v.info.text()                      # wraps forward
    press(win, Qt.Key_Left)
    assert "2 / 2" in v.info.text()                      # wraps backward


def test_single_image_has_no_counter(qapp):
    win, *_ = open_thread_with(qapp)
    lone = Attachment(42, "lone", ".jpg", 10, 40, 30, "https://i.4cdn.org/g/42s.jpg", "https://i.4cdn.org/g/42.jpg", False)
    win.open_media("g", lone)                                          # not part of this thread's gallery
    assert " / " not in win.viewer.info.text()
    press(win, Qt.Key_Right)                                          # nothing to cycle, must not crash
    assert win.viewer.isVisible()


def test_late_response_for_previous_image_is_ignored(qapp):
    win, *_ = open_thread_with(qapp)
    v = win.viewer
    first = win.thread.model.post_at(0).attachment
    win.open_media("g", first)
    press(win, Qt.Key_Right)
    v.canvas.set_note("Loading image…")
    from helpers import png_bytes
    from PySide6.QtGui import QImage
    img = QImage.fromData(png_bytes())
    v.on_media(first.original_url, img, "")
    assert v.canvas.img is None


def test_closing_moves_thread_selection_to_last_shown_post(qapp):
    win, *_ = open_thread_with(qapp)
    win.thread.list.setCurrentIndex(win.thread.model.index(0))
    win.open_media("g", win.thread.model.post_at(0).attachment)
    press(win, Qt.Key_Right)
    press(win, Qt.Key_Escape)
    assert not win.viewer.isVisible()
    assert win.thread.current_post().number == 103


def test_arrow_keys_do_not_move_thread_while_viewer_open(qapp):
    win, *_ = open_thread_with(qapp)
    win.thread.list.setCurrentIndex(win.thread.model.index(0))
    win.open_media("g", win.thread.model.post_at(0).attachment)
    press(win, Qt.Key_Down)
    assert win.thread.current_post().number == 100


def test_video_opens_in_viewer_and_downloads_to_a_file(qapp, webm):
    win, _, repo, _ = open_thread_with(qapp, [WEBM_POST], webm)
    att = win.thread.model.post_at(win.thread.model.row_of(104)).attachment
    got = []
    repo.media_ready.connect(lambda url, data, err: got.append((url, data, err)))
    win.open_media("g", att)
    assert win.viewer.isVisible()
    assert pump(qapp, lambda: bool(got))
    url, path, err = got[0]
    assert url == att.original_url and isinstance(path, str) and err == "" and os.path.exists(path)
    assert win.viewer.stack.currentWidget() is win.viewer.video
    assert win.viewer.player.source().toLocalFile() == path
    assert "1 / 3" not in win.viewer.info.text() and "3 / 3" in win.viewer.info.text()


def test_video_controls_and_cleanup(qapp, monkeypatch, webm):
    win, _, repo, _ = open_thread_with(qapp, [WEBM_POST], webm)
    v = win.viewer
    att = win.thread.model.post_at(win.thread.model.row_of(104)).attachment
    win.open_media("g", att)
    pump(qapp, lambda: v.stack.currentWidget() is v.video)
    calls = []
    monkeypatch.setattr(v, "_toggle_play", lambda: calls.append("toggle"))
    press(win, Qt.Key_Space)
    assert calls == ["toggle"]
    assert v.audio.isMuted()                       # starts muted
    press(win, "m")
    assert not v.audio.isMuted()
    press(win, Qt.Key_Escape)
    assert not v.isVisible() and v.player.source().isEmpty()


def test_leaving_a_video_for_an_image_switches_back_to_the_canvas(qapp, webm):
    win, *_ = open_thread_with(qapp, [WEBM_POST], webm)
    v = win.viewer
    win.open_media("g", win.thread.model.post_at(win.thread.model.row_of(104)).attachment)
    pump(qapp, lambda: v.stack.currentWidget() is v.video)
    press(win, Qt.Key_Right)                        # wraps to the first image
    assert v.stack.currentWidget() is v.canvas and v.player.source().isEmpty()
    assert pump(qapp, lambda: v.canvas.img is not None)


def test_v_opens_external_player(qapp, monkeypatch):
    import lurkmoar.ui_media as um
    calls = []
    monkeypatch.setattr(um, "play_video", lambda cmd, url: calls.append((cmd, url)))
    win, *_ = open_thread_with(qapp, [WEBM_POST])
    att = win.thread.model.post_at(win.thread.model.row_of(104)).attachment
    win.open_media("g", att)
    press(win, "v")
    assert calls == [("mpv", att.original_url)]


def test_missing_external_player_gives_a_message(qapp, monkeypatch):
    import lurkmoar.ui_media as um

    def boom(cmd, url): raise FileNotFoundError(cmd)
    monkeypatch.setattr(um, "play_video", boom)
    win, *_ = open_thread_with(qapp, [WEBM_POST])
    win.open_media("g", win.thread.model.post_at(win.thread.model.row_of(104)).attachment)
    got = []
    win.viewer.message.connect(got.append)
    press(win, "v")
    assert got and "mpv" in got[0]


def test_player_error_is_explained_and_points_at_v(qapp):
    win, *_ = open_thread_with(qapp, [WEBM_POST])
    v = win.viewer
    win.open_media("g", win.thread.model.post_at(win.thread.model.row_of(104)).attachment)
    v.on_player_error("decoder missing")
    assert "Couldn't play this video" in v.canvas.note and v.stack.currentWidget() is v.canvas
