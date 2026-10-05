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


from lurkmoar.models import Board
from lurkmoar.sites import load_sites
from lurkmoar.ui_misc import filter_site_boards, parse_typed

SITES = load_sites()
BY_SITE = {"4chan": [Board("g", "Technology", True, 10), Board("v", "Video Games", False, 10)],
           **{sid: list(s.boards) for sid, s in SITES.items() if sid != "4chan"}}


def rail_rows(win):
    out = []
    for i in range(win.sidebar.list.count()):
        it = win.sidebar.list.item(i)
        out.append(("H", it.text()) if it.data(Qt.UserRole) is None else ("B", it.data(Qt.UserRole)))
    return out


def test_rail_groups_favourites_under_site_headers_in_registry_order(qapp):
    win, _, _, db = make_window(qapp)
    for s, b in (("lainchan", "sec"), ("4chan", "g"), ("kissu", "b"), ("lainchan", "lit")):
        db.fav_toggle(s, b)
    win.sidebar.set_boards(db.fav_boards(), None, win.repo.sites)
    assert rail_rows(win) == [("H", "── 4chan"), ("B", ("4chan", "g")), ("H", "── Kissu"), ("B", ("kissu", "b")),
                              ("H", "── Lainchan"), ("B", ("lainchan", "sec")), ("B", ("lainchan", "lit"))]
    header = win.sidebar.list.item(0)
    assert not (header.flags() & Qt.ItemIsSelectable)


def test_rail_shows_current_non_favourite_under_its_site_and_no_empty_headers(qapp):
    win, _, _, db = make_window(qapp)
    db.fav_toggle("4chan", "g")
    win.sidebar.set_boards(db.fav_boards(), ("wizchan", "wiz"), win.repo.sites)
    assert rail_rows(win) == [("H", "── 4chan"), ("B", ("4chan", "g")), ("H", "── Wizchan"), ("B", ("wizchan", "wiz"))]
    assert win.sidebar.list.currentItem().data(Qt.UserRole) == ("wizchan", "wiz")
    win.sidebar.set_boards([], None, win.repo.sites)
    assert rail_rows(win) == []


def test_rail_arrows_skip_headers_and_enter_opens_the_board(qapp):
    win, api, repo, db = make_window(qapp)
    pump(qapp, lambda: "g" in win.boards)
    for s, b in (("4chan", "g"), ("lainchan", "sec")):
        db.fav_toggle(s, b)
    win.open_board("lainchan", "sec")
    pump(qapp, lambda: win.catalog.model.rowCount() >= 2)
    press(win, Qt.Key_Left)
    assert win.sidebar.list.currentItem().data(Qt.UserRole) == ("lainchan", "sec")
    press(win, Qt.Key_Up)                                  # skips the "Lainchan" header
    assert win.sidebar.list.currentItem().data(Qt.UserRole) == ("4chan", "g")
    press(win, Qt.Key_Up)                                  # nothing above: stays put
    assert win.sidebar.list.currentItem().data(Qt.UserRole) == ("4chan", "g")
    press(win, Qt.Key_Return)
    assert (win.site, win.board) == ("4chan", "g")


def test_filter_site_boards_matches_codes_titles_and_sites():
    fav = {("lainchan", "sec")}
    sec = filter_site_boards(BY_SITE, SITES, "sec", fav)
    assert ("lainchan", "sec") in [(sid, b.code) for sid, bs in sec for b in bs]
    lain = dict(filter_site_boards(BY_SITE, SITES, "lain", fav))
    assert {b.code for b in lain["lainchan"]} == {b.code for b in SITES["lainchan"].boards}
    one = filter_site_boards(BY_SITE, SITES, "lain sec", fav)
    assert [(sid, [b.code for b in bs]) for sid, bs in one] == [("lainchan", ["sec"])]
    assert [sid for sid, _ in filter_site_boards(BY_SITE, SITES, "", fav)][0] == "4chan"
    assert filter_site_boards(BY_SITE, SITES, "zzzzzz", fav) == []
    tech = [(sid, b.code) for sid, bs in filter_site_boards(BY_SITE, SITES, "technology", ()) for b in bs]
    assert tech == [("4chan", "g")]


def test_parse_typed_codes():
    assert parse_typed("qa", SITES, "kissu") == ("kissu", "qa")
    assert parse_typed("/qa/", SITES, "kissu") == ("kissu", "qa")
    assert parse_typed("kissu qa", SITES, "lainchan") == ("kissu", "qa")
    assert parse_typed("lain zzz", SITES, "4chan") == ("lainchan", "zzz")
    assert parse_typed("../x", SITES, "kissu") is None and parse_typed("a b c", SITES, "kissu") is None
    assert parse_typed("nosuch qa", SITES, "kissu") is None and parse_typed("", SITES, "kissu") is None
    assert parse_typed("A", SITES, "kissu") == ("kissu", "a")        # typing is case-insensitive, like the filter
    assert parse_typed("a/b", SITES, "kissu") is None


def test_picker_groups_by_site_and_enter_opens(qapp):
    win, *_ = make_window(qapp)
    pump(qapp, lambda: "g" in win.boards)
    press(win, "b")
    p = win._picker

    def rows():
        return [(p.list.item(i).data(Qt.UserRole) or p.list.item(i).text()) for i in range(p.list.count())]

    assert rows()[0] == "── 4chan" and ("lainchan", "sec") in rows() and "── Lainchan" in rows()
    p.search.setText("lain sec")
    assert rows() == ["── Lainchan", ("lainchan", "sec")]
    assert p.list.currentItem().data(Qt.UserRole) == ("lainchan", "sec")
    p._accept_current()
    assert (win.site, win.board) == ("lainchan", "sec")


def test_picker_typed_code_opens_an_unlisted_board_on_the_current_site(qapp):
    win, *_ = make_window(qapp)
    win.open_board("kissu", "b")
    pump(qapp, lambda: win.catalog.model.rowCount() >= 2)
    win.open_picker()
    p = win._picker
    p.search.setText("qa")
    assert p.list.currentItem() is None
    p._accept_current()
    assert (win.site, win.board) == ("kissu", "qa")


def test_picker_rejects_invalid_typed_code(qapp):
    win, api, *_ = make_window(qapp)
    n = len(api.calls)
    win.open_picker()
    win._picker.search.setText("../x")
    win._picker._accept_current()
    assert win.mode == "welcome" and win._picker.isVisible() and "valid board" in win._picker.msg.text()


def test_favourite_in_picker_lands_in_the_right_rail_group(qapp):
    win, _, _, db = make_window(qapp)
    win.open_picker()
    p = win._picker
    p.search.setText("lain sec")
    p.fav_btn.click()
    assert db.fav_boards() == [("lainchan", "sec")]
    assert rail_rows(win) == [("H", "── Lainchan"), ("B", ("lainchan", "sec"))]
    p.reject()
