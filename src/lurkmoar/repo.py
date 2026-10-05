"""Cache-or-fetch repository. UI talks to Repo; only api.Client touches the network."""
import json
import os
import threading
import time
from collections import OrderedDict, deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage

from .adapters import adapter_for
from .api import ApiError, NotFound, boards_url
from .models import Board, is_video
from .sites import key as site_key, load_sites

BOARDS_TTL = 6 * 3600
LIVE_TTL = 10  # the API asks clients not to refetch the same resource faster than this


@dataclass
class Result:
    data: Any
    fetched_at: float | None
    from_cache: bool
    error: str | None = None
    gone: bool = False


class Core:
    def __init__(self, db, client, now=time.time, sites=None):
        self.db, self.client, self.now = db, client, now
        self.sites = sites or load_sites()

    def _client(self, site):
        return self.client[site] if isinstance(self.client, dict) else self.client

    def _load(self, key, url, ttl, offline, site="4chan"):
        row = self.db.cache_get(key)
        cached = None
        if row:
            try:
                cached = json.loads(row.body)
            except ValueError:
                cached = None
        stamp = row.fetched_at if cached is not None else None
        if offline or (cached is not None and self.now() - row.fetched_at < ttl):
            return Result(cached, stamp, True)
        ims = row.last_modified if cached is not None else None
        try:
            r = self._client(site).get(url, ims)
            if r.status == 304 and cached is not None:
                self.db.cache_touch(key, self.now())
                return Result(cached, self.now(), False)
            data = json.loads(r.body)
        except NotFound:
            return Result(cached, stamp, True, error="not found", gone=True)
        except ApiError as e:
            return Result(cached, stamp, True, error=str(e))
        except ValueError:
            return Result(cached, stamp, True, error="bad response")
        self.db.cache_put(key, r.body.decode("utf-8", "replace"), r.last_modified, self.now())
        return Result(data, self.now(), False)

    @staticmethod
    def _typed(res, fn):
        if res.data is None:
            return res
        try:
            return replace(res, data=fn(res.data))
        except (KeyError, TypeError, ValueError, AttributeError, IndexError):
            return Result(None, res.fetched_at, res.from_cache, error="bad response", gone=res.gone)

    def boards(self, offline=False):
        res = self._load("boards", boards_url(), BOARDS_TTL, offline)
        return self._typed(res, lambda d: [Board.from_api(b) for b in d["boards"]])

    def catalog(self, site, board, offline=False):
        s = self.sites[site]
        ad = adapter_for(s)
        try:
            url = ad.catalog_url(s, board)
        except ValueError:
            return Result(None, None, False, error="bad board")
        res = self._typed(self._load(site_key(site, "catalog", board), url, LIVE_TTL, offline, site),
                          lambda d: ad.parse_catalog(s, board, d))
        if res.data is not None and not offline and res.error is None:
            self.db.bookmarks_observe(site, board, {t.number: t.replies for t in res.data if t.board == board})
        return res

    def thread(self, site, board, no, offline=False):
        s = self.sites[site]
        ad = adapter_for(s)
        try:
            url = ad.thread_url(s, board, no)
        except ValueError:
            return Result(None, None, False, error="bad board")
        res = self._typed(self._load(site_key(site, "thread", board, no), url, LIVE_TTL, offline, site),
                          lambda d: ad.parse_thread(s, board, no, d))
        if offline:
            return res
        if res.gone:
            self.db.bookmark_expire(site, board, no)
        elif res.data is not None and res.error is None:
            self.db.bookmark_latest(site, board, no, res.data.replies)
            if not res.from_cache:
                self.db.prune_threads()
        return res


def evict(dirs, max_bytes):
    files = []
    for d in dirs:
        for f in Path(d).glob("*"):
            if f.is_file():
                st = f.stat()
                files.append((st.st_mtime, st.st_size, f))
    total = sum(s for _, s, _ in files)
    for _, size, f in sorted(files, key=lambda x: x[0]):
        if total <= max_bytes:
            break
        f.unlink(missing_ok=True)
        total -= size


class ThumbLoader:
    """Newest-first thumbnail fetch+decode off the GUI thread. Old requests fall off a bounded queue."""

    def __init__(self, client_for, directory, on_change, workers=4, cap=64, keep=400):
        self.client_for, self.dir, self.on_change = client_for, Path(directory), on_change
        self._winner: dict = {}
        self._cap, self._keep = cap, keep
        self._q: deque = deque()
        self._queued, self._active = set(), set()
        self._failed: dict[str, float] = {}
        self._images: OrderedDict = OrderedDict()
        self._cv = threading.Condition()
        for _ in range(workers):
            threading.Thread(target=self._run, daemon=True).start()

    def image(self, key, urls, group=None, site="4chan"):
        urls = (urls,) if isinstance(urls, str) else tuple(urls)
        with self._cv:
            img = self._images.get(key)
            if img is not None:
                self._images.move_to_end(key)
                return img
            if key in self._queued or key in self._active:
                return None
            if time.time() - self._failed.get(key, 0) < 60:
                return None
            if not any(urls):
                self._failed[key] = time.time()
                return None
            self._q.append((key, urls, group, site))
            self._queued.add(key)
            while len(self._q) > self._cap:
                self._queued.discard(self._q.popleft()[0])
            self._cv.notify()
        return None

    def _ordered(self, urls, group):
        ext = self._winner.get(group)
        if not ext:
            return [u for u in urls if u]
        return sorted((u for u in urls if u), key=lambda u: not u.endswith(ext))   # stable: winner first

    def _fetch(self, key, urls, group, site):
        dest = self.dir / key
        if dest.exists():
            data = dest.read_bytes()
            os.utime(dest)
            img = QImage.fromData(data)
            return None if img.isNull() else img
        for u in self._ordered(urls, group):
            try:
                body = self.client_for(site).get(u).body
            except (ApiError, OSError):
                continue
            img = QImage.fromData(body)
            if img.isNull():
                continue
            tmp = dest.with_suffix(dest.suffix + ".tmp")
            tmp.write_bytes(body)
            tmp.replace(dest)
            if group:
                self._winner[group] = Path(u).suffix
            return img
        return None

    def failed(self, key):
        return time.time() - self._failed.get(key, 0) < 60

    def _run(self):
        while True:
            with self._cv:
                while not self._q:
                    self._cv.wait()
                key, urls, group, site = self._q.pop()
                self._queued.discard(key)
                self._active.add(key)
            try:
                img = self._fetch(key, urls, group, site)
            except Exception:                              # a worker must never die on one bad thumbnail
                img = None
            with self._cv:
                self._active.discard(key)
                if img is None:
                    self._failed[key] = time.time()
                else:
                    self._images[key] = img
                    while len(self._images) > self._keep:
                        self._images.popitem(last=False)
            self.on_change()


class Repo(QObject):
    boards_ready = Signal(object)
    catalog_ready = Signal(str, str, object)
    thread_ready = Signal(str, str, int, object)
    media_ready = Signal(str, object, str)
    thumbs_changed = Signal()

    def __init__(self, db, api_client, cdn_client, paths, cfg, now=time.time, sites=None):
        super().__init__()
        self.db, self.paths, self.cfg = db, paths, cfg
        self.sites = sites or load_sites(cfg.extra_boards, cfg.hidden_sites)
        self.core = Core(db, api_client, now, self.sites)
        self._cdn = cdn_client
        self._api_pool = ThreadPoolExecutor(1)  # serial queue; the client also rate-limits
        self._media_pool = ThreadPoolExecutor(2)
        self._inflight: set = set()
        self._lock = threading.Lock()
        self.thumbs = ThumbLoader(self._cdn_for, paths.thumbs, self.thumbs_changed.emit)

    def _submit(self, pool, key, fn, done):
        with self._lock:
            if key in self._inflight:
                return False
            self._inflight.add(key)

        def run():
            try:
                res = fn()
            except Exception as e:  # a bug must surface as an error state, not a dead worker
                res = Result(None, None, False, error=f"internal: {e!r}")
            with self._lock:
                self._inflight.discard(key)
            done(res)

        pool.submit(run)
        return True

    def request_boards(self):
        return self._submit(self._api_pool, "boards", self.core.boards, self.boards_ready.emit)

    def _cdn_for(self, site):
        return self._cdn[site] if isinstance(self._cdn, dict) else self._cdn

    @staticmethod
    def _file_stem(site, board, att_id):
        return f"{board}_{att_id}" if site == "4chan" else f"{site}_{board}_{att_id}"

    def request_catalog(self, site, board):
        return self._submit(self._api_pool, ("c", site, board), lambda: self.core.catalog(site, board),
                            lambda r: self.catalog_ready.emit(site, board, r))

    def request_thread(self, site, board, no):
        return self._submit(self._api_pool, ("t", site, board, no), lambda: self.core.thread(site, board, no),
                            lambda r: self.thread_ready.emit(site, board, no, r))

    def cached_boards(self): return self.core.boards(offline=True)
    def cached_catalog(self, site, board): return self.core.catalog(site, board, offline=True)
    def cached_thread(self, site, board, no): return self.core.thread(site, board, no, offline=True)

    def _thumb_key(self, site, board, att): return f"{self._file_stem(site, board, att.id)}s.jpg"

    def thumb_image(self, site, board, att):
        if att is None or att.deleted:
            return None
        return self.thumbs.image(self._thumb_key(site, board, att), (att.thumbnail_url, *att.thumbnail_alts),
                                 f"{site}/{board}", site)

    def thumb_failed(self, site, board, att):
        return bool(att) and self.thumbs.failed(self._thumb_key(site, board, att))

    def _media_path(self, site, board, att):
        return self.paths.media / f"{self._file_stem(site, board, att.id)}{att.extension}"

    def cached_media_path(self, site, board, att):
        """The downloaded original, or None if it hasn't finished downloading."""
        p = self._media_path(site, board, att)
        return p if p.is_file() else None

    def request_media(self, site, board, att):
        url, dest = att.original_url, self._media_path(site, board, att)

        def work():
            try:
                if dest.exists():
                    os.utime(dest)
                else:
                    tmp = dest.with_suffix(dest.suffix + ".tmp")
                    tmp.write_bytes(self._cdn_for(site).get(url).body)
                    tmp.replace(dest)
            except (ApiError, OSError) as e:
                return None, str(e)
            if is_video(att.extension):
                return str(dest), ""                  # videos play from the cached file
            img = QImage(str(dest))
            return (img, "") if not img.isNull() else (None, "Can't decode this image")

        return self._submit(self._media_pool, ("m", site, url), work,
                            lambda r: self.media_ready.emit(url, r[0], r[1]))
