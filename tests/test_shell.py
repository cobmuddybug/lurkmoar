from PySide6.QtCore import Qt

from helpers import make_window, press, pump
from lurkmoar.models import Board
from lurkmoar.ui_misc import HINTS, KEYS, ago, filter_boards

B = [Board("g", "Technology", True, 10), Board("v", "Video Games", False, 10),
     Board("vg", "Video Game Generals", False, 10), Board("gd", "Graphic Design", True, 10)]


def test_ago():
    assert ago(0) == "just now" and ago(14) == "14s ago" and ago(125) == "2 min ago"
    assert ago(7300) == "2 h ago" and ago(200000) == "2 d ago" and ago(-5) == "just now"


def test_filter_boards_ranking():
    assert [b.code for b in filter_boards(B, "g")][:2] == ["g", "gd"]
    assert filter_boards(B, "/v/")[0].code == "v"
    assert {b.code for b in filter_boards(B, "gam")} == {"v", "vg"}
    assert filter_boards(B, "zzz") == []
    assert [b.code for b in filter_boards(B, "", favs={"vg"})][0] == "vg"


def test_every_mode_has_a_hint_and_keys_documented():
    assert {"welcome", "catalog", "thread", "bookmarks"} <= set(HINTS)
    assert any("B" in k for k, _ in KEYS)


def test_starts_on_welcome_and_b_opens_picker(qapp):
    win, *_ = make_window(qapp)
    assert win.mode == "welcome"
    press(win, "b")
    assert win._picker is not None and win._picker.isVisible()
    win._picker.reject()


def test_help_opens_on_question_mark(qapp):
    win, *_ = make_window(qapp)
    press(win, "?")
    assert win._help is not None and win._help.isVisible()
    win._help.reject()


def test_picker_loads_boards_and_filters(qapp):
    win, *_ = make_window(qapp)
    assert pump(qapp, lambda: "g" in win.boards)
    press(win, "b")
    p = win._picker

    def four():
        return [p.list.item(i).data(Qt.UserRole) for i in range(p.list.count())
                if p.list.item(i).data(Qt.UserRole) and p.list.item(i).data(Qt.UserRole)[0] == "4chan"]

    assert four() == [("4chan", "g"), ("4chan", "v"), ("4chan", "vg")]
    p.search.setText("vid")
    assert four() == [("4chan", "v"), ("4chan", "vg")]
    p.reject()


def test_favourite_from_picker_shows_in_sidebar(qapp):
    win, _, _, db = make_window(qapp)
    pump(qapp, lambda: "g" in win.boards)
    press(win, "b")
    win._picker.search.setText("g")
    win._picker.fav_btn.click()
    assert db.fav_boards() == [("4chan", "g")] and win.sidebar.list.count() == 2
    win._picker.reject()


def test_banner_wording_on_error(qapp):
    from lurkmoar.repo import Result
    win, *_ = make_window(qapp)
    win.note_result(Result(None, None, True, error="network: down"), "/g/ catalog", lambda: None)
    assert "Couldn't reach the server" in win.banner.label.text() and not win.banner.isHidden()
    win.note_result(Result([1], 1.0, False), "/g/ catalog", lambda: None)
    assert win.banner.isHidden()


def test_about_text_names_no_single_site():
    from lurkmoar.ui_misc import ABOUT
    assert ABOUT == ("LurkMoar is an independent read-only client.\n"
                     "Content is sourced from the sites you open and belongs to them. "
                     "Not affiliated with or endorsed by any of them.")


def test_help_dialog_has_no_4chan_link(qapp):
    from PySide6.QtWidgets import QLabel
    win, *_ = make_window(qapp)
    win.show_help()
    text = " ".join(l.text() for l in win._help.findChildren(QLabel))
    assert "4chan.org" not in text and "independent read-only client" in text
    win._help.reject()
