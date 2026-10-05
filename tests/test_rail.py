from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from helpers import make_window, press, pump


def setup_rail(qapp, favs=("v", "g")):
    win, api, repo, db = make_window(qapp)
    win.activateWindow()
    pump(qapp, lambda: "g" in win.boards)
    for f in favs:
        db.fav_toggle("4chan", f)
    win.open_board("4chan", "g")
    pump(qapp, lambda: win.catalog.model.rowCount() == 3)
    return win, api, repo, db


def focus(win):
    QApplication.processEvents()
    return win.focusWidget()


def test_left_in_catalog_focuses_the_rail(qapp):
    win, *_ = setup_rail(qapp)
    press(win, Qt.Key_Left)
    assert focus(win) is win.sidebar.list and win.sidebar.isVisible()
    assert win.sidebar.list.currentItem().data(Qt.UserRole) == ("4chan", "g")      # current board is highlighted


def test_arrows_and_enter_pick_a_board(qapp):
    win, *_ = setup_rail(qapp)
    press(win, Qt.Key_Left)
    press(win, Qt.Key_Up)                                                # favourites are v, g: v is above g
    assert win.sidebar.list.currentItem().data(Qt.UserRole) == ("4chan", "v")
    assert win.board == "g"                                              # moving alone does not switch
    press(win, Qt.Key_Return)
    assert win.board == "v" and win.mode == "catalog"
    assert focus(win) is win.catalog.list                                # focus returns to the content


def test_right_and_escape_return_to_the_page_without_leaving_it(qapp):
    win, *_ = setup_rail(qapp)
    win.open_thread("4chan", "g", 100)
    pump(qapp, lambda: win.thread.loaded)
    press(win, Qt.Key_Left)
    assert focus(win) is win.sidebar.list
    press(win, Qt.Key_Right)
    assert focus(win) is win.thread.list and win.mode == "thread"
    press(win, Qt.Key_Left)
    press(win, Qt.Key_Escape)
    assert focus(win) is win.thread.list and win.mode == "thread"      # Esc closes the rail focus first


def test_picking_a_board_from_a_thread_goes_to_that_catalog(qapp):
    win, *_ = setup_rail(qapp)
    win.open_thread("4chan", "g", 100)
    pump(qapp, lambda: win.thread.loaded)
    press(win, Qt.Key_Left)
    press(win, Qt.Key_Up)
    press(win, Qt.Key_Return)
    assert win.mode == "catalog" and win.board == "v"


def test_left_does_not_steal_keys_from_the_filter_box(qapp):
    win, *_ = setup_rail(qapp)
    win.catalog.key_action("filter")
    win.catalog.filter.setText("gpu")
    press(win, Qt.Key_Left)
    assert focus(win) is win.catalog.filter


def test_hidden_rail_is_shown_by_left(qapp):
    win, *_ = setup_rail(qapp)
    win._toggle_rail()
    assert not win.sidebar.isVisible()
    press(win, Qt.Key_Left)
    assert win.sidebar.isVisible() and focus(win) is win.sidebar.list


def test_down_past_the_boards_reaches_all_boards_button(qapp):
    win, *_ = setup_rail(qapp)
    press(win, Qt.Key_Left)                                              # "g" is the last row
    press(win, Qt.Key_Down)
    assert focus(win) is win.sidebar.all_btn
    press(win, Qt.Key_Down)
    assert focus(win) is win.sidebar.bm_btn
    press(win, Qt.Key_Up)
    press(win, Qt.Key_Return)
    assert win._picker is not None and win._picker.isVisible()
    win._picker.reject()


def test_up_from_the_buttons_returns_to_the_list(qapp):
    win, *_ = setup_rail(qapp)
    press(win, Qt.Key_Left)
    press(win, Qt.Key_Down)
    assert focus(win) is win.sidebar.all_btn
    press(win, Qt.Key_Up)
    assert focus(win) is win.sidebar.list
