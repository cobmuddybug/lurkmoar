import json

from lurkmoar.sites import FOURCHAN, key, load_sites, valid_board


def test_registry_order_and_ids():
    s = load_sites()
    assert list(s) == ["4chan", "kissu", "lainchan", "leftypol", "sushichan", "uboachan", "wizchan"]
    assert s["4chan"] is FOURCHAN or s["4chan"] == FOURCHAN
    assert s["leftypol"].family == "vichan-files" and s["lainchan"].family == "vichan"


def test_shipped_boards_are_valid_and_present():
    s = load_sites()
    assert {"sec", "inter", "lit"} <= {b.code for b in s["lainchan"].boards}
    assert {"b", "jp"} <= {b.code for b in s["kissu"].boards}
    assert {"yn", "yndd", "ot"} <= {b.code for b in s["uboachan"].boards}
    assert "overboard" in {b.code for b in s["leftypol"].boards}
    for site in s.values():
        assert all(valid_board(site, b.code) for b in site.boards)


def test_page_url_templates():
    s = load_sites()
    assert s["4chan"].page_url("g", 5, 7) == "https://boards.4chan.org/g/thread/5#p7"
    assert s["4chan"].page_url("g", 5) == "https://boards.4chan.org/g/thread/5"
    assert s["lainchan"].page_url("sec", 5, 7) == "https://lainchan.org/sec/res/5.html#7"
    assert s["lainchan"].page_url("sec", 5) == "https://lainchan.org/sec/res/5.html"
    assert s["kissu"].page_url("b", 5, 7) == "https://kissu.moe/b/res/5#7"


def test_extra_boards_merge_validate_and_dedupe():
    s = load_sites(extra_boards={"kissu": ["qa", "b", "BAD CODE", "../x", "a" * 20], "nosuch": ["x"],
                                 "4chan": ["zz"]})
    codes = [b.code for b in s["kissu"].boards]
    assert "qa" in codes and codes.count("b") == 1
    assert not any(c in codes for c in ("BAD CODE", "../x"))
    assert s["4chan"].boards == ()                       # 4chan's list comes from boards.json only


def test_hidden_sites_removed():
    s = load_sites(hidden=["wizchan", "nosuch"])
    assert "wizchan" not in s and "lainchan" in s


def test_bad_registry_file_falls_back_to_4chan_only(tmp_path):
    f = tmp_path / "s.json"
    f.write_text("{nope")
    assert list(load_sites(path=f)) == ["4chan"]


def test_valid_board_rules():
    s = load_sites()
    assert valid_board(s["lainchan"], "sec") and valid_board(s["lainchan"], "a_b")
    assert not valid_board(s["lainchan"], "Sec") and not valid_board(s["lainchan"], "a/b")
    assert valid_board(s["4chan"], "g") and not valid_board(s["4chan"], "a_b")


def test_cache_keys_keep_4chan_unchanged():
    assert key("4chan", "boards") == "boards"
    assert key("4chan", "catalog", "g") == "catalog:g"
    assert key("4chan", "thread", "g", 12) == "thread:g:12"
    assert key("lainchan", "catalog", "sec") == "lainchan:catalog:sec"
    assert key("lainchan", "thread", "sec", 12) == "lainchan:thread:sec:12"
