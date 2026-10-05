import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("bind_hyprland", Path(__file__).parents[1] / "scripts" / "bind_hyprland.py")
bind = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bind)

LINE = 'o.bind("SUPER + ALT + L", "LurkMoar", os.getenv("HOME") .. "/.local/bin/lurkmoar")'
BASE = 'local o = require("omarchy")\no.bind("SUPER + RETURN", "Terminal", "foot")\n'


def write(tmp_path, text):
    f = tmp_path / "bindings.lua"
    f.write_text(text)
    return f


def test_appends_a_binding_when_none_exists_and_backs_up_once(tmp_path):
    f = write(tmp_path, BASE)
    status, _ = bind.apply(f)
    assert status == "added" and f.read_text() == BASE + LINE + "\n"
    assert (tmp_path / "bindings.lua.bak.lurkmoar").read_text() == BASE


def test_second_run_changes_nothing_and_keeps_the_original_backup(tmp_path):
    f = write(tmp_path, BASE)
    bind.apply(f)
    after = f.read_text()
    status, _ = bind.apply(f)
    assert status == "unchanged" and f.read_text() == after
    assert (tmp_path / "bindings.lua.bak.lurkmoar").read_text() == BASE


def test_repoints_an_existing_lurkmoar_binding_but_keeps_its_keys(tmp_path):
    old = 'o.bind("SUPER + SHIFT + X", "LurkMoar", home .. "/old/path")\n'
    f = write(tmp_path, BASE + old)
    status, _ = bind.apply(f)
    assert status == "repointed"
    assert f.read_text() == BASE + 'o.bind("SUPER + SHIFT + X", "LurkMoar", os.getenv("HOME") .. "/.local/bin/lurkmoar")\n'


def test_explicit_keys_are_used(tmp_path):
    f = write(tmp_path, BASE)
    bind.apply(f, "SUPER + L")
    assert 'o.bind("SUPER + L", "LurkMoar"' in f.read_text()


def test_refuses_keys_already_bound_to_something_else(tmp_path):
    f = write(tmp_path, BASE + 'o.bind("SUPER + ALT + L", "Other", "other")\n')
    with pytest.raises(bind.BindError, match="already bound"):
        bind.apply(f)
    assert not (tmp_path / "bindings.lua.bak.lurkmoar").exists()           # nothing changed, nothing backed up


def test_refuses_a_file_that_is_not_in_the_expected_format(tmp_path):
    f = write(tmp_path, "-- empty\n")
    with pytest.raises(bind.BindError, match="o.bind"):
        bind.apply(f)
    with pytest.raises(bind.BindError, match="No bindings file"):
        bind.apply(tmp_path / "missing.lua")


def test_command_line_prints_the_manual_line_on_failure(tmp_path, capsys):
    f = write(tmp_path, "-- empty\n")
    assert bind.main([str(f)]) == 1
    assert 'o.bind("SUPER + ALT + L", "LurkMoar"' in capsys.readouterr().err
