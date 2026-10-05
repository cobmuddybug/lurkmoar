import time

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QAbstractItemView

from helpers import make_window, press, pump
from lurkmoar.models import Post, Thread
from lurkmoar.parse import parse_comment
from lurkmoar.theme import DEFAULT
from lurkmoar.ui_thread import Divider, ThreadModel, spans_html
from samples import THREAD


def posts(n, start=1):
    return [Post.from_api("g", {"no": i, "resto": 1, "time": i, "com": f"post {i}"})
            for i in range(start, start + n)]


def test_model_load_and_merge_adds_single_divider():
    m = ThreadModel()
    m.load(posts(3))
    assert m.rowCount() == 3 and m.post_count() == 3
    assert m.merge(posts(3)) == 0 and m.rowCount() == 3          # nothing new: no divider
    assert m.merge(posts(5)) == 2
    kinds = [type(m.data(m.index(r), 256)).__name__ for r in range(m.rowCount())]
    assert kinds == ["Post"] * 3 + ["Divider", "Post", "Post"]
    assert m.merge(posts(7)) == 2                                 # old divider replaced, not stacked
    items = [m.data(m.index(r), 256) for r in range(m.rowCount())]
    assert sum(isinstance(i, Divider) for i in items) == 1
    assert isinstance(items[5], Divider) and items[5].count == 2


def test_model_row_of_and_replies_to():
    th = Thread.from_api("g", 100, THREAD)
    m = ThreadModel()
    m.load(th.posts)
    assert m.row_of(102) == 2 and m.row_of(999) == -1
    assert m.replies_to == {100: [101], 101: [103]}
    m.merge(th.posts + [Post.from_api("g", {"no": 104, "resto": 100, "time": 5,
                                           "com": '<a href="#p101" class="quotelink">&gt;&gt;101</a>'})])
    assert m.replies_to[101] == [103, 104]


def test_spans_html_escapes_and_hides_spoilers():
    spans = parse_comment("<b>1 &lt; 2</b><br><s>secret</s> <a href=\"#p5\" class=\"quotelink\">&gt;&gt;5</a>")
    h = spans_html(spans, DEFAULT, set())
    assert "1 &lt; 2" in h and "<script" not in h
    assert 'href="s:' in h and 'href="q:#p5"' in h
    shown = spans_html(spans, DEFAULT, {2})
    assert 'href="s:' not in shown


def test_spans_html_external_link_and_hostile_text():
    h = spans_html(parse_comment('<a href="https://e.com/?a=1&amp;b=2">x</a> <img src=x onerror=y>'),
                   DEFAULT, set())
    assert 'href="l:https://e.com/?a=1&amp;b=2"' in h and "<img" not in h


def open_thread_in(qapp, n_extra=0):
    win, api, repo, db = make_window(qapp)
    win.open_board("g")
    pump(qapp, lambda: win.catalog.model.rowCount() == 3)
    win.open_thread("g", 100)
    assert pump(qapp, lambda: win.thread.loaded)
    return win, api, repo, db


def test_open_thread_shows_header_and_posts(qapp):
    win, *_ = open_thread_in(qapp)
    assert win.mode == "thread" and win.thread.model.post_count() == 4
    assert "3 replies" in win.thread.stats.text() and "2 images" in win.thread.stats.text()
    assert "No.100" in win.header.where.text()


def test_quote_jump_and_back_restore_position(qapp):
    win, *_ = open_thread_in(qapp)
    tv = win.thread
    tv.list.setCurrentIndex(tv.model.index(tv.model.row_of(103)))
    before = tv.list.verticalScrollBar().value()
    tv.follow_quote("#p101")
    assert tv.current_post().number == 101 and len(tv.jumps) == 1
    tv.follow_quote("#p100")
    assert len(tv.jumps) == 2
    press(win, Qt.Key_Escape)
    assert tv.current_post().number == 101 and len(tv.jumps) == 1
    press(win, Qt.Key_Escape)
    assert tv.current_post().number == 103 and not tv.jumps
    assert tv.list.verticalScrollBar().value() == before
    press(win, Qt.Key_Escape)                                # empty stack: leaves the thread
    assert win.mode == "catalog"


def test_quote_to_missing_post_is_a_message_not_a_crash(qapp):
    win, *_ = open_thread_in(qapp)
    got = []
    win.thread.message.connect(got.append)
    win.thread.follow_quote("#p99999")
    assert got and "isn't in this thread" in got[0] and not win.thread.jumps


def test_cross_thread_quote_emits_request(qapp):
    win, *_ = open_thread_in(qapp)
    got = []
    win.thread.cross_requested.disconnect()                  # keep the window's modal dialog out of the test
    win.thread.cross_requested.connect(lambda b, t, p: got.append((b, t, p)))
    win.thread.follow_quote("/v/thread/55#p56")
    assert got == [("v", 55, 56)]


def test_refresh_appends_new_posts_without_moving_reader(qapp):
    win, api, repo, _ = open_thread_in(qapp)
    tv = win.thread
    filler = [{"no": 300 + i, "resto": 100, "name": "Anonymous", "time": 1500 + i,
               "com": "filler " * 30} for i in range(40)]
    base = {"posts": THREAD["posts"] + filler}                # long: mid-thread is never "at the bottom"
    api.thread = base
    tv.load(Thread.from_api("g", 100, base))
    tv.list.setCurrentIndex(tv.model.index(1))
    tv.list.scrollTo(tv.model.index(1), QAbstractItemView.PositionAtTop)
    top_before = tv.anchor()
    assert top_before == 101 and not tv.following
    extra = [{"no": 200 + i, "resto": 100, "name": "Anonymous", "time": 2000 + i,
              "com": f"new {i}"} for i in range(7)]
    api.thread = {"posts": base["posts"] + extra}
    repo.core.now = lambda: time.time() + 100
    win._refresh_thread()
    assert pump(qapp, lambda: tv.model.post_count() == 51)
    assert tv.anchor() == top_before
    items = [tv.model.data(tv.model.index(r), 256) for r in range(tv.model.rowCount())]
    assert sum(isinstance(i, Divider) for i in items) == 1
    assert "7 new" in win.status.msg.text()


def test_following_indicator_states(qapp):
    win, *_ = open_thread_in(qapp)
    win.cfg.auto_refresh = True
    win.thread.load(Thread("g", 100, posts(60)))          # enough posts to overflow the viewport
    win.thread.list.verticalScrollBar().setValue(0)
    win.thread._on_scroll(0)
    assert not win.thread.following and "Follow paused" in win.thread.follow_lbl.text()
    win.thread.list.scrollToBottom()
    win.thread._on_scroll(win.thread.list.verticalScrollBar().maximum())
    assert win.thread.following and "Following new posts" in win.thread.follow_lbl.text()


def test_spoiler_cover_then_reveal(qapp):
    win, *_ = open_thread_in(qapp)
    tv = win.thread
    p103 = tv.model.post_at(tv.model.row_of(103))
    assert p103.attachment.id not in tv.delegate.revealed_files
    tv.list.setCurrentIndex(tv.model.index(tv.model.row_of(103)))
    assert tv.key_action("reveal") is True
    assert p103.attachment.id in tv.delegate.revealed_files


def test_deleted_thread_with_cache_keeps_cached_copy_and_explains(qapp):
    win, api, repo, db = open_thread_in(qapp)
    win.leave_thread()
    api.gone.add(100)
    repo.core.now = lambda: time.time() + 100
    win.open_thread("g", 100)
    assert win.thread.loaded and win.thread.model.post_count() == 4   # cached copy shown at once
    assert pump(qapp, lambda: not win.banner.isHidden())
    assert "no longer available" in win.banner.label.text()
    assert "cached copy" in win.banner.label.text()
    assert [b.text() for b in win.banner._btns] == ["Back to /g/"]
    assert win.thread_gone


def test_deleted_thread_without_cache(qapp):
    win, api, *_ = make_window(qapp)
    api.gone.add(100)
    win.open_board("g")
    pump(qapp, lambda: win.catalog.model.rowCount() == 3)
    win.open_thread("g", 100)
    assert pump(qapp, lambda: not win.banner.isHidden())
    assert "No cached copy" in win.banner.label.text()


def test_large_thread_lays_out_fast(qapp):
    win, *_ = open_thread_in(qapp)
    tv = win.thread
    big = Thread("g", 100, [Post.from_api("g", {"no": 1000 + i, "resto": 100, "time": i,
                  "com": "lorem ipsum dolor sit amet " * 12 + (f'<a href="#p{1000 + i - 1}" class="quotelink">&gt;&gt;x</a>' if i else "")})
                  for i in range(1500)])
    t = time.time()
    tv.begin("g", 100, "big", False)
    tv.load(big)
    tv.list.doItemsLayout()
    assert time.time() - t < 3.0
