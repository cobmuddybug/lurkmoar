#!/usr/bin/env bash
# Installs LurkMoar for the current user and repoints the existing SUPER+ALT+L binding.
# Safe to re-run. Never deletes the old AppImage in ~/.local/opt/LurkMoar.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
cd "$here"

[ -d .venv ] || uv venv --system-site-packages .venv
uv pip install -q --python .venv/bin/python -e .

mkdir -p ~/.local/bin ~/.local/share/applications ~/.local/share/icons/hicolor/scalable/apps
cat > ~/.local/bin/lurkmoar <<WRAP
#!/bin/sh
exec "$here/.venv/bin/python" -m lurkmoar.main "\$@"
WRAP
chmod +x ~/.local/bin/lurkmoar
install -m644 assets/icon.svg ~/.local/share/icons/hicolor/scalable/apps/lurkmoar.svg
app=~/.local/share/applications/LurkMoar.desktop
[ -f "$app" ] && ! cmp -s "$app" assets/desktop/LurkMoar.desktop && [ ! -f "$app.old-appimage" ] && cp "$app" "$app.old-appimage"
install -m644 assets/desktop/LurkMoar.desktop "$app"
update-desktop-database ~/.local/share/applications 2>/dev/null || true

b=~/.config/hypr/bindings.lua
if [ -f "$b" ]; then
  python3 - "$b" <<'PY'
import re, shutil, sys
path = sys.argv[1]
src = open(path).read()
new = 'o.bind("SUPER + ALT + L", "LurkMoar", home .. "/.local/bin/lurkmoar")'
pat = re.compile(r'^o\.bind\("SUPER \+ ALT \+ L", "LurkMoar",.*\)\s*$', re.M)
if not pat.search(src):
    sys.exit("No existing SUPER + ALT + L LurkMoar binding found; add it by hand: " + new)
out = pat.sub(new, src)
if out != src:
    shutil.copy(path, path + ".bak.lurkmoar")
    open(path, "w").write(out)
    print("Repointed SUPER+ALT+L (backup: bindings.lua.bak.lurkmoar)")
else:
    print("Binding already points at the new launcher")
PY
  hyprctl reload >/dev/null 2>&1 || true
fi
echo "Installed. Launch with SUPER+ALT+L or from the app launcher."
