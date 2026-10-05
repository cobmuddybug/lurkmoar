import time

from lurkmoar.parse import parse_comment, plain_text, quote_target, references


def test_plain_and_br():
    assert plain_text(parse_comment("a<br>b")) == "a\nb"


def test_entities():
    assert plain_text(parse_comment("it&#039;s &gt;&gt; &amp;")) == "it's >> &"


def test_quote_link_is_reference():
    s = parse_comment('<a href="#p123" class="quotelink">&gt;&gt;123</a> hi')
    assert s[0].styles == {"quote"} and s[0].target == "#p123"
    assert references(s) == (123,)


def test_cross_thread_quote_not_a_reference():
    s = parse_comment('<a href="/v/thread/9#p10" class="quotelink">&gt;&gt;&gt;/v/10</a>')
    assert references(s) == () and s[0].target == "/v/thread/9#p10"


def test_references_deduplicated_in_order():
    html = ''.join(f'<a href="#p{n}" class="quotelink">x</a>' for n in (5, 3, 5))
    assert references(parse_comment(html)) == (5, 3)


def test_greentext_spoiler_code_bold():
    s = parse_comment('<span class="quote">&gt;a</span><s>b</s><pre>c</pre><b>d</b>')
    assert [x.styles for x in s] == [{"greentext"}, {"spoiler"}, {"code"}, {"b"}]


def test_script_and_style_dropped():
    assert plain_text(parse_comment("x<script>alert(1)</script>y<style>p{}</style>z")) == "xyz"


def test_unknown_tags_flattened():
    s = parse_comment('<div onclick="x">hi</div>')
    assert plain_text(s) == "hi" and s[0].styles == frozenset()


def test_javascript_href_is_not_a_link():
    s = parse_comment('<a href="javascript:alert(1)">x</a>')
    assert s[0].target is None and "link" not in s[0].styles


def test_external_link():
    s = parse_comment('<a href="https://example.com/a">x</a>')
    assert s[0].styles == {"link"} and s[0].target == "https://example.com/a"


def test_unclosed_nested_does_not_crash():
    s = parse_comment("<b><i>x")
    assert s[0].styles == {"b", "i"}


def test_huge_hostile_input_is_fast():
    t = time.time()
    parse_comment("<b>" * 50000 + "x")
    parse_comment("a<br>" * 20000)
    assert time.time() - t < 2


def test_quote_target():
    assert quote_target("#p12") == (None, None, 12)
    assert quote_target("/v/thread/55#p56") == ("v", 55, 56)
    assert quote_target("/g/") is None and quote_target(None) is None
