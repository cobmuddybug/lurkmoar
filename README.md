# LurkMoar

A fast, keyboard-first, **read-only** desktop browser for 4chan and a handful of vichan-family imageboards, built for
[Omarchy](https://omarchy.org). Board → catalog → thread → gallery, with bookmarks, favourites and session restore.

There is no posting, no captcha and no account: the network layer exposes `GET` and nothing else.

## Features

- **Catalog and threads** that stay smooth on 1000+ post threads (virtualised lists), with quote links you can follow
  and undo, a *NEW* divider and position-preserving refresh, and a "following new posts" indicator.
- **Gallery.** Open any image or video and cycle through every file in the thread with the arrow keys. Videos
  (WebM/MP4) play in the same viewer; zoom and pan images; save the current file with one key.
- **Several sites in one place.** Favourite boards sit in the left rail, grouped by site.
- **Bookmarks and recents** with "N → M replies" tracking and an explanation when a thread has expired, plus
  everything restored on relaunch (board, thread, scroll position).
- **Works offline-ish.** Everything is cached; when the network is down you get the cached copy and a clear banner.
- **Follows your Omarchy theme live**: change the theme and LurkMoar restyles itself without a restart.
- Polite by design: per-site request spacing, `If-Modified-Since`, no refetching within 10 s, bounded retries.

## Supported sites

| Site | Engine |
|---|---|
| 4chan | its own JSON API |
| Kissu, Lainchan, Leftypol, Sushichan, Uboachan, Wizchan | vichan family (two JSON variants) |

Sites were checked against their live JSON before being listed. Not supported: soyjak.party (unreachable when
checked), Holotower (Cloudflare challenge), lolcow.farm and Ponychan (no usable catalog), 8kun (media host
unreachable), and sites on other engines such as jschan (Sportschan, Erischan) or LynxChan (8chan.moe, Endchan).
Adding a site that fits an existing family is one entry in `src/lurkmoar/sites.json`.

The board picker (`B`) lists every site and accepts `site board` (for example `lain sec`) or a bare code for the
current site, so boards that are not in the shipped lists can still be opened.

## Install

Requirements: Linux, Python ≥ 3.11, [uv](https://docs.astral.sh/uv/), and `mpv` if you want the external-player
fallback. PySide6 and httpx are installed by the installer (a system PySide6 is reused if present).

    git clone <this repository> lurkmoar && cd lurkmoar
    ./install.sh

This creates `./.venv`, `~/.local/bin/lurkmoar`, a desktop entry and an icon, and nothing else. Start it with
`lurkmoar` or from your app launcher. Re-run `./install.sh` after pulling updates.

**Key binding (opt-in).** On Omarchy you can bind a key with `./install.sh --bind` (default `SUPER + ALT + L`; set
`LURKMOAR_KEYS="SUPER + L"` to choose another). It adds one line to `~/.config/hypr/bindings.lua`, refuses keys that
are already taken, and keeps a one-time backup. Without `--bind`, nothing in your Hyprland config is touched.

## Keys

Press `?` in the app for the full list. The essentials:

| Key | Action |
|---|---|
| `B` | Choose a board (any site) |
| `←` | Move to the board list on the left (`↑`/`↓` pick, `Enter` opens, `→` or `Esc` returns) |
| `/` · `S` · `R` | Filter the catalog · cycle sort · refresh |
| `↑` `↓` (or `K` `J`) | Previous / next item |
| `Enter` | Open the thread; in a thread follow a quote, or open the post's media |
| `Esc` or `Backspace` | Back (undoes quote jumps first; Backspace still edits text in a text box) |
| `M` | Open the selected post's media |
| `←` `→` (in the viewer) | Previous / next file in the thread, wrapping around |
| `S` (in the viewer) | Save the file (original name, never overwrites) |
| `Space` `M` `[` `]` `V` (video) | Pause · mute · seek 5 s · open in mpv |
| `F` · `Shift+F` | Bookmark the thread · favourite the board |
| `O` · `C` | Open the page in a browser · copy its URL |

## Configuration

`~/.config/lurkmoar/config.json` is written on first run. Unknown keys and wrongly-typed values are ignored.

| Key | Default | Meaning |
|---|---|---|
| `start_on_last_board` | `true` | Reopen the last board |
| `restore_thread` | `true` | Reopen the thread you left open |
| `cache_mb` | `1024` | Thumbnail and media cache ceiling (least-recently-used eviction) |
| `font_size` | `11` | Body text size in pt |
| `thumb_size` | `96` | Thumbnail box in px |
| `reveal_spoilers` | `false` | Show spoilered images without clicking |
| `auto_refresh` / `refresh_seconds` | `true` / `30` | Refresh the open thread (minimum 10 s) |
| `video_command` | `"mpv"` | External player, used with `V` on a video |
| `video_start_muted` | `true` | Videos in the viewer start muted |
| `save_dir` | `"~/Downloads/LurkMoar"` | Where `S` saves files (non-4chan sites get a subfolder) |
| `extra_boards` | `{}` | Extra board codes per site, e.g. `{"kissu": ["qa"]}` |
| `hidden_sites` | `[]` | Site ids to leave out of the rail and picker |

Data: cache in `~/.cache/lurkmoar/`, bookmarks and state in `~/.local/share/lurkmoar/lurkmoar.db`. Colours come from the
current Omarchy theme (`~/.local/state/omarchy/current/theme/colors.toml`) and fall back to a built-in palette.

## Development

    uv venv --system-site-packages .venv
    uv pip install --python .venv/bin/python pytest -e .
    .venv/bin/pytest

The suite runs offscreen with fake networking only, and never contacts a real site. The video tests generate a tiny
clip with `ffmpeg` and skip themselves if it is not installed.

Layout: `api.py` (the only httpx user, GET-only), `adapters.py` (site JSON → models), `repo.py` (cache-or-fetch,
thumbnails), `db.py` (sqlite), `parse.py` (whitelisted comment HTML → spans), `ui_*.py` (Qt views), `main.py` (window).
Design notes are in [`docs/design/`](docs/design/).

## Disclaimer

LurkMoar is an independent read-only client. Content is sourced from the sites you open and belongs to them. Not
affiliated with or endorsed by any of them. Some of the supported sites host adult or otherwise objectionable content;
you choose which sites and boards to open, and individual sites can be hidden with `hidden_sites`.
