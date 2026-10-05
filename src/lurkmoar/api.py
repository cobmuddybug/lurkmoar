"""The only module that talks HTTP. GET-only by construction: no other verb is exposed."""
import re
import threading
import time
from dataclasses import dataclass

import httpx

API = "https://a.4cdn.org"
USER_AGENT = "LurkMoar/0.1 (independent read-only client)"
BOARD_RE = re.compile(r"[a-z0-9]{1,10}")


class ApiError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class NotFound(ApiError):
    pass


@dataclass(frozen=True)
class Response:
    status: int
    body: bytes
    last_modified: str | None


def _board(code):
    if not BOARD_RE.fullmatch(code or ""):
        raise ValueError(f"bad board code: {code!r}")
    return code


def boards_url(): return f"{API}/boards.json"
def catalog_url(board): return f"{API}/{_board(board)}/catalog.json"
def thread_url(board, no): return f"{API}/{_board(board)}/thread/{int(no)}.json"


class Client:
    def __init__(self, min_interval=1.0, transport=None, clock=time.monotonic,
                 sleep=time.sleep, retries=3, backoff=1.0):
        self._http = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=10,
                                  follow_redirects=True, transport=transport)
        self._min, self._clock, self._sleep = min_interval, clock, sleep
        self._retries, self._backoff = retries, backoff
        self._lock = threading.Lock()
        self._next = 0.0

    def _wait(self):
        with self._lock:
            now = self._clock()
            wait = self._next - now
            if wait > 0:
                self._sleep(wait)
                now += wait
            self._next = now + self._min

    def get(self, url, last_modified=None) -> Response:
        headers = {"If-Modified-Since": last_modified} if last_modified else {}
        err = ApiError("request failed")
        for attempt in range(self._retries + 1):
            if attempt:
                self._sleep(min(8.0, self._backoff * 2 ** (attempt - 1)))
            self._wait()
            try:
                r = self._http.get(url, headers=headers)
            except httpx.HTTPError as e:
                err = ApiError(f"network: {type(e).__name__}")
                continue
            if r.status_code in (200, 304):
                return Response(r.status_code, r.content, r.headers.get("Last-Modified"))
            if r.status_code == 404:
                raise NotFound("not found", 404)
            err = ApiError(f"http {r.status_code}", r.status_code)
            if r.status_code != 429 and r.status_code < 500:
                raise err
        raise err

    def close(self):
        self._http.close()
