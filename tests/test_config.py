from lurkmoar.config import load_config, paths


def test_paths_created():
    p = paths()
    assert p.thumbs.is_dir() and p.media.is_dir() and p.config.is_dir() and p.share.is_dir()


def test_defaults_written():
    p = paths()
    cfg = load_config(p)
    assert cfg.video_command == "mpv" and cfg.cache_mb == 1024
    assert p.config_file.exists()


def test_bad_json_falls_back():
    p = paths()
    p.config_file.write_text("{nope")
    assert load_config(p).refresh_seconds == 30


def test_wrong_type_ignored_right_type_kept():
    p = paths()
    p.config_file.write_text('{"cache_mb": "lots", "font_size": 13}')
    cfg = load_config(p)
    assert cfg.cache_mb == 1024 and cfg.font_size == 13


def test_refresh_floor():
    p = paths()
    p.config_file.write_text('{"refresh_seconds": 1}')
    assert load_config(p).refresh_seconds == 10
