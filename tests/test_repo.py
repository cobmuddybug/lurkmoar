import json
import os

import pytest

from lurkmoar.api import ApiError, NotFound, Response
from lurkmoar.db import DB
from lurkmoar.repo import Core, evict
from samples import BOARDS, CATALOG, THREAD


class FakeClient:
    """Maps url -> list of outcomes (Response or Exception); last one repeats."""
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def get(self, url, last_modified=None):
        self.calls.append((url, last_modified))
        seq = self.routes[url]
        out = seq.pop(0) if len(seq) > 1 else seq[0]
        if isinstance(out, Exception):
            raise out
        return out


def ok(obj, lm="Mon"):
    return Response(200, json.dumps(obj).encode(), lm)


CAT = "https://a.4cdn.org/g/catalog.json"
THR = "https://a.4cdn.org/g/thread/100.json"


def core(routes, t):
    db = DB(":memory:")
    return Core(db, FakeClient(routes), now=lambda: t[0]), db


def test_catalog_fetch_then_ttl_hit_makes_one_call():
    t = [1000.0]
    c, _ = core({CAT: [ok(CATALOG)]}, t)
    r1 = c.catalog("4chan", "g")
    assert [x.number for x in r1.data] == [100, 101, 102] and not r1.from_cache
    t[0] += 5
    r2 = c.catalog("4chan", "g")
    assert r2.from_cache and r2.error is None and len(c.client.calls) == 1


def test_after_ttl_sends_if_modified_since_and_304_serves_cache():
    t = [1000.0]
    c, _ = core({CAT: [ok(CATALOG), Response(304, b"", None)]}, t)
    c.catalog("4chan", "g")
    t[0] += 11
    r = c.catalog("4chan", "g")
    assert c.client.calls[1] == (CAT, "Mon") and len(r.data) == 3 and not r.from_cache


def test_network_error_with_cache_returns_cached_with_error():
    t = [1000.0]
    c, _ = core({CAT: [ok(CATALOG), ApiError("network: ConnectError")]}, t)
    c.catalog("4chan", "g")
    t[0] += 11
    r = c.catalog("4chan", "g")
    assert r.from_cache and r.error and not r.gone and len(r.data) == 3


def test_network_error_without_cache():
    c, _ = core({CAT: [ApiError("network: ConnectError")]}, [0.0])
    r = c.catalog("4chan", "g")
    assert r.data is None and r.error and r.fetched_at is None


def test_thread_404_is_gone_and_expires_bookmark():
    t = [1000.0]
    c, db = core({THR: [ok(THREAD), NotFound("nf", 404)]}, t)
    db.bookmark_add("4chan", "g", 100, "x", 3)
    assert c.thread("4chan", "g", 100).data.replies == 3
    t[0] += 11
    r = c.thread("4chan", "g", 100)
    assert r.gone and r.data is not None and r.from_cache
    assert db.bookmarks()[0].expired


def test_thread_404_without_cache():
    c, _ = core({THR: [NotFound("nf", 404)]}, [0.0])
    r = c.thread("4chan", "g", 100)
    assert r.gone and r.data is None


def test_catalog_updates_bookmarks():
    c, db = core({CAT: [ok(CATALOG)]}, [0.0])
    db.bookmark_add("4chan", "g", 100, "a", 10)
    db.bookmark_add("4chan", "g", 999, "gone", 10)
    c.catalog("4chan", "g")
    by = {b.thread_id: b for b in db.bookmarks()}
    assert by[100].latest_replies == 183 and not by[100].expired and by[999].expired


def test_malformed_json_keeps_old_cache():
    t = [0.0]
    c, db = core({CAT: [ok(CATALOG), Response(200, b"<html>", None)]}, t)
    c.catalog("4chan", "g")
    t[0] += 11
    r = c.catalog("4chan", "g")
    assert r.error and len(r.data) == 3
    assert json.loads(db.cache_get("catalog:g").body) == CATALOG


def test_corrupt_cache_row_is_treated_as_absent():
    t = [0.0]
    c, db = core({CAT: [ok(CATALOG)]}, t)
    db.cache_put("catalog:g", "not json", None, now=0)
    r = c.catalog("4chan", "g")
    assert len(r.data) == 3 and not r.from_cache


def test_offline_never_hits_network():
    c, _ = core({}, [0.0])
    assert c.catalog("4chan", "g", offline=True).data is None and c.client.calls == []


def test_boards_ttl_is_long():
    t = [0.0]
    c, _ = core({"https://a.4cdn.org/boards.json": [ok(BOARDS)]}, t)
    c.boards()
    t[0] += 3600
    r = c.boards()
    assert r.from_cache and [b.code for b in r.data] == ["g", "v", "vg"]
    assert len(c.client.calls) == 1


def test_wrong_shape_payload_is_an_error_not_a_crash():
    c, _ = core({CAT: [ok({"unexpected": True})]}, [0.0])
    r = c.catalog("4chan", "g")
    assert r.data is None and r.error


def test_evict_removes_oldest_first(tmp_path):
    for i, name in enumerate("abc"):
        f = tmp_path / name
        f.write_bytes(b"x" * 100)
        os.utime(f, (i, i))
    evict([tmp_path], 150)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["c"]


def test_repo_dedupes_and_emits(qapp, tmp_path):
    import time as _t
    from lurkmoar.config import load_config, paths
    from lurkmoar.repo import Repo

    p = paths()
    client = FakeClient({CAT: [ok(CATALOG)]})
    repo = Repo(DB(":memory:"), client, FakeClient({}), p, load_config(p))
    got = []
    repo.catalog_ready.connect(lambda s, b, r: got.append((b, r)))
    assert repo.request_catalog("4chan", "g") is True
    repo.request_catalog("4chan", "g")  # may be in flight or already done; either way
    end = _t.time() + 5
    while not got and _t.time() < end:
        qapp.processEvents()
        _t.sleep(0.01)
    assert got and got[0][0] == "g" and len(got[0][1].data) == 3
    assert len(client.calls) == 1
    assert repo.cached_catalog("4chan", "g").data is not None


def test_failed_refresh_does_not_expire_bookmarks_or_overwrite_counts():
    t = [1000.0]
    c, db = core({CAT: [ok(CATALOG), ApiError("network: ConnectError")]}, t)
    c.catalog("4chan", "g")
    db.bookmark_add("4chan", "g", 999, "newer than cache", 10)
    t[0] += 11
    r = c.catalog("4chan", "g")
    assert r.error and r.from_cache
    assert not db.bookmarks()[0].expired


def test_failed_thread_refresh_keeps_bookmark_counts():
    t = [1000.0]
    c, db = core({THR: [ok(THREAD), ApiError("network: ConnectError")]}, t)
    db.bookmark_add("4chan", "g", 100, "x", 50)
    c.thread("4chan", "g", 100)
    db.bookmark_latest("4chan", "g", 100, 77)
    t[0] += 11
    assert c.thread("4chan", "g", 100).error
    assert db.bookmarks()[0].latest_replies == 77


import time as _time

from lurkmoar.sites import load_sites
from samples_vichan import VICHAN_CATALOG, VICHAN_THREAD

LCAT = "https://lainchan.org/sec/catalog.json"
LTHR = "https://lainchan.org/sec/res/10.json"


def test_vichan_catalog_and_thread_through_core_use_prefixed_cache_keys():
    t = [1000.0]
    c, db = core({LCAT: [ok(VICHAN_CATALOG)], LTHR: [ok(VICHAN_THREAD)]}, t)
    r = c.catalog("lainchan", "sec")
    assert [x.number for x in r.data] == [10, 11, 12] and r.data[0].site == "lainchan"
    th = c.thread("lainchan", "sec", 10)
    assert th.data.site == "lainchan" and len(th.data.posts) == 3
    assert db.cache_get("lainchan:catalog:sec") and db.cache_get("lainchan:thread:sec:10")
    assert db.cache_get("catalog:sec") is None and db.cache_get("thread:sec:10") is None


def test_same_board_on_two_sites_does_not_share_cache():
    t = [1000.0]
    kissu = "https://kissu.moe/b/catalog.json"
    c, db = core({kissu: [ok(VICHAN_CATALOG)], "https://a.4cdn.org/b/catalog.json": [ok(CATALOG)]}, t)
    assert [x.number for x in c.catalog("kissu", "b").data] == [10, 11, 12]
    assert [x.number for x in c.catalog("4chan", "b").data] == [100, 101, 102]
    assert db.cache_get("kissu:catalog:b") and db.cache_get("catalog:b")


def test_bad_board_code_is_an_error_result_not_a_request():
    c, _ = core({}, [0.0])
    r = c.catalog("lainchan", "../x")
    assert r.data is None and r.error == "bad board" and c.client.calls == []


def test_per_site_clients_are_used():
    a, b = FakeClient({LCAT: [ok(VICHAN_CATALOG)]}), FakeClient({"https://a.4cdn.org/g/catalog.json": [ok(CATALOG)]})
    c = Core(DB(":memory:"), {"lainchan": a, "4chan": b}, now=lambda: 0.0)
    c.catalog("lainchan", "sec")
    c.catalog("4chan", "g")
    assert len(a.calls) == 1 and len(b.calls) == 1


def test_failing_site_does_not_affect_another():
    t = [0.0]
    c, db = core({LCAT: [ApiError("network: down")], "https://a.4cdn.org/g/catalog.json": [ok(CATALOG)]}, t)
    assert c.catalog("lainchan", "sec").error
    assert c.catalog("4chan", "g").error is None


def test_overboard_bookmarks_are_keyed_by_real_board():
    t = [0.0]
    from samples_vichan import FILES_CATALOG
    url = "https://leftypol.org/overboard/catalog.json"
    c, db = core({url: [ok(FILES_CATALOG)]}, t)
    db.bookmark_add("leftypol", "alt", 20, "kept", 3)
    r = c.catalog("leftypol", "overboard")
    assert [x.board for x in r.data] == ["alt", "leftypol"]
    assert not db.bookmarks()[0].expired                     # a bookmark on /alt/ is not judged by the overboard


def test_thumb_loader_falls_back_and_remembers_winner(qapp, tmp_path):
    from helpers import png_bytes
    from lurkmoar.repo import ThumbLoader
    calls = []

    class C:
        def get(self, url, last_modified=None):
            calls.append(url)
            if url.endswith(".png"):
                return Response(200, png_bytes(), None)
            raise NotFound("nf", 404)

    tl = ThumbLoader(lambda site: C(), tmp_path, lambda: None, workers=1)

    def wait(key, urls):
        end = _time.time() + 5
        while tl.image(key, urls, "lainchan/sec", "lainchan") is None and _time.time() < end:
            _time.sleep(0.01)

    wait("k1", ("https://x/b/thumb/1.jpg", "https://x/b/thumb/1.png", "https://x/b/thumb/1.webp"))
    assert calls == ["https://x/b/thumb/1.jpg", "https://x/b/thumb/1.png"]
    calls.clear()
    wait("k2", ("https://x/b/thumb/2.jpg", "https://x/b/thumb/2.png", "https://x/b/thumb/2.webp"))
    assert calls[0] == "https://x/b/thumb/2.png"            # the winning extension is tried first now


def test_thumb_loader_gives_up_once_when_every_candidate_fails(qapp, tmp_path):
    from lurkmoar.repo import ThumbLoader
    calls = []

    class C:
        def get(self, url, last_modified=None):
            calls.append(url)
            raise NotFound("nf", 404)

    tl = ThumbLoader(lambda site: C(), tmp_path, lambda: None, workers=1)
    urls = ("https://x/b/thumb/3.jpg", "https://x/b/thumb/3.png", "https://x/b/thumb/3.webp")
    tl.image("k3", urls)
    end = _time.time() + 5
    while not tl.failed("k3") and _time.time() < end:
        _time.sleep(0.01)
    assert tl.failed("k3") and len(calls) == 3
    tl.image("k3", urls)
    _time.sleep(0.2)
    assert len(calls) == 3                                    # no retry storm inside the failure window


def test_empty_thumbnail_url_is_a_failure_without_any_request(qapp, tmp_path):
    from lurkmoar.repo import ThumbLoader
    calls = []

    class C:
        def get(self, url, last_modified=None):
            calls.append(url)

    tl = ThumbLoader(lambda site: C(), tmp_path, lambda: None, workers=1)
    assert tl.image("k4", ("",)) is None and tl.failed("k4") and calls == []


def test_media_and_thumb_file_names_never_collide_across_sites(qapp, tmp_path):
    from lurkmoar.config import load_config, paths
    from lurkmoar.models import Attachment
    from lurkmoar.repo import Repo
    p = paths()
    att = Attachment("77", "f", ".jpg", 1, 1, 1, "https://x/t.jpg", "https://x/o.jpg", False)
    repo = Repo(DB(":memory:"), FakeClient({}), FakeClient({}), p, load_config(p))
    assert repo.cached_media_path("lainchan", "sec", att) is None
    (p.media / "lainchan_sec_77.jpg").write_bytes(b"x")
    assert repo.cached_media_path("lainchan", "sec", att) is not None
    assert repo.cached_media_path("kissu", "sec", att) is None
    assert repo.cached_media_path("4chan", "sec", att) is None


def test_build_clients_make_one_per_site_with_their_intervals():
    from lurkmoar.api import build_clients
    s = load_sites()
    api_c, cdn_c = build_clients(s)
    assert set(api_c) == set(cdn_c) == set(s)
    assert api_c["lainchan"]._min == 1.0 and cdn_c["lainchan"]._min == 0.35 and cdn_c["4chan"]._min == 0.05
