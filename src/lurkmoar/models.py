"""Explicit internal models. API dicts stop at this module's from_api methods."""
import html
from dataclasses import dataclass

from .parse import Span, parse_comment, plain_text, references

CDN = "https://i.4cdn.org"


@dataclass(frozen=True)
class Board:
    code: str
    title: str
    worksafe: bool
    pages: int

    @classmethod
    def from_api(cls, d):
        return cls(d["board"], html.unescape(d.get("title", d["board"])),
                   bool(d.get("ws_board")), d.get("pages", 10))


@dataclass(frozen=True)
class Attachment:
    id: int
    filename: str
    extension: str
    size: int
    width: int
    height: int
    thumbnail_url: str
    original_url: str
    spoiler: bool
    deleted: bool = False


def attachment_from_api(board, d):
    if d.get("filedeleted"):
        return Attachment(0, "", "", 0, 0, 0, "", "", False, deleted=True)
    if "tim" not in d:
        return None
    tim, ext = d["tim"], d.get("ext", "")
    return Attachment(tim, html.unescape(d.get("filename", "")), ext, d.get("fsize", 0),
                      d.get("w", 0), d.get("h", 0), f"{CDN}/{board}/{tim}s.jpg",
                      f"{CDN}/{board}/{tim}{ext}", bool(d.get("spoiler")))


@dataclass(frozen=True)
class ThreadSummary:
    board: str
    number: int
    subject: str
    comment: str
    thumbnail: Attachment | None
    replies: int
    images: int
    created_at: int
    modified_at: int
    sticky: bool
    closed: bool

    @classmethod
    def from_api(cls, board, d):
        created = d.get("time", 0)
        return cls(board, d["no"], html.unescape(d.get("sub", "")),
                   plain_text(parse_comment(d.get("com", ""))), attachment_from_api(board, d),
                   d.get("replies", 0), d.get("images", 0), created,
                   d.get("last_modified", created), bool(d.get("sticky")), bool(d.get("closed")))


def flatten_catalog(board, pages):
    return [ThreadSummary.from_api(board, t) for page in pages for t in page.get("threads", [])]


@dataclass(frozen=True)
class Post:
    number: int
    thread_number: int
    name: str
    subject: str
    comment_html: str
    comment_plain: str
    timestamp: int
    attachment: Attachment | None
    references: tuple
    capcode: str
    spans: tuple[Span, ...]

    @classmethod
    def from_api(cls, board, d):
        spans = parse_comment(d.get("com", ""))
        name = html.unescape(d.get("name") or "Anonymous")
        if d.get("trip"):
            name += " " + d["trip"]
        return cls(d["no"], d.get("resto") or d["no"], name, html.unescape(d.get("sub", "")),
                   d.get("com", ""), plain_text(spans), d.get("time", 0),
                   attachment_from_api(board, d), references(spans), d.get("capcode") or "", spans)


@dataclass
class Thread:
    board: str
    number: int
    posts: list
    last_modified: str | None = None

    @classmethod
    def from_api(cls, board, number, data, last_modified=None):
        return cls(board, number, [Post.from_api(board, p) for p in data["posts"]], last_modified)

    @property
    def replies(self): return max(0, len(self.posts) - 1)

    @property
    def images(self):
        return sum(1 for p in self.posts if p.attachment and not p.attachment.deleted)

    @property
    def subject(self): return self.posts[0].subject if self.posts else ""
