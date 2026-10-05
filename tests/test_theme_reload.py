import os
import shutil
from pathlib import Path

from helpers import make_window, pump
from lurkmoar.theme import DEFAULT, read_theme

DARK = 'accent = "#112233"\nbackground = "#000000"\nforeground = "#ffffff"\n'
LIGHT = 'accent = "#aa5500"\nbackground = "#fafafa"\nforeground = "#101010"\n'


def make_current(tmp_path, colors=DARK):
    """A directory shaped like ~/.local/state/omarchy/current: theme/colors.toml plus theme.name."""
    cur = tmp_path / "current"
    (cur / "theme").mkdir(parents=True)
    (cur / "theme" / "colors.toml").write_text(colors)
    (cur / "theme.name").write_text("first\n")
    return cur


def swap_theme(cur, colors, name):
    """What omarchy-theme-set does: stage next-theme, rm -rf theme, mv into place, then write theme.name."""
    nxt = cur / "next-theme"
    nxt.mkdir()
    (nxt / "colors.toml").write_text(colors)
    shutil.rmtree(cur / "theme")
    os.rename(nxt, cur / "theme")
    (cur / "theme.name").write_text(name + "\n")


def window_for(qapp, cur):
    win, *_ = make_window(qapp, theme_path=cur / "theme" / "colors.toml")
    return win


def test_read_theme_returns_none_when_missing_or_broken(tmp_path):
    assert read_theme(tmp_path / "nope.toml") is None
    bad = tmp_path / "bad.toml"
    bad.write_text("= = =")
    assert read_theme(bad) is None
    good = tmp_path / "good.toml"
    good.write_text(DARK)
    assert read_theme(good).accent == "#112233"


def test_window_starts_with_the_theme_on_disk(qapp, tmp_path):
    win = window_for(qapp, make_current(tmp_path))
    assert win.theme.accent == "#112233"


def test_reload_applies_to_stylesheet_and_every_view(qapp, tmp_path):
    cur = make_current(tmp_path)
    win = window_for(qapp, cur)
    rev = win.thread.delegate._rev
    (cur / "theme" / "colors.toml").write_text(LIGHT)
    win._reload_theme()
    assert win.theme.accent == "#aa5500" and win.theme.background == "#fafafa"
    assert "#aa5500" in qapp.styleSheet()
    assert win.catalog.delegate.t is win.theme and win.thread.delegate.t is win.theme and win.catalog.t is win.theme
    assert win.thread.delegate._rev > rev                   # cached post documents had the old colours baked in
    assert win.viewer.canvas.bg == "#fafafa" and "#fafafa" in win.viewer.styleSheet()


def test_unchanged_colours_do_not_reapply(qapp, tmp_path):
    cur = make_current(tmp_path)
    win = window_for(qapp, cur)
    calls = []
    win.apply_theme = lambda t: calls.append(t)
    win._reload_theme()
    assert calls == []


def test_missing_or_broken_file_keeps_the_current_theme(qapp, tmp_path):
    cur = make_current(tmp_path)
    win = window_for(qapp, cur)
    (cur / "theme" / "colors.toml").write_text("= = =")
    win._reload_theme()
    assert win.theme.accent == "#112233"
    (cur / "theme" / "colors.toml").unlink()
    win._reload_theme()
    assert win.theme.accent == "#112233"


def test_omarchy_style_theme_swap_is_picked_up_automatically(qapp, tmp_path):
    cur = make_current(tmp_path)
    win = window_for(qapp, cur)
    swap_theme(cur, LIGHT, "second")
    assert pump(qapp, lambda: win.theme.accent == "#aa5500", timeout=5)
    swap_theme(cur, DARK, "third")                          # a second swap works too: watches were re-armed
    assert pump(qapp, lambda: win.theme.accent == "#112233", timeout=5)


def test_a_burst_of_events_reloads_once(qapp, tmp_path):
    cur = make_current(tmp_path)
    win = window_for(qapp, cur)
    calls = []
    win._reload_theme = lambda: calls.append(1)
    for _ in range(5):
        win._theme_event()
    pump(qapp, lambda: False, timeout=0.8)
    assert calls == [1]


def test_no_watch_when_the_omarchy_directory_does_not_exist(qapp, tmp_path):
    win = window_for(qapp, tmp_path / "absent")
    assert win.theme == DEFAULT
    assert win._theme_watcher.directories() == [] and win._theme_watcher.files() == []
