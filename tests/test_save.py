from PySide6.QtCore import Qt

from helpers import make_window, press, pump
from lurkmoar.models import Attachment
from samples import THREAD


def open_viewer(qapp, tmp_path, att_index=0):
    win, api, repo, db = make_window(qapp)
    win.cfg.save_dir = str(tmp_path / "saved")
    win.open_board("4chan", "g")
    pump(qapp, lambda: win.catalog.model.rowCount() == 3)
    win.open_thread("4chan", "g", 100)
    assert pump(qapp, lambda: win.thread.loaded)
    att = win.thread.gallery()[att_index][1]
    win.open_media("4chan", "g", att)
    return win, repo, att


def loaded(qapp, win):
    return pump(qapp, lambda: win.viewer.canvas.img is not None)


def test_cached_media_path_is_none_until_downloaded(qapp, tmp_path):
    win, repo, att = open_viewer(qapp, tmp_path)
    assert loaded(qapp, win)
    p = repo.cached_media_path("4chan", "g", att)
    assert p is not None and p.exists() and p.suffix == ".jpg"
    other = Attachment(999, "z", ".png", 1, 1, 1, "", "https://i.4cdn.org/g/999.png", False)
    assert repo.cached_media_path("4chan", "g", other) is None


def test_s_saves_original_filename_and_reports_it(qapp, tmp_path):
    win, repo, att = open_viewer(qapp, tmp_path)
    assert loaded(qapp, win)
    got = []
    win.viewer.message.connect(got.append)
    press(win, "s")
    saved = tmp_path / "saved" / "gpu.jpg"
    assert saved.exists() and saved.read_bytes() == repo.cached_media_path("4chan", "g", att).read_bytes()
    assert got and "Saved to" in got[0] and str(saved) in got[0]


def test_saving_twice_never_overwrites(qapp, tmp_path):
    win, repo, att = open_viewer(qapp, tmp_path)
    assert loaded(qapp, win)
    press(win, "s")
    press(win, "s")
    assert sorted(p.name for p in (tmp_path / "saved").iterdir()) == ["gpu (1).jpg", "gpu.jpg"]


def test_s_before_download_finishes_says_so(qapp, tmp_path):
    win, repo, att = open_viewer(qapp, tmp_path)           # no pump: still loading
    win.viewer.att = att
    repo.cached_media_path = lambda s, b, a: None
    got = []
    win.viewer.message.connect(got.append)
    press(win, "s")
    assert got and "Still downloading" in got[0] and not (tmp_path / "saved").exists()


def test_hostile_filename_stays_inside_the_save_folder(qapp, tmp_path):
    win, repo, att = open_viewer(qapp, tmp_path)
    evil = Attachment(1700000000001, "../../evil", ".jpg", 5, 40, 30, att.thumbnail_url, att.original_url, False)
    win.viewer.items, win.viewer.index = [evil], 0
    win.viewer.att = evil
    assert loaded(qapp, win)
    press(win, "s")
    files = list((tmp_path / "saved").iterdir())
    assert [f.name for f in files] == ["evil.jpg"] and not (tmp_path / "evil.jpg").exists()


def test_unwritable_folder_gives_a_message_not_a_crash(qapp, tmp_path):
    win, repo, att = open_viewer(qapp, tmp_path)
    blocker = tmp_path / "blocker"
    blocker.write_text("a file, not a folder")
    win.cfg.save_dir = str(blocker / "sub")
    assert loaded(qapp, win)
    got = []
    win.viewer.message.connect(got.append)
    press(win, "s")
    assert got and "Couldn't save" in got[0]


def test_s_in_the_viewer_does_not_trigger_catalog_sort(qapp, tmp_path):
    win, repo, att = open_viewer(qapp, tmp_path)
    assert loaded(qapp, win)
    before = win.catalog.sort.currentIndex()
    press(win, "s")
    assert win.catalog.sort.currentIndex() == before
