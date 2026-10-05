from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from helpers import make_window, press, pump
from test_rail import focus, setup_rail


def in_thread(qapp):
    win, *rest = setup_rail(qapp)
    win.open_thread("4chan", "g", 100)
    assert pump(qapp, lambda: win.thread.loaded)
    return win


def test_backspace_leaves_a_thread_like_escape(qapp):
    win = in_thread(qapp)
    press(win, Qt.Key_Backspace)
    assert win.mode == "catalog"


def test_backspace_undoes_quote_jumps_first(qapp):
    win = in_thread(qapp)
    tv = win.thread
    tv.list.setCurrentIndex(tv.model.index(tv.model.row_of(103)))
    tv.follow_quote("#p101")
    press(win, Qt.Key_Backspace)
    assert win.mode == "thread" and not tv.jumps and tv.current_post().number == 103
    press(win, Qt.Key_Backspace)
    assert win.mode == "catalog"


def test_backspace_closes_the_viewer(qapp):
    win = in_thread(qapp)
    win.open_media("4chan", "g", win.thread.gallery()[0][1])
    assert win.viewer.isVisible()
    press(win, Qt.Key_Backspace)
    assert not win.viewer.isVisible() and win.mode == "thread"


def test_backspace_from_the_rail_returns_to_the_page(qapp):
    win = in_thread(qapp)
    press(win, Qt.Key_Left)
    assert focus(win) is win.sidebar.list
    press(win, Qt.Key_Backspace)
    assert focus(win) is win.thread.list and win.mode == "thread"


def test_backspace_leaves_bookmarks(qapp):
    win, *_ = setup_rail(qapp)
    win.show_bookmarks()
    press(win, Qt.Key_Backspace)
    assert win.mode == "catalog"


def test_backspace_still_edits_text_in_the_filter_box(qapp):
    win, *_ = setup_rail(qapp)
    win.catalog.key_action("filter")
    win.catalog.filter.setText("gpu")
    QTest.keyClick(win.catalog.filter, Qt.Key_Backspace)      # delivered to the box, as in a live session
    assert win.catalog.filter.text() == "gp" and win.mode == "catalog"
    press(win, Qt.Key_Backspace)                              # through the app filter: must not be swallowed
    assert win.catalog.filter.text() == "gp"


def test_ctrl_backspace_is_left_alone(qapp):
    win = in_thread(qapp)
    QTest.keyClick(win, Qt.Key_Backspace, Qt.ControlModifier)
    assert win.mode == "thread"


def test_backspace_closes_help(qapp):
    win, *_ = make_window(qapp)
    win.show_help()
    QTest.keyClick(win._help, Qt.Key_Backspace)
    assert not win._help.isVisible()


def test_picker_backspace_deletes_text_then_closes_when_empty(qapp):
    win, *_ = make_window(qapp)
    pump(qapp, lambda: "g" in win.boards)
    win.open_picker()
    p = win._picker
    p.search.setText("v")
    QTest.keyClick(p.search, Qt.Key_Backspace)
    assert p.search.text() == "" and p.isVisible()
    QTest.keyClick(p.search, Qt.Key_Backspace)
    assert not p.isVisible()
