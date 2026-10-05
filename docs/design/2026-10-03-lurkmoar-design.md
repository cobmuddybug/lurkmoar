# LurkMoar: Design Spec

Read-only imageboard reader for Omarchy (Board → Catalog → Thread → Post/Media). This spec records the design decisions of the first version; later additions have their own documents in this folder. Where it is silent, follow the design philosophy: calm, discoverable, always show state, no invisible modes.

## Goals and constraints

- Lean: few files, few dependencies, no features beyond brief phases 1–5.
- Read-only by construction: the API client exposes `get()` only. No POST anywhere.
- Python 3, PySide6, httpx, stdlib `sqlite3`. Nothing else. (Dropped from the brief: qasync, platformdirs, bleach.)
- Stays responsive on 1000+ post threads: `QListView` + `QAbstractListModel` + `QStyledItemDelegate` for both catalog and thread.

## Out of scope (v1)

Phase 6 polish, archive.json, grid catalog, density/theme settings UI, GIF animation, sync/accounts. Kept because the brief requires them: shortcut help overlay (`?`), About text, deleted-thread handling.

## Layout

```
src/lurkmoar/
  main.py        entry, window, key bindings, view stack, nav history
  api.py         Client: GET-only, 1 req/s queue, If-Modified-Since, backoff, worker thread
  repo.py        cache-or-fetch for boards/catalog/thread/thumb; emits Qt signals; dedupes in-flight
  db.py          sqlite: bookmarks, favourites, nav state, cached thread/catalog JSON, kv
  models.py      dataclasses: Board, ThreadSummary, Thread, Post, Attachment
  parse.py       comment HTML -> list of spans (text/bold/italic/underline/spoiler/quote/code/link)
  theme.py       semantic colour roles, loaded from Omarchy colors.toml if present, else default
  ui_catalog.py  CatalogModel/Delegate/View (+ sort, filter)
  ui_thread.py   ThreadModel/Delegate/View (+ NEW divider, quote jump stack, follow state)
  ui_media.py    overlay viewer (zoom/pan), spoiler cover, mpv launcher
  ui_misc.py     board picker, sidebar, bookmarks view, status bar, help overlay, welcome
```

Layering rule: UI → `repo` → `api`. Only `api.py` imports httpx.

## Data and network

- `api.py` runs one worker `QThread` with a request queue. Min 1 s between requests, global. Sends `If-Modified-Since` from stored `Last-Modified`; a 304 serves cache. Timeouts of 10 s, up to 3 retries with exponential backoff on 5xx and network errors. Results come back to the UI by signal as `(key, data | error, from_cache)`.
- `repo.py` returns cached data immediately with a `cached_at` timestamp, then triggers a refresh. Concurrent requests for the same key share one in-flight job. Thumbnails go through the same queue at low priority and are fetched only for visible rows. Jobs for rows that have scrolled away are dropped before they run. Thumbnails are written to `~/.cache/lurkmoar/thumbnails/`.
- Paths: cache `~/.cache/lurkmoar/{thumbnails,media}`, config `~/.config/lurkmoar/config.json`, db `~/.local/share/lurkmoar/lurkmoar.db`. Media cache is LRU-evicted past the configured ceiling (default 1 GB). Bookmarks and favourites are never evicted.
- Thread auto-refresh defaults to 30 s and is never faster than the client floor.
- Errors map to the brief's wording: offline shows the cached copy with a banner and Retry; a 404 thread shows "no longer available" with a cached copy if one exists; a failed attachment shows "Attachment unavailable" and leaves the post intact.

## UI behaviour

- One window: left rail (favourites, current board, All Boards, Bookmarks; collapsible), a `QStackedWidget` main area (catalog, thread, bookmarks, welcome), a bottom status bar with context shortcuts, and a header showing board, loading state, cached/offline state and updated-ago.
- Catalog rows: thumbnail, subject, "Anonymous · No.", excerpt, replies/images/active-ago. Toolbar: Filter field (`/`), Sort dropdown (activity, replies, images, created), refresh. "N of M threads" feedback while filtering.
- Thread posts: header line (name, No., time, OP/capcode badges), body painted from `parse.py` spans, thumbnail with a size/type caption. NEW divider before the first new post after refresh. Scroll position is preserved on append. The "● Following new posts / ○ Follow paused" indicator is shown in the header. Refresh appends only new rows.
- Quote links: click or Enter on `>>N` pushes the current position onto a jump stack and scrolls to the target, which flashes briefly. Esc pops the stack, and only when the stack is empty does it leave the thread. Cross-thread references offer to open the thread or the official URL.
- Media: Enter/M/click on a thumbnail opens a full-window overlay. Wheel zooms, drag pans, and the keys +, -, 0, 1, O, C and Esc work as in the brief. WebM and MP4 play inside the same overlay (QtMultimedia, looping, muted at start). `←`/`→` cycle every image and video in the thread, wrapping at the ends, and closing the overlay selects the last post shown. `V` hands a video to the configured command (default `mpv`), which is also the fallback when the built-in player errors. Spoilers are covered with "SPOILER / Click or Space to reveal", and revealed state lasts for the session.
- Per-board state (catalog scroll, selected thread, thread scroll) lives in the DB and is restored on Back and on relaunch.
- Keys: as in the brief section 11. Arrow keys are first-class; J/K are aliases.
- Theme: semantic colour roles. `theme.py` reads accent, background and foreground from the Omarchy theme's `colors.toml` when present and falls back to defaults. The window watches the Omarchy `current` directory and re-applies the theme live when it changes (debounced; a missing or unreadable file keeps the current theme).
- Settings: `config.json` with start-on-last-board, restore-thread, cache size, font size, thumbnail size, reveal-spoilers, video command, auto-refresh and interval. There is no settings UI in v1, and the file is documented in the README.

## HTML handling

`parse.py` is a stdlib `html.parser` subclass with a tag whitelist: `br`, `b`/`strong`, `i`/`em`, `u`, `s` (spoiler), `pre`/`code`, and `a` (internal `>>N` quote links become quote spans; external hrefs become link spans). Everything else is emitted as plain text. There is no rich-text widget and no remote HTML renders. External links open via `xdg-open` only after an explicit click.

## Testing

pytest. Parser (fixtures with real-shaped comments, hostile tags), client (GET-only surface, rate floor, 304 handling, backoff, using a fake transport), cache LRU eviction, db round-trips, catalog filter/sort, new-post diff. Manual acceptance journeys A–E from the brief run offscreen with `QT_QPA_PLATFORM=offscreen` where scriptable, and live otherwise.

## Install

`install.sh`: a `uv`-managed venv, a `~/.local/bin/lurkmoar` wrapper, a desktop entry and an icon under `~/.local/share/`. It is idempotent and never touches keybindings unless asked: `./install.sh --bind` runs `scripts/bind_hyprland.py`, which adds (or re-points) a `LurkMoar` line in Omarchy's `~/.config/hypr/bindings.lua`, refuses keys that are already taken, and keeps a one-time backup of the file. An existing `LurkMoar.desktop` that differs is saved once as `LurkMoar.desktop.bak`.

## Attribution

An About line, reachable from the help overlay: "LurkMoar is an independent read-only client. Content sourced from 4chan. Not affiliated with or endorsed by 4chan."
