"""Semantic colour roles. Change a role here, never hunt hex codes in widgets."""
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

COLORS_TOML = Path.home() / ".local/state/omarchy/current/theme/colors.toml"
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


def derive(bg, fg, accent, error="#f7768e") -> Theme:
    return Theme(
        background=bg, surface=mix(bg, fg, .05), surface_hover=mix(bg, fg, .09),
        surface_selected=mix(bg, accent, .25), foreground=fg,
        foreground_muted=mix(bg, fg, .6), accent=accent, accent_muted=mix(bg, accent, .5),
        quote="#789922", link=accent, warning="#e0af68", error=error,
        new_post=accent, spoiler=mix(bg, fg, .3), border=mix(bg, fg, .16))


DEFAULT = derive("#0f1115", "#e6e6e6", "#7aa2f7")


def load_theme(path=COLORS_TOML) -> Theme:
    try:
        with open(path, "rb") as f:
            c = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return DEFAULT

    def pick(key, default):
        v = c.get(key)
        return v.lower() if isinstance(v, str) and HEX.fullmatch(v) else default

    return derive(pick("background", DEFAULT.background), pick("foreground", DEFAULT.foreground),
                  pick("accent", DEFAULT.accent), pick("color1", "#f7768e"))


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
