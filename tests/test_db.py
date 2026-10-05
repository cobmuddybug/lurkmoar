from lurkmoar.db import DB


def test_cache_roundtrip_and_touch():
    d = DB(":memory:")
    assert d.cache_get("k") is None
    d.cache_put("k", "{}", "Mon", now=10)
    r = d.cache_get("k")
    assert (r.body, r.fetched_at, r.last_modified) == ("{}", 10, "Mon")
    d.cache_touch("k", 20)
    assert d.cache_get("k").fetched_at == 20 and d.cache_get("k").last_modified == "Mon"


def test_prune_keeps_newest_and_bookmarked():
    d = DB(":memory:")
    for i in range(5):
        d.cache_put(f"thread:g:{i}", "{}", None, now=i)
    d.cache_put("catalog:g", "[]", None, now=0)
    d.bookmark_add("g", 0, "old", 1)
    d.prune_threads(keep=2)
    keys = {k for k in ("thread:g:%d" % i for i in range(5)) if d.cache_get(k)}
    assert keys == {"thread:g:4", "thread:g:3", "thread:g:0"}
    assert d.cache_get("catalog:g")


def test_bookmark_lifecycle():
    d = DB(":memory:")
    d.bookmark_add("g", 1, "GPU", 183)
    d.bookmark_add("g", 1, "GPU", 183)
    assert d.bookmark_has("g", 1) and len(d.bookmarks()) == 1
    d.bookmark_latest("g", 1, 207)
    b = d.bookmarks()[0]
    assert (b.last_known_reply_count, b.latest_replies, b.expired) == (183, 207, 0)
    d.bookmark_seen("g", 1, 207, 555)
    b = d.bookmarks()[0]
    assert (b.last_known_reply_count, b.last_opened_post) == (207, 555)
    d.bookmark_remove("g", 1)
    assert not d.bookmark_has("g", 1)


def test_observe_marks_missing_expired_and_present_alive():
    d = DB(":memory:")
    d.bookmark_add("g", 1, "a", 5)
    d.bookmark_add("g", 2, "b", 5)
    d.bookmark_add("v", 3, "c", 5)
    d.bookmarks_observe("g", {1: 9})
    by = {b.thread_id: b for b in d.bookmarks()}
    assert by[1].latest_replies == 9 and not by[1].expired
    assert by[2].expired and not by[3].expired
    d.bookmark_expire("v", 3)
    assert {b.thread_id: b.expired for b in d.bookmarks()}[3]


def test_favourites_keep_order():
    d = DB(":memory:")
    assert d.fav_toggle("v") and d.fav_toggle("g")
    assert d.fav_boards() == ["v", "g"]
    assert not d.fav_toggle("v") and d.fav_boards() == ["g"]


def test_nav_defaults_and_partial_update():
    d = DB(":memory:")
    n = d.nav_get("g")
    assert (n.catalog_anchor, n.thread_no, n.thread_anchor) == (0, 0, 0)
    d.nav_set("g", catalog_anchor=7)
    d.nav_set("g", thread_no=9, thread_anchor=11)
    n = d.nav_get("g")
    assert (n.catalog_anchor, n.thread_no, n.thread_anchor) == (7, 9, 11)


def test_nav_rejects_unknown_field():
    import pytest
    with pytest.raises(ValueError):
        DB(":memory:").nav_set("g", bogus=1)


def test_recent_dedupes_orders_and_caps():
    d = DB(":memory:")
    for i in range(40):
        d.recent_add("g", i, f"t{i}", now=i)
    d.recent_add("g", 5, "t5", now=100)
    r = d.recent(limit=50)
    assert r[0] == ("g", 5, "t5") and len(r) == 30 and len({x[1] for x in r}) == 30


def test_kv_and_persistence(tmp_path):
    f = tmp_path / "x.db"
    d = DB(f)
    d.kv_set("last_board", "g")
    d.bookmark_add("g", 1, "keep me", 3)
    d2 = DB(f)
    assert d2.kv_get("last_board") == "g" and d2.kv_get("zzz", "dflt") == "dflt"
    assert d2.bookmarks()[0].subject == "keep me"
