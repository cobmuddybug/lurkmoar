from lurkmoar.models import Board, Post, Thread, ThreadSummary, flatten_catalog
from samples import BOARDS, CATALOG, THREAD


def test_board():
    b = [Board.from_api(d) for d in BOARDS["boards"]]
    assert b[0].worksafe and not b[1].worksafe and b[0].code == "g"


def test_catalog_flatten_and_fields():
    ts = flatten_catalog("g", CATALOG)
    assert [t.number for t in ts] == [100, 101, 102]
    t = ts[0]
    assert t.subject == "GPU Prices & Stuff" and t.comment.endswith("cost'")
    assert t.sticky and not t.closed and t.replies == 183
    assert t.thumbnail.thumbnail_url == "https://i.4cdn.org/g/1700000000001s.jpg"
    assert t.thumbnail.original_url == "https://i.4cdn.org/g/1700000000001.jpg"
    assert ts[2].closed and ts[2].thumbnail.extension == ".webm"


def test_sparse_catalog_thread():
    t = ThreadSummary.from_api("g", {"no": 5, "time": 1})
    assert t.subject == "" and t.comment == "" and t.thumbnail is None
    assert t.modified_at == 1 and t.replies == 0


def test_thread_posts():
    th = Thread.from_api("g", 100, THREAD, "Mon")
    assert len(th.posts) == 4 and th.replies == 3 and th.images == 2 and th.subject == "GPU Prices"
    op, p101, p102, p103 = th.posts
    assert op.thread_number == 100 and op.number == 100
    assert p101.references == (100,) and p101.comment_plain == ">>100\nreply"
    assert p102.attachment.deleted
    assert p103.references == (101,) and p103.capcode == "mod" and p103.attachment.spoiler
    assert th.last_modified == "Mon"


def test_hostile_comment_in_post():
    p = Post.from_api("g", {"no": 1, "com": "hi<script>x</script>", "time": 1})
    assert p.comment_plain == "hi"
    assert p.name == "Anonymous"


def test_post_attachment_property_and_images_count():
    from lurkmoar.models import Attachment
    a = Attachment("1", "f", ".jpg", 1, 1, 1, "t", "o", False)
    d = Attachment(0, "", "", 0, 0, 0, "", "", False, deleted=True)
    from lurkmoar.models import Post, Thread
    p = Post(1, 1, "n", "", "", "", 0, (a, d), (), "", ())
    q = Post(2, 1, "n", "", "", "", 0, (), (), "", ())
    assert p.attachment is a and q.attachment is None
    assert Thread("g", 1, [p, q]).images == 1
    assert Post.from_api("g", {"no": 3, "time": 1}).site == "4chan"
