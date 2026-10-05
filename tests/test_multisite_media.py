import copy
from pathlib import Path

from PySide6.QtCore import Qt

from helpers import make_window, press, pump
from samples_vichan import VICHAN_THREAD


def image_only_thread():
    d = copy.deepcopy(VICHAN_THREAD)
    d["posts"][2]["extra_files"] = [d["posts"][2]["extra_files"][0]]      # drop the .webm: images only
    return d


def open_in(qapp, tmp_path, site="lainchan", board="sec"):
    win, api, repo, db = make_window(qapp)
    api.vichan_thread = image_only_thread()
    win.cfg.save_dir = str(tmp_path / "saved")
    win.open_board(site, board)
    assert pump(qapp, lambda: win.catalog.model.rowCount() >= 2)
    win.open_thread(site, board, 10)
    assert pump(qapp, lambda: win.thread.loaded)
    return win, repo


def test_gallery_includes_every_attachment_in_thread_order(qapp, tmp_path):
    win, _ = open_in(qapp, tmp_path)
    assert [(p, a.extension) for p, a in win.thread.gallery()] == [(10, ".jpg"), (12, ".png"), (12, ".gif")]


def test_caption_mentions_extra_files(qapp, tmp_path):
    win, _ = open_in(qapp, tmp_path)
    op, p11, p12 = win.thread.model.post_at(0), win.thread.model.post_at(1), win.thread.model.post_at(2)
    assert "more file" not in win.thread.delegate.caption(op)
    assert win.thread.delegate.caption(p12).endswith("+1 more files") or win.thread.delegate.caption(p12).endswith("+1 more file")
    assert win.thread.delegate.caption(p11) == ""


def test_arrows_cycle_through_a_posts_extra_files_and_wrap(qapp, tmp_path):
    win, _ = open_in(qapp, tmp_path)
    win.open_media("lainchan", "sec", win.thread.gallery()[0][1])
    assert win.viewer.site == "lainchan" and "1 / 3" in win.viewer.info.text()
    press(win, Qt.Key_Right)
    press(win, Qt.Key_Right)
    assert "3 / 3" in win.viewer.info.text() and win.viewer.att.extension == ".gif"
    press(win, Qt.Key_Right)
    assert "1 / 3" in win.viewer.info.text()


def test_closing_selects_the_post_that_owns_the_last_shown_extra_file(qapp, tmp_path):
    win, _ = open_in(qapp, tmp_path)
    win.thread.list.setCurrentIndex(win.thread.model.index(0))
    win.open_media("lainchan", "sec", win.thread.gallery()[0][1])
    press(win, Qt.Key_Right)
    press(win, Qt.Key_Right)
    press(win, Qt.Key_Escape)
    assert win.thread.current_post().number == 12


def test_save_goes_to_a_site_subfolder_for_non_4chan(qapp, tmp_path):
    win, _ = open_in(qapp, tmp_path)
    win.open_media("lainchan", "sec", win.thread.gallery()[0][1])
    assert pump(qapp, lambda: win.viewer.canvas.img is not None)
    press(win, "s")
    assert (tmp_path / "saved" / "lainchan" / "pic.jpg").exists()


def test_4chan_save_stays_flat(qapp, tmp_path):
    win, api, repo, db = make_window(qapp)
    win.cfg.save_dir = str(tmp_path / "saved")
    win.open_board("4chan", "g")
    pump(qapp, lambda: win.catalog.model.rowCount() == 3)
    win.open_thread("4chan", "g", 100)
    pump(qapp, lambda: win.thread.loaded)
    win.open_media("4chan", "g", win.thread.gallery()[0][1])
    assert pump(qapp, lambda: win.viewer.canvas.img is not None)
    press(win, "s")
    assert (tmp_path / "saved" / "gpu.jpg").exists()


def test_same_attachment_id_on_two_sites_uses_two_cache_files(qapp, tmp_path):
    win, repo = open_in(qapp, tmp_path, "lainchan", "sec")
    att = win.thread.gallery()[0][1]
    win.open_media("lainchan", "sec", att)
    assert pump(qapp, lambda: win.viewer.canvas.img is not None)
    press(win, Qt.Key_Escape)
    win.leave_thread()
    win.open_board("kissu", "b")
    pump(qapp, lambda: win.catalog.model.rowCount() >= 2)
    win.open_thread("kissu", "b", 10)
    pump(qapp, lambda: win.thread.loaded)
    att2 = win.thread.gallery()[0][1]
    assert att.id == att2.id
    win.open_media("kissu", "b", att2)
    assert pump(qapp, lambda: win.viewer.canvas.img is not None)
    names = sorted(p.name for p in repo.paths.media.iterdir())
    assert len(names) == 2 and names[0].startswith("kissu_b_") and names[1].startswith("lainchan_sec_")
