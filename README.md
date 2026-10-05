# LurkMoar

A fast, local, read-only desktop browser for 4chan, built for Omarchy. Board → Catalog → Thread → Media.
No posting, no captcha, no accounts: the network layer exposes `GET` and nothing else.

## Run

    ./install.sh          # venv, ~/.local/bin/lurkmoar, desktop entry, SUPER+ALT+L
    lurkmoar

Press `?` inside the app for shortcuts. `B` chooses a board, `/` filters the catalog, `Enter` opens,
`Esc` goes back (and undoes quote jumps first).

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
| video_command | "mpv" | player for .webm/.mp4 |
| auto_refresh | true | refresh the open thread |
| refresh_seconds | 30 | interval (minimum 10) |

Data: cache `~/.cache/lurkmoar/`, bookmarks and state `~/.local/share/lurkmoar/lurkmoar.db`.
Colours follow the current Omarchy theme (`~/.local/state/omarchy/current/theme/colors.toml`).

## Develop

    uv venv --system-site-packages .venv && uv pip install --python .venv/bin/python pytest -e .
    .venv/bin/pytest

LurkMoar is an independent read-only client. Content sourced from 4chan. Not affiliated with or endorsed by 4chan.
