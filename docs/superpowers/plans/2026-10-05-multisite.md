# LurkMoar Multi-Site (vichan family) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Read 4chan plus six verified vichan-family sites (Wizchan, Lainchan, Leftypol, Sushichan, Kissu, Uboachan) from LurkMoar, with favourites grouped by site in the left rail.

**Architecture:** A site registry (`sites.py` + `sites.json`) and one pure adapter per JSON family (`adapters.py`) turn site JSON into the existing models. `site` becomes the first argument wherever a board is named (Repo, DB, UI). Models gain `site` (trailing, default `"4chan"`) and multi-attachment posts. The DB migrates to schema v2 keeping all data. Everything stays read-only and offline-tested with synthetic fixtures.

**Tech Stack:** Python, PySide6, httpx, stdlib sqlite3, pytest (unchanged).

**Spec:** `docs/superpowers/specs/2026-10-05-multisite-vichan-design.md` (builds on `2026-10-03-lurkmoar-design.md`).

## Global Constraints

- Dependencies: only `PySide6` and `httpx`. Read-only: `api.Client` exposes `get()` and `close()` only; no write verbs anywhere in `src/` (the existing grep test keeps guarding this).
- Only `api.py` imports httpx. Layering: UI → `repo` → `adapters`/`api`.
- JSON request spacing per site host: `json_interval` (default 1.0 s). Media/thumbnails on the same host: `media_interval` (default 0.35 s). 4chan keeps `1.0` and `0.05`. Same cache key never refetched within 10 s.
- Non-4chan board codes match `[a-z0-9_]{1,16}`; 4chan keeps `[a-z0-9]{1,10}`. `tim` matches `[A-Za-z0-9._-]{1,80}`, extensions `\.[A-Za-z0-9]{1,6}`, files-list paths `/[a-z0-9_]{1,16}/(src|thumb)/[A-Za-z0-9._-]{1,120}`. Anything else is dropped, never built into a URL.
- Cache keys: 4chan keys unchanged (`catalog:g`, `thread:g:123`, `boards`); other sites prefixed `{site}:` (`lainchan:catalog:sec`). Built only through `sites.key(site, kind, *parts)`.
- `site` is the first positional argument wherever a board is named (Repo, DB, UI). Models take `site` as a trailing keyword defaulting to `"4chan"`.
- Every commit ends with the trailer `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` (pass it as a second `-m`).
- Tests are offline (`FakeApi`, `FakeCdn`, synthetic fixtures); never hit real sites from automated tests. Run with `QT_QPA_PLATFORM=offscreen` as `conftest.py` sets. Offscreen windows are never "active": observe focus with `win.focusWidget()`, and use `QAbstractItemView.PositionAtTop` (not `list.PositionAtTop`).
- About text: "LurkMoar is an independent read-only client. Content is sourced from the sites you open and belongs to them. Not affiliated with or endorsed by any of them."

## Review Focus

1. Hostile site JSON: `tim`/`ext`/`file_path`/`thumb_path` containing `../`, `//evil.example/`, schemes or whitespace must never yield a URL off the site's own host and board path; the attachment is dropped. (Task 3)
2. Sparse or odd vichan JSON: missing `tim`/`files`, `extra_files` not a list, `files: []`, flags as int/bool/str, a catalog that is flat or not a list, duplicate attachment ids in one thread. Must not raise (a wrong shape is the existing "bad response" error). (Task 3)
3. Thumbnail extension guessing: first candidate 404s → next candidate; all fail → failed once (no retry storm); the winning extension is remembered per site+board. (Task 5)
4. Migration of a real v1 database: bookmarks, favourites, nav, recents and cache survive; re-running is a no-op; a backup file exists; the old `last_view` format still restores. (Tasks 4, 6)
5. Site isolation: the same board code and thread number on two sites never collide in cache, bookmarks, nav, favourites, media files or thumbnails; one failing site does not affect another. (Tasks 4, 5, 6)

## File Structure

```
src/lurkmoar/
  sites.py        Site, load_sites, key()           (new)
  sites.json      shipped registry                  (new)
  adapters.py     FourChan, Vichan, VichanFiles     (new)
  config.py       + extra_boards, hidden_sites
  models.py       + site, Post.attachments, Attachment.thumbnail_alts
  parse.py        + vichan quote forms, span classes, ctx references
  api.py          + build_clients(sites)
  db.py           schema v2 + site-aware methods
  repo.py         Core/Repo/ThumbLoader site-aware
  main.py ui_catalog.py ui_thread.py ui_misc.py ui_media.py   site plumbing + rail/picker grouping
tests/ samples_vichan.py test_sites.py test_adapters.py test_multisite.py + updated existing tests
```

---

### Task 1: Site registry, config and cache keys

**Files:**
- Create: `src/lurkmoar/sites.py`, `src/lurkmoar/sites.json`, `tests/test_sites.py`
- Modify: `src/lurkmoar/config.py`, `tests/test_config.py`

**Interfaces:**
- Produces: `sites.Site` (frozen: `id, name, base, family, order, boards: tuple[models.Board, ...], json_interval=1.0, media_interval=0.35, thread_url`; method `page_url(board, no, post=None) -> str`), `sites.FOURCHAN`, `sites.load_sites(extra_boards=None, hidden=(), path=SITES_JSON) -> dict[str, Site]` (ordered: 4chan first, then `order`, then name), `sites.valid_board(site, code) -> bool`, `sites.key(site, kind, *parts) -> str`. `Config.extra_boards: dict`, `Config.hidden_sites: list`.

- [ ] **Step 1: Write the failing tests**

`tests/test_sites.py`:

```python
import json

from lurkmoar.sites import FOURCHAN, key, load_sites, valid_board


def test_registry_order_and_ids():
    s = load_sites()
    assert list(s) == ["4chan", "kissu", "lainchan", "leftypol", "sushichan", "uboachan", "wizchan"]
    assert s["4chan"] is FOURCHAN or s["4chan"] == FOURCHAN
    assert s["leftypol"].family == "vichan-files" and s["lainchan"].family == "vichan"


def test_shipped_boards_are_valid_and_present():
    s = load_sites()
    assert {"sec", "inter", "lit"} <= {b.code for b in s["lainchan"].boards}
    assert {"b", "jp"} <= {b.code for b in s["kissu"].boards}
    assert {"yn", "yndd", "ot"} <= {b.code for b in s["uboachan"].boards}
    assert "overboard" in {b.code for b in s["leftypol"].boards}
    for site in s.values():
        assert all(valid_board(site, b.code) for b in site.boards)


def test_page_url_templates():
    s = load_sites()
    assert s["4chan"].page_url("g", 5, 7) == "https://boards.4chan.org/g/thread/5#p7"
    assert s["4chan"].page_url("g", 5) == "https://boards.4chan.org/g/thread/5"
    assert s["lainchan"].page_url("sec", 5, 7) == "https://lainchan.org/sec/res/5.html#7"
    assert s["lainchan"].page_url("sec", 5) == "https://lainchan.org/sec/res/5.html"
    assert s["kissu"].page_url("b", 5, 7) == "https://kissu.moe/b/res/5#7"


def test_extra_boards_merge_validate_and_dedupe():
    s = load_sites(extra_boards={"kissu": ["qa", "b", "BAD CODE", "../x", "a" * 20], "nosuch": ["x"],
                                 "4chan": ["zz"]})
    codes = [b.code for b in s["kissu"].boards]
    assert "qa" in codes and codes.count("b") == 1
    assert not any(c in codes for c in ("BAD CODE", "../x"))
    assert s["4chan"].boards == ()                       # 4chan's list comes from boards.json only


def test_hidden_sites_removed():
    s = load_sites(hidden=["wizchan", "nosuch"])
    assert "wizchan" not in s and "lainchan" in s


def test_bad_registry_file_falls_back_to_4chan_only(tmp_path):
    f = tmp_path / "s.json"
    f.write_text("{nope")
    assert list(load_sites(path=f)) == ["4chan"]


def test_valid_board_rules():
    s = load_sites()
    assert valid_board(s["lainchan"], "sec") and valid_board(s["lainchan"], "a_b")
    assert not valid_board(s["lainchan"], "Sec") and not valid_board(s["lainchan"], "a/b")
    assert valid_board(s["4chan"], "g") and not valid_board(s["4chan"], "a_b")


def test_cache_keys_keep_4chan_unchanged():
    assert key("4chan", "boards") == "boards"
    assert key("4chan", "catalog", "g") == "catalog:g"
    assert key("4chan", "thread", "g", 12) == "thread:g:12"
    assert key("lainchan", "catalog", "sec") == "lainchan:catalog:sec"
    assert key("lainchan", "thread", "sec", 12) == "lainchan:thread:sec:12"
```

Append to `tests/test_config.py`:

```python
def test_site_config_fields():
    p = paths()
    p.config_file.write_text('{"extra_boards": {"kissu": ["qa"]}, "hidden_sites": ["wizchan"]}')
    cfg = load_config(p)
    assert cfg.extra_boards == {"kissu": ["qa"]} and cfg.hidden_sites == ["wizchan"]
    p.config_file.write_text('{"extra_boards": ["wrong type"], "hidden_sites": "nope"}')
    cfg = load_config(p)
    assert cfg.extra_boards == {} and cfg.hidden_sites == []
```

- [ ] **Step 2: Run to verify failure**

Run: `cd ~/Projects/lurkmoar && .venv/bin/pytest tests/test_sites.py tests/test_config.py -q`
Expected: `ModuleNotFoundError: lurkmoar.sites` and the config test failing on missing attributes.

- [ ] **Step 3: Implement `config.py` fields**

In `config.py` change the import to `from dataclasses import asdict, dataclass, field, fields` and add to `Config` (after `save_dir`):

```python
    extra_boards: dict = field(default_factory=dict)
    hidden_sites: list = field(default_factory=list)
```
(`load_config`'s existing `type(v) is type(getattr(cfg, f.name))` check already rejects wrong types.)

- [ ] **Step 4: Create `src/lurkmoar/sites.json`**

```json
{"sites": [
  {"id": "kissu", "name": "Kissu", "base": "https://kissu.moe", "family": "vichan", "order": 10,
   "thread_url": "{base}/{board}/res/{no}#{post}", "boards": ["b", "jp"]},
  {"id": "lainchan", "name": "Lainchan", "base": "https://lainchan.org", "family": "vichan", "order": 20,
   "boards": ["sec", "inter", "lit", "music", "vis", "hum", "drug", "zzz", "layer", "q", "r", "culture", "psy", "mega", "random", "zine"]},
  {"id": "leftypol", "name": "Leftypol", "base": "https://leftypol.org", "family": "vichan-files", "order": 30,
   "boards": ["overboard", "sfw", "alt", "leftypol", "edu", "labor", "siberia", "lgbt", "latam", "hobby", "tech", "games", "anime", "music", "draw", "ufo", "420", "meta"]},
  {"id": "sushichan", "name": "Sushichan", "base": "https://sushigirl.us", "family": "vichan", "order": 40,
   "boards": ["lounge", "yakuza", "arcade", "kawaii", "kitchen", "tunes", "culture", "silicon", "otaku", "hell", "chat"]},
  {"id": "uboachan", "name": "Uboachan", "base": "https://uboachan.net", "family": "vichan", "order": 50,
   "boards": ["yn", "yndd", "ot", "n", "o"]},
  {"id": "wizchan", "name": "Wizchan", "base": "https://wizchan.org", "family": "vichan", "order": 60,
   "boards": ["wiz", "dep", "hob", "lounge", "jp", "meta", "games", "music", "all"]}
]}
```

- [ ] **Step 5: Implement `sites.py`**

```python
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
```

- [ ] **Step 6: Run tests**

Run: `cd ~/Projects/lurkmoar && .venv/bin/pytest -q`
Expected: all PASS (the new sites/config tests plus the existing suite).

- [ ] **Step 7: Commit**

```bash
cd ~/Projects/lurkmoar && git add -A && git commit -q -m "feat: site registry, config fields and cache keys" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Parser: vichan quote links, span classes, context references

**Files:**
- Modify: `src/lurkmoar/parse.py`
- Test: `tests/test_parse.py`

**Interfaces:**
- Produces: `parse.parse_comment(html, ctx=None)` (`ctx = (board, thread)` optional, accepted for forward use), `parse.quote_target(href) -> (board|None, thread|None, post) | None` accepting `#p12`, `#12`, `/v/thread/55#p56`, `/b/res/5.html#12`, `/b/res/5#12`; `parse.references(spans, board=None, thread=None) -> tuple[int, ...]` (same-thread posts only; with a context, `/board/res/T#P` counts when board and thread equal the context).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_parse.py`)

```python
def test_quote_target_vichan_forms():
    assert quote_target("#12") == (None, None, 12)
    assert quote_target("/b/res/5.html#12") == ("b", 5, 12)
    assert quote_target("/b/res/5#12") == ("b", 5, 12)
    assert quote_target("/v/thread/55#p56") == ("v", 55, 56)
    assert quote_target("https://x.example/b/res/5.html#12") is None


def test_vichan_quote_link_without_class_is_a_quote():
    s = parse_comment('<a onclick="highlightReply(\'12\', event);" href="/sec/res/5.html#12">&gt;&gt;12</a> hi')
    assert s[0].styles == {"quote"} and s[0].target == "/sec/res/5.html#12"
    assert references(s, "sec", 5) == (12,)


def test_cross_board_and_cross_thread_vichan_quotes_are_not_references():
    s = parse_comment('<a href="/qa/res/9#4">x</a><a href="/sec/res/6.html#3">y</a><a href="/sec/res/5.html#2">z</a>')
    assert references(s, "sec", 5) == (2,)
    assert [x.styles for x in s] == [{"quote"}] * 3


def test_external_links_with_fragments_stay_links():
    s = parse_comment('<a href="https://archive.example/x#12">x</a>')
    assert s[0].styles == {"link"}


def test_vichan_span_classes():
    s = parse_comment('<span class="quote">&gt;g</span><span class="orangeQuote">&lt;o</span>'
                      '<span class="spoiler">sp</span><span class="heading">h</span><strike>st</strike>'
                      '<span class="yen">y</span>')
    assert [x.styles for x in s] == [{"greentext"}, {"greentext"}, {"spoiler"}, {"b"}, {"spoiler"}, frozenset()] or \
        [x.styles for x in s] == [{"greentext"}, {"spoiler"}, {"b"}, {"spoiler"}, frozenset()]


def test_vichan_markup_flattens_safely():
    s = parse_comment("a<wbr>b<details><summary>s</summary>d</details><ol><li>1</li></ol>")
    assert plain_text(s) == "absd1"
```

(The `or` in `test_vichan_span_classes` is deliberate: adjacent spans with identical styles merge, so the first two greentext spans merge into one.)

- [ ] **Step 2: Run to verify failure**

Run: `cd ~/Projects/lurkmoar && .venv/bin/pytest tests/test_parse.py -q`
Expected: FAIL (`quote_target` returns `None` for the new forms; `references` takes no context).

- [ ] **Step 3: Implement**

In `parse.py`:

1. Replace `QUOTE_RE` with `QUOTE_RE = re.compile(r"(?:/(\w+)/(?:thread|res)/(\d+)(?:\.html)?)?#p?(\d+)")`.
2. In `_Parser.handle_starttag`, replace the `a` branch with:

```python
        elif tag == "a":
            href = a.get("href") or ""
            if "quotelink" in cls or (href[:1] in ("#", "/") and QUOTE_RE.fullmatch(href)):
                s, t = {"quote"}, href
            elif href.startswith(("http://", "https://")):
                s, t = {"link"}, href
```
3. Replace the `span` branch and the `s`/`strike` handling:

```python
        elif tag == "span":
            if "deadlink" in cls: s = {"quote"}
            elif "spoiler" in cls: s = {"spoiler"}
            elif "heading" in cls: s = {"b"}
            elif "orangeQuote" in cls or "quote" in cls: s = {"greentext"}
```
and change `elif tag == "s": s = {"spoiler"}` to `elif tag in ("s", "strike"): s = {"spoiler"}`.
4. Change `parse_comment` to `def parse_comment(html: str, ctx=None) -> tuple[Span, ...]:` (ctx is accepted and reserved; the body is unchanged).
5. Replace `references`:

```python
def references(spans, board=None, thread=None) -> tuple[int, ...]:
    out: list[int] = []
    for s in spans:
        if "quote" in s.styles and s.target:
            q = quote_target(s.target)
            if not q:
                continue
            qb, qt, qp = q
            same = (qb is None) or (board is not None and qb == board and qt == thread)
            if same and qp not in out:
                out.append(qp)
    return tuple(out)
```
Note: with no context, the old 4chan behaviour is preserved (`qb is None` only).

- [ ] **Step 4: Run all tests**

Run: `cd ~/Projects/lurkmoar && .venv/bin/pytest -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/Projects/lurkmoar && git add -A && git commit -q -m "feat: parse vichan quote links and span classes" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Models and adapters

**Files:**
- Create: `src/lurkmoar/adapters.py`, `tests/samples_vichan.py`, `tests/test_adapters.py`
- Modify: `src/lurkmoar/models.py`, `tests/test_models.py`

**Interfaces:**
- Consumes: `sites.Site`, `parse.parse_comment/plain_text/references`.
- Produces: `models.Attachment(..., deleted=False, thumbnail_alts=())`; `models.Post(..., attachments: tuple, references, capcode, spans, site="4chan")` with property `attachment`; `models.ThreadSummary(..., site="4chan")`, `models.Thread(board, number, posts, last_modified=None, site="4chan")` with `images` counting every live attachment. `adapters.adapter_for(site) -> Adapter` with `catalog_url(site, board)`, `thread_url(site, board, no)`, `parse_catalog(site, board, data) -> list[ThreadSummary]`, `parse_thread(site, board, no, data, last_modified=None) -> Thread`; `adapters.thumb_exts(ext) -> list[str]`.

- [ ] **Step 1: Write sample payloads**

`tests/samples_vichan.py`:

```python
"""Synthetic payloads shaped like the structure probes of the vichan-family sites. No real content."""

VICHAN_CATALOG = [
    {"page": 0, "threads": [
        {"no": 10, "sub": "First &amp; thread", "com": "hello<br>world", "name": "Anonymous", "time": 1000,
         "last_modified": 2000, "replies": 4, "images": 2, "sticky": 1, "locked": 0, "cyclical": "0",
         "tn_w": 200, "tn_h": 100, "w": 800, "h": 400, "fsize": 5000, "filename": "pic", "ext": ".jpg",
         "tim": "1700000000000", "md5": "x", "resto": 0},
        {"no": 11, "com": "no file", "name": "Anonymous", "time": 1100, "replies": 0, "images": 0,
         "sticky": 0, "locked": 1, "resto": 0},
    ]},
    {"page": 1, "threads": [
        {"no": 12, "sub": "Video", "com": "clip", "time": 900, "last_modified": 3000, "replies": 9,
         "images": 3, "ext": ".webm", "tim": "1700000000001-9", "filename": "v", "w": 640, "h": 360,
         "fsize": 99999, "resto": 0},
    ]},
]

VICHAN_THREAD = {"posts": [
    {"no": 10, "resto": 0, "sub": "First", "com": "OP text", "name": "Anonymous", "time": 1000,
     "tim": "1700000000000", "ext": ".jpg", "filename": "pic", "w": 800, "h": 400, "fsize": 5000,
     "tn_w": 200, "tn_h": 100, "md5": "x"},
    {"no": 11, "resto": 10, "name": "Anonymous", "time": 1010,
     "com": "<a onclick=\"highlightReply('10', event);\" href=\"/sec/res/10.html#10\">&gt;&gt;10</a><br>reply"},
    {"no": 12, "resto": 10, "name": "Anon", "trip": "!abc", "capcode": "Admin", "time": 1020,
     "com": "<span class=\"quote\">&gt;green</span>", "tim": "1700000000002-1", "ext": ".png",
     "filename": "a", "w": 10, "h": 10, "fsize": 99,
     "extra_files": [{"tim": "1700000000002-2", "ext": ".gif", "filename": "b", "w": 5, "h": 5, "fsize": 9},
                     {"tim": "1700000000002-3", "ext": ".webm", "filename": "c", "w": 6, "h": 6, "fsize": 8}]},
]}

FILES_CATALOG = [
    {"page": 0, "threads": [
        {"no": 20, "sub": "Files thread", "com": "text", "name": "Anonymous", "time": 1000, "last_modified": 2000,
         "replies": 3, "images": 1, "sticky": 0, "locked": 0, "board": "alt",
         "files": [{"id": "f1", "mime": "image/jpeg", "ext": ".jpg", "w": 10, "h": 10, "fsize": 100,
                    "filename": "p", "tim": "1700000000010-6", "spoiler": False, "md5": "m",
                    "file_path": "/alt/src/1700000000010-6.jpg", "thumb_path": "/alt/thumb/1700000000010-6.webp"}],
         "resto": 0},
        {"no": 21, "com": "no files", "time": 1100, "replies": 0, "images": 0, "board": "leftypol",
         "files": [], "resto": 0},
    ]},
]

FILES_THREAD = {"posts": [
    {"no": 20, "resto": 0, "sub": "Files thread", "com": "OP", "name": "Anonymous", "time": 1000,
     "board": "alt",
     "files": [{"id": "f1", "ext": ".jpg", "w": 10, "h": 10, "fsize": 100, "filename": "p", "spoiler": True,
                "tim": "1700000000010-6", "file_path": "/alt/src/1700000000010-6.jpg",
                "thumb_path": "/alt/thumb/1700000000010-6.webp"},
               {"id": "f2", "ext": ".mp4", "w": 20, "h": 20, "fsize": 200, "filename": "q",
                "tim": "1700000000010-7", "file_path": "/alt/src/1700000000010-7.mp4",
                "thumb_path": "/alt/thumb/1700000000010-7.webp"}]},
    {"no": 21, "resto": 20, "name": "Anonymous", "time": 1010, "com": "reply", "files": []},
]}
```

- [ ] **Step 2: Write failing adapter and model tests**

`tests/test_adapters.py`:

```python
import pytest

from lurkmoar.adapters import adapter_for, thumb_exts
from lurkmoar.sites import load_sites
from samples_vichan import FILES_CATALOG, FILES_THREAD, VICHAN_CATALOG, VICHAN_THREAD

S = load_sites()
LAIN, LEFT, KISSU = S["lainchan"], S["leftypol"], S["kissu"]


def test_urls_and_validation():
    a = adapter_for(LAIN)
    assert a.catalog_url(LAIN, "sec") == "https://lainchan.org/sec/catalog.json"
    assert a.thread_url(LAIN, "sec", 10) == "https://lainchan.org/sec/res/10.json"
    for bad in ("../x", "A", "", "a/b", "x" * 17, "a b"):
        with pytest.raises(ValueError):
            a.catalog_url(LAIN, bad)
    with pytest.raises(ValueError):
        a.thread_url(LAIN, "sec", "1/../2")


def test_thumb_exts_order():
    assert thumb_exts(".jpg") == [".jpg", ".png", ".webp"]
    assert thumb_exts(".png") == [".png", ".jpg", ".webp"]
    assert thumb_exts(".webm") == [".jpg", ".png", ".webp"]
    assert thumb_exts(".MP4") == [".jpg", ".png", ".webp"]


def test_classic_catalog_mapping():
    ts = adapter_for(LAIN).parse_catalog(LAIN, "sec", VICHAN_CATALOG)
    assert [t.number for t in ts] == [10, 11, 12]
    t = ts[0]
    assert t.site == "lainchan" and t.board == "sec" and t.subject == "First & thread"
    assert t.comment == "hello\nworld" and t.sticky and not t.closed and t.replies == 4
    assert t.thumbnail.original_url == "https://lainchan.org/sec/src/1700000000000.jpg"
    assert t.thumbnail.thumbnail_url == "https://lainchan.org/sec/thumb/1700000000000.jpg"
    assert t.thumbnail.thumbnail_alts == ("https://lainchan.org/sec/thumb/1700000000000.png",
                                          "https://lainchan.org/sec/thumb/1700000000000.webp")
    assert ts[1].thumbnail is None and ts[1].closed
    assert ts[2].thumbnail.extension == ".webm" and ts[2].thumbnail.id == "1700000000001-9"


def test_classic_thread_mapping_with_extra_files_and_context_references():
    th = adapter_for(LAIN).parse_thread(LAIN, "sec", 10, VICHAN_THREAD, "Mon")
    assert th.site == "lainchan" and th.number == 10 and th.last_modified == "Mon"
    op, p11, p12 = th.posts
    assert op.thread_number == 10 and op.attachment.id == "1700000000000"
    assert p11.references == (10,) and p11.comment_plain == ">>10\nreply"
    assert p12.name == "Anon !abc" and p12.capcode == "Admin"
    assert [a.id for a in p12.attachments] == ["1700000000002-1", "1700000000002-2", "1700000000002-3"]
    assert [a.extension for a in p12.attachments] == [".png", ".gif", ".webm"]
    assert th.images == 4 and th.replies == 2


def test_kissu_style_quote_without_html_suffix_resolves():
    data = {"posts": [{"no": 5, "resto": 0, "time": 1, "com": "op"},
                      {"no": 6, "resto": 5, "time": 2, "com": '<a href="/b/res/5#5">&gt;&gt;5</a>'}]}
    th = adapter_for(KISSU).parse_thread(KISSU, "b", 5, data)
    assert th.posts[1].references == (5,)


def test_files_family_catalog_and_thread():
    a = adapter_for(LEFT)
    ts = a.parse_catalog(LEFT, "leftypol", FILES_CATALOG)
    assert ts[0].board == "alt"                      # overboard threads carry their real board
    assert ts[0].thumbnail.original_url == "https://leftypol.org/alt/src/1700000000010-6.jpg"
    assert ts[0].thumbnail.thumbnail_url == "https://leftypol.org/alt/thumb/1700000000010-6.webp"
    assert ts[0].thumbnail.thumbnail_alts == () and ts[1].thumbnail is None and ts[1].board == "leftypol"
    th = a.parse_thread(LEFT, "alt", 20, FILES_THREAD)
    assert [x.id for x in th.posts[0].attachments] == ["f1", "f2"]
    assert th.posts[0].attachments[0].spoiler and th.posts[0].attachments[1].extension == ".mp4"
    assert th.posts[1].attachment is None


@pytest.mark.parametrize("tim,ext", [("../../etc/passwd", ".jpg"), ("1/../2", ".jpg"), ("a b", ".jpg"),
                                      ("12345", ".jpg/../x"), ("12345", "jpg"), ("12345", ".verylongext"),
                                      ("//evil.example/x", ".jpg"), ("12345", None), (None, ".jpg")])
def test_hostile_classic_file_fields_drop_the_attachment(tim, ext):
    d = {"posts": [{"no": 1, "resto": 0, "time": 1, "com": "x", "tim": tim, "ext": ext, "filename": "f"}]}
    th = adapter_for(LAIN).parse_thread(LAIN, "sec", 1, d)
    assert th.posts[0].attachments == ()


@pytest.mark.parametrize("path,thumb", [("//evil.example/a.jpg", "/a/thumb/x.jpg"), ("https://evil.example/a.jpg", "/a/thumb/x.jpg"),
                                         ("/a/src/../../x.jpg", "/a/thumb/x.jpg"), ("/a/other/x.jpg", "/a/thumb/x.jpg"),
                                         ("/a/src/x y.jpg", "/a/thumb/x.jpg"), (None, "/a/thumb/x.jpg")])
def test_hostile_file_paths_drop_the_attachment(path, thumb):
    d = {"posts": [{"no": 1, "resto": 0, "time": 1, "com": "x",
                    "files": [{"id": "f", "ext": ".jpg", "file_path": path, "thumb_path": thumb}]}]}
    assert adapter_for(LEFT).parse_thread(LEFT, "alt", 1, d).posts[0].attachments == ()


def test_hostile_thumb_path_keeps_file_but_blanks_thumbnail():
    d = {"posts": [{"no": 1, "resto": 0, "time": 1, "com": "x",
                    "files": [{"id": "f", "ext": ".jpg", "file_path": "/a/src/x.jpg", "thumb_path": "//evil.example/t.jpg"}]}]}
    att = adapter_for(LEFT).parse_thread(LEFT, "alt", 1, d).posts[0].attachment
    assert att.original_url == "https://leftypol.org/a/src/x.jpg" and att.thumbnail_url == ""


def test_sparse_and_odd_shapes_do_not_raise():
    a = adapter_for(LAIN)
    d = {"posts": [{"no": 1, "time": 1},
                   {"no": 2, "resto": 1, "extra_files": "nope", "sticky": "1", "com": None, "name": None},
                   {"no": 3, "resto": 1, "extra_files": [None, 5, {"tim": "9", "ext": ".png"}], "tim": "8", "ext": ".jpg"}]}
    th = a.parse_thread(LAIN, "sec", 1, d)
    assert th.posts[0].comment_plain == "" and th.posts[1].name == "Anonymous"
    assert [x.id for x in th.posts[2].attachments] == ["8", "9"]
    assert a.parse_catalog(LAIN, "sec", [{"page": 0}]) == []
    assert a.parse_catalog(LAIN, "sec", [{"page": 0, "threads": [{"no": 1, "sticky": True, "locked": "1"}]}])[0].closed
    with pytest.raises((TypeError, AttributeError)):
        a.parse_catalog(LAIN, "sec", {"not": "a list"})


def test_duplicate_attachment_ids_are_disambiguated():
    d = {"posts": [{"no": 1, "resto": 0, "time": 1, "tim": "7", "ext": ".jpg"},
                   {"no": 2, "resto": 1, "time": 2, "tim": "7", "ext": ".jpg"}]}
    th = adapter_for(LAIN).parse_thread(LAIN, "sec", 1, d)
    ids = [p.attachment.id for p in th.posts]
    assert len(set(ids)) == 2 and ids[0] == "7"


def test_fourchan_adapter_matches_existing_models():
    from samples import CATALOG, THREAD
    s = S["4chan"]
    a = adapter_for(s)
    assert a.catalog_url(s, "g") == "https://a.4cdn.org/g/catalog.json"
    assert a.thread_url(s, "g", 100) == "https://a.4cdn.org/g/thread/100.json"
    ts = a.parse_catalog(s, "g", CATALOG)
    assert [t.number for t in ts] == [100, 101, 102] and ts[0].site == "4chan"
    th = a.parse_thread(s, "g", 100, THREAD)
    assert th.site == "4chan" and len(th.posts) == 4
```

Append to `tests/test_models.py`:

```python
def test_post_attachment_property_and_images_count():
    from lurkmoar.models import Attachment
    a = Attachment("1", "f", ".jpg", 1, 1, 1, "t", "o", False)
    d = Attachment(0, "", "", 0, 0, 0, "", "", False, deleted=True)
    from lurkmoar.models import Post, Thread
    p = Post(1, 1, "n", "", "", "", 0, (a, d), (), "", ())
    q = Post(2, 1, "n", "", "", "", 0, (), (), "", ())
    assert p.attachment is a and q.attachment is None
    assert Thread("g", 1, [p, q]).images == 1
    assert Post.from_api("g", {"no": 3, "time": 1}).site == "4chan"
```

- [ ] **Step 3: Run to verify failure**

Run: `cd ~/Projects/lurkmoar && .venv/bin/pytest tests/test_adapters.py tests/test_models.py -q`
Expected: `ModuleNotFoundError: lurkmoar.adapters` and the model test failing.

- [ ] **Step 4: Update `models.py`**

1. `Attachment`: add as last field `thumbnail_alts: tuple = ()` (after `deleted`).
2. `ThreadSummary`: add last field `site: str = "4chan"`; `from_api(cls, board, d, site="4chan")` passes `site=site`; `flatten_catalog(board, pages, site="4chan")` passes it through.
3. `Post`: rename field `attachment` to `attachments: tuple` (same position), add last field `site: str = "4chan"`, and add:

```python
    @property
    def attachment(self):
        return self.attachments[0] if self.attachments else None
```
`Post.from_api(cls, board, d, site="4chan")`: build `att = attachment_from_api(board, d)`, `thread_no = d.get("resto") or d["no"]`, `spans = parse_comment(d.get("com", ""), (board, thread_no))`, `attachments=(att,) if att else ()`, `references=references(spans, board, thread_no)`, `site=site`.
4. `Thread`: add last field `site: str = "4chan"`; `from_api(cls, board, number, data, last_modified=None, site="4chan")` passes `site` to each `Post.from_api` and to the constructor; `images` becomes `sum(1 for p in self.posts for a in p.attachments if not a.deleted)`.

- [ ] **Step 5: Implement `adapters.py`**

```python
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
```

- [ ] **Step 6: Run all tests**

Run: `cd ~/Projects/lurkmoar && .venv/bin/pytest -q`
Expected: all PASS. If existing UI code still reads `post.attachment` it keeps working (property); anything constructing `Post(...)` positionally must be updated (only `Post.from_api` does).

- [ ] **Step 7: Commit**

```bash
cd ~/Projects/lurkmoar && git add -A && git commit -q -m "feat: multi-attachment models and vichan-family adapters" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Database schema v2 (site-aware, migrating)

**Files:**
- Modify: `src/lurkmoar/db.py` (rewrite), `tests/test_db.py`, `tests/test_persistence.py` (call sites only)
- Test: `tests/test_db.py`

**Interfaces:**
- Produces (all `site` first): `DB.bookmark_add(site, board, thread_id, subject, replies)`, `bookmark_remove(site, board, thread_id)`, `bookmark_has(site, board, thread_id)`, `bookmarks() -> list[Bookmark]` (`Bookmark.site: str = "4chan"` as last field), `bookmarks_observe(site, board, replies)`, `bookmark_latest(site, board, thread_id, replies)`, `bookmark_expire(site, board, thread_id)`, `bookmark_seen(site, board, thread_id, replies, last_post)`, `fav_boards() -> list[tuple[site, board]]` (favourite order), `fav_toggle(site, board) -> bool`, `nav_get(site, board)`, `nav_set(site, board, **fields)`, `recent_add(site, board, thread_id, subject, now=None)`, `recent(limit=20) -> list[tuple[site, board, thread_id, subject]]`. `cache_*`, `kv_*` unchanged. `DB(path)` migrates a v1 file in place, after writing `<path>.v1.bak`.

- [ ] **Step 1: Mechanically update existing call sites in tests**

Run this once; it inserts `"4chan", ` before a literal board argument in every site-aware DB call:

```bash
cd ~/Projects/lurkmoar && python3 - <<'EOF'
import re, pathlib
pat = re.compile(r'(\.(?:bookmark_add|bookmark_remove|bookmark_has|bookmark_expire|bookmark_latest|bookmark_seen|'
                 r'bookmarks_observe|nav_get|nav_set|recent_add|fav_toggle)\()("[a-z]+")')
for f in pathlib.Path("tests").glob("test_*.py"):
    s = f.read_text(); n = pat.sub(r'\1"4chan", \2', s)
    if n != s: f.write_text(n); print("updated", f)
EOF
```

Then edit by hand in `tests/test_db.py`: `test_favourites_keep_order` becomes

```python
def test_favourites_keep_order():
    d = DB(":memory:")
    assert d.fav_toggle("4chan", "v") and d.fav_toggle("lainchan", "sec") and d.fav_toggle("4chan", "g")
    assert d.fav_boards() == [("4chan", "v"), ("lainchan", "sec"), ("4chan", "g")]
    assert not d.fav_toggle("4chan", "v") and d.fav_boards() == [("lainchan", "sec"), ("4chan", "g")]
```
and `test_recent_dedupes_orders_and_caps` asserts `r[0] == ("4chan", "g", 5, "t5")` and `len({x[2] for x in r}) == 30`. `test_observe_marks_missing_expired_and_present_alive` is already updated by the script.

- [ ] **Step 2: Add the new failing tests** (append to `tests/test_db.py`)

```python
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
```

- [ ] **Step 3: Run to verify failure**

Run: `cd ~/Projects/lurkmoar && .venv/bin/pytest tests/test_db.py -q`
Expected: failures (`TypeError`: wrong argument counts, missing migration).

- [ ] **Step 4: Rewrite `db.py`**

```python
"""SQLite store (schema v2): API cache, bookmarks, favourites, per-board nav state, recents, kv. Site-aware."""
import shutil
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path

SCHEMA_VERSION = 2
SCHEMA = """
CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY, body TEXT NOT NULL,
  fetched_at REAL NOT NULL, last_modified TEXT);
CREATE TABLE IF NOT EXISTS bookmarks(site TEXT NOT NULL DEFAULT '4chan', board TEXT NOT NULL,
  thread_id INTEGER NOT NULL, subject TEXT NOT NULL, saved_at REAL NOT NULL,
  last_known_reply_count INTEGER NOT NULL DEFAULT 0, last_opened_post INTEGER NOT NULL DEFAULT 0,
  latest_replies INTEGER NOT NULL DEFAULT 0, expired INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY(site, board, thread_id));
CREATE TABLE IF NOT EXISTS favourites(site TEXT NOT NULL DEFAULT '4chan', board TEXT NOT NULL,
  pos INTEGER NOT NULL, PRIMARY KEY(site, board));
CREATE TABLE IF NOT EXISTS nav(site TEXT NOT NULL DEFAULT '4chan', board TEXT NOT NULL,
  catalog_anchor INTEGER NOT NULL DEFAULT 0, thread_no INTEGER NOT NULL DEFAULT 0,
  thread_anchor INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(site, board));
CREATE TABLE IF NOT EXISTS recent(site TEXT NOT NULL DEFAULT '4chan', board TEXT NOT NULL,
  thread_id INTEGER NOT NULL, subject TEXT NOT NULL, visited_at REAL NOT NULL,
  PRIMARY KEY(site, board, thread_id));
CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""
V1_COLUMNS = {
    "bookmarks": "board, thread_id, subject, saved_at, last_known_reply_count, last_opened_post, latest_replies, expired",
    "favourites": "board, pos",
    "nav": "board, catalog_anchor, thread_no, thread_anchor",
    "recent": "board, thread_id, subject, visited_at",
}
NAV_FIELDS = {"catalog_anchor", "thread_no", "thread_anchor"}
THREAD_KEY = "(key LIKE 'thread:%' OR key LIKE '%:thread:%')"


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
    site: str = "4chan"


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
            self._migrate(path)

    def _migrate(self, path):
        old = [t for t in V1_COLUMNS
               if (cols := [r[1] for r in self._c.execute(f"PRAGMA table_info({t})")]) and "site" not in cols]
        if old and str(path) != ":memory:":
            backup = Path(str(path) + ".v1.bak")
            if not backup.exists():
                self._c.commit()
                shutil.copy2(str(path), backup)
        script = ["BEGIN;"]
        script += [f"ALTER TABLE {t} RENAME TO {t}_v1;" for t in old]
        script.append(SCHEMA)
        script += [f"INSERT INTO {t}(site, {V1_COLUMNS[t]}) SELECT '4chan', {V1_COLUMNS[t]} FROM {t}_v1;" for t in old]
        script += [f"DROP TABLE {t}_v1;" for t in old]
        script += [f"PRAGMA user_version={SCHEMA_VERSION};", "COMMIT;"]
        self._c.executescript("\n".join(script))

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
        self._x(f"""DELETE FROM cache WHERE {THREAD_KEY}
          AND key NOT IN (SELECT CASE WHEN site='4chan' THEN 'thread:'||board||':'||thread_id
                                      ELSE site||':thread:'||board||':'||thread_id END FROM bookmarks)
          AND key NOT IN (SELECT key FROM cache WHERE {THREAD_KEY} ORDER BY fetched_at DESC LIMIT ?)""", (keep,))

    # bookmarks
    def bookmark_add(self, site, board, thread_id, subject, replies):
        self._x("INSERT OR IGNORE INTO bookmarks(site, board, thread_id, subject, saved_at,"
                " last_known_reply_count, last_opened_post, latest_replies, expired) VALUES(?,?,?,?,?,?,0,?,0)",
                (site, board, thread_id, subject, time.time(), replies, replies))

    def bookmark_remove(self, site, board, thread_id):
        self._x("DELETE FROM bookmarks WHERE site=? AND board=? AND thread_id=?", (site, board, thread_id))

    def bookmark_has(self, site, board, thread_id):
        return bool(self._q("SELECT 1 FROM bookmarks WHERE site=? AND board=? AND thread_id=?",
                            (site, board, thread_id)))

    def bookmarks(self):
        return [Bookmark(r[1], r[2], r[3], r[4], r[5], r[6], r[7], bool(r[8]), r[0]) for r in
                self._q("SELECT site, board, thread_id, subject, saved_at, last_known_reply_count,"
                        " last_opened_post, latest_replies, expired FROM bookmarks ORDER BY saved_at DESC")]

    def bookmarks_observe(self, site, board, replies):
        for b in self.bookmarks():
            if b.site != site or b.board != board:
                continue
            if b.thread_id in replies:
                self._x("UPDATE bookmarks SET latest_replies=?, expired=0"
                        " WHERE site=? AND board=? AND thread_id=?", (replies[b.thread_id], site, board, b.thread_id))
            else:
                self.bookmark_expire(site, board, b.thread_id)

    def bookmark_latest(self, site, board, thread_id, replies):
        self._x("UPDATE bookmarks SET latest_replies=?, expired=0 WHERE site=? AND board=? AND thread_id=?",
                (replies, site, board, thread_id))

    def bookmark_expire(self, site, board, thread_id):
        self._x("UPDATE bookmarks SET expired=1 WHERE site=? AND board=? AND thread_id=?", (site, board, thread_id))

    def bookmark_seen(self, site, board, thread_id, replies, last_post):
        self._x("UPDATE bookmarks SET last_known_reply_count=?, latest_replies=?, last_opened_post=?"
                " WHERE site=? AND board=? AND thread_id=?", (replies, replies, last_post, site, board, thread_id))

    # favourites
    def fav_boards(self):
        return [(r[0], r[1]) for r in self._q("SELECT site, board FROM favourites ORDER BY pos")]

    def fav_toggle(self, site, board):
        if (site, board) in self.fav_boards():
            self._x("DELETE FROM favourites WHERE site=? AND board=?", (site, board))
            return False
        self._x("INSERT INTO favourites(site, board, pos) VALUES(?,?, COALESCE((SELECT MAX(pos)+1 FROM favourites),0))",
                (site, board))
        return True

    # nav
    def nav_get(self, site, board):
        r = self._q("SELECT catalog_anchor, thread_no, thread_anchor FROM nav WHERE site=? AND board=?", (site, board))
        return Nav(*r[0]) if r else Nav()

    def nav_set(self, site, board, **fields):
        if not fields or not set(fields) <= NAV_FIELDS:
            raise ValueError(f"bad nav fields: {sorted(fields)}")
        self._x("INSERT OR IGNORE INTO nav(site, board) VALUES(?,?)", (site, board))
        sets = ", ".join(f"{k}=?" for k in fields)
        self._x(f"UPDATE nav SET {sets} WHERE site=? AND board=?", (*fields.values(), site, board))

    # recent
    def recent_add(self, site, board, thread_id, subject, now=None):
        self._x("INSERT OR REPLACE INTO recent(site, board, thread_id, subject, visited_at) VALUES(?,?,?,?,?)",
                (site, board, thread_id, subject, now if now is not None else time.time()))
        self._x("""DELETE FROM recent WHERE rowid NOT IN
                   (SELECT rowid FROM recent ORDER BY visited_at DESC LIMIT 30)""")

    def recent(self, limit=20):
        return [(r[0], r[1], r[2], r[3]) for r in self._q(
            "SELECT site, board, thread_id, subject FROM recent ORDER BY visited_at DESC LIMIT ?", (limit,))]

    # kv
    def kv_get(self, key, default=None):
        r = self._q("SELECT value FROM kv WHERE key=?", (key,))
        return r[0][0] if r else default

    def kv_set(self, key, value):
        self._x("INSERT OR REPLACE INTO kv VALUES(?,?)", (key, str(value)))
```

- [ ] **Step 5: Run the DB tests**

Run: `cd ~/Projects/lurkmoar && .venv/bin/pytest tests/test_db.py -q`
Expected: all PASS. The rest of the suite is allowed to fail here (Repo/UI still call the old signatures); Tasks 5 and 6 repair it.

- [ ] **Step 6: Commit**

```bash
cd ~/Projects/lurkmoar && git add -A && git commit -q -m "feat: site-aware database with v1 migration" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Core, Repo, thumbnails and per-site clients

**Files:**
- Modify: `src/lurkmoar/repo.py`, `src/lurkmoar/api.py`, `tests/test_repo.py`, `tests/helpers.py`
- Test: `tests/test_repo.py`

**Interfaces:**
- Consumes: `sites.load_sites/key`, `adapters.adapter_for`, Task 4 DB methods.
- Produces: `api.build_clients(sites) -> (api_clients: dict, media_clients: dict)`; `repo.Core(db, client, now=time.time, sites=None)` where `client` is one client or a `{site: client}` dict; `Core.boards(offline=False)` (4chan only), `Core.catalog(site, board, offline=False)`, `Core.thread(site, board, no, offline=False)` (a bad board code returns `Result(None, None, False, error="bad board")`); `repo.ThumbLoader(client_for, directory, on_change, workers=4, cap=64, keep=400)` with `image(key, urls, group=None, site="4chan") -> QImage | None` (`urls` is a str or tuple tried in order) and `failed(key)`; `repo.Repo(db, api_client, cdn_client, paths, cfg, now=time.time, sites=None)` with signals `boards_ready(object)`, `catalog_ready(str, str, object)` (site, board, result), `thread_ready(str, str, int, object)`, `media_ready(str, object, str)`, `thumbs_changed()`; methods `request_boards()`, `request_catalog(site, board)`, `request_thread(site, board, no)`, `request_media(site, board, att)`, `cached_boards()`, `cached_catalog(site, board)`, `cached_thread(site, board, no)`, `thumb_image(site, board, att)`, `thumb_failed(site, board, att)`, `cached_media_path(site, board, att)`, attribute `sites`. Thumbnail and media file names: 4chan `{board}_{id}…` (legacy), others `{site}_{board}_{id}…`.

- [ ] **Step 1: Update existing tests mechanically**

```bash
cd ~/Projects/lurkmoar && python3 - <<'EOF'
import re, pathlib
f = pathlib.Path("tests/test_repo.py"); s = f.read_text()
s = re.sub(r'\bc\.catalog\("g"', 'c.catalog("4chan", "g"', s)
s = re.sub(r'\bc\.thread\("g", ', 'c.thread("4chan", "g", ', s)
s = s.replace('repo.request_catalog("g")', 'repo.request_catalog("4chan", "g")')
s = s.replace('repo.cached_catalog("g")', 'repo.cached_catalog("4chan", "g")')
s = s.replace("repo.catalog_ready.connect(lambda b, r: got.append((b, r)))", "repo.catalog_ready.connect(lambda s, b, r: got.append((b, r)))")
f.write_text(s)
EOF
```
(In `test_repo_dedupes_and_emits` the handler now receives `(site, board, result)`; the assertions on `got[0][0] == "g"` still hold.)

- [ ] **Step 2: Add the failing tests** (append to `tests/test_repo.py`)

```python
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
```

- [ ] **Step 3: Run to verify failure**

Run: `cd ~/Projects/lurkmoar && .venv/bin/pytest tests/test_repo.py -q`
Expected: failures (signatures, missing `build_clients`).

- [ ] **Step 4: Implement `api.build_clients`** (append to `api.py`)

```python
def build_clients(sites):
    """One JSON client and one (faster) media client per site host; each enforces its own spacing."""
    api_clients, media_clients = {}, {}
    for sid, site in sites.items():
        api_clients[sid] = Client(min_interval=site.json_interval)
        media_clients[sid] = Client(min_interval=site.media_interval)
    return api_clients, media_clients
```

- [ ] **Step 5: Implement Core changes in `repo.py`**

Add imports: `from .adapters import adapter_for` and `from .sites import key as site_key, load_sites`. Replace `Core.__init__`, `_load`'s client use, `catalog`, `thread`:

```python
class Core:
    def __init__(self, db, client, now=time.time, sites=None):
        self.db, self.client, self.now = db, client, now
        self.sites = sites or load_sites()

    def _client(self, site):
        return self.client[site] if isinstance(self.client, dict) else self.client
```
In `_load(self, key, url, ttl, offline, site="4chan")` replace `self.client.get(url, ims)` with `self._client(site).get(url, ims)`. `boards()` keeps `self._load("boards", boards_url(), BOARDS_TTL, offline)` (site defaults to 4chan). Then:

```python
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
```

- [ ] **Step 6: Implement `ThumbLoader` and `Repo` changes**

`ThumbLoader`: constructor first parameter becomes `client_for` (a callable `site -> client`) stored as `self.client_for`; add `self._winner: dict = {}`. Queue entries become `(key, urls, group, site)`. Replace `image` and `_run`'s fetch section:

```python
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
```
In `_run`, unpack `key, urls, group, site = self._q.pop()` and replace the whole try/except fetch block with `img = self._fetch(key, urls, group, site)` (wrapped in `try: ... except Exception: img = None` so a worker never dies on an unexpected error).

`Repo`: new `__init__(self, db, api_client, cdn_client, paths, cfg, now=time.time, sites=None)`: `self.sites = sites or load_sites(cfg.extra_boards, cfg.hidden_sites)`, `self.core = Core(db, api_client, now, self.sites)`, `self._cdn = cdn_client`, `self.thumbs = ThumbLoader(self._cdn_for, paths.thumbs, self.thumbs_changed.emit)`. Add:

```python
    def _cdn_for(self, site):
        return self._cdn[site] if isinstance(self._cdn, dict) else self._cdn

    @staticmethod
    def _file_stem(site, board, att_id):
        return f"{board}_{att_id}" if site == "4chan" else f"{site}_{board}_{att_id}"
```
Signals: `catalog_ready = Signal(str, str, object)`, `thread_ready = Signal(str, str, int, object)`. Methods:

```python
    def request_catalog(self, site, board):
        return self._submit(self._api_pool, ("c", site, board), lambda: self.core.catalog(site, board),
                            lambda r: self.catalog_ready.emit(site, board, r))

    def request_thread(self, site, board, no):
        return self._submit(self._api_pool, ("t", site, board, no), lambda: self.core.thread(site, board, no),
                            lambda r: self.thread_ready.emit(site, board, no, r))

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
        p = self._media_path(site, board, att)
        return p if p.is_file() else None

    def request_media(self, site, board, att):
        url, dest = att.original_url, self._media_path(site, board, att)
        # body of work() unchanged except: self._cdn.get(url) -> self._cdn_for(site).get(url)
        ...
```
(keep the existing `work()` body and `_submit` call; the in-flight key becomes `("m", site, url)`.)

- [ ] **Step 7: Extend `tests/helpers.py` `FakeApi`** (needed by Task 6; add now and keep it small)

Add attributes in `__init__`: `self.vichan_catalog, self.vichan_thread = VICHAN_CATALOG, VICHAN_THREAD`, `self.files_catalog, self.files_thread = FILES_CATALOG, FILES_THREAD`, `self.fail_hosts = set()` (imports from `samples_vichan`). At the start of `get`, after recording the call:

```python
        host = url.split("/")[2]
        if self.fail or host in self.fail_hosts:
            raise ApiError("network: down")
        if host != "a.4cdn.org":
            if url.endswith("catalog.json"):
                return ok(self.files_catalog if "leftypol" in host else self.vichan_catalog)
            m = re.search(r"/res/(\d+)\.json$", url)
            if m:
                if int(m.group(1)) in self.gone:
                    raise NotFound("nf", 404)
                return ok(self.files_thread if "leftypol" in host else self.vichan_thread)
            raise NotFound("nf", 404)
```
and remove the old `if self.fail:` line.

- [ ] **Step 8: Run the repo tests**

Run: `cd ~/Projects/lurkmoar && .venv/bin/pytest tests/test_repo.py tests/test_db.py tests/test_adapters.py tests/test_sites.py -q`
Expected: PASS. UI tests are still red until Task 6.

- [ ] **Step 9: Commit**

```bash
cd ~/Projects/lurkmoar && git add -A && git commit -q -m "feat: site-aware repository, per-site clients and thumbnail fallback" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Site plumbing through the window and views

**Files:**
- Modify: `src/lurkmoar/main.py`, `src/lurkmoar/ui_catalog.py`, `src/lurkmoar/ui_thread.py`, `src/lurkmoar/ui_misc.py` (BookmarksView only), existing tests (call sites), `tests/helpers.py`
- Create: `tests/test_multisite.py`
- Test: `tests/test_multisite.py` and the whole existing suite

**Interfaces:**
- Consumes: Tasks 1–5.
- Produces: `MainWindow.site` (current site id, default `"4chan"`), `MainWindow.open_board(site, board)`, `open_thread(site, board, no)`, `open_media(site, board, att)`, `_toggle_fav(site, board)`, `_rail_chose(site, board)`, `thread_ref == (site, board, no)`; `CatalogView.set_board(site, code, board=None)`, `CatalogView.open_thread = Signal(str, str, int)`, `CatalogDelegate.bookmarked: set[(site, board, number)]`; `ThreadView.site`, `ThreadView.begin(site, board, number, subject, bookmarked)`, `ThreadView.media_requested = Signal(str, str, object)`; `BookmarksView(db, sites)` with `open_thread = Signal(str, str, int)`; every `current_ref()` dict gains `site`. Header title for non-4chan sites is `"{SiteName} /{board}/ {title}"`; 4chan's stays `"/{board}/ {title}"`. `kv` keys: `last_site` (absent = 4chan) and `last_view = "thread:{site}:{board}:{no}"` (the old `thread:{board}:{no}` still restores as 4chan).

- [ ] **Step 1: Mechanically update existing UI tests**

```bash
cd ~/Projects/lurkmoar && python3 - <<'EOF'
import re, pathlib
subs = [
    (r'\.open_board\("([a-z]+)"\)', r'.open_board("4chan", "\1")'),
    (r'\.open_thread\("([a-z]+)", (\d+)\)', r'.open_thread("4chan", "\1", \2)'),
    (r'\.open_media\("([a-z]+)", ', r'.open_media("4chan", "\1", '),
    (r'\.cached_media_path\("([a-z]+)", ', r'.cached_media_path("4chan", "\1", '),
    (r'\bwin\._refresh_thread\(\)', 'win._refresh_thread()'),
]
for f in pathlib.Path("tests").glob("test_*.py"):
    s = f.read_text(); n = s
    for a, b in subs: n = re.sub(a, b, n)
    if n != s: f.write_text(n); print("updated", f)
EOF
```
Then fix by hand what the script cannot: `tests/test_catalog.py::test_enter_opens_selected_thread` expects `got == [("4chan", "g", 100)]` and its lambda becomes `lambda s, b, n: got.append((s, b, n))`; `tests/test_persistence.py::test_bookmarks_screen_lists_and_opens` the same lambda/expectation with `("4chan", "g", 100)`; `test_f_bookmarks_selected_thread_and_marks_row` asserts `("4chan", "g", 100) in win.catalog.delegate.bookmarked`; `tests/test_thread.py` lambdas on `cross_requested` are unchanged (`(board, thread, post)`); `tests/test_media.py`/`test_gallery.py`/`test_save.py` pass `win.viewer` calls unchanged until Task 7.

- [ ] **Step 2: Write the failing multi-site tests**

`tests/test_multisite.py`:

```python
import time

from PySide6.QtCore import Qt

from helpers import make_window, press, pump


def open_site_thread(qapp, site="lainchan", board="sec", no=10):
    win, api, repo, db = make_window(qapp)
    win.open_board(site, board)
    assert pump(qapp, lambda: win.catalog.model.rowCount() >= 2)
    win.open_thread(site, board, no)
    assert pump(qapp, lambda: win.thread.loaded)
    return win, api, repo, db


def test_open_vichan_board_and_thread_end_to_end(qapp):
    win, *_ = open_site_thread(qapp)
    assert win.site == "lainchan" and win.board == "sec" and win.mode == "thread"
    assert win.thread.model.post_count() == 3 and win.thread.site == "lainchan"
    assert win.thread.model.replies_to == {10: [11]}
    assert "Lainchan /sec/" in win.header.where.text() and "No.10" in win.header.where.text()
    assert len(win.thread.gallery()) == 4                     # OP file + the post with 3 files... minus none: 1 + 3


def test_catalog_header_names_the_site_for_non_4chan_only(qapp):
    win, *_ = make_window(qapp)
    win.open_board("lainchan", "sec")
    assert win.header.where.text().startswith("Lainchan /sec/")
    win.open_board("4chan", "g")
    assert win.header.where.text().startswith("/g/")


def test_site_state_does_not_collide_between_sites_with_same_board_and_thread(qapp):
    win, api, repo, db = make_window(qapp)
    win.open_board("4chan", "b")
    pump(qapp, lambda: win.catalog.model.rowCount() == 3)
    win.open_board("kissu", "b")
    pump(qapp, lambda: win.catalog.model.rowCount() == 3 and win.site == "kissu")
    db.bookmark_add("4chan", "b", 10, "four", 1)
    assert not db.bookmark_has("kissu", "b", 10)
    assert db.cache_get("kissu:catalog:b") and db.cache_get("catalog:b")
    win.catalog.on_bookmarks_changed()
    assert ("kissu", "b", 10) not in win.catalog.delegate.bookmarked


def test_page_urls_use_each_sites_template(qapp):
    win, *_ = open_site_thread(qapp)
    win.thread.list.setCurrentIndex(win.thread.model.index(win.thread.model.row_of(11)))
    assert win.thread.current_ref()["url"] == "https://lainchan.org/sec/res/10.html#11"
    assert win.thread.current_ref()["site"] == "lainchan"
    win.leave_thread()
    assert win.catalog.current_ref()["url"].startswith("https://lainchan.org/sec/res/")
    win2, *_ = open_site_thread(qapp, "kissu", "b", 10)
    win2.thread.list.setCurrentIndex(win2.thread.model.index(win2.thread.model.row_of(11)))
    assert win2.thread.current_ref()["url"] == "https://kissu.moe/b/res/10#11"


def test_bookmark_on_a_vichan_thread_is_site_specific_and_survives_relaunch(qapp):
    from helpers import cleanup
    win, api, repo, db = open_site_thread(qapp)
    press(win, "f")
    assert db.bookmark_has("lainchan", "sec", 10) and not db.bookmark_has("4chan", "sec", 10)
    cleanup()
    win2, *_ = make_window(qapp, api=api, db=db)
    assert win2.site == "lainchan" and win2.board == "sec" and win2.mode == "thread" and win2.thread.number == 10


def test_old_last_view_format_still_restores_as_4chan(qapp):
    win, api, repo, db = make_window(qapp)
    db.kv_set("last_board", "g")
    db.kv_set("last_view", "thread:g:100")
    from helpers import cleanup
    cleanup()
    win2, *_ = make_window(qapp, api=api, db=db)
    assert win2.site == "4chan" and win2.mode == "thread" and win2.thread.number == 100


def test_failing_site_shows_banner_without_touching_the_other(qapp):
    win, api, *_ = make_window(qapp)
    api.fail_hosts.add("lainchan.org")
    win.open_board("lainchan", "sec")
    assert pump(qapp, lambda: not win.banner.isHidden())
    assert "Nothing is cached" in win.banner.label.text()
    win.open_board("4chan", "g")
    assert pump(qapp, lambda: win.catalog.model.rowCount() == 3 and win.banner.isHidden())


def test_invalid_typed_board_is_refused_before_any_request(qapp):
    win, api, *_ = make_window(qapp)
    n = len(api.calls)
    win.open_board("lainchan", "../x")
    assert win.mode == "welcome" and len(api.calls) == n and "isn't a valid board" in win.status.msg.text()


def test_cross_board_quote_on_the_same_site_asks_to_open_it(qapp):
    win, *_ = open_site_thread(qapp)
    got = []
    win.thread.cross_requested.disconnect()
    win.thread.cross_requested.connect(lambda b, t, p: got.append((b, t, p)))
    win.thread.follow_quote("/qa/res/9.html#4")
    assert got == [("qa", 9, 4)]


def test_bookmarks_screen_prefixes_non_4chan_sites_and_checks_each_board_once(qapp):
    win, api, repo, db = make_window(qapp)
    db.bookmark_add("lainchan", "sec", 10, "Lain thread", 1)
    db.bookmark_add("4chan", "g", 100, "Four thread", 1)
    win.show_bookmarks()
    text = " ".join(win.bookmarks.list.item(i).text() for i in range(win.bookmarks.list.count()))
    assert "Lainchan · /sec/  Lain thread" in text and "/g/  Four thread" in text and "4chan ·" not in text
    win.refresh()
    assert pump(qapp, lambda: any(u.endswith("lainchan.org/sec/catalog.json") for u in api.calls))
    assert pump(qapp, lambda: any(u.endswith("a.4cdn.org/g/catalog.json") for u in api.calls))
```

(The comment on the gallery-length assertion is wrong prose; the assertion is correct: `VICHAN_THREAD` has one file on the OP and three on post 12, so 4.)

- [ ] **Step 3: Run to verify failure**

Run: `cd ~/Projects/lurkmoar && .venv/bin/pytest -q`
Expected: the UI suite fails broadly (old signatures) and `test_multisite.py` fails.

- [ ] **Step 4: Implement `ui_catalog.py` changes**

- `CatalogDelegate.paint`: `star = "★ " if (t.site, t.board, t.number) in self.bookmarked else ""`; `_thumb`: `self.thumb_fn(t.site, t.board, att)` and `self.failed_fn(t.site, t.board, att)`.
- `CatalogView.__init__`: `self.site = "4chan"`, `self.repo = repo`; `open_thread = Signal(str, str, int)`.
- `set_board(self, site, code, board=None)`: set `self.site = site`; title `f"{prefix}/{code}/ {board.title}"` or `f"{prefix}/{code}/"` with `prefix = "" if site == "4chan" else self.repo.sites[site].name + " "`; rest unchanged.
- `_open`: `self.open_thread.emit(t.site, t.board, t.number)`.
- `current_ref`: `site = self.repo.sites[t.site]`; `dict(site=t.site, board=t.board, number=t.number, replies=t.replies, subject=..., url=site.page_url(t.board, t.number))`.
- `on_bookmarks_changed`: `self.delegate.bookmarked = {(b.site, b.board, b.thread_id) for b in self.db.bookmarks()}`.

- [ ] **Step 5: Implement `ui_thread.py` changes**

- `ThreadView.__init__`: `self.site = "4chan"`; delegate lambdas `lambda a: repo.thumb_image(self.site, self.board, a)` and `lambda a: repo.thumb_failed(self.site, self.board, a)`; `media_requested = Signal(str, str, object)`.
- `begin(self, site, board, number, subject, bookmarked)`: set `self.site = site` first.
- `open_media`: `self.media_requested.emit(self.site, self.board, a)`.
- `on_bookmarks_changed`: `self.db.bookmark_has(self.site, self.board, self.number)`.
- `current_ref`: `url = self.repo.sites[self.site].page_url(self.board, self.number, post.number if post else None)`, include `site=self.site`.

- [ ] **Step 6: Implement `BookmarksView(db, sites)` in `ui_misc.py`**

- Constructor `__init__(self, db, sites)`; store `self.sites = sites`; `open_thread = Signal(str, str, int)`.
- A helper `def _label(self, site, board, subject): return f"/{board}/  {subject}" if site == "4chan" else f"{self.sites[site].name if site in self.sites else site} · /{board}/  {subject}"`.
- `reload`: bookmark rows `("bm", b.site, b.board, b.thread_id)` with text `f"{self._label(...)}\n      {bookmark_status(b, has)}"` where `has = self.db.cache_get(site_key(b.site, "thread", b.board, b.thread_id)) is not None` (import `from .sites import key as site_key`); `marked = {(b.site, b.board, b.thread_id) ...}`; recents `("recent", site, board, tid)` from the 4-tuples, filtered against `marked`.
- `_open`/`key_action("open")`: emit `(d[1], d[2], d[3])`; `"delete"`: `self.db.bookmark_remove(d[1], d[2], d[3])`.
- `current_ref`: `dict(site=d[1], board=d[2], number=d[3], subject="", replies=0, url=self.sites[d[1]].page_url(d[2], d[3]) if d[1] in self.sites else "")`.

- [ ] **Step 7: Implement `main.py` changes**

- Imports: `from .sites import valid_board`.
- `__init__`: `self.site = "4chan"` beside `self.board`; `BookmarksView(db, repo.sites)`; connections: `self.catalog.open_thread.connect(lambda s, b, n: self.open_thread(s, b, n))`, `self.bookmarks.open_thread.connect(lambda s, b, n: self.open_thread(s, b, n))`, `self.sidebar.board_chosen.connect(self._rail_chose)` (Task 8 changes the sidebar signal to `(str, str)`; until then keep a temporary adapter `lambda c: self._rail_chose("4chan", c)` and the picker `chosen` lambda `lambda c: self.open_board("4chan", c)`, and `_toggle_fav` connections likewise `lambda c: self._toggle_fav("4chan", c)` — Task 8 removes these shims), `self.thread.media_requested.connect(self.open_media)`.
- `_title(self, site, board)`: 4chan → `self.boards[board].title` if known else `""`; others → the registry `Board.title` or `""`.
- `_prefix(self)`: `"" if self.site == "4chan" else self.repo.sites[self.site].name + " "`.
- `_update_where`: build `t = f"{self._prefix()}/{self.board}/ {title}".strip()`; thread mode: `f"{self._prefix()}/{self.board}/ › No.{n}"`.
- `_toggle_fav(self, site, code)`: `on = self.db.fav_toggle(site, code)`; `self.sidebar.set_boards(self.db.fav_boards(), self.board)` (Task 8 reshapes the arguments); `self.catalog.set_favourite((self.site, self.board) in self.db.fav_boards())`; status message `f"/{code}/ added to/removed from favourites"`. `toggle_board_favourite`: `self._toggle_fav(self.site, self.board)` when `self.board`.
- `_rail_chose(self, site, board)`: `self.open_board(site, board)`; `self.page().focus_list()`.
- `open_board(self, site, code)`:

```python
        code = code.lower()
        if site not in self.repo.sites or not valid_board(self.repo.sites[site], code):
            self.status.message(f"“{code}” isn't a valid board code")
            return
        if self.mode == "thread":
            self._save_thread_state()
        self.site, self.board = site, code
        self.db.kv_set("last_board", code)
        self.db.kv_set("last_site", site)
        self.db.kv_set("last_view", "catalog")
        self.banner.hide()
        self.catalog.set_board(site, code, self._board_obj(site, code))
        self.catalog.set_favourite((site, code) in self.db.fav_boards())
        self.sidebar.set_boards(self.db.fav_boards(), code)       # Task 8 passes (site, code)
        cached, nav = self.repo.cached_catalog(site, code), self.db.nav_get(site, code)
        ... (unchanged body, then) ...
        self._refresh_catalog(announce=False)
```
with `_board_obj(site, board)` returning the `models.Board` (4chan: `self.boards.get(board)`; others: the registry entry with that code or `None`).
- `_refresh_catalog`: `self.repo.request_catalog(self.site, self.board)`.
- `_on_catalog(self, site, code, res)`: first line fans out bookmark changes; `if (site, code) != (self.site, self.board): return`; the status line uses `code` as before.
- `show_bookmarks` unchanged. `_refresh_bookmarks`: `pairs = sorted({(b.site, b.board) for b in self.db.bookmarks()})`; `for s, b in pairs: self.repo.request_catalog(s, b)`.
- `_restore`:

```python
        last = self.db.kv_get("last_board")
        site = self.db.kv_get("last_site", "4chan")
        if site not in self.repo.sites:
            site = "4chan"
        if not last or not self.cfg.start_on_last_board:
            return
        view = self.db.kv_get("last_view", "")       # read first: open_board resets it to "catalog"
        self.open_board(site, last)
        if self.cfg.restore_thread and view.startswith("thread:"):
            parts = view.split(":")
            try:
                s, b, n = ("4chan", parts[1], parts[2]) if len(parts) == 3 else (parts[1], parts[2], parts[3])
                if (s, b) == (site, last):
                    self.open_thread(s, b, int(n))
            except (ValueError, IndexError):
                pass
```
- `open_thread(self, site, board, no, announce=True)`: `if (site, board) != (self.site, self.board): self.open_board(site, board)` (return if `self.site != site` afterwards, meaning the board was refused); `elif self.mode == "thread": self._save_thread_state()`; `nav = self.db.nav_get(site, board)`; `bm = next((b for b in self.db.bookmarks() if (b.site, b.board, b.thread_id) == (site, board, no)), None)`; `self.db.nav_set(site, board, catalog_anchor=self.catalog.anchor(), thread_no=no)`; `self.db.recent_add(site, board, no, subject or f"No.{no}")`; `last_view = f"thread:{site}:{board}:{no}"`; `self.thread_ref = (site, board, no)`; `self.thread.begin(site, board, no, subject, self.db.bookmark_has(site, board, no))`; `self.repo.cached_thread(site, board, no)`; `self.repo.request_thread(site, board, no)`.
- `_refresh_thread` and `_auto_refresh` keep `self.repo.request_thread(*self.thread_ref)`; the status text uses `self.thread_ref[2]`.
- `_on_thread(self, site, board, no, res)`: `if self.thread_ref != (site, board, no): return` (after the bookmark fan-out). Banner text `Back to /{board}/` unchanged.
- `_save_thread_state`: `s, b, n = self.thread_ref`; `self.db.nav_set(s, b, thread_no=n, thread_anchor=a)`; `self.db.bookmark_seen(s, b, n, self.thread.replies(), a)`.
- `leave_thread`: `n = self.thread_ref[2]`.
- `toggle_bookmark`: `s, b, n = ref["site"], ref["board"], ref["number"]`; every `db.bookmark_*` call gains `s` first; status text unchanged.
- `_cross_thread(self, board, thread, post)`: `site = self.repo.sites[self.thread_ref[0]]` (fall back to `self.site`); label `f"Open on {site.name}"`; "Open here" calls `self.open_thread(site.id, board, thread)` only if `valid_board(site, board)`; the external link is `site.page_url(board, thread, post)`.
- `open_media(self, site, board, att)`: `self.viewer.show_attachment(board, att, [a for _, a in self.thread.gallery()])` for now (Task 7 adds `site` to the viewer).
- `closeEvent`: `self.db.nav_set(self.site, self.board, catalog_anchor=self.catalog.anchor())`.
- `main()`: replace the client construction with

```python
    from .api import build_clients
    from .sites import load_sites
    sites = load_sites(cfg.extra_boards, cfg.hidden_sites)
    api_clients, media_clients = build_clients(sites)
    repo = Repo(DB(p.db_file), api_clients, media_clients, p, cfg, sites=sites)
```
and drop the now-unused `Client` import there.
- `ui_media.MediaViewer.show_attachment` is untouched in this task; it still calls `self.repo.request_media(self.board, att)`, which no longer exists. Change that one call, and `cached_media_path`, to pass `"4chan"` for now: `self.repo.request_media("4chan", self.board, att)` and `self.repo.cached_media_path("4chan", self.board, att)`. Task 7 replaces the placeholder with the real site.
- `tests/helpers.make_window` is unchanged; `win.boards` stays the 4chan title map.

- [ ] **Step 8: Run the full suite**

Run: `cd ~/Projects/lurkmoar && .venv/bin/pytest -q`
Expected: all PASS. If a test still uses an old signature, fix the call, not the production code, unless the test exposes a real site-plumbing bug.

- [ ] **Step 9: Commit**

```bash
cd ~/Projects/lurkmoar && git add -A && git commit -q -m "feat: site-aware window, catalog, thread and bookmarks" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Multiple attachments, site-aware viewer, per-site save folder

**Files:**
- Modify: `src/lurkmoar/ui_thread.py`, `src/lurkmoar/ui_media.py`, `src/lurkmoar/main.py`
- Create: `tests/test_multisite_media.py`
- Test: the new file plus existing `test_gallery.py`, `test_media.py`, `test_save.py`

**Interfaces:**
- Consumes: Tasks 3, 5, 6.
- Produces: `ThreadDelegate.caption(post) -> str` (file name line, ending in ` · +N more files` when a post has more than one live attachment); `ThreadView.gallery() -> list[(post_number, Attachment)]` over **every** attachment; `ThreadView.select_attachment(att_id)` matching any attachment of any post; `MediaViewer.show_attachment(site, board, att, gallery=None)`, `MediaViewer.site`; `MainWindow.open_media(site, board, att)` passes the site; saved files from non-4chan sites go to `save_dir/{site}/`.

- [ ] **Step 1: Write the failing tests**

`tests/test_multisite_media.py`:

```python
import copy
from pathlib import Path

from PySide6.QtCore import Qt

from helpers import make_window, press, pump
from samples_vichan import VICHAN_THREAD


def image_only_thread():
    d = copy.deepcopy(VICHAN_THREAD)
    d["posts"][2]["extra_files"] = [d["posts"][2]["extra_files"][0]]      # drop the .webm: images only
    return d


def open_in(qapp, tmp_path, site="lainchan", board="sec"):
    win, api, repo, db = make_window(qapp)
    api.vichan_thread = image_only_thread()
    win.cfg.save_dir = str(tmp_path / "saved")
    win.open_board(site, board)
    assert pump(qapp, lambda: win.catalog.model.rowCount() >= 2)
    win.open_thread(site, board, 10)
    assert pump(qapp, lambda: win.thread.loaded)
    return win, repo


def test_gallery_includes_every_attachment_in_thread_order(qapp, tmp_path):
    win, _ = open_in(qapp, tmp_path)
    assert [(p, a.extension) for p, a in win.thread.gallery()] == [(10, ".jpg"), (12, ".png"), (12, ".gif")]


def test_caption_mentions_extra_files(qapp, tmp_path):
    win, _ = open_in(qapp, tmp_path)
    op, p11, p12 = win.thread.model.post_at(0), win.thread.model.post_at(1), win.thread.model.post_at(2)
    assert "more file" not in win.thread.delegate.caption(op)
    assert win.thread.delegate.caption(p12).endswith("+1 more files") or win.thread.delegate.caption(p12).endswith("+1 more file")
    assert win.thread.delegate.caption(p11) == ""


def test_arrows_cycle_through_a_posts_extra_files_and_wrap(qapp, tmp_path):
    win, _ = open_in(qapp, tmp_path)
    win.open_media("lainchan", "sec", win.thread.gallery()[0][1])
    assert win.viewer.site == "lainchan" and "1 / 3" in win.viewer.info.text()
    press(win, Qt.Key_Right)
    press(win, Qt.Key_Right)
    assert "3 / 3" in win.viewer.info.text() and win.viewer.att.extension == ".gif"
    press(win, Qt.Key_Right)
    assert "1 / 3" in win.viewer.info.text()


def test_closing_selects_the_post_that_owns_the_last_shown_extra_file(qapp, tmp_path):
    win, _ = open_in(qapp, tmp_path)
    win.thread.list.setCurrentIndex(win.thread.model.index(0))
    win.open_media("lainchan", "sec", win.thread.gallery()[0][1])
    press(win, Qt.Key_Right)
    press(win, Qt.Key_Right)
    press(win, Qt.Key_Escape)
    assert win.thread.current_post().number == 12


def test_save_goes_to_a_site_subfolder_for_non_4chan(qapp, tmp_path):
    win, _ = open_in(qapp, tmp_path)
    win.open_media("lainchan", "sec", win.thread.gallery()[0][1])
    assert pump(qapp, lambda: win.viewer.canvas.img is not None)
    press(win, "s")
    assert (tmp_path / "saved" / "lainchan" / "pic.jpg").exists()


def test_4chan_save_stays_flat(qapp, tmp_path):
    win, api, repo, db = make_window(qapp)
    win.cfg.save_dir = str(tmp_path / "saved")
    win.open_board("4chan", "g")
    pump(qapp, lambda: win.catalog.model.rowCount() == 3)
    win.open_thread("4chan", "g", 100)
    pump(qapp, lambda: win.thread.loaded)
    win.open_media("4chan", "g", win.thread.gallery()[0][1])
    assert pump(qapp, lambda: win.viewer.canvas.img is not None)
    press(win, "s")
    assert (tmp_path / "saved" / "gpu.jpg").exists()


def test_same_attachment_id_on_two_sites_uses_two_cache_files(qapp, tmp_path):
    win, repo = open_in(qapp, tmp_path, "lainchan", "sec")
    att = win.thread.gallery()[0][1]
    win.open_media("lainchan", "sec", att)
    assert pump(qapp, lambda: win.viewer.canvas.img is not None)
    press(win, Qt.Key_Escape)
    win.leave_thread()
    win.open_board("kissu", "b")
    pump(qapp, lambda: win.catalog.model.rowCount() >= 2)
    win.open_thread("kissu", "b", 10)
    pump(qapp, lambda: win.thread.loaded)
    att2 = win.thread.gallery()[0][1]
    assert att.id == att2.id
    win.open_media("kissu", "b", att2)
    assert pump(qapp, lambda: win.viewer.canvas.img is not None)
    names = sorted(p.name for p in repo.paths.media.iterdir())
    assert len(names) == 2 and names[0].startswith("kissu_b_") and names[1].startswith("lainchan_sec_")
```

- [ ] **Step 2: Run to verify failure**

Run: `cd ~/Projects/lurkmoar && .venv/bin/pytest tests/test_multisite_media.py -q`
Expected: failures (`caption` missing, viewer has no `site`, gallery lists only first attachments).

- [ ] **Step 3: Implement `ui_thread.py` changes**

- Extract the attachment caption logic from `ThreadDelegate.paint` into a method and call it from `paint`:

```python
    def caption(self, post):
        a = post.attachment
        if a is None:
            return ""
        live = [x for x in post.attachments if not x.deleted]
        if a.deleted:
            cap = "File deleted"
        else:
            cap = (f"{a.filename}{a.extension} · {a.width}×{a.height} · {a.size / 1024:.0f} KB"
                   + (" · spoiler" if a.spoiler and a.id not in self.revealed_files else ""))
        if len(live) > 1:
            cap += f" · +{len(live) - 1} more files"
        return cap
```
In `paint`, the `if a:` block draws `self.caption(post)`.
- `gallery()`:

```python
    def gallery(self):
        out = []
        for r in range(self.model.rowCount()):
            p = self.model.post_at(r)
            if p:
                out += [(p.number, a) for a in p.attachments if not a.deleted]
        return out
```
- `select_attachment(att_id)`: loop posts and `any(a.id == att_id for a in p.attachments)`.
- `images()` (header stats): `sum(1 for r ... for a in p.attachments if not a.deleted)`.

- [ ] **Step 4: Implement `ui_media.py` viewer changes**

- `MediaViewer.__init__`: `self.site = "4chan"`.
- `show_attachment(self, site, board, att, gallery=None)`: set `self.site = site` along with `self.board`.
- Replace the Task 6 placeholders: `self.repo.request_media(self.site, self.board, att)`; `self.repo.cached_media_path(self.site, self.board, att)`.
- `_save`: `folder = Path(self.cfg.save_dir).expanduser()`; `if self.site != "4chan": folder = folder / self.site`.

- [ ] **Step 5: Implement `main.py`**

`open_media(self, site, board, att)`: `self.viewer.show_attachment(site, board, att, [a for _, a in self.thread.gallery()])`.

- [ ] **Step 6: Run the full suite**

Run: `cd ~/Projects/lurkmoar && .venv/bin/pytest -q`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
cd ~/Projects/lurkmoar && git add -A && git commit -q -m "feat: multi-file posts in the gallery, per-site media cache and save folder" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Left rail grouped by site, board picker across sites

**Files:**
- Modify: `src/lurkmoar/ui_misc.py`, `src/lurkmoar/main.py`, `tests/test_shell.py`, `tests/test_rail.py`, `tests/test_backspace.py`
- Test: `tests/test_shell.py`, `tests/test_rail.py` (updated) and new tests appended to `tests/test_multisite.py`

**Interfaces:**
- Consumes: Task 6 shims in `main.py` (removed here).
- Produces: `ui_misc.filter_site_boards(boards_by_site, sites, query, favs=()) -> list[(site_id, list[Board])]`, `ui_misc.parse_typed(query, sites, current_site) -> (site, code) | None`; `Sidebar.set_boards(favs: list[(site, board)], current: (site, board) | None, sites)`, `Sidebar.board_chosen = Signal(str, str)`; list items are non-selectable headers (`data(Qt.UserRole) is None`, text `"── {Site name}"`) followed by selectable boards (`data == (site, board)`); sites appear in registry order and a header only when its group has boards; `BoardPicker(parent, boards_by_site, favs, sites, current_site="4chan")` with `chosen = Signal(str, str)`, `favourite_toggled = Signal(str, str)`, `set_boards(boards_by_site, favs)`, `set_favs(favs)`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_multisite.py`)

```python
from lurkmoar.models import Board
from lurkmoar.sites import load_sites
from lurkmoar.ui_misc import filter_site_boards, parse_typed

SITES = load_sites()
BY_SITE = {"4chan": [Board("g", "Technology", True, 10), Board("v", "Video Games", False, 10)],
           **{sid: list(s.boards) for sid, s in SITES.items() if sid != "4chan"}}


def rail_rows(win):
    out = []
    for i in range(win.sidebar.list.count()):
        it = win.sidebar.list.item(i)
        out.append(("H", it.text()) if it.data(Qt.UserRole) is None else ("B", it.data(Qt.UserRole)))
    return out


def test_rail_groups_favourites_under_site_headers_in_registry_order(qapp):
    win, _, _, db = make_window(qapp)
    for s, b in (("lainchan", "sec"), ("4chan", "g"), ("kissu", "b"), ("lainchan", "lit")):
        db.fav_toggle(s, b)
    win.sidebar.set_boards(db.fav_boards(), None, win.repo.sites)
    assert rail_rows(win) == [("H", "── 4chan"), ("B", ("4chan", "g")), ("H", "── Kissu"), ("B", ("kissu", "b")),
                              ("H", "── Lainchan"), ("B", ("lainchan", "sec")), ("B", ("lainchan", "lit"))]
    header = win.sidebar.list.item(0)
    assert not (header.flags() & Qt.ItemIsSelectable)


def test_rail_shows_current_non_favourite_under_its_site_and_no_empty_headers(qapp):
    win, _, _, db = make_window(qapp)
    db.fav_toggle("4chan", "g")
    win.sidebar.set_boards(db.fav_boards(), ("wizchan", "wiz"), win.repo.sites)
    assert rail_rows(win) == [("H", "── 4chan"), ("B", ("4chan", "g")), ("H", "── Wizchan"), ("B", ("wizchan", "wiz"))]
    assert win.sidebar.list.currentItem().data(Qt.UserRole) == ("wizchan", "wiz")
    win.sidebar.set_boards([], None, win.repo.sites)
    assert rail_rows(win) == []


def test_rail_arrows_skip_headers_and_enter_opens_the_board(qapp):
    win, api, repo, db = make_window(qapp)
    pump(qapp, lambda: "g" in win.boards)
    for s, b in (("4chan", "g"), ("lainchan", "sec")):
        db.fav_toggle(s, b)
    win.open_board("lainchan", "sec")
    pump(qapp, lambda: win.catalog.model.rowCount() >= 2)
    press(win, Qt.Key_Left)
    assert win.sidebar.list.currentItem().data(Qt.UserRole) == ("lainchan", "sec")
    press(win, Qt.Key_Up)                                  # skips the "Lainchan" header
    assert win.sidebar.list.currentItem().data(Qt.UserRole) == ("4chan", "g")
    press(win, Qt.Key_Up)                                  # nothing above: stays put
    assert win.sidebar.list.currentItem().data(Qt.UserRole) == ("4chan", "g")
    press(win, Qt.Key_Return)
    assert (win.site, win.board) == ("4chan", "g")


def test_filter_site_boards_matches_codes_titles_and_sites():
    fav = {("lainchan", "sec")}
    sec = filter_site_boards(BY_SITE, SITES, "sec", fav)
    assert ("lainchan", "sec") in [(sid, b.code) for sid, bs in sec for b in bs]
    lain = dict(filter_site_boards(BY_SITE, SITES, "lain", fav))
    assert {b.code for b in lain["lainchan"]} == {b.code for b in SITES["lainchan"].boards}
    one = filter_site_boards(BY_SITE, SITES, "lain sec", fav)
    assert [(sid, [b.code for b in bs]) for sid, bs in one] == [("lainchan", ["sec"])]
    assert [sid for sid, _ in filter_site_boards(BY_SITE, SITES, "", fav)][0] == "4chan"
    assert filter_site_boards(BY_SITE, SITES, "zzzzzz", fav) == []
    tech = [(sid, b.code) for sid, bs in filter_site_boards(BY_SITE, SITES, "technology", ()) for b in bs]
    assert tech == [("4chan", "g")]


def test_parse_typed_codes():
    assert parse_typed("qa", SITES, "kissu") == ("kissu", "qa")
    assert parse_typed("/qa/", SITES, "kissu") == ("kissu", "qa")
    assert parse_typed("kissu qa", SITES, "lainchan") == ("kissu", "qa")
    assert parse_typed("lain zzz", SITES, "4chan") == ("lainchan", "zzz")
    assert parse_typed("../x", SITES, "kissu") is None and parse_typed("a b c", SITES, "kissu") is None
    assert parse_typed("nosuch qa", SITES, "kissu") is None and parse_typed("", SITES, "kissu") is None
    assert parse_typed("A", SITES, "kissu") is None


def test_picker_groups_by_site_and_enter_opens(qapp):
    win, *_ = make_window(qapp)
    pump(qapp, lambda: "g" in win.boards)
    press(win, "b")
    p = win._picker

    def rows():
        return [(p.list.item(i).data(Qt.UserRole) or p.list.item(i).text()) for i in range(p.list.count())]

    assert rows()[0] == "── 4chan" and ("lainchan", "sec") in rows() and "── Lainchan" in rows()
    p.search.setText("lain sec")
    assert rows() == ["── Lainchan", ("lainchan", "sec")]
    assert p.list.currentItem().data(Qt.UserRole) == ("lainchan", "sec")
    press(p, Qt.Key_Return) if False else p._accept_current()
    assert (win.site, win.board) == ("lainchan", "sec")


def test_picker_typed_code_opens_an_unlisted_board_on_the_current_site(qapp):
    win, *_ = make_window(qapp)
    win.open_board("kissu", "b")
    pump(qapp, lambda: win.catalog.model.rowCount() >= 2)
    win.open_picker()
    p = win._picker
    p.search.setText("qa")
    assert p.list.count() == 0 or p.list.currentItem() is None or True
    p._accept_current()
    assert (win.site, win.board) == ("kissu", "qa")


def test_picker_rejects_invalid_typed_code(qapp):
    win, api, *_ = make_window(qapp)
    n = len(api.calls)
    win.open_picker()
    win._picker.search.setText("../x")
    win._picker._accept_current()
    assert win.mode == "welcome" and win._picker.isVisible() and "valid board" in win._picker.msg.text()


def test_favourite_in_picker_lands_in_the_right_rail_group(qapp):
    win, _, _, db = make_window(qapp)
    win.open_picker()
    p = win._picker
    p.search.setText("lain sec")
    p.fav_btn.click()
    assert db.fav_boards() == [("lainchan", "sec")]
    assert rail_rows(win) == [("H", "── Lainchan"), ("B", ("lainchan", "sec"))]
    p.reject()
```

(Two assertions above are deliberately permissive where the picker legitimately shows either an empty list or an unrelated first entry for an unlisted typed code; the behaviour under test is the typed fallback in `_accept_current`. Replace the `or True` line with `assert p.list.currentItem() is None` once the picker's refill is written: an unlisted code produces no rows. Also replace `press(p, Qt.Key_Return) if False else p._accept_current()` with plain `p._accept_current()`.)

Update the existing tests that touched the old shapes:
- `tests/test_shell.py`: `test_picker_loads_boards_and_filters` asserts `len(boards of 4chan in the list) == 3` using `[p.list.item(i).data(Qt.UserRole) for i in range(p.list.count()) if p.list.item(i).data(Qt.UserRole) and p.list.item(i).data(Qt.UserRole)[0] == "4chan"]`, then filters `"vid"` and expects `[("4chan","v"), ("4chan","vg")]`; `test_favourite_from_picker_shows_in_sidebar` expects `db.fav_boards() == [("4chan", "g")]` and `win.sidebar.list.count() == 2` (header + board); `test_picker...` uses `win._picker.search.setText("g")` then `fav_btn.click()` — the first listed board for `"g"` is `("4chan","g")` so it still works.
- `tests/test_rail.py`: `setup_rail` favourites become `db.fav_toggle("4chan", f)`; `current_item().data(Qt.UserRole) == ("4chan", "g")`; in `test_arrows_and_enter_pick_a_board` the favourite order is `v` then `g` under one `4chan` header, so Up from `g` lands on `v` (the header is above `v`, not between them) and `Enter` opens `("4chan","v")`; `test_down_past_the_boards_reaches_all_boards_button` is unchanged in behaviour.
- `tests/test_backspace.py` needs no change.

- [ ] **Step 2: Run to verify failure**

Run: `cd ~/Projects/lurkmoar && .venv/bin/pytest -q`
Expected: failures in the rail/picker tests (old shapes), `ImportError` for `filter_site_boards`.

- [ ] **Step 3: Implement the helpers in `ui_misc.py`**

```python
from .sites import valid_board


def _site_matches(site, token):
    return site.id.startswith(token) or site.name.lower().startswith(token)


def filter_site_boards(boards_by_site, sites, query, favs=()):
    """Filter boards across sites. 'lain' lists a whole site, 'lain sec' narrows to one board, 'sec' matches everywhere."""
    toks = query.strip().lower().split()
    favs_of = lambda sid: {b for s, b in favs if s == sid}
    only, board_q = None, query
    if len(toks) >= 2:
        hit = {sid for sid, site in sites.items() if _site_matches(site, toks[0])}
        if hit:
            only, board_q = hit, " ".join(toks[1:])
    out = []
    for sid, site in sites.items():
        if only is not None and sid not in only:
            continue
        boards = boards_by_site.get(sid, [])
        if only is None and len(toks) == 1 and _site_matches(site, toks[0]):
            sel = filter_boards(boards, "", favs_of(sid))          # the whole site
        else:
            sel = filter_boards(boards, board_q, favs_of(sid))
        if sel:
            out.append((sid, sel))
    return out


def parse_typed(query, sites, current_site):
    """'qa' -> (current site, qa); 'kissu qa' -> (kissu, qa); None when it is not a valid board reference."""
    toks = query.strip().lower().split()
    if len(toks) == 1:
        sid, code = current_site, toks[0].strip("/")
    elif len(toks) == 2:
        sid = next((i for i, s in sites.items() if _site_matches(s, toks[0])), None)
        code = toks[1].strip("/")
    else:
        return None
    if sid is None or sid not in sites or not valid_board(sites[sid], code):
        return None
    return sid, code
```

- [ ] **Step 4: Rewrite `Sidebar.set_boards`, `nav`, `enter`, `choose_current`**

```python
    board_chosen = Signal(str, str)

    def set_boards(self, favs, current, sites):
        self.list.clear()
        wanted = list(favs)
        if current and tuple(current) not in wanted:
            wanted.append(tuple(current))
        groups = {}
        for s, b in wanted:
            groups.setdefault(s, []).append(b)
        order = [(sid, site.name) for sid, site in sites.items()] + [(sid, sid) for sid in groups if sid not in sites]
        bold = QFont(self.list.font())
        bold.setBold(True)
        for sid, name in order:
            boards = groups.get(sid)
            if not boards:
                continue
            head = QListWidgetItem(f"── {name}")
            head.setFlags(Qt.NoItemFlags)
            head.setFont(bold)
            self.list.addItem(head)
            for b in boards:
                it = QListWidgetItem(("★ " if (sid, b) in favs else "   ") + f"/{b}/")
                it.setData(Qt.UserRole, (sid, b))
                self.list.addItem(it)
                if current and (sid, b) == tuple(current):
                    self.list.setCurrentItem(it)

    def _rows(self):
        return [i for i in range(self.list.count()) if self.list.item(i).data(Qt.UserRole)]

    def enter(self):
        rows = self._rows()
        if rows and self.list.currentRow() not in rows:
            self.list.setCurrentRow(rows[0])
        self.list.setFocus()

    def choose_current(self):
        it = self.list.currentItem()
        if it and it.data(Qt.UserRole):
            self.board_chosen.emit(*it.data(Qt.UserRole))
```
`nav`'s list branch becomes:

```python
        if cur == 0:
            rows = self._rows()
            row = self.list.currentRow()
            i = rows.index(row) if row in rows else -1
            if key == Qt.Key_Down:
                if i < 0 and rows:
                    self.list.setCurrentRow(rows[0])
                elif i >= len(rows) - 1:
                    self.all_btn.setFocus()
                else:
                    self.list.setCurrentRow(rows[i + 1])
                return True
            if key == Qt.Key_Up:
                if i > 0:
                    self.list.setCurrentRow(rows[i - 1])
                return True
            return False
```
and the Up-from-All branch selects `rows[-1]` (`self._rows()[-1]` when rows exist). The list's `itemClicked` handler becomes `lambda it: it.data(Qt.UserRole) and self.board_chosen.emit(*it.data(Qt.UserRole))`.

- [ ] **Step 5: Rewrite `BoardPicker`**

Constructor `(self, parent, boards_by_site, favs, sites, current_site="4chan")`; store `self.sites`, `self.current_site`; signals `chosen = Signal(str, str)`, `favourite_toggled = Signal(str, str)`. `set_boards(boards_by_site, favs)` stores `self.boards_by_site`, `self.favs = set(favs)` and sets `self.msg` to `"Loading 4chan boards…"` while `not boards_by_site.get("4chan")`, else `""`. `refill()`:

```python
    def refill(self):
        keep = self._current()
        self.list.clear()
        bold = QFont(self.list.font())
        bold.setBold(True)
        for sid, boards in filter_site_boards(self.boards_by_site, self.sites, self.search.text(), self.favs):
            head = QListWidgetItem(f"── {self.sites[sid].name}")
            head.setFlags(Qt.NoItemFlags)
            head.setFont(bold)
            self.list.addItem(head)
            for b in boards:
                it = QListWidgetItem(f"{'★' if (sid, b.code) in self.favs else ' '} /{b.code}/".ljust(9)
                                     + (f" {b.title}" if b.title else "") + ("" if b.worksafe else "   NSFW"))
                it.setData(Qt.UserRole, (sid, b.code))
                self.list.addItem(it)
                if (sid, b.code) == keep:
                    self.list.setCurrentItem(it)
        rows = self._rows()
        if rows and self.list.currentRow() not in rows:
            self.list.setCurrentRow(rows[0])
```
`_rows()` as in the sidebar; `_current()` returns `self.list.currentItem().data(Qt.UserRole)` or `None`; the `eventFilter` Up/Down steps through `_rows()` instead of raw rows (and Backspace-on-empty still rejects); `_accept_item(it)`: `self.chosen.emit(*it.data(Qt.UserRole)); self.accept()`; `_accept_current()`:

```python
    def _accept_current(self):
        cur = self._current()
        if cur:
            self.chosen.emit(*cur)
            self.accept()
            return
        typed = parse_typed(self.search.text(), self.sites, self.current_site)
        if typed is None:
            self.msg.setText("No matching board, and that isn't a valid board code.")
            return
        self.chosen.emit(*typed)
        self.accept()
```
`_fav`: `cur = self._current(); if cur: self.favourite_toggled.emit(*cur)`; double-click uses `_accept_item` only on selectable rows.

- [ ] **Step 6: Update `main.py` (remove the Task 6 shims)**

- `self.sidebar.board_chosen.connect(self._rail_chose)`.
- Every `self.sidebar.set_boards(a, b)` becomes `self.sidebar.set_boards(self.db.fav_boards(), (self.site, self.board) if self.board else None, self.repo.sites)` (add a small `_refresh_rail()` helper and call it from `__init__`, `open_board`, `_toggle_fav`).
- `_boards_by_site()`:

```python
    def _boards_by_site(self):
        return {sid: (list(self.boards.values()) if sid == "4chan" else list(s.boards))
                for sid, s in self.repo.sites.items()}
```
- `open_picker`: `p = BoardPicker(self, self._boards_by_site(), self.db.fav_boards(), self.repo.sites, self.site)`; `p.chosen.connect(lambda s, c: self.open_board(s, c))`; `p.favourite_toggled.connect(self._toggle_fav)`.
- `_set_boards` refreshes the picker with `self._picker.set_boards(self._boards_by_site(), self.db.fav_boards())`; `_toggle_fav` calls `self._picker.set_favs(self.db.fav_boards())`.
- The picker must not request 4chan boards when only other sites are used: `open_picker` calls `self.repo.request_boards()` only when `not self.boards` (unchanged).

- [ ] **Step 7: Run the full suite**

Run: `cd ~/Projects/lurkmoar && .venv/bin/pytest -q`
Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
cd ~/Projects/lurkmoar && git add -A && git commit -q -m "feat: rail grouped by site and a site-aware board picker" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Copy, docs, final verification, install

**Files:**
- Modify: `src/lurkmoar/ui_misc.py` (`ABOUT`, help dialog link), `README.md`, `docs/superpowers/specs/2026-10-05-multisite-vichan-design.md` (only if the implementation deviated)
- Test: `tests/test_shell.py` (About text)

- [ ] **Step 1: Write the failing test** (append to `tests/test_shell.py`)

```python
def test_about_text_names_no_single_site():
    from lurkmoar.ui_misc import ABOUT
    assert ABOUT == ("LurkMoar is an independent read-only client.\n"
                     "Content is sourced from the sites you open and belongs to them. "
                     "Not affiliated with or endorsed by any of them.")


def test_help_dialog_has_no_4chan_link(qapp):
    win, *_ = make_window(qapp)
    win.show_help()
    assert "4chan.org" not in win._help.findChild(__import__("PySide6.QtWidgets", fromlist=["QLabel"]).QLabel).text()
    win._help.reject()
```

- [ ] **Step 2: Run to verify failure**, then **Step 3: implement.**

Run: `cd ~/Projects/lurkmoar && .venv/bin/pytest tests/test_shell.py -q` → FAIL.

In `ui_misc.py` set:

```python
ABOUT = ("LurkMoar is an independent read-only client.\n"
         "Content is sourced from the sites you open and belongs to them. "
         "Not affiliated with or endorsed by any of them.")
```
and delete the `<p><a href='https://www.4chan.org'>4chan.org</a></p>` line from the help body (keep `setOpenExternalLinks(True)` harmless).

- [ ] **Step 4: Update `README.md`**

Replace the opening paragraph with a description of the supported sites, add the `extra_boards` and `hidden_sites` rows to the config table, and add a short "Sites" section listing the supported sites, how to add boards (`config.json` `extra_boards` or typing `site board` / a code in the picker), and the excluded-sites note. Replace the final About sentence with the new About text.

- [ ] **Step 5: Full suite, three runs**

Run: `cd ~/Projects/lurkmoar && for i in 1 2 3; do .venv/bin/pytest -q 2>&1 | tail -1; done`
Expected: `N passed` each time (no flakes). If a test fails intermittently, reproduce before changing anything (systematic-debugging).

- [ ] **Step 6: Install**

Run: `cd ~/Projects/lurkmoar && ./install.sh`
Expected: "Binding already points at the new launcher" and "Installed." (it only refreshes the editable install).

- [ ] **Step 7: Manual live check (left to the user)**

For each of Wizchan, Lainchan, Leftypol, Sushichan, Kissu and Uboachan: open one board, open one thread, open one image, open one video if present, save, bookmark, relaunch. Note any site whose thumbnails stay on "…": that points at a thumbnail-extension candidate the fallback list does not cover.

- [ ] **Step 8: Commit**

```bash
cd ~/Projects/lurkmoar && git add -A && git commit -q -m "docs: multi-site README and neutral About text" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Self-review notes

- **Spec coverage:** registry and config (T1), quote/span parsing (T2), models and both adapters including multi-attachment, hostile and sparse payloads (T3), DB migration and isolation (T4), per-site clients, cache keys, thumbnail fallback, media names (T5), site state through window/catalog/thread/bookmarks, header, URL templates, restore with old and new `last_view`, cross-board quotes, failure isolation (T6), gallery over extra files, caption, per-site save folder (T7), rail grouping, picker grouping, typed codes (T8), About text, README, install (T9). Deferred per spec: jschan/LynxChan, 8kun, Cloudflare sites, discovery, site-management UI.
- **Type consistency:** `site` first in every Repo/DB/UI method and signal; models take trailing `site="4chan"`; `Bookmark.site` last; `fav_boards()` returns `(site, board)`; `recent()` returns 4-tuples; `Attachment.id` is `int | str`; `Sidebar.board_chosen`/`BoardPicker.chosen` are `(str, str)`.
- **Known risks to watch while executing:** Task 6 touches most of `main.py` at once (keep the shims until Task 8 so the suite stays green between tasks); `test_multisite.py`'s two permissive assertions in Task 8 must be tightened as noted; the thumbnail candidate list is a guess for sites not probed with real thumbnails of every type.
