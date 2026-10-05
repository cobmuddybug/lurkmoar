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
    r1 = c.catalog("g")
    assert [x.number for x in r1.data] == [100, 101, 102] and not r1.from_cache
    t[0] += 5
    r2 = c.catalog("g")
    assert r2.from_cache and r2.error is None and len(c.client.calls) == 1


def test_after_ttl_sends_if_modified_since_and_304_serves_cache():
    t = [1000.0]
    c, _ = core({CAT: [ok(CATALOG), Response(304, b"", None)]}, t)
    c.catalog("g")
    t[0] += 11
    r = c.catalog("g")
    assert c.client.calls[1] == (CAT, "Mon") and len(r.data) == 3 and not r.from_cache


def test_network_error_with_cache_returns_cached_with_error():
    t = [1000.0]
    c, _ = core({CAT: [ok(CATALOG), ApiError("network: ConnectError")]}, t)
    c.catalog("g")
    t[0] += 11
    r = c.catalog("g")
    assert r.from_cache and r.error and not r.gone and len(r.data) == 3


def test_network_error_without_cache():
    c, _ = core({CAT: [ApiError("network: ConnectError")]}, [0.0])
    r = c.catalog("g")
    assert r.data is None and r.error and r.fetched_at is None


def test_thread_404_is_gone_and_expires_bookmark():
    t = [1000.0]
    c, db = core({THR: [ok(THREAD), NotFound("nf", 404)]}, t)
    db.bookmark_add("4chan", "g", 100, "x", 3)
    assert c.thread("g", 100).data.replies == 3
    t[0] += 11
    r = c.thread("g", 100)
    assert r.gone and r.data is not None and r.from_cache
    assert db.bookmarks()[0].expired


def test_thread_404_without_cache():
    c, _ = core({THR: [NotFound("nf", 404)]}, [0.0])
    r = c.thread("g", 100)
    assert r.gone and r.data is None


def test_catalog_updates_bookmarks():
    c, db = core({CAT: [ok(CATALOG)]}, [0.0])
    db.bookmark_add("4chan", "g", 100, "a", 10)
    db.bookmark_add("4chan", "g", 999, "gone", 10)
    c.catalog("g")
    by = {b.thread_id: b for b in db.bookmarks()}
    assert by[100].latest_replies == 183 and not by[100].expired and by[999].expired


def test_malformed_json_keeps_old_cache():
    t = [0.0]
    c, db = core({CAT: [ok(CATALOG), Response(200, b"<html>", None)]}, t)
    c.catalog("g")
    t[0] += 11
    r = c.catalog("g")
    assert r.error and len(r.data) == 3
    assert json.loads(db.cache_get("catalog:g").body) == CATALOG


def test_corrupt_cache_row_is_treated_as_absent():
    t = [0.0]
    c, db = core({CAT: [ok(CATALOG)]}, t)
    db.cache_put("catalog:g", "not json", None, now=0)
    r = c.catalog("g")
    assert len(r.data) == 3 and not r.from_cache


def test_offline_never_hits_network():
    c, _ = core({}, [0.0])
    assert c.catalog("g", offline=True).data is None and c.client.calls == []


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
    r = c.catalog("g")
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
    repo.catalog_ready.connect(lambda b, r: got.append((b, r)))
    assert repo.request_catalog("g") is True
    repo.request_catalog("g")  # may be in flight or already done; either way
    end = _t.time() + 5
    while not got and _t.time() < end:
        qapp.processEvents()
        _t.sleep(0.01)
    assert got and got[0][0] == "g" and len(got[0][1].data) == 3
    assert len(client.calls) == 1
    assert repo.cached_catalog("g").data is not None


def test_failed_refresh_does_not_expire_bookmarks_or_overwrite_counts():
    t = [1000.0]
    c, db = core({CAT: [ok(CATALOG), ApiError("network: ConnectError")]}, t)
    c.catalog("g")
    db.bookmark_add("4chan", "g", 999, "newer than cache", 10)
    t[0] += 11
    r = c.catalog("g")
    assert r.error and r.from_cache
    assert not db.bookmarks()[0].expired


def test_failed_thread_refresh_keeps_bookmark_counts():
    t = [1000.0]
    c, db = core({THR: [ok(THREAD), ApiError("network: ConnectError")]}, t)
    db.bookmark_add("4chan", "g", 100, "x", 50)
    c.thread("g", 100)
    db.bookmark_latest("4chan", "g", 100, 77)
    t[0] += 11
    assert c.thread("g", 100).error
    assert db.bookmarks()[0].latest_replies == 77
