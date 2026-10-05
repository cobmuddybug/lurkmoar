"""Whitelist comment HTML -> styled spans. Anything unknown becomes plain text."""
import re
from dataclasses import dataclass
from html.parser import HTMLParser

QUOTE_RE = re.compile(r"(?:/(\w+)/(?:thread|res)/(\d+)(?:\.html)?)?#p?(\d+)")


@dataclass(frozen=True)
class Span:
    text: str
    styles: frozenset = frozenset()
    target: str | None = None


class _Parser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.spans: list[Span] = []
        self.stack: list[tuple[str, frozenset, str | None]] = []
        self.skip = 0

    def _cur(self):
        # each stack entry already holds the cumulative styles/target, so this is O(1)
        return (self.stack[-1][1], self.stack[-1][2]) if self.stack else (frozenset(), None)

    def _add(self, text):
        st, t = self._cur()
        if self.spans and self.spans[-1].styles == st and self.spans[-1].target == t:
            self.spans[-1] = Span(self.spans[-1].text + text, st, t)
        else:
            self.spans.append(Span(text, st, t))

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class") or ""
        if tag in ("script", "style"):
            self.skip += 1
            return
        if tag == "br":
            self._add("\n")
            return
        if tag == "wbr":
            return
        s, t = set(), None
        if tag in ("b", "strong"): s = {"b"}
        elif tag in ("i", "em"): s = {"i"}
        elif tag == "u": s = {"u"}
        elif tag in ("s", "strike"): s = {"spoiler"}
        elif tag in ("pre", "code"): s = {"code"}
        elif tag == "a":
            href = a.get("href") or ""
            if "quotelink" in cls or (href[:1] in ("#", "/") and QUOTE_RE.fullmatch(href)):
                s, t = {"quote"}, href
            elif href.startswith(("http://", "https://")):
                s, t = {"link"}, href
        elif tag == "span":
            if "deadlink" in cls: s = {"quote"}
            elif "spoiler" in cls: s = {"spoiler"}
            elif "heading" in cls: s = {"b"}
            elif "orangeQuote" in cls or "quote" in cls: s = {"greentext"}
        styles, target = self._cur()
        self.stack.append((tag, styles | frozenset(s), t or target))

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
            return
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        if not self.skip:
            self._add(data)


def parse_comment(html: str, ctx=None) -> tuple[Span, ...]:
    p = _Parser()
    p.feed(html or "")
    p.close()
    return tuple(p.spans)


def plain_text(spans) -> str:
    return "".join(s.text for s in spans)


def quote_target(href):
    m = QUOTE_RE.fullmatch(href or "")
    if not m:
        return None
    return (m.group(1), int(m.group(2)) if m.group(2) else None, int(m.group(3)))


def references(spans, board=None, thread=None) -> tuple[int, ...]:
    out: list[int] = []
    for s in spans:
        if "quote" in s.styles and s.target:
            q = quote_target(s.target)
            if not q:
                continue
            qb, qt, qp = q
            same = (qb is None) or (board is not None and qb == board and qt == thread)
            if same and qp not in out:
                out.append(qp)
    return tuple(out)
