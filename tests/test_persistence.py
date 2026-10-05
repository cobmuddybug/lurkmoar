import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView

from helpers import cleanup, make_window, press, pump
from lurkmoar.db import Bookmark, DB
from lurkmoar.ui_misc import bookmark_status
from samples import THREAD


def bm(**kw):
    base = dict(board="g", thread_id=1, subject="s", saved_at=0, last_known_reply_count=183,
                last_opened_post=0, latest_replies=183, expired=False)
    return Bookmark(**{**base, **kw})


def test_bookmark_status_lines():
    assert bookmark_status(bm(latest_replies=207), False) == "183 → 207 replies    +24 new"
    assert bookmark_status(bm(), False) == "183 replies    unchanged"
    assert bookmark_status(bm(expired=True), True) == "Thread expired    cached copy available"
    assert bookmark_status(bm(expired=True), False) == "Thread expired    no cached copy"


def test_f_bookmarks_selected_thread_and_marks_row(qapp):
    win, _, _, db = make_window(qapp)
    win.open_board("g")
    pump(qapp, lambda: win.catalog.model.rowCount() == 3)
    press(win, "f")
    assert db.bookmark_has("4chan", "g", 100) and 100 in win.catalog.delegate.bookmarked
    assert "Bookmarked" in win.status.msg.text()
    press(win, "f")
    assert not db.bookmark_has("4chan", "g", 100)


def test_bookmarks_screen_lists_and_opens(qapp):
    win, _, _, db = make_window(qapp)
    db.bookmark_add("4chan", "g", 100, "GPU Prices", 3)
    win.show_bookmarks()
    assert win.mode == "bookmarks"
    items = [win.bookmarks.list.item(i).text() for i in range(win.bookmarks.list.count())]
    assert any("/g/" in t and "GPU Prices" in t and "3 replies" in t for t in items)
    win.bookmarks.list.setCurrentRow(next(i for i, t in enumerate(items) if "GPU Prices" in t))
    got = []
    win.bookmarks.open_thread.disconnect()                   # keep the window's open_thread out of this test
    win.bookmarks.open_thread.connect(lambda b, n: got.append((b, n)))
    assert win.bookmarks.key_action("open") and got == [("g", 100)]
    press(win, Qt.Key_Escape)
    assert win.mode == "welcome"


def test_delete_removes_bookmark(qapp):
    win, _, _, db = make_window(qapp)
    db.bookmark_add("4chan", "g", 100, "x", 1)
    win.show_bookmarks()
    win.bookmarks.list.setCurrentRow(next(i for i in range(win.bookmarks.list.count())
                                          if win.bookmarks.list.item(i).data(Qt.UserRole)))
    press(win, Qt.Key_Delete)
    assert not db.bookmark_has("4chan", "g", 100)


def test_refresh_on_bookmarks_checks_each_board_once_and_updates_counts(qapp):
    win, api, repo, db = make_window(qapp)
    db.bookmark_add("4chan", "g", 100, "GPU", 10)
    db.bookmark_add("4chan", "g", 101, "other", 1)
    win.show_bookmarks()
    win.refresh()
    def shown():
        return " ".join(win.bookmarks.list.item(i).text() for i in range(win.bookmarks.list.count()))
    assert pump(qapp, lambda: "10 → 183 replies" in shown())     # the view reloads on the queued signal
    assert sum(u.endswith("/g/catalog.json") for u in api.calls) == 1


def test_journey_e_expired_bookmark_explains_and_offers_cache(qapp):
    win, api, repo, db = make_window(qapp)
    db.bookmark_add("4chan", "g", 999, "Upcoming RPG Thread", 10)
    db.cache_put("thread:g:999", json.dumps(THREAD), None, now=0)
    api.gone.add(999)
    win.show_bookmarks()
    win.bookmarks.list.setCurrentRow(next(i for i in range(win.bookmarks.list.count())
                                          if win.bookmarks.list.item(i).data(Qt.UserRole)))
    win.bookmarks.key_action("open")
    assert pump(qapp, lambda: win.thread_gone)
    assert win.thread.loaded and "no longer available" in win.banner.label.text()
    win.show_bookmarks()
    text = " ".join(win.bookmarks.list.item(i).text() for i in range(win.bookmarks.list.count()))
    assert "Thread expired    cached copy available" in text


def test_relaunch_restores_board_thread_and_position(qapp):
    win, api, repo, db = make_window(qapp)
    api.thread = {"posts": THREAD["posts"] + [{"no": 200 + i, "resto": 100, "name": "Anonymous", "time": 2000 + i,
                                               "com": "filler " * 40} for i in range(60)]}   # long enough to scroll
    win.open_board("g")
    pump(qapp, lambda: win.catalog.model.rowCount() == 3)
    win.catalog.select(101)
    win.open_thread("g", 100)
    pump(qapp, lambda: win.thread.loaded)
    win.thread.list.scrollTo(win.thread.model.index(2), QAbstractItemView.PositionAtTop)
    anchor = win.thread.anchor()
    assert anchor == 102
    cleanup()                                          # closes the window: state is saved
    win2, *_ = make_window(qapp, api=api, db=db)
    assert win2.board == "g" and win2.mode == "thread" and win2.thread.number == 100
    assert pump(qapp, lambda: win2.thread.loaded)
    assert win2.thread.anchor() == 102
    win2.leave_thread()
    assert win2.catalog.current_number() == 100 or win2.catalog.current_number() == 101


def test_recent_threads_listed(qapp):
    win, _, _, db = make_window(qapp)
    db.recent_add("4chan", "g", 100, "Seen it")
    win.show_bookmarks()
    text = " ".join(win.bookmarks.list.item(i).text() for i in range(win.bookmarks.list.count()))
    assert "Seen it" in text and "RECENTLY VISITED" in text


def test_restore_can_be_disabled(qapp):
    win, api, repo, db = make_window(qapp)
    db.kv_set("last_board", "g")
    cleanup()
    from lurkmoar.config import load_config, paths
    p = paths()
    p.config_file.write_text('{"start_on_last_board": false}')
    win2, *_ = make_window(qapp, api=api, db=db)
    assert win2.mode == "welcome"
