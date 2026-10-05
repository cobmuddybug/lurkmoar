# LurkMoar

A fast, local, read-only desktop browser for 4chan and a handful of vichan-family imageboards, built for Omarchy.
Board → Catalog → Thread → Media.
No posting, no captcha, no accounts: the network layer exposes `GET` and nothing else.

## Run

    ./install.sh          # venv, ~/.local/bin/lurkmoar, desktop entry, SUPER+ALT+L
    lurkmoar

Press `?` inside the app for shortcuts. `B` chooses a board, `/` filters the catalog, `Enter` opens,
`Esc` or `Backspace` goes back (and undoes quote jumps first; Backspace still edits text in the filter box). `←` moves focus to the board list on the left
(`↑`/`↓` to pick, `Enter` to open, `→` or `Esc` to return).
In a thread, opening any image or video starts a gallery: `←`/`→` cycle through the thread's media (wrapping),
`S` saves the file to `save_dir` (original name, never overwriting),
`Space` pauses, `M` mutes, `[` `]` seek, `V` hands the video to mpv.

## Sites

4chan, Kissu, Lainchan, Leftypol, Sushichan, Uboachan and Wizchan. The left rail groups your favourite boards under
a header per site; the board picker (`B`) lists every site and accepts `site board` (e.g. `lain sec`) or a bare code
for the current site, so boards that are not in the shipped list can still be opened. Files and thumbnails on these
sites come from the same host as the pages, so they are fetched at a gentler rate (about 3 per second) and one
request per second is used for the page data.

Add boards to a site, or hide a site, in `config.json`:

    "extra_boards": {"kissu": ["qa", "amv"]},
    "hidden_sites": ["wizchan"]

Sites that were checked and are not supported: soyjak.party (unreachable), Holotower (Cloudflare challenge),
lolcow.farm and Ponychan (no usable catalog), 8kun (media host unreachable), and the jschan sites such as
Sportschan and Erischan (a different API).

## Config

`~/.config/lurkmoar/config.json` is written on first run:

| key | default | meaning |
|---|---|---|
| start_on_last_board | true | reopen the last board |
| restore_thread | true | reopen the thread you left open |
| cache_mb | 1024 | thumbnail and media cache ceiling (LRU) |
| font_size | 11 | body text size in pt |
| thumb_size | 96 | thumbnail box in px |
| reveal_spoilers | false | show spoilered images without clicking |
| save_dir | "~/Downloads/LurkMoar" | where `S` in the viewer saves the current image or video |
| extra_boards | {} | extra board codes per site, e.g. `{"kissu": ["qa"]}` |
| hidden_sites | [] | site ids to leave out of the rail and picker |
| video_command | "mpv" | external player, opened with `V` while a video is showing |
| video_start_muted | true | videos in the viewer start muted (`M` toggles) |
| auto_refresh | true | refresh the open thread |
| refresh_seconds | 30 | interval (minimum 10) |

Data: cache `~/.cache/lurkmoar/`, bookmarks and state `~/.local/share/lurkmoar/lurkmoar.db`.
Colours follow the current Omarchy theme (`~/.local/state/omarchy/current/theme/colors.toml`).

## Develop

    uv venv --system-site-packages .venv && uv pip install --python .venv/bin/python pytest -e .
    .venv/bin/pytest

LurkMoar is an independent read-only client. Content is sourced from the sites you open and belongs to them. Not affiliated with or endorsed by any of them.
