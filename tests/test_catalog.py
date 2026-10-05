import time

from PySide6.QtCore import Qt

from helpers import make_window, press, pump
from lurkmoar.models import flatten_catalog
from lurkmoar.ui_catalog import CatalogModel, arrange
from samples import CATALOG


def test_arrange_sorts_and_filters():
    ts = flatten_catalog("g", CATALOG)
    nums = lambda sort, q="": [t.number for t in arrange(ts, sort, q)]
    assert nums("activity") == [100, 101, 102]          # API order is bump order
    assert nums("replies") == [102, 100, 101]
    assert nums("images") == [100, 102, 101]
    assert nums("created") == [101, 100, 102]
    assert nums("activity", "traveller") == [102]
    assert nums("activity", "GPU") == [100]
    assert nums("activity", "6090") == [100]             # OP text
    assert nums("activity", "101") == [101]              # thread number
    assert nums("activity", "   ") == [100, 101, 102]


def test_model_new_count_and_counts():
    ts = flatten_catalog("g", CATALOG)
    m = CatalogModel()
    assert m.set_threads(ts[:2]) is None
    assert m.set_threads(ts) == 1
    assert m.counts() == (3, 3)
    m.set_filter("traveller")
    assert m.counts() == (1, 3) and m.row_of(102) == 0 and m.row_of(100) == -1


def test_open_board_lists_threads_and_filters(qapp):
    win, *_ = make_window(qapp)
    win.open_board("g")
    assert win.mode == "catalog"
    assert pump(qapp, lambda: win.catalog.model.rowCount() == 3)
    assert win.catalog.count.text() == "3 threads"
    win.catalog.filter.setText("traveller")
    assert win.catalog.model.rowCount() == 1 and win.catalog.count.text() == "1 of 3 threads"
    press(win, Qt.Key_Escape)
    assert win.catalog.filter.text() == "" and win.catalog.model.rowCount() == 3
    win.catalog.sort.setCurrentIndex(1)
    assert win.catalog.model.thread_at(0).number == 102
    assert "updated" in win.status.msg.text() or "loaded" in win.status.msg.text()


def test_enter_opens_selected_thread(qapp):
    win, *_ = make_window(qapp)
    got = []
    win.catalog.open_thread.connect(lambda b, n: got.append((b, n)))
    win.open_board("g")
    pump(qapp, lambda: win.catalog.model.rowCount() == 3)
    assert win.catalog.key_action("open") is True
    assert got == [("g", 100)]


def test_selection_and_scroll_survive_refresh(qapp):
    win, api, repo, _ = make_window(qapp)
    win.open_board("g")
    pump(qapp, lambda: win.catalog.model.rowCount() == 3)
    win.catalog.select(101)
    repo.core.now = lambda: time.time() + 100
    win._refresh_catalog()
    pump(qapp, lambda: not win.refreshing)
    assert win.catalog.current_number() == 101


def test_offline_shows_cached_with_banner(qapp):
    win, api, repo, db = make_window(qapp)
    win.open_board("g")
    pump(qapp, lambda: win.catalog.model.rowCount() == 3 and not win.refreshing)
    win2, api2, repo2, _ = make_window(qapp, db=db)
    api2.fail = True
    repo2.core.now = lambda: time.time() + 100
    win2.open_board("g")
    assert pump(qapp, lambda: not win2.banner.isHidden())
    assert "Showing cached /g/ catalog" in win2.banner.label.text()
    assert win2.catalog.model.rowCount() == 3
    win2._tick()
    assert "cached" in win2.header.status.text()


def test_no_cache_and_offline_says_so(qapp):
    win, api, *_ = make_window(qapp)
    api.fail = True
    win.open_board("v")
    assert pump(qapp, lambda: not win.banner.isHidden())
    assert "Nothing is cached" in win.banner.label.text()
