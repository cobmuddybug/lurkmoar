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
    d.bookmark_add("4chan", "g", 0, "old", 1)
    d.prune_threads(keep=2)
    keys = {k for k in ("thread:g:%d" % i for i in range(5)) if d.cache_get(k)}
    assert keys == {"thread:g:4", "thread:g:3", "thread:g:0"}
    assert d.cache_get("catalog:g")


def test_bookmark_lifecycle():
    d = DB(":memory:")
    d.bookmark_add("4chan", "g", 1, "GPU", 183)
    d.bookmark_add("4chan", "g", 1, "GPU", 183)
    assert d.bookmark_has("4chan", "g", 1) and len(d.bookmarks()) == 1
    d.bookmark_latest("4chan", "g", 1, 207)
    b = d.bookmarks()[0]
    assert (b.last_known_reply_count, b.latest_replies, b.expired) == (183, 207, 0)
    d.bookmark_seen("4chan", "g", 1, 207, 555)
    b = d.bookmarks()[0]
    assert (b.last_known_reply_count, b.last_opened_post) == (207, 555)
    d.bookmark_remove("4chan", "g", 1)
    assert not d.bookmark_has("4chan", "g", 1)


def test_observe_marks_missing_expired_and_present_alive():
    d = DB(":memory:")
    d.bookmark_add("4chan", "g", 1, "a", 5)
    d.bookmark_add("4chan", "g", 2, "b", 5)
    d.bookmark_add("4chan", "v", 3, "c", 5)
    d.bookmarks_observe("4chan", "g", {1: 9})
    by = {b.thread_id: b for b in d.bookmarks()}
    assert by[1].latest_replies == 9 and not by[1].expired
    assert by[2].expired and not by[3].expired
    d.bookmark_expire("4chan", "v", 3)
    assert {b.thread_id: b.expired for b in d.bookmarks()}[3]


def test_favourites_keep_order():
    d = DB(":memory:")
    assert d.fav_toggle("4chan", "v") and d.fav_toggle("lainchan", "sec") and d.fav_toggle("4chan", "g")
    assert d.fav_boards() == [("4chan", "v"), ("lainchan", "sec"), ("4chan", "g")]
    assert not d.fav_toggle("4chan", "v") and d.fav_boards() == [("lainchan", "sec"), ("4chan", "g")]


def test_nav_defaults_and_partial_update():
    d = DB(":memory:")
    n = d.nav_get("4chan", "g")
    assert (n.catalog_anchor, n.thread_no, n.thread_anchor) == (0, 0, 0)
    d.nav_set("4chan", "g", catalog_anchor=7)
    d.nav_set("4chan", "g", thread_no=9, thread_anchor=11)
    n = d.nav_get("4chan", "g")
    assert (n.catalog_anchor, n.thread_no, n.thread_anchor) == (7, 9, 11)


def test_nav_rejects_unknown_field():
    import pytest
    with pytest.raises(ValueError):
        DB(":memory:").nav_set("4chan", "g", bogus=1)


def test_recent_dedupes_orders_and_caps():
    d = DB(":memory:")
    for i in range(40):
        d.recent_add("4chan", "g", i, f"t{i}", now=i)
    d.recent_add("4chan", "g", 5, "t5", now=100)
    r = d.recent(limit=50)
    assert r[0] == ("4chan", "g", 5, "t5") and len(r) == 30 and len({x[2] for x in r}) == 30


def test_kv_and_persistence(tmp_path):
    f = tmp_path / "x.db"
    d = DB(f)
    d.kv_set("last_board", "g")
    d.bookmark_add("4chan", "g", 1, "keep me", 3)
    d2 = DB(f)
    assert d2.kv_get("last_board") == "g" and d2.kv_get("zzz", "dflt") == "dflt"
    assert d2.bookmarks()[0].subject == "keep me"


def test_same_board_and_thread_on_two_sites_never_collide():
    d = DB(":memory:")
    d.bookmark_add("4chan", "b", 10, "four", 1)
    d.bookmark_add("kissu", "b", 10, "kissu", 2)
    assert d.bookmark_has("4chan", "b", 10) and d.bookmark_has("kissu", "b", 10)
    d.bookmark_remove("kissu", "b", 10)
    assert d.bookmark_has("4chan", "b", 10) and not d.bookmark_has("kissu", "b", 10)
    d.nav_set("4chan", "b", catalog_anchor=1)
    d.nav_set("kissu", "b", catalog_anchor=2)
    assert d.nav_get("4chan", "b").catalog_anchor == 1 and d.nav_get("kissu", "b").catalog_anchor == 2
    d.recent_add("4chan", "b", 10, "a", now=1)
    d.recent_add("kissu", "b", 10, "b", now=2)
    assert [r[0] for r in d.recent()] == ["kissu", "4chan"]
    d.bookmarks_observe("kissu", "b", {})
    assert not [b for b in d.bookmarks() if b.site == "4chan"][0].expired


def test_prune_keeps_bookmarked_threads_of_every_site():
    d = DB(":memory:")
    for i in range(4):
        d.cache_put(f"lainchan:thread:sec:{i}", "{}", None, now=i)
        d.cache_put(f"thread:g:{i}", "{}", None, now=i)
    d.bookmark_add("lainchan", "sec", 0, "x", 1)
    d.bookmark_add("4chan", "g", 0, "y", 1)
    d.prune_threads(keep=1)
    alive = {k for k in [f"lainchan:thread:sec:{i}" for i in range(4)] + [f"thread:g:{i}" for i in range(4)]
             if d.cache_get(k)}
    assert "lainchan:thread:sec:0" in alive and "thread:g:0" in alive
    assert len(alive) == 3                                   # two bookmarked + the single newest


V1_SCHEMA = """
CREATE TABLE cache(key TEXT PRIMARY KEY, body TEXT NOT NULL, fetched_at REAL NOT NULL, last_modified TEXT);
CREATE TABLE bookmarks(board TEXT NOT NULL, thread_id INTEGER NOT NULL, subject TEXT NOT NULL, saved_at REAL NOT NULL,
  last_known_reply_count INTEGER NOT NULL DEFAULT 0, last_opened_post INTEGER NOT NULL DEFAULT 0,
  latest_replies INTEGER NOT NULL DEFAULT 0, expired INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(board, thread_id));
CREATE TABLE favourites(board TEXT PRIMARY KEY, pos INTEGER NOT NULL);
CREATE TABLE nav(board TEXT PRIMARY KEY, catalog_anchor INTEGER NOT NULL DEFAULT 0,
  thread_no INTEGER NOT NULL DEFAULT 0, thread_anchor INTEGER NOT NULL DEFAULT 0);
CREATE TABLE recent(board TEXT NOT NULL, thread_id INTEGER NOT NULL, subject TEXT NOT NULL, visited_at REAL NOT NULL,
  PRIMARY KEY(board, thread_id));
CREATE TABLE kv(key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT INTO cache VALUES('catalog:g','[]',5,'Mon');
INSERT INTO bookmarks VALUES('g',100,'GPU',7,10,3,12,0);
INSERT INTO bookmarks VALUES('v',200,'RPG',8,5,0,5,1);
INSERT INTO favourites VALUES('v',0);
INSERT INTO favourites VALUES('g',1);
INSERT INTO nav VALUES('g',11,100,22);
INSERT INTO recent VALUES('g',100,'GPU',9);
INSERT INTO kv VALUES('last_board','g');
"""


def make_v1(path):
    import sqlite3
    c = sqlite3.connect(path)
    c.executescript(V1_SCHEMA)
    c.commit()
    c.close()


def test_v1_database_migrates_keeping_everything(tmp_path):
    f = tmp_path / "old.db"
    make_v1(f)
    d = DB(f)
    assert {(b.site, b.board, b.thread_id): (b.subject, b.last_known_reply_count, b.last_opened_post,
                                             b.latest_replies, b.expired) for b in d.bookmarks()} == {
        ("4chan", "g", 100): ("GPU", 10, 3, 12, False), ("4chan", "v", 200): ("RPG", 5, 0, 5, True)}
    assert d.fav_boards() == [("4chan", "v"), ("4chan", "g")]
    n = d.nav_get("4chan", "g")
    assert (n.catalog_anchor, n.thread_no, n.thread_anchor) == (11, 100, 22)
    assert d.recent() == [("4chan", "g", 100, "GPU")]
    assert d.cache_get("catalog:g").last_modified == "Mon" and d.kv_get("last_board") == "g"
    assert (tmp_path / "old.db.v1.bak").exists()


def test_migration_is_idempotent_and_leaves_one_backup(tmp_path):
    f = tmp_path / "old.db"
    make_v1(f)
    DB(f).bookmark_add("kissu", "b", 1, "new", 1)
    d = DB(f)                                               # second open must not migrate again
    assert len(d.bookmarks()) == 3
    assert sorted(p.name for p in tmp_path.iterdir()) == ["old.db", "old.db.v1.bak"]


def test_fresh_database_is_v2_without_backup(tmp_path):
    f = tmp_path / "new.db"
    DB(f).bookmark_add("4chan", "g", 1, "x", 1)
    assert [p.name for p in tmp_path.iterdir()] == ["new.db"]
