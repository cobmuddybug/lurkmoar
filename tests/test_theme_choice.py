import json

from helpers import make_window, pump
from lurkmoar.config import load_config, paths, save_setting
from lurkmoar.theme import AUTO, DEFAULT, HEX, PRESETS, choices, custom_themes, resolve

MINE = 'background = "#101010"\nforeground = "#eeeeee"\naccent = "#ff00aa"\nerror = "#ff0000"\n'


def omarchy(tmp_path, accent="#112233"):
    f = tmp_path / "current" / "theme" / "colors.toml"
    f.parent.mkdir(parents=True)
    f.write_text(f'accent = "{accent}"\nbackground = "#000000"\nforeground = "#ffffff"\n')
    return f


def test_presets_are_complete_and_valid():
    assert len(PRESETS) == 7
    for name, bg, fg, accent, error in PRESETS.values():
        assert name and all(HEX.fullmatch(c) for c in (bg, fg, accent, error))


def test_resolve_preset_custom_auto_and_unknown(tmp_path):
    themes = tmp_path / "themes"
    themes.mkdir()
    (themes / "mine.toml").write_text(MINE)
    auto = omarchy(tmp_path)
    nord, watch = resolve("nord", themes, auto)
    assert nord.background == "#2e3440" and watch is None
    mine, watch = resolve("mine", themes, auto)
    assert (mine.accent, mine.error) == ("#ff00aa", "#ff0000") and watch == themes / "mine.toml"
    assert resolve(AUTO, themes, auto) == (resolve(AUTO, themes, auto)[0], auto)
    assert resolve(AUTO, themes, auto)[0].accent == "#112233"
    assert resolve("deleted-file", themes, auto)[1] == auto          # unknown choice: back to auto


def test_custom_themes_skip_reserved_names_and_missing_folder(tmp_path):
    assert custom_themes(tmp_path / "nope") == {}
    (tmp_path / "nord.toml").write_text(MINE)                         # can't shadow a built-in
    (tmp_path / "auto.toml").write_text(MINE)
    (tmp_path / "Zed.toml").write_text(MINE)
    (tmp_path / "abc.toml").write_text(MINE)
    (tmp_path / "notes.txt").write_text("x")
    assert list(custom_themes(tmp_path)) == ["abc", "Zed"]
    kinds = [k for _, _, k in choices(tmp_path)]
    assert kinds == ["auto"] + ["preset"] * 7 + ["custom"] * 2


def test_broken_custom_file_falls_back_to_default(tmp_path):
    (tmp_path / "bad.toml").write_text("= = =")
    assert resolve("bad", tmp_path)[0] == DEFAULT


def test_save_setting_keeps_other_keys():
    p = paths()
    load_config(p)
    raw = json.loads(p.config_file.read_text())
    raw["something_unknown"] = 5
    p.config_file.write_text(json.dumps(raw))
    save_setting(p, "theme", "nord")
    raw = json.loads(p.config_file.read_text())
    assert raw["theme"] == "nord" and raw["something_unknown"] == 5 and raw["cache_mb"] == 1024
    assert load_config(p).theme == "nord"


def test_choosing_a_preset_applies_saves_and_stops_watching(qapp, tmp_path):
    win, *_ = make_window(qapp, theme_path=omarchy(tmp_path))
    assert win.theme.accent == "#112233" and win._theme_watcher.directories()
    win.set_theme_choice("gruvbox-dark")
    assert win.theme.background == "#282828" and "#fe8019" in qapp.styleSheet()
    assert win.thread.delegate.t is win.theme
    assert not win._theme_watcher.directories() and not win._theme_watcher.files()
    assert load_config(paths()).theme == "gruvbox-dark"
    win._reload_theme()                                               # stray events change nothing
    assert win.theme.background == "#282828"
    win.set_theme_choice(AUTO)
    assert win.theme.accent == "#112233" and win._theme_watcher.directories()


def test_custom_theme_edits_apply_live(qapp, tmp_path):
    p = paths()
    p.themes.mkdir(parents=True, exist_ok=True)
    mine = p.themes / "mine.toml"
    mine.write_text(MINE)
    win, *_ = make_window(qapp, theme_path=omarchy(tmp_path))
    win.set_theme_choice("mine")
    assert win.theme.accent == "#ff00aa" and str(mine) in win._theme_watcher.files()
    mine.write_text(MINE.replace("#ff00aa", "#00ccff"))
    win._reload_theme()
    assert win.theme.accent == "#00ccff"


def test_picker_previews_then_esc_restores(qapp, tmp_path):
    win, *_ = make_window(qapp, theme_path=omarchy(tmp_path))
    win.open_theme_picker()
    picker = win._theme_picker
    assert pump(qapp, picker.isVisible)
    rows = [i for i in range(picker.list.count()) if picker.list.item(i).data(256)]
    assert picker.current() == AUTO and len(rows) == 8
    nord = next(i for i in rows if picker.list.item(i).data(256) == "nord")
    picker.list.setCurrentRow(nord)
    assert win.theme.background == "#2e3440"                          # previewed
    assert load_config(paths()).theme == AUTO                         # but not saved
    picker.reject()
    assert win.theme.accent == "#112233"


def test_picker_enter_keeps_the_choice(qapp, tmp_path):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    win, *_ = make_window(qapp, theme_path=omarchy(tmp_path))
    QTest.keyClick(win, "t")
    picker = win._theme_picker
    assert picker is not None and pump(qapp, picker.isVisible)
    row = next(i for i in range(picker.list.count()) if picker.list.item(i).data(256) == "rose-pine")
    picker.list.setCurrentRow(row)
    QTest.keyClick(picker, Qt.Key_Return)
    assert not picker.isVisible() and win.theme.background == "#191724"
    assert load_config(paths()).theme == "rose-pine" and win.cfg.theme == "rose-pine"


def test_light_presets_get_a_readable_warning_colour(tmp_path):
    assert resolve("solarized-light", tmp_path)[0].warning == "#9a6700"
    assert resolve("catppuccin-latte", tmp_path)[0].warning == "#9a6700"
    assert resolve("nord", tmp_path)[0].warning == "#e0af68"
