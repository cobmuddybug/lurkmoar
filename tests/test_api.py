import pathlib

import httpx
import pytest

from lurkmoar.api import ApiError, Client, NotFound, catalog_url, thread_url


class Clock:
    def __init__(self): self.t = 0.0
    def now(self): return self.t
    def sleep(self, s): self.t += s


def make(handler, **kw):
    c = Clock()
    return Client(transport=httpx.MockTransport(handler), clock=c.now, sleep=c.sleep, **kw), c


def test_get_returns_body_and_last_modified():
    cl, _ = make(lambda r: httpx.Response(200, content=b"{}", headers={"Last-Modified": "Mon"}))
    r = cl.get("https://a.4cdn.org/boards.json")
    assert (r.status, r.body, r.last_modified) == (200, b"{}", "Mon")


def test_if_modified_since_sent_and_304():
    seen = {}

    def h(req):
        seen["ims"] = req.headers.get("If-Modified-Since")
        return httpx.Response(304)

    cl, _ = make(h)
    assert cl.get("https://x/a", "Mon").status == 304 and seen["ims"] == "Mon"


def test_404_raises_notfound_without_retry():
    calls = []
    cl, _ = make(lambda r: calls.append(1) or httpx.Response(404))
    with pytest.raises(NotFound):
        cl.get("https://x/a")
    assert len(calls) == 1


def test_5xx_retried_then_succeeds():
    seq = [503, 503, 200]
    cl, _ = make(lambda r: httpx.Response(seq.pop(0), content=b"ok"))
    assert cl.get("https://x/a").body == b"ok" and seq == []


def test_gives_up_after_bounded_retries():
    calls = []
    cl, _ = make(lambda r: calls.append(1) or httpx.Response(503), retries=3)
    with pytest.raises(ApiError):
        cl.get("https://x/a")
    assert len(calls) == 4


def test_network_error_is_retried_and_wrapped():
    def h(req): raise httpx.ConnectError("down")
    cl, _ = make(h, retries=1)
    with pytest.raises(ApiError):
        cl.get("https://x/a")


def test_rate_floor_one_second_between_requests():
    stamps = []
    cl, clock = make(lambda r: stamps.append(clock.now()) or httpx.Response(200, content=b""))
    for _ in range(3):
        cl.get("https://x/a")
    assert stamps[1] - stamps[0] >= 1.0 and stamps[2] - stamps[1] >= 1.0


def test_zero_interval_never_sleeps():
    cl, clock = make(lambda r: httpx.Response(200, content=b""), min_interval=0.0)
    for _ in range(3):
        cl.get("https://x/a")
    assert clock.now() == 0.0


def test_get_only_surface():
    public = sorted(n for n in dir(Client) if not n.startswith("_"))
    assert public == ["close", "get"]


def test_no_write_verbs_anywhere_in_src():
    src = pathlib.Path(__file__).parents[1] / "src"
    for f in src.rglob("*.py"):
        text = f.read_text().lower()
        for needle in (".post(", ".put(", ".delete(", ".patch(", 'method="post"', ".request("):
            assert needle not in text, f"{f.name} contains {needle}"


def test_bad_board_codes_rejected():
    for bad in ("../x", "G", "", "a/b", "x" * 11):
        with pytest.raises(ValueError):
            catalog_url(bad)
    assert thread_url("g", 123) == "https://a.4cdn.org/g/thread/123.json"
