from app.pipeline.crawler import _clean, _rank_internal_links


def test_clean_strips_scripts_keeps_text():
    html = "<title>Acme</title><script>evil()</script><style>x{}</style><p>Hello world</p>"
    title, text = _clean(html)
    assert title == "Acme"
    assert "Hello world" in text
    assert "evil" not in text


def test_rank_internal_links_scores_signal_words():
    base = "https://x.com"
    html = ('<a href="/pricing">p</a><a href="/about">a</a>'
            '<a href="/random">r</a>'
            '<a href="https://other.com/pricing">ext</a>')
    links = _rank_internal_links(base, html, limit=5)
    assert "https://x.com/pricing" in links
    assert "https://x.com/about" in links
    assert "https://x.com/random" not in links        # no signal word
    assert all("other.com" not in u for u in links)   # external excluded


def test_rank_respects_limit():
    base = "https://x.com"
    html = "".join(f'<a href="/pricing{i}">x</a>' for i in range(10))
    assert len(_rank_internal_links(base, html, limit=3)) == 3
