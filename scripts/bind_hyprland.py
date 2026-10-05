#!/usr/bin/env python3
"""Opt-in helper: bind a key to LurkMoar in an Omarchy bindings.lua. Run by `install.sh --bind`.

Usage: bind_hyprland.py BINDINGS_LUA [KEYS]       (KEYS default: "SUPER + ALT + L")

Adds a line, or re-points an existing LurkMoar line (keeping its keys unless KEYS is given). Refuses to take keys
that are already bound to something else. The original file is copied to BINDINGS_LUA.bak.lurkmoar before the first
change and that backup is never overwritten.
"""
import re
import shutil
import sys
from pathlib import Path

DEFAULT_KEYS = "SUPER + ALT + L"
COMMAND = 'os.getenv("HOME") .. "/.local/bin/lurkmoar"'
EXISTING = re.compile(r'^o\.bind\("([^"]*)",\s*"LurkMoar",.*\)[ \t]*$', re.M)


class BindError(Exception):
    pass


def line_for(keys):
    return f'o.bind("{keys}", "LurkMoar", {COMMAND})'


def apply(path, keys=None):
    path = Path(path)
    if not path.is_file():
        raise BindError(f"No bindings file at {path}")
    src = path.read_text()
    mine = EXISTING.search(src)
    if mine:
        new = line_for(keys or mine.group(1))
        out = EXISTING.sub(lambda m: new, src, count=1)
        status = "unchanged" if out == src else "repointed"
    else:
        if "o.bind(" not in src:
            raise BindError(f"{path} has no o.bind(...) lines, so it is not in the format this helper edits")
        keys = keys or DEFAULT_KEYS
        if f'o.bind("{keys}"' in src:
            raise BindError(f'"{keys}" is already bound to something else in {path}')
        out, status = src.rstrip("\n") + "\n" + line_for(keys) + "\n", "added"
    if out != src:
        backup = path.with_name(path.name + ".bak.lurkmoar")
        if not backup.exists():
            shutil.copy2(path, backup)
        path.write_text(out)
    return status, f"{status}: {line_for(keys or (mine.group(1) if mine else DEFAULT_KEYS))}"


def main(argv):
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2
    keys = argv[1] if len(argv) > 1 else None
    try:
        _, message = apply(argv[0], keys)
    except BindError as e:
        print(f"Could not add the key binding: {e}\nAdd it by hand if you want one:\n  {line_for(keys or DEFAULT_KEYS)}",
              file=sys.stderr)
        return 1
    print(message)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
