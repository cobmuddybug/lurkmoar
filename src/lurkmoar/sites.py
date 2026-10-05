"""Site registry: which imageboards LurkMoar can read, their boards, pacing and page-URL templates."""
import json
import re
from dataclasses import dataclass
from pathlib import Path

from .models import Board

SITES_JSON = Path(__file__).with_name("sites.json")
VALID_BOARD = re.compile(r"[a-z0-9_]{1,16}")
VALID_4CHAN = re.compile(r"[a-z0-9]{1,10}")
DEFAULT_THREAD_URL = "{base}/{board}/res/{no}.html#{post}"


@dataclass(frozen=True)
class Site:
    id: str
    name: str
    base: str
    family: str
    order: int
    boards: tuple = ()
    json_interval: float = 1.0
    media_interval: float = 0.35
    thread_url: str = DEFAULT_THREAD_URL

    def page_url(self, board, no, post=None):
        url = self.thread_url.format(base=self.base, board=board, no=no, post=post if post else "")
        return url if post else url.split("#")[0]


FOURCHAN = Site("4chan", "4chan", "https://boards.4chan.org", "4chan", 0, (), 1.0, 0.05,
                "{base}/{board}/thread/{no}#p{post}")


def valid_board(site, code) -> bool:
    rule = VALID_4CHAN if site.id == "4chan" else VALID_BOARD
    return isinstance(code, str) and bool(rule.fullmatch(code))


def key(site, kind, *parts) -> str:
    """Cache key. 4chan keys keep their original shape so existing caches stay valid."""
    head = [] if site == "4chan" else [site]
    return ":".join(head + [kind, *map(str, parts)])


def load_sites(extra_boards=None, hidden=(), path=SITES_JSON) -> dict:
    sites = {"4chan": FOURCHAN}
    try:
        raw = json.loads(Path(path).read_text())["sites"]
        for e in raw:
            site = Site(e["id"], e["name"], e["base"].rstrip("/"), e["family"], int(e.get("order", 100)),
                        (), float(e.get("json_interval", 1.0)), float(e.get("media_interval", 0.35)),
                        e.get("thread_url", DEFAULT_THREAD_URL))
            boards = [Board(c, "", True, 0) for c in e.get("boards", []) if valid_board(site, c)]
            sites[site.id] = Site(**{**site.__dict__, "boards": tuple(boards)})
    except (OSError, ValueError, KeyError, TypeError):
        return {"4chan": FOURCHAN}
    for sid, codes in (extra_boards or {}).items():
        site = sites.get(sid)
        if site is None or sid == "4chan" or not isinstance(codes, (list, tuple)):
            continue
        have = {b.code for b in site.boards}
        added = []
        for c in codes:
            if valid_board(site, c) and c not in have:
                have.add(c)
                added.append(Board(c, "", True, 0))
        sites[sid] = Site(**{**site.__dict__, "boards": site.boards + tuple(added)})
    for sid in hidden:
        sites.pop(sid, None)
    return dict(sorted(sites.items(), key=lambda kv: (kv[1].order, kv[1].name)))
