# LurkMoar: multi-site support (vichan family)

Extends `2026-10-03-lurkmoar-design.md`. Read-only stays a hard constraint: GET only, no posting, runtime dependencies stay PySide6 and httpx.

## Goal

Read the vichan-family imageboards from LurkMoar the same way 4chan is read today: board → catalog → thread → gallery, with bookmarks, favourites, session restore, the gallery with video and save. The left rail shows favourite boards **grouped under a header per site**.

## Scope

In: 4chan (unchanged behaviour) plus six verified vichan-family sites. Out: any site not listed below, any site behind a captcha or browser challenge, jschan and LynxChan engines (later, as new adapters), posting of any kind.

### Verified sites (probed 2026-10-05, structure only, no content kept)

| Site | id | Base URL | Family | Boards shipped |
|---|---|---|---|---|
| 4chan | `4chan` | existing hosts | `4chan` | all (from `boards.json`) |
| Wizchan | `wizchan` | `https://wizchan.org` | `vichan` | wiz dep hob lounge jp meta games music all |
| Lainchan | `lainchan` | `https://lainchan.org` | `vichan` | sec inter lit music vis hum drug zzz layer q r culture psy mega random zine |
| Leftypol | `leftypol` | `https://leftypol.org` | `vichan-files` | overboard sfw alt leftypol edu labor siberia lgbt latam hobby tech games anime music draw ufo 420 meta |
| Sushichan | `sushichan` | `https://sushigirl.us` | `vichan` | lounge yakuza arcade kawaii kitchen tunes culture silicon otaku hell chat |
| Kissu | `kissu` | `https://kissu.moe` | `vichan` | b jp (others via typed code) |
| Uboachan | `uboachan` | `https://uboachan.net` | `vichan` | yn yndd ot n o (others via typed code) |

Probed and **excluded**: soyjak.party (every request timed out), Holotower (Cloudflare 403), lolcow.farm (`catalog.json` 404 on all boards), Ponychan (custom fork, no catalog), 8kun (catalog works but its media host does not resolve), Sportschan and Erischan (jschan, not vichan: `_id`/`postId`/`replyposts`, a `{boards,page,maxPage}` board list). Not probed, domains unknown: Autismchan, Bantculture, 39chan, Flying Dog Island, Azu. Adding a site later is one registry entry if it fits an existing family.

Verified boards for Leftypol include `overboard`, whose posts carry a per-post `board` field; the adapter treats it as a normal board and reads each thread's real board from that field.

## Verified wire formats

Classic family (`vichan`): `GET {base}/{board}/catalog.json` → list of `{page, threads:[…]}`. `GET {base}/{board}/res/{no}.json` → `{posts:[…]}`. Thread/post fields seen: `no, resto, sub, com, name, trip, capcode, email, time, last_modified, replies, images, sticky(int), locked(int), cyclical, omitted_posts, omitted_images, tn_w, tn_h, w, h, fsize, filename, ext, tim(str), md5, extra_files:[{tn_w,tn_h,w,h,fsize,filename,ext,tim,md5}]`. `tim` is a string (`1700000000000` or `1700000000000-9`). Files: `{base}/{board}/src/{tim}{ext}`. Thumbnails: `{base}/{board}/thumb/{tim}{x}` where `x` is **not in the JSON**: observed `.jpg`→`.jpg`, `.png`→`.png` (Wizchan, Lainchan) but `.jpg`→`.png` on Sushichan.

Files-list family (`vichan-files`, Leftypol): same endpoints; each post has `files:[{id, mime, ext, w, h, fsize, filename, tim, spoiler(bool), md5, file_path, thumb_path}]` with `file_path` like `/leftypol/src/<tim>-6.jpg` and `thumb_path` like `/leftypol/thumb/<tim>-6.webp`. URLs are `{base}{file_path}` and `{base}{thumb_path}`: no guessing. Catalog threads carry `files` and a `board` field.

Board lists: no `boards.json` on these sites (404), and Kissu/Uboachan home pages have no board list, so boards come from the shipped registry plus user additions and a typed code. Pages are 0-based but LurkMoar only uses the catalog, so this does not matter.

Comment HTML (sampled as href/class patterns only): quote links are `<a onclick="…" href="/{board}/res/{thread}.html#{post}">` with **no `quotelink` class** (Kissu: `/{board}/res/{thread}#{post}`, no `.html`; cross-board links like `/qa/res/N#N` occur). Greentext is `<span class="quote">`; other seen classes: `orangeQuote`, `heading`, `spoiler`, `yen`, `glowpink`, `glowgold`, `hljs-*`. Tags seen: `br wbr a span pre code em strong s strike u li ol details summary`.

## Design

### Identity: `site` everywhere
A board is addressed by `(site, board)`. `site` is a registry id (`"4chan"` for the existing behaviour). It is the first parameter wherever a board is named: `Repo.request_catalog(site, board)`, `request_thread(site, board, no)`, `request_media(site, board, att)`, `thumb_image/thumb_failed(site, board, att)`, `cached_*`, `db.bookmark_*`, `fav_*`, `nav_*`, `recent_*`. Qt signals gain a leading `site` argument. `MainWindow` tracks `self.site` next to `self.board`.

### Site registry (`sites.py`, `sites.json`)
`src/lurkmoar/sites.json` ships the table above. Each entry: `id, name, base, family, order, boards:[{code,title,nsfw}], json_interval (1.0), media_interval (0.35), thread_url` (a page-URL template, e.g. `{base}/{board}/res/{no}.html#{post}`; Kissu omits `.html`). 4chan's entry has `family:"4chan"` and no boards (they come from `boards.json` as today). `sites.load_sites(config)` merges user additions from `config.json`:

```
"extra_boards": {"kissu": ["a", "qa"]},   // codes added to a site's list
"hidden_sites": ["wizchan"]               // sites to leave out of the rail and picker
```
Board codes for non-4chan sites must match `[a-z0-9_]{1,16}`; invalid codes are dropped with a one-line log, never an exception. 4chan keeps its stricter `[a-z0-9]{1,10}`. Site order: 4chan first, then by `order`, then name.

Typed board codes: the board picker accepts `site board` (`lain sec`) or a bare code, which is looked up in the current site. An unknown code is tried once; a 404 on its catalog shows the existing "no longer available / couldn't reach" banner and the code is not remembered.

### Adapters (`adapters.py`)
One small adapter object per family, each pure (JSON in, models out) and stateless:

- `FourChan` wraps today's `models.*.from_api` logic (moved, not rewritten).
- `Vichan` and `VichanFiles` implement:
  `catalog_url(site, board)`, `thread_url(site, board, no)`, `parse_catalog(site, board, data) -> list[ThreadSummary]`, `parse_thread(site, board, no, data) -> Thread`.
  Both families map the same fields to the same models. Differences are limited to attachment extraction.

Models change:
- `ThreadSummary`, `Thread`, `Post` gain `site`. `Post.attachments: tuple[Attachment, ...]`; `Post.attachment` becomes a property returning the first or `None`. `Thread.images` counts all live attachments.
- `Attachment.id` is `int | str` (4chan: int `tim`; others: the string `tim`, or `file id`+index for `files` lists). Attachment gains `thumbnail_alts: tuple[str, ...]` (fallback thumbnail URLs). `thumbnail_url` is the first candidate. `original_url` is always absolute.
- Classic thumbnail candidates, in order: the original extension if it is an image type (`.jpg .jpeg .png .gif .webp`), then `.png`, `.jpg`, `.webp`, de-duplicated. For video originals the order is `.jpg`, `.png`, `.webp`. The loader remembers per `(site, board)` which extension last succeeded and tries it first.
- `vichan-files` uses `file_path` / `thumb_path` verbatim and has no alternatives.
- Sparse payloads never raise: missing `sub/com/tim/files`, `filedeleted`-style deleted markers, a non-list `extra_files`, non-string `tim`, absolute vs relative paths.
- `sticky` and `locked` may be int or bool; `locked` maps to `closed`.

Attachment filenames and board codes in URLs are validated (`[a-z0-9_]`, `tim` and extensions restricted to `[A-Za-z0-9._-]`) before a URL is built, so a hostile payload cannot redirect a request to another host or path.

### Comment parsing
`parse_comment(html, ctx=None)` gains an optional context `(board, thread)`. A link becomes a **quote** when either it has class `quotelink` (4chan) or its href matches `^/([a-z0-9_]+)/res/(\d+)(?:\.html)?#(\d+)$` or `^#p?(\d+)$`. `quote_target(href)` returns `(board, thread, post)` for all forms; `references(spans, board, thread)` returns posts in the same thread (target board and thread equal the context; `#N`/`#pN` forms are always same-thread). 4chan's existing forms keep working. New class mappings: `span.spoiler` and `<s>`/`<strike>` → spoiler; `span.heading` and `strong` → bold; `span.orangeQuote` and `span.quote` → greentext; `<details>/<summary>/<wbr>/<li>/<ol>` render as plain text; every other class is ignored. The hostile-input and linear-time guarantees from the first spec still hold and keep their tests.

### Network
`SiteClients` holds one `api.Client` per site host (JSON, `json_interval` between requests) and one lower-rate media client per site (`media_interval`). Files and thumbnails live on the **same host** as the JSON on these sites, so media requests are paced separately but never faster than `media_interval` (default 0.35 s, roughly 3 per second). 4chan keeps today's two clients. Retry/backoff, If-Modified-Since, 304 handling and the same-key 10 s TTL are unchanged. Non-JSON responses (a challenge or error HTML page) are treated as the existing "bad response" error and surface the existing banner; no site-specific handling. Timeouts stay at 10 s. `api.py` remains the only module importing httpx and still exposes only `get()` and `close()`.

The thumbnail loader tries `thumbnail_url` then `thumbnail_alts` on a 404, a non-image body or a decode failure, stops at the first success, and records failure only after all candidates fail.

### Data and migration
`db.py` schema version 2 (stored in `PRAGMA user_version`). Migration, run once inside a transaction, keeps all data:
- `bookmarks`, `favourites`, `nav`, `recent` gain `site TEXT NOT NULL DEFAULT '4chan'`; primary keys become `(site, board, thread_id)`, `(site, board)`, etc. Tables are rebuilt with copy-and-rename.
- `cache` keys: existing 4chan keys stay as they are; other sites use a `{site}:` prefix (`lainchan:catalog:sec`, `lainchan:thread:sec:123`).
- `kv`: `last_board` stays; `last_site` is added (absent means `4chan`); `last_view` becomes `thread:{site}:{board}:{no}` and the old `thread:{board}:{no}` form is still read.
- `prune_threads` keeps bookmarked threads for every site.
- `favourites` ordering stays by `pos` within a site.
Downgrade is not supported; a backup copy of the db file is written to `lurkmoar.db.v1.bak` before the first migration.

### Interface
- **Left rail:** favourites grouped under non-selectable site headers, sites in registry order, boards in each group in the order they were favourited. The current board is shown under its site's header even if it is not a favourite (as today). `Up/Down` skip headers; the rest of the rail's keyboard behaviour is unchanged. The rail never shows a header with no boards under it.
- **Board picker:** one list grouped by site with the same headers; typing filters across all sites (match on board code, board title, site name or id); `Enter` opens; the favourite toggle applies to the highlighted board of the highlighted site. NSFW boards keep the `NSFW` tag. 4chan's list still loads from `boards.json`; the others are instant.
- **Header and titles:** `Lainchan /sec/ Security` in the header; the board title line in the catalog gets the site name; thread header shows `Lainchan /sec/ › No.123`.
- **URLs:** `O` and `C` produce each site's own page URL (4chan `boards.4chan.org/{b}/thread/{n}#p{post}`; vichan `{base}/{b}/res/{n}.html#{post}`, Kissu `{base}/{b}/res/{n}#{post}` via a registry field `thread_url` template). The cross-thread quote prompt names the right site and board; "open on site" uses that template. Links to other boards on the same site open in-app; links to other sites are opened externally only.
- **Bookmarks screen:** each row is prefixed with the site name when it is not 4chan; refresh checks each `(site, board)` once.
- **Gallery and save:** unchanged, but a post with several attachments contributes all of them to the gallery in order; the post shows its first thumbnail plus a muted `+N more files` caption. Saved files are named as today and placed in `save_dir/{site}/` for non-4chan sites (4chan keeps the flat folder).
- **About/help:** the About line becomes "LurkMoar is an independent read-only client. Content is sourced from the sites you open and belongs to them. Not affiliated with or endorsed by any of them."
- **Welcome screen:** unchanged text; the picker lists all sites.

### Errors and edge cases
- A site that stops answering behaves like 4chan offline: cached copy plus banner plus Retry; nothing site-specific blocks the rest of the app.
- A board that exists in the registry but 404s is shown as usual, never removed automatically.
- The catalog `board` field on `overboard` threads is used for thread URLs and bookmarks.
- Duplicate attachment ids inside one thread are disambiguated by appending the index.
- Quote to a post not in the thread keeps the existing message.

### Testing
All tests use synthetic fixtures shaped like the probes, in `tests/samples_vichan.py` (no scraped content, no live traffic). New tests: adapter field mapping for both families including sparse and hostile payloads (host-escaping `tim`/`ext`, huge `extra_files`); thumbnail candidate order and fallback with a fake client; quote-link parsing for all observed href forms and for the old 4chan forms; span class mapping; registry merge, validation and ordering; DB migration from a v1 file (all bookmarks, favourites, nav, recents and cache survive and reload); rail grouping, header skipping and keyboard navigation; picker grouping, filtering and `site board` entry; per-site rate-floor independence; multi-attachment gallery order and the `+N more files` caption; URL templates; a regression test that 4chan behaviour is byte-for-byte unchanged for the existing fixtures. The suite stays offline and under about 40 s. Live verification is manual: open one board per site, one thread, one image, one video, save, bookmark, relaunch.

## Deferred

jschan and LynxChan adapters (Sportschan, Erischan, zzzchan, Chaddy, 8chan.moe, Endchan, Capybarachan), 8kun, Cloudflare-gated sites, automatic board discovery, a site-management screen (sites and boards are edited in `config.json` for now), search across sites.
