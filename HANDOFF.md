# LurkMoar handoff

Written 2026-10-03 at the end of the design and planning session. Read this first, then the two docs it points to.

## State

- **No product code exists yet.** The repo holds only the spec and the plan (plus this file and `CLAUDE.md`).
- Spec (approved by the user): `docs/superpowers/specs/2026-10-03-lurkmoar-design.md`
- Implementation plan (written, **not yet reviewed or approved by the user**): `docs/superpowers/plans/2026-10-03-lurkmoar.md`
  - 11 tasks, TDD, each ends in a commit. Nothing in it has been run, so expect small Qt API fixes while executing.
- Git: initialised in this folder, three commits (spec, spec update, plan). No remote.

## What it is

A lean, read-only 4chan reader for Omarchy (Board → Catalog → Thread → Media). Python, PySide6, httpx, stdlib sqlite3. The original product brief was pasted into the first session and is not stored here. The spec captures every decision that matters; where the spec is silent, follow the design philosophy in the spec ("calm, discoverable, always show state, no invisible modes").

## Next step

1. Ask the user to review the plan and choose an execution method:
   - **Subagent-driven** (recommended): skill `superpowers:subagent-driven-development`
   - **Native**: skill `superpowers:executing-plans`
2. Do not start implementing before they answer. They approved the spec, not the plan.
3. Execute Task 1 onward in order. Tasks 6–10 share names (page protocol, `MainWindow` methods), so keep the plan's signatures exactly.

## Decisions made with the user

- Lean: only PySide6 and httpx at runtime (no qasync, platformdirs, bleach). About 12 modules.
- Thread reader is `QListView` + delegate (virtualised), not a widget per post.
- Phase 6 polish is out of scope. Also cut: archive.json, grid catalog, settings UI, thread-level `/` filter.
- Launcher: reuse the existing **SUPER+ALT+L** binding (it currently launches the old AppImage at `~/.local/opt/LurkMoar/LurkMoar.AppImage`). The installer repoints that line in `~/.config/hypr/bindings.lua` (backup `bindings.lua.bak.lurkmoar` first), overwrites the old `~/.local/share/applications/LurkMoar.desktop` (keeping a `.old-appimage` copy), and never deletes the old AppImage.
- Thumbnails and media come from the CDN host through a second `Client(min_interval=0.05)`. The 1 req/s floor applies to the API host only.
- Deleted thread with a cached copy: show the cached copy at once and explain in a banner (no separate "Read cached copy" button).

## Environment facts checked

- System Python 3.14.7, PySide6 6.11.2, httpx 0.28.1, mpv and uv installed. pytest is **not** installed system-wide; the plan creates `.venv` with `--system-site-packages` and installs pytest there.
- Omarchy theme colours: `~/.local/state/omarchy/current/theme/colors.toml` (flat keys: `accent`, `background`, `foreground`, `color0`…`color15`).
- Other projects in `~/Projects/` follow "edit the repo, rerun install.sh" and use an env var like `X_HOME` for test isolation. Here it is `LURKMOAR_HOME` (set by `tests/conftest.py`).
- `~/Projects/lurkmoar` did not exist before this session. The old LurkMoar is only the AppImage.

## Cautions

- Read-only is a hard constraint: `api.Client` exposes `get()` and `close()` only, and a test greps `src/` for write verbs.
- Never hit the real 4chan API from automated tests. All tests use `FakeApi`/`FakeCdn` in `tests/helpers.py`. Live checks are manual and small (the plan marks them).
- `install.sh` edits the user's Hyprland config. Run it only at the end of Task 11, and tell the user what it changed.
- Commit trailer on every commit: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
