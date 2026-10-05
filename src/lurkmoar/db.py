"""SQLite store: API cache, bookmarks, favourites, per-board nav state, recents, kv."""
import sqlite3
import threading
import time
from dataclasses import dataclass

SCHEMA = """
CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY, body TEXT NOT NULL,
  fetched_at REAL NOT NULL, last_modified TEXT);
CREATE TABLE IF NOT EXISTS bookmarks(board TEXT NOT NULL, thread_id INTEGER NOT NULL,
  subject TEXT NOT NULL, saved_at REAL NOT NULL,
  last_known_reply_count INTEGER NOT NULL DEFAULT 0, last_opened_post INTEGER NOT NULL DEFAULT 0,
  latest_replies INTEGER NOT NULL DEFAULT 0, expired INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY(board, thread_id));
CREATE TABLE IF NOT EXISTS favourites(board TEXT PRIMARY KEY, pos INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS nav(board TEXT PRIMARY KEY, catalog_anchor INTEGER NOT NULL DEFAULT 0,
  thread_no INTEGER NOT NULL DEFAULT 0, thread_anchor INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS recent(board TEXT NOT NULL, thread_id INTEGER NOT NULL,
  subject TEXT NOT NULL, visited_at REAL NOT NULL, PRIMARY KEY(board, thread_id));
CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""
NAV_FIELDS = {"catalog_anchor", "thread_no", "thread_anchor"}


@dataclass(frozen=True)
class CacheRow:
    body: str
    fetched_at: float
    last_modified: str | None


@dataclass(frozen=True)
class Bookmark:
    board: str
    thread_id: int
    subject: str
    saved_at: float
    last_known_reply_count: int
    last_opened_post: int
    latest_replies: int
    expired: bool


@dataclass(frozen=True)
class Nav:
    catalog_anchor: int = 0
    thread_no: int = 0
    thread_anchor: int = 0


class DB:
    def __init__(self, path):
        self._c = sqlite3.connect(str(path), check_same_thread=False)
        self._c.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._c.executescript(SCHEMA)

    def _q(self, sql, args=()):
        with self._lock:
            return self._c.execute(sql, args).fetchall()

    def _x(self, sql, args=()):
        with self._lock, self._c:
            self._c.execute(sql, args)

    # cache
    def cache_get(self, key):
        r = self._q("SELECT body, fetched_at, last_modified FROM cache WHERE key=?", (key,))
        return CacheRow(r[0][0], r[0][1], r[0][2]) if r else None

    def cache_put(self, key, body, last_modified, now=None):
        self._x("INSERT OR REPLACE INTO cache VALUES(?,?,?,?)",
                (key, body, now if now is not None else time.time(), last_modified))

    def cache_touch(self, key, now):
        self._x("UPDATE cache SET fetched_at=? WHERE key=?", (now, key))

    def prune_threads(self, keep=50):
        self._x("""DELETE FROM cache WHERE key LIKE 'thread:%'
          AND key NOT IN (SELECT 'thread:'||board||':'||thread_id FROM bookmarks)
          AND key NOT IN (SELECT key FROM cache WHERE key LIKE 'thread:%'
                          ORDER BY fetched_at DESC LIMIT ?)""", (keep,))

    # bookmarks
    def bookmark_add(self, board, thread_id, subject, replies):
        self._x("INSERT OR IGNORE INTO bookmarks VALUES(?,?,?,?,?,0,?,0)",
                (board, thread_id, subject, time.time(), replies, replies))

    def bookmark_remove(self, board, thread_id):
        self._x("DELETE FROM bookmarks WHERE board=? AND thread_id=?", (board, thread_id))

    def bookmark_has(self, board, thread_id):
        return bool(self._q("SELECT 1 FROM bookmarks WHERE board=? AND thread_id=?",
                            (board, thread_id)))

    def bookmarks(self):
        return [Bookmark(r[0], r[1], r[2], r[3], r[4], r[5], r[6], bool(r[7])) for r in
                self._q("SELECT board, thread_id, subject, saved_at, last_known_reply_count,"
                        " last_opened_post, latest_replies, expired FROM bookmarks"
                        " ORDER BY saved_at DESC")]

    def bookmarks_observe(self, board, replies):
        for b in self.bookmarks():
            if b.board != board:
                continue
            if b.thread_id in replies:
                self._x("UPDATE bookmarks SET latest_replies=?, expired=0"
                        " WHERE board=? AND thread_id=?", (replies[b.thread_id], board, b.thread_id))
            else:
                self.bookmark_expire(board, b.thread_id)

    def bookmark_latest(self, board, thread_id, replies):
        self._x("UPDATE bookmarks SET latest_replies=?, expired=0 WHERE board=? AND thread_id=?",
                (replies, board, thread_id))

    def bookmark_expire(self, board, thread_id):
        self._x("UPDATE bookmarks SET expired=1 WHERE board=? AND thread_id=?", (board, thread_id))

    def bookmark_seen(self, board, thread_id, replies, last_post):
        self._x("UPDATE bookmarks SET last_known_reply_count=?, latest_replies=?,"
                " last_opened_post=? WHERE board=? AND thread_id=?",
                (replies, replies, last_post, board, thread_id))

    # favourites
    def fav_boards(self):
        return [r[0] for r in self._q("SELECT board FROM favourites ORDER BY pos")]

    def fav_toggle(self, board):
        if board in self.fav_boards():
            self._x("DELETE FROM favourites WHERE board=?", (board,))
            return False
        self._x("INSERT INTO favourites VALUES(?, COALESCE((SELECT MAX(pos)+1 FROM favourites),0))",
                (board,))
        return True

    # nav
    def nav_get(self, board):
        r = self._q("SELECT catalog_anchor, thread_no, thread_anchor FROM nav WHERE board=?", (board,))
        return Nav(*r[0]) if r else Nav()

    def nav_set(self, board, **fields):
        if not fields or not set(fields) <= NAV_FIELDS:
            raise ValueError(f"bad nav fields: {sorted(fields)}")
        self._x("INSERT OR IGNORE INTO nav(board) VALUES(?)", (board,))
        sets = ", ".join(f"{k}=?" for k in fields)
        self._x(f"UPDATE nav SET {sets} WHERE board=?", (*fields.values(), board))

    # recent
    def recent_add(self, board, thread_id, subject, now=None):
        self._x("INSERT OR REPLACE INTO recent VALUES(?,?,?,?)",
                (board, thread_id, subject, now if now is not None else time.time()))
        self._x("""DELETE FROM recent WHERE rowid NOT IN
                   (SELECT rowid FROM recent ORDER BY visited_at DESC LIMIT 30)""")

    def recent(self, limit=20):
        return [(r[0], r[1], r[2]) for r in self._q(
            "SELECT board, thread_id, subject FROM recent ORDER BY visited_at DESC LIMIT ?", (limit,))]

    # kv
    def kv_get(self, key, default=None):
        r = self._q("SELECT value FROM kv WHERE key=?", (key,))
        return r[0][0] if r else default

    def kv_set(self, key, value):
        self._x("INSERT OR REPLACE INTO kv VALUES(?,?)", (key, str(value)))
