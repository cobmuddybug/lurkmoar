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


def test_deeply_nested_unclosed_tags_with_data_are_fast():
    t = time.time()
    parse_comment("<span>x" * 50000)
    parse_comment("<b>x" * 50000)
    assert time.time() - t < 2


def test_quote_target_vichan_forms():
    assert quote_target("#12") == (None, None, 12)
    assert quote_target("/b/res/5.html#12") == ("b", 5, 12)
    assert quote_target("/b/res/5#12") == ("b", 5, 12)
    assert quote_target("/v/thread/55#p56") == ("v", 55, 56)
    assert quote_target("https://x.example/b/res/5.html#12") is None


def test_vichan_quote_link_without_class_is_a_quote():
    s = parse_comment('<a onclick="highlightReply(\'12\', event);" href="/sec/res/5.html#12">&gt;&gt;12</a> hi')
    assert s[0].styles == {"quote"} and s[0].target == "/sec/res/5.html#12"
    assert references(s, "sec", 5) == (12,)


def test_cross_board_and_cross_thread_vichan_quotes_are_not_references():
    s = parse_comment('<a href="/qa/res/9#4">x</a><a href="/sec/res/6.html#3">y</a><a href="/sec/res/5.html#2">z</a>')
    assert references(s, "sec", 5) == (2,)
    assert [x.styles for x in s] == [{"quote"}] * 3


def test_external_links_with_fragments_stay_links():
    s = parse_comment('<a href="https://archive.example/x#12">x</a>')
    assert s[0].styles == {"link"}


def test_vichan_span_classes():
    s = parse_comment('<span class="quote">&gt;g</span><span class="orangeQuote">&lt;o</span>'
                      '<span class="spoiler">sp</span><span class="heading">h</span><strike>st</strike>'
                      '<span class="yen">y</span>')
    assert [x.styles for x in s] == [{"greentext"}, {"greentext"}, {"spoiler"}, {"b"}, {"spoiler"}, frozenset()] or \
        [x.styles for x in s] == [{"greentext"}, {"spoiler"}, {"b"}, {"spoiler"}, frozenset()]


def test_vichan_markup_flattens_safely():
    s = parse_comment("a<wbr>b<details><summary>s</summary>d</details><ol><li>1</li></ol>")
    assert plain_text(s) == "absd1"
