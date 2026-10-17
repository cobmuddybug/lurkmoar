"""Semantic colour roles. Change a role here, never hunt hex codes in widgets."""
import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

COLORS_TOML = Path.home() / ".local/state/omarchy/current/theme/colors.toml"
DMS_COLORS = Path.home() / ".cache/DankMaterialShell/dms-colors.json"
HEX = re.compile(r"#[0-9a-fA-F]{6}")


def _rgb(h): return [int(h[i:i + 2], 16) for i in (1, 3, 5)]


def mix(a, b, t):
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(_rgb(a), _rgb(b)))


@dataclass(frozen=True)
class Theme:
    background: str
    surface: str
    surface_hover: str
    surface_selected: str
    foreground: str
    foreground_muted: str
    accent: str
    accent_muted: str
    quote: str
    link: str
    warning: str
    error: str
    new_post: str
    spoiler: str
    border: str


def is_light(colour) -> bool:
    r, g, b = _rgb(colour)
    return 0.299 * r + 0.587 * g + 0.114 * b > 140


def derive(bg, fg, accent, error="#f7768e") -> Theme:
    return Theme(
        background=bg, surface=mix(bg, fg, .05), surface_hover=mix(bg, fg, .09),
        surface_selected=mix(bg, accent, .25), foreground=fg,
        foreground_muted=mix(bg, fg, .6), accent=accent, accent_muted=mix(bg, accent, .5),
        quote="#789922", link=accent, warning="#9a6700" if is_light(bg) else "#e0af68", error=error,
        new_post=accent, spoiler=mix(bg, fg, .3), border=mix(bg, fg, .16))


DEFAULT = derive("#0f1115", "#e6e6e6", "#7aa2f7")

AUTO = "auto"
# Built-in palettes: id -> (name, background, foreground, accent, error). Every other role is derived.
PRESETS = {
    "tokyo-night": ("Tokyo Night", "#1a1b26", "#c0caf5", "#7aa2f7", "#f7768e"),
    "catppuccin-mocha": ("Catppuccin Mocha", "#1e1e2e", "#cdd6f4", "#cba6f7", "#f38ba8"),
    "gruvbox-dark": ("Gruvbox Dark", "#282828", "#ebdbb2", "#fe8019", "#fb4934"),
    "nord": ("Nord", "#2e3440", "#e5e9f0", "#88c0d0", "#bf616a"),
    "rose-pine": ("Rosé Pine", "#191724", "#e0def4", "#c4a7e7", "#eb6f92"),
    "catppuccin-latte": ("Catppuccin Latte", "#eff1f5", "#4c4f69", "#8839ef", "#d20f39"),
    "solarized-light": ("Solarized Light", "#fdf6e3", "#586e75", "#268bd2", "#dc322f"),
}


def default_source() -> Path:
    """Omarchy's colors.toml if present, else DankMaterialShell's dms-colors.json (niri + DMS), else the Omarchy path."""
    if COLORS_TOML.exists() or not DMS_COLORS.exists():
        return COLORS_TOML
    return DMS_COLORS


def _read_dms(path) -> "Theme | None":
    try:
        with open(path, "rb") as f:
            d = json.load(f)
        mode = d.get("mode") if d.get("mode") in ("dark", "light") else "dark"
        c, red = d["colors"][mode], d.get("dank16", {}).get("color1", {}).get(mode)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
    if not isinstance(c, dict):
        return None

    def pick(key, default):
        v = c.get(key)
        return v.lower() if isinstance(v, str) and HEX.fullmatch(v) else default

    return derive(pick("background", DEFAULT.background), pick("on_background", DEFAULT.foreground),
                  pick("primary", DEFAULT.accent), pick("error", red if isinstance(red, str) and HEX.fullmatch(red) else "#f7768e"))


def read_theme(path=None) -> "Theme | None":
    """The theme in a colors.toml (Omarchy) or dms-colors.json (DMS), or None if missing or unreadable (callers keep what they have)."""
    path = Path(path) if path else default_source()
    if path.suffix == ".json":
        return _read_dms(path)
    try:
        with open(path, "rb") as f:
            c = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return None

    def pick(key, default):
        v = c.get(key)
        return v.lower() if isinstance(v, str) and HEX.fullmatch(v) else default

    return derive(pick("background", DEFAULT.background), pick("foreground", DEFAULT.foreground),
                  pick("accent", DEFAULT.accent), pick("error", pick("color1", "#f7768e")))


def load_theme(path=None) -> Theme:
    return read_theme(path) or DEFAULT


def custom_themes(themes_dir) -> dict:
    """Your own themes: every *.toml in the themes folder, by file stem (Omarchy colors.toml format)."""
    try:
        files = sorted(Path(themes_dir).glob("*.toml"), key=lambda f: f.stem.lower())
    except OSError:
        return {}
    return {f.stem: f for f in files if f.is_file() and f.stem != AUTO and f.stem not in PRESETS}


def choices(themes_dir) -> list:
    """(id, label, kind) for every selectable theme, in picker order."""
    return ([(AUTO, "Auto (follow Omarchy / DMS)", "auto")]
            + [(k, v[0], "preset") for k, v in PRESETS.items()]
            + [(k, k, "custom") for k in custom_themes(themes_dir)])


def resolve(choice, themes_dir, auto_path=None) -> "tuple[Theme, Path | None]":
    """The theme for a config choice, and the file to watch for live changes (None for a built-in).
    An unknown choice, such as a deleted custom file, falls back to auto."""
    if choice in PRESETS:
        _, bg, fg, accent, error = PRESETS[choice]
        return derive(bg, fg, accent, error), None
    custom = custom_themes(themes_dir).get(choice)
    if custom is not None:
        return load_theme(custom), custom
    path = Path(auto_path or default_source())
    return load_theme(path), path


def stylesheet(t: Theme, pt: int) -> str:
    return f"""
* {{ font-size: {pt}pt; }}
QWidget {{ background: {t.background}; color: {t.foreground}; }}
QLabel {{ background: transparent; }}
QLineEdit, QComboBox {{ background: {t.surface}; border: 1px solid {t.border}; padding: 4px 6px; }}
QLineEdit:focus, QComboBox:focus {{ border-color: {t.accent}; }}
QPushButton, QToolButton {{ background: {t.surface}; border: 1px solid {t.border}; padding: 4px 10px; }}
QPushButton:hover, QToolButton:hover {{ background: {t.surface_hover}; }}
QPushButton:focus, QToolButton:focus {{ border-color: {t.accent}; }}
QListView, QListWidget {{ border: none; outline: 0; }}
QListWidget::item {{ padding: 4px 6px; }}
QListWidget::item:selected {{ background: {t.surface_selected}; color: {t.foreground}; border-left: 3px solid {t.accent}; }}
QScrollBar:vertical {{ width: 10px; background: {t.background}; }}
QScrollBar::handle:vertical {{ background: {t.border}; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QToolTip {{ background: {t.surface}; color: {t.foreground}; border: 1px solid {t.border}; }}
#header, #rail, #statusline {{ background: {t.surface}; }}
#header {{ border-bottom: 1px solid {t.border}; }}
#statusline {{ border-top: 1px solid {t.border}; }}
#brand {{ color: {t.accent}; font-weight: bold; letter-spacing: 2px; }}
#muted {{ color: {t.foreground_muted}; }}
#where {{ border: none; font-weight: bold; text-align: left; background: transparent; }}
#banner {{ background: {t.surface_selected}; border-left: 3px solid {t.warning}; }}
"""
