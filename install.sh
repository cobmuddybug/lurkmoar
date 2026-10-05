#!/usr/bin/env bash
# Install LurkMoar for the current user. Safe to re-run.
#
#   ./install.sh                 install the launcher, desktop entry and icon (no keybinding)
#   ./install.sh --bind          also bind a key in Omarchy's ~/.config/hypr/bindings.lua (default SUPER + ALT + L)
#   LURKMOAR_KEYS="SUPER + L" ./install.sh --bind     use different keys
#
# It creates ./.venv, ~/.local/bin/lurkmoar, ~/.local/share/applications/LurkMoar.desktop and an icon. It touches
# nothing else; the Hyprland keybinding is only edited when you pass --bind (and the file is backed up first).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
cd "$here"

bind=0
for arg in "$@"; do
  case "$arg" in
    --bind) bind=1 ;;
    -h|--help) sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $arg (try --help)" >&2; exit 2 ;;
  esac
done

command -v uv >/dev/null || { echo "uv is required (https://docs.astral.sh/uv/). Install it and re-run." >&2; exit 1; }

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
if [ -f "$app" ] && ! cmp -s "$app" assets/desktop/LurkMoar.desktop && [ ! -f "$app.bak" ]; then
  cp "$app" "$app.bak"                       # keep whatever entry was there before, once
  echo "Existing LurkMoar.desktop saved as $app.bak"
fi
install -m644 assets/desktop/LurkMoar.desktop "$app"
update-desktop-database ~/.local/share/applications 2>/dev/null || true

bindings=~/.config/hypr/bindings.lua
if [ "$bind" = 1 ]; then
  if python3 scripts/bind_hyprland.py "$bindings" ${LURKMOAR_KEYS:+"$LURKMOAR_KEYS"}; then
    hyprctl reload >/dev/null 2>&1 || true
  fi
else
  echo "No keybinding was added. To bind a key on Omarchy, re-run with --bind, or add this to $bindings:"
  echo '  o.bind("SUPER + ALT + L", "LurkMoar", os.getenv("HOME") .. "/.local/bin/lurkmoar")'
fi
echo "Installed. Start it with: lurkmoar"
