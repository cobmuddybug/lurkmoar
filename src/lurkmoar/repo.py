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

from .api import ApiError, NotFound, boards_url, catalog_url, thread_url
from .models import Board, Thread, flatten_catalog, is_video

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
    def __init__(self, db, client, now=time.time):
        self.db, self.client, self.now = db, client, now

    def _load(self, key, url, ttl, offline):
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
            r = self.client.get(url, ims)
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

    def catalog(self, board, offline=False):
        res = self._typed(self._load(f"catalog:{board}", catalog_url(board), LIVE_TTL, offline),
                          lambda d: flatten_catalog(board, d))
        if res.data is not None and not offline and res.error is None:
            self.db.bookmarks_observe(board, {t.number: t.replies for t in res.data})
        return res

    def thread(self, board, no, offline=False):
        key = f"thread:{board}:{no}"
        res = self._typed(self._load(key, thread_url(board, no), LIVE_TTL, offline),
                          lambda d: Thread.from_api(board, no, d))
        if offline:
            return res
        if res.gone:
            self.db.bookmark_expire(board, no)
        elif res.data is not None and res.error is None:
            self.db.bookmark_latest(board, no, res.data.replies)
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

    def __init__(self, client, directory, on_change, workers=4, cap=64, keep=400):
        self.client, self.dir, self.on_change = client, Path(directory), on_change
        self._cap, self._keep = cap, keep
        self._q: deque = deque()
        self._queued, self._active = set(), set()
        self._failed: dict[str, float] = {}
        self._images: OrderedDict = OrderedDict()
        self._cv = threading.Condition()
        for _ in range(workers):
            threading.Thread(target=self._run, daemon=True).start()

    def image(self, key, url):
        with self._cv:
            img = self._images.get(key)
            if img is not None:
                self._images.move_to_end(key)
                return img
            if key in self._queued or key in self._active:
                return None
            if time.time() - self._failed.get(key, 0) < 60:
                return None
            self._q.append((key, url))
            self._queued.add(key)
            while len(self._q) > self._cap:
                self._queued.discard(self._q.popleft()[0])
            self._cv.notify()
        return None

    def failed(self, key):
        return time.time() - self._failed.get(key, 0) < 60

    def _run(self):
        while True:
            with self._cv:
                while not self._q:
                    self._cv.wait()
                key, url = self._q.pop()
                self._queued.discard(key)
                self._active.add(key)
            img = None
            try:
                dest = self.dir / key
                if dest.exists():
                    data = dest.read_bytes()
                    os.utime(dest)
                else:
                    data = self.client.get(url).body
                    tmp = dest.with_suffix(dest.suffix + ".tmp")
                    tmp.write_bytes(data)
                    tmp.replace(dest)
                img = QImage.fromData(data)
                if img.isNull():
                    img = None
            except (ApiError, OSError):
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
    catalog_ready = Signal(str, object)
    thread_ready = Signal(str, int, object)
    media_ready = Signal(str, object, str)
    thumbs_changed = Signal()

    def __init__(self, db, api_client, cdn_client, paths, cfg, now=time.time):
        super().__init__()
        self.db, self.paths, self.cfg = db, paths, cfg
        self.core = Core(db, api_client, now)
        self._cdn = cdn_client
        self._api_pool = ThreadPoolExecutor(1)  # serial queue; the client also rate-limits
        self._media_pool = ThreadPoolExecutor(2)
        self._inflight: set = set()
        self._lock = threading.Lock()
        self.thumbs = ThumbLoader(cdn_client, paths.thumbs, self.thumbs_changed.emit)

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

    def request_catalog(self, board):
        return self._submit(self._api_pool, ("c", board), lambda: self.core.catalog(board),
                            lambda r: self.catalog_ready.emit(board, r))

    def request_thread(self, board, no):
        return self._submit(self._api_pool, ("t", board, no), lambda: self.core.thread(board, no),
                            lambda r: self.thread_ready.emit(board, no, r))

    def cached_boards(self): return self.core.boards(offline=True)
    def cached_catalog(self, board): return self.core.catalog(board, offline=True)
    def cached_thread(self, board, no): return self.core.thread(board, no, offline=True)

    def _thumb_key(self, board, att): return f"{board}_{att.id}s.jpg"

    def thumb_image(self, board, att):
        if att is None or att.deleted:
            return None
        return self.thumbs.image(self._thumb_key(board, att), att.thumbnail_url)

    def thumb_failed(self, board, att):
        return bool(att) and self.thumbs.failed(self._thumb_key(board, att))

    def cached_media_path(self, board, att):
        """The downloaded original, or None if it hasn't finished downloading."""
        p = self.paths.media / f"{board}_{att.id}{att.extension}"
        return p if p.is_file() else None

    def request_media(self, board, att):
        url, dest = att.original_url, self.paths.media / f"{board}_{att.id}{att.extension}"

        def work():
            try:
                if dest.exists():
                    os.utime(dest)
                else:
                    tmp = dest.with_suffix(dest.suffix + ".tmp")
                    tmp.write_bytes(self._cdn.get(url).body)
                    tmp.replace(dest)
            except (ApiError, OSError) as e:
                return None, str(e)
            if is_video(att.extension):
                return str(dest), ""                  # videos play from the cached file
            img = QImage(str(dest))
            return (img, "") if not img.isNull() else (None, "Can't decode this image")

        return self._submit(self._media_pool, ("m", url), work,
                            lambda r: self.media_ready.emit(url, r[0], r[1]))
