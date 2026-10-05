import pytest

from lurkmoar.adapters import adapter_for, thumb_exts
from lurkmoar.sites import load_sites
from samples_vichan import FILES_CATALOG, FILES_THREAD, VICHAN_CATALOG, VICHAN_THREAD

S = load_sites()
LAIN, LEFT, KISSU = S["lainchan"], S["leftypol"], S["kissu"]


def test_urls_and_validation():
    a = adapter_for(LAIN)
    assert a.catalog_url(LAIN, "sec") == "https://lainchan.org/sec/catalog.json"
    assert a.thread_url(LAIN, "sec", 10) == "https://lainchan.org/sec/res/10.json"
    for bad in ("../x", "A", "", "a/b", "x" * 17, "a b"):
        with pytest.raises(ValueError):
            a.catalog_url(LAIN, bad)
    with pytest.raises(ValueError):
        a.thread_url(LAIN, "sec", "1/../2")


def test_thumb_exts_order():
    assert thumb_exts(".jpg") == [".jpg", ".png", ".webp"]
    assert thumb_exts(".png") == [".png", ".jpg", ".webp"]
    assert thumb_exts(".webm") == [".jpg", ".png", ".webp"]
    assert thumb_exts(".MP4") == [".jpg", ".png", ".webp"]


def test_classic_catalog_mapping():
    ts = adapter_for(LAIN).parse_catalog(LAIN, "sec", VICHAN_CATALOG)
    assert [t.number for t in ts] == [10, 11, 12]
    t = ts[0]
    assert t.site == "lainchan" and t.board == "sec" and t.subject == "First & thread"
    assert t.comment == "hello\nworld" and t.sticky and not t.closed and t.replies == 4
    assert t.thumbnail.original_url == "https://lainchan.org/sec/src/1700000000000.jpg"
    assert t.thumbnail.thumbnail_url == "https://lainchan.org/sec/thumb/1700000000000.jpg"
    assert t.thumbnail.thumbnail_alts == ("https://lainchan.org/sec/thumb/1700000000000.png",
                                          "https://lainchan.org/sec/thumb/1700000000000.webp")
    assert ts[1].thumbnail is None and ts[1].closed
    assert ts[2].thumbnail.extension == ".webm" and ts[2].thumbnail.id == "1700000000001-9"


def test_classic_thread_mapping_with_extra_files_and_context_references():
    th = adapter_for(LAIN).parse_thread(LAIN, "sec", 10, VICHAN_THREAD, "Mon")
    assert th.site == "lainchan" and th.number == 10 and th.last_modified == "Mon"
    op, p11, p12 = th.posts
    assert op.thread_number == 10 and op.attachment.id == "1700000000000"
    assert p11.references == (10,) and p11.comment_plain == ">>10\nreply"
    assert p12.name == "Anon !abc" and p12.capcode == "Admin"
    assert [a.id for a in p12.attachments] == ["1700000000002-1", "1700000000002-2", "1700000000002-3"]
    assert [a.extension for a in p12.attachments] == [".png", ".gif", ".webm"]
    assert th.images == 4 and th.replies == 2


def test_kissu_style_quote_without_html_suffix_resolves():
    data = {"posts": [{"no": 5, "resto": 0, "time": 1, "com": "op"},
                      {"no": 6, "resto": 5, "time": 2, "com": '<a href="/b/res/5#5">&gt;&gt;5</a>'}]}
    th = adapter_for(KISSU).parse_thread(KISSU, "b", 5, data)
    assert th.posts[1].references == (5,)


def test_files_family_catalog_and_thread():
    a = adapter_for(LEFT)
    ts = a.parse_catalog(LEFT, "leftypol", FILES_CATALOG)
    assert ts[0].board == "alt"                      # overboard threads carry their real board
    assert ts[0].thumbnail.original_url == "https://leftypol.org/alt/src/1700000000010-6.jpg"
    assert ts[0].thumbnail.thumbnail_url == "https://leftypol.org/alt/thumb/1700000000010-6.webp"
    assert ts[0].thumbnail.thumbnail_alts == () and ts[1].thumbnail is None and ts[1].board == "leftypol"
    th = a.parse_thread(LEFT, "alt", 20, FILES_THREAD)
    assert [x.id for x in th.posts[0].attachments] == ["f1", "f2"]
    assert th.posts[0].attachments[0].spoiler and th.posts[0].attachments[1].extension == ".mp4"
    assert th.posts[1].attachment is None


@pytest.mark.parametrize("tim,ext", [("../../etc/passwd", ".jpg"), ("1/../2", ".jpg"), ("a b", ".jpg"),
                                      ("12345", ".jpg/../x"), ("12345", "jpg"), ("12345", ".verylongext"),
                                      ("//evil.example/x", ".jpg"), ("12345", None), (None, ".jpg")])
def test_hostile_classic_file_fields_drop_the_attachment(tim, ext):
    d = {"posts": [{"no": 1, "resto": 0, "time": 1, "com": "x", "tim": tim, "ext": ext, "filename": "f"}]}
    th = adapter_for(LAIN).parse_thread(LAIN, "sec", 1, d)
    assert th.posts[0].attachments == ()


@pytest.mark.parametrize("path,thumb", [("//evil.example/a.jpg", "/a/thumb/x.jpg"), ("https://evil.example/a.jpg", "/a/thumb/x.jpg"),
                                         ("/a/src/../../x.jpg", "/a/thumb/x.jpg"), ("/a/other/x.jpg", "/a/thumb/x.jpg"),
                                         ("/a/src/x y.jpg", "/a/thumb/x.jpg"), (None, "/a/thumb/x.jpg")])
def test_hostile_file_paths_drop_the_attachment(path, thumb):
    d = {"posts": [{"no": 1, "resto": 0, "time": 1, "com": "x",
                    "files": [{"id": "f", "ext": ".jpg", "file_path": path, "thumb_path": thumb}]}]}
    assert adapter_for(LEFT).parse_thread(LEFT, "alt", 1, d).posts[0].attachments == ()


def test_hostile_thumb_path_keeps_file_but_blanks_thumbnail():
    d = {"posts": [{"no": 1, "resto": 0, "time": 1, "com": "x",
                    "files": [{"id": "f", "ext": ".jpg", "file_path": "/a/src/x.jpg", "thumb_path": "//evil.example/t.jpg"}]}]}
    att = adapter_for(LEFT).parse_thread(LEFT, "alt", 1, d).posts[0].attachment
    assert att.original_url == "https://leftypol.org/a/src/x.jpg" and att.thumbnail_url == ""


def test_sparse_and_odd_shapes_do_not_raise():
    a = adapter_for(LAIN)
    d = {"posts": [{"no": 1, "time": 1},
                   {"no": 2, "resto": 1, "extra_files": "nope", "sticky": "1", "com": None, "name": None},
                   {"no": 3, "resto": 1, "extra_files": [None, 5, {"tim": "9", "ext": ".png"}], "tim": "8", "ext": ".jpg"}]}
    th = a.parse_thread(LAIN, "sec", 1, d)
    assert th.posts[0].comment_plain == "" and th.posts[1].name == "Anonymous"
    assert [x.id for x in th.posts[2].attachments] == ["8", "9"]
    assert a.parse_catalog(LAIN, "sec", [{"page": 0}]) == []
    assert a.parse_catalog(LAIN, "sec", [{"page": 0, "threads": [{"no": 1, "sticky": True, "locked": "1"}]}])[0].closed
    with pytest.raises((TypeError, AttributeError)):
        a.parse_catalog(LAIN, "sec", {"not": "a list"})


def test_duplicate_attachment_ids_are_disambiguated():
    d = {"posts": [{"no": 1, "resto": 0, "time": 1, "tim": "7", "ext": ".jpg"},
                   {"no": 2, "resto": 1, "time": 2, "tim": "7", "ext": ".jpg"}]}
    th = adapter_for(LAIN).parse_thread(LAIN, "sec", 1, d)
    ids = [p.attachment.id for p in th.posts]
    assert len(set(ids)) == 2 and ids[0] == "7"


def test_fourchan_adapter_matches_existing_models():
    from samples import CATALOG, THREAD
    s = S["4chan"]
    a = adapter_for(s)
    assert a.catalog_url(s, "g") == "https://a.4cdn.org/g/catalog.json"
    assert a.thread_url(s, "g", 100) == "https://a.4cdn.org/g/thread/100.json"
    ts = a.parse_catalog(s, "g", CATALOG)
    assert [t.number for t in ts] == [100, 101, 102] and ts[0].site == "4chan"
    th = a.parse_thread(s, "g", 100, THREAD)
    assert th.site == "4chan" and len(th.posts) == 4
