import re
from dataclasses import asdict

from lurkmoar.theme import DEFAULT, load_theme, mix, stylesheet


def test_default_when_missing(tmp_path):
    assert load_theme(tmp_path / "nope.toml") == DEFAULT


def test_bad_toml_is_default(tmp_path):
    f = tmp_path / "c.toml"
    f.write_text("= = =")
    assert load_theme(f) == DEFAULT


def test_accent_and_background_from_file(tmp_path):
    f = tmp_path / "c.toml"
    f.write_text('accent="#112233"\nbackground="#000000"\nforeground="#ffffff"\n')
    t = load_theme(f)
    assert t.accent == "#112233" and t.background == "#000000"


def test_invalid_colour_ignored(tmp_path):
    f = tmp_path / "c.toml"
    f.write_text('accent="red"\n')
    assert load_theme(f).accent == DEFAULT.accent


def test_roles_are_hex_and_mix():
    assert all(re.fullmatch(r"#[0-9a-f]{6}", v) for v in asdict(DEFAULT).values())
    assert mix("#000000", "#ffffff", 0.5) == "#808080"


def test_stylesheet_mentions_accent():
    assert DEFAULT.accent in stylesheet(DEFAULT, 11)
