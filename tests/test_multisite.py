import time

from PySide6.QtCore import Qt

from helpers import make_window, press, pump


def open_site_thread(qapp, site="lainchan", board="sec", no=10):
    win, api, repo, db = make_window(qapp)
    win.open_board(site, board)
    assert pump(qapp, lambda: win.catalog.model.rowCount() >= 2)
    win.open_thread(site, board, no)
    assert pump(qapp, lambda: win.thread.loaded)
    return win, api, repo, db


def test_open_vichan_board_and_thread_end_to_end(qapp):
    win, *_ = open_site_thread(qapp)
    assert win.site == "lainchan" and win.board == "sec" and win.mode == "thread"
    assert win.thread.model.post_count() == 3 and win.thread.site == "lainchan"
    assert win.thread.model.replies_to == {10: [11]}
    assert "Lainchan /sec/" in win.header.where.text() and "No.10" in win.header.where.text()


def test_catalog_header_names_the_site_for_non_4chan_only(qapp):
    win, *_ = make_window(qapp)
    win.open_board("lainchan", "sec")
    assert win.header.where.text().startswith("Lainchan /sec/")
    win.open_board("4chan", "g")
    assert win.header.where.text().startswith("/g/")


def test_site_state_does_not_collide_between_sites_with_same_board_and_thread(qapp):
    win, api, repo, db = make_window(qapp)
    win.open_board("4chan", "b")
    pump(qapp, lambda: win.catalog.model.rowCount() == 3)
    win.open_board("kissu", "b")
    pump(qapp, lambda: win.catalog.model.rowCount() == 3 and win.site == "kissu")
    db.bookmark_add("4chan", "b", 10, "four", 1)
    assert not db.bookmark_has("kissu", "b", 10)
    assert db.cache_get("kissu:catalog:b") and db.cache_get("catalog:b")
    win.catalog.on_bookmarks_changed()
    assert ("kissu", "b", 10) not in win.catalog.delegate.bookmarked


def test_page_urls_use_each_sites_template(qapp):
    win, *_ = open_site_thread(qapp)
    win.thread.list.setCurrentIndex(win.thread.model.index(win.thread.model.row_of(11)))
    assert win.thread.current_ref()["url"] == "https://lainchan.org/sec/res/10.html#11"
    assert win.thread.current_ref()["site"] == "lainchan"
    win.leave_thread()
    assert win.catalog.current_ref()["url"].startswith("https://lainchan.org/sec/res/")
    win2, *_ = open_site_thread(qapp, "kissu", "b", 10)
    win2.thread.list.setCurrentIndex(win2.thread.model.index(win2.thread.model.row_of(11)))
    assert win2.thread.current_ref()["url"] == "https://kissu.moe/b/res/10#11"


def test_bookmark_on_a_vichan_thread_is_site_specific_and_survives_relaunch(qapp):
    from helpers import cleanup
    win, api, repo, db = open_site_thread(qapp)
    press(win, "f")
    assert db.bookmark_has("lainchan", "sec", 10) and not db.bookmark_has("4chan", "sec", 10)
    cleanup()
    win2, *_ = make_window(qapp, api=api, db=db)
    assert win2.site == "lainchan" and win2.board == "sec" and win2.mode == "thread" and win2.thread.number == 10


def test_old_last_view_format_still_restores_as_4chan(qapp):
    win, api, repo, db = make_window(qapp)
    db.kv_set("last_board", "g")
    db.kv_set("last_view", "thread:g:100")
    from helpers import cleanup
    cleanup()
    win2, *_ = make_window(qapp, api=api, db=db)
    assert win2.site == "4chan" and win2.mode == "thread" and win2.thread.number == 100


def test_failing_site_shows_banner_without_touching_the_other(qapp):
    win, api, *_ = make_window(qapp)
    api.fail_hosts.add("lainchan.org")
    win.open_board("lainchan", "sec")
    assert pump(qapp, lambda: not win.banner.isHidden())
    assert "Nothing is cached" in win.banner.label.text()
    win.open_board("4chan", "g")
    assert pump(qapp, lambda: win.catalog.model.rowCount() == 3 and win.banner.isHidden())


def test_invalid_typed_board_is_refused_before_any_request(qapp):
    win, api, *_ = make_window(qapp)
    n = len(api.calls)
    win.open_board("lainchan", "../x")
    assert win.mode == "welcome" and len(api.calls) == n and "isn't a valid board" in win.status.msg.text()


def test_cross_board_quote_on_the_same_site_asks_to_open_it(qapp):
    win, *_ = open_site_thread(qapp)
    got = []
    win.thread.cross_requested.disconnect()
    win.thread.cross_requested.connect(lambda b, t, p: got.append((b, t, p)))
    win.thread.follow_quote("/qa/res/9.html#4")
    assert got == [("qa", 9, 4)]


def test_bookmarks_screen_prefixes_non_4chan_sites_and_checks_each_board_once(qapp):
    win, api, repo, db = make_window(qapp)
    db.bookmark_add("lainchan", "sec", 10, "Lain thread", 1)
    db.bookmark_add("4chan", "g", 100, "Four thread", 1)
    win.show_bookmarks()
    text = " ".join(win.bookmarks.list.item(i).text() for i in range(win.bookmarks.list.count()))
    assert "Lainchan · /sec/  Lain thread" in text and "/g/  Four thread" in text and "4chan ·" not in text
    win.refresh()
    assert pump(qapp, lambda: any(u.endswith("lainchan.org/sec/catalog.json") for u in api.calls))
    assert pump(qapp, lambda: any(u.endswith("a.4cdn.org/g/catalog.json") for u in api.calls))
