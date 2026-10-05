"""Per-family translation of site JSON into the shared models. Pure: no I/O, no Qt."""
import html
import re

from . import api
from .models import (Attachment, Post, Thread, ThreadSummary, flatten_catalog)
from .parse import parse_comment, plain_text, references

BOARD_RE = re.compile(r"[a-z0-9_]{1,16}")
TIM_RE = re.compile(r"[A-Za-z0-9._-]{1,80}")
EXT_RE = re.compile(r"\.[A-Za-z0-9]{1,6}")
PATH_RE = re.compile(r"/[a-z0-9_]{1,16}/(?:src|thumb)/[A-Za-z0-9._-]{1,120}")
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".gif", ".webp")


def _int(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _text(v):
    return html.unescape(v) if isinstance(v, str) else ""


def _board(code):
    if not isinstance(code, str) or not BOARD_RE.fullmatch(code):
        raise ValueError(f"bad board code: {code!r}")
    return code


def thumb_exts(ext):
    ext = (ext or "").lower()
    order = ([ext, ".png", ".jpg", ".webp"] if ext in IMAGE_EXT else [".jpg", ".png", ".webp"])
    return list(dict.fromkeys(order))


class FourChan:
    def catalog_url(self, site, board): return api.catalog_url(board)
    def thread_url(self, site, board, no): return api.thread_url(board, no)

    def parse_catalog(self, site, board, data):
        return flatten_catalog(board, data, site.id)

    def parse_thread(self, site, board, no, data, last_modified=None):
        return Thread.from_api(board, no, data, last_modified, site.id)


class Vichan:
    """Classic vichan JSON: one file in the post, more in extra_files."""

    def catalog_url(self, site, board): return f"{site.base}/{_board(board)}/catalog.json"

    def thread_url(self, site, board, no): return f"{site.base}/{_board(board)}/res/{int(no)}.json"

    # -- files
    def _classic(self, site, board, d):
        if not isinstance(d, dict):
            return None
        tim, ext = d.get("tim"), d.get("ext")
        if tim is None or not isinstance(ext, str):
            return None
        tim = str(tim)
        if not TIM_RE.fullmatch(tim) or not EXT_RE.fullmatch(ext):
            return None
        base, exts = f"{site.base}/{board}", thumb_exts(ext)
        return Attachment(tim, _text(d.get("filename")), ext, _int(d.get("fsize")), _int(d.get("w")),
                          _int(d.get("h")), f"{base}/thumb/{tim}{exts[0]}", f"{base}/src/{tim}{ext}",
                          bool(d.get("spoiler")),
                          thumbnail_alts=tuple(f"{base}/thumb/{tim}{x}" for x in exts[1:]))

    def files(self, site, board, d):
        out = [self._classic(site, board, d)]
        extra = d.get("extra_files")
        if isinstance(extra, list):
            out += [self._classic(site, board, e) for e in extra]
        return tuple(a for a in out if a is not None)

    # -- catalog
    def parse_catalog(self, site, board, data):
        out = []
        for page in data:
            for t in page.get("threads", []) or []:
                out.append(self._summary(site, board, t))
        return out

    def _summary(self, site, board, t):
        real = t.get("board") if isinstance(t.get("board"), str) and BOARD_RE.fullmatch(t["board"]) else board
        created = _int(t.get("time"))
        files = self.files(site, real, t)
        return ThreadSummary(real, _int(t["no"]), _text(t.get("sub")),
                             plain_text(parse_comment(t.get("com") if isinstance(t.get("com"), str) else "")),
                             files[0] if files else None, _int(t.get("replies")), _int(t.get("images")),
                             created, _int(t.get("last_modified"), created), bool(_int(t.get("sticky"))),
                             bool(_int(t.get("locked"))), site.id)

    # -- thread
    def parse_thread(self, site, board, no, data, last_modified=None):
        posts, seen = [], {}
        for d in data["posts"]:
            posts.append(self._post(site, board, no, d, seen))
        return Thread(board, no, posts, last_modified, site.id)

    def _post(self, site, board, no, d, seen):
        com = d.get("com") if isinstance(d.get("com"), str) else ""
        thread_no = _int(d.get("resto")) or _int(d["no"])
        spans = parse_comment(com, (board, thread_no))
        name = _text(d.get("name")) or "Anonymous"
        if isinstance(d.get("trip"), str) and d["trip"]:
            name += " " + d["trip"]
        atts = []
        for a in self.files(site, board, d):
            n = seen.get(a.id, 0)
            seen[a.id] = n + 1
            atts.append(a if n == 0 else Attachment(**{**a.__dict__, "id": f"{a.id}~{n}"}))
        return Post(_int(d["no"]), thread_no, name, _text(d.get("sub")), com, plain_text(spans),
                    _int(d.get("time")), tuple(atts), references(spans, board, thread_no),
                    d.get("capcode") if isinstance(d.get("capcode"), str) else "", spans, site.id)


class VichanFiles(Vichan):
    """Leftypol-style JSON: a `files` list whose entries carry file_path/thumb_path."""

    def files(self, site, board, d):
        lst = d.get("files")
        if not isinstance(lst, list):
            return ()
        out = []
        for i, f in enumerate(lst):
            if not isinstance(f, dict):
                continue
            path, thumb = f.get("file_path"), f.get("thumb_path")
            if not (isinstance(path, str) and PATH_RE.fullmatch(path)):
                continue
            ext = f.get("ext")
            if not (isinstance(ext, str) and EXT_RE.fullmatch(ext)):
                ext = path[path.rfind("."):] if "." in path else ""
                if not EXT_RE.fullmatch(ext):
                    continue
            fid = str(f.get("id") or f.get("tim") or i)
            if not TIM_RE.fullmatch(fid):
                fid = str(i)
            turl = site.base + thumb if isinstance(thumb, str) and PATH_RE.fullmatch(thumb) else ""
            out.append(Attachment(fid, _text(f.get("filename")), ext, _int(f.get("fsize")), _int(f.get("w")),
                                  _int(f.get("h")), turl, site.base + path, bool(f.get("spoiler"))))
        return tuple(out)


ADAPTERS = {"4chan": FourChan(), "vichan": Vichan(), "vichan-files": VichanFiles()}


def adapter_for(site):
    return ADAPTERS[site.family]
