"""Paths and the small user config. LURKMOAR_HOME redirects everything (tests)."""
import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path


@dataclass(frozen=True)
class Paths:
    cache: Path
    config: Path
    share: Path

    @property
    def thumbs(self): return self.cache / "thumbnails"
    @property
    def media(self): return self.cache / "media"
    @property
    def config_file(self): return self.config / "config.json"
    @property
    def db_file(self): return self.share / "lurkmoar.db"


def paths() -> Paths:
    root = os.environ.get("LURKMOAR_HOME")
    if root:
        r = Path(root)
        p = Paths(r / "cache", r / "config", r / "share")
    else:
        home = Path.home()
        p = Paths(
            Path(os.environ.get("XDG_CACHE_HOME", home / ".cache")) / "lurkmoar",
            Path(os.environ.get("XDG_CONFIG_HOME", home / ".config")) / "lurkmoar",
            Path(os.environ.get("XDG_DATA_HOME", home / ".local/share")) / "lurkmoar",
        )
    for d in (p.thumbs, p.media, p.config, p.share):
        d.mkdir(parents=True, exist_ok=True)
    return p


@dataclass
class Config:
    start_on_last_board: bool = True
    restore_thread: bool = True
    cache_mb: int = 1024
    font_size: int = 11
    thumb_size: int = 96
    reveal_spoilers: bool = False
    video_command: str = "mpv"
    video_start_muted: bool = True
    save_dir: str = "~/Downloads/LurkMoar"
    extra_boards: dict = field(default_factory=dict)
    hidden_sites: list = field(default_factory=list)
    auto_refresh: bool = True
    refresh_seconds: int = 30


def load_config(p: Paths) -> Config:
    cfg = Config()
    try:
        raw = json.loads(p.config_file.read_text())
    except (OSError, ValueError):
        raw = {}
    if isinstance(raw, dict):
        for f in fields(cfg):
            v = raw.get(f.name)
            if v is not None and type(v) is type(getattr(cfg, f.name)):
                setattr(cfg, f.name, v)
    cfg.refresh_seconds = max(10, cfg.refresh_seconds)
    if not p.config_file.exists():
        p.config_file.write_text(json.dumps(asdict(cfg), indent=2) + "\n")
    return cfg
