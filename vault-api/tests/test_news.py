import pytest

from config import KioskNewsFeedConfig
from services.news import fetch_headlines, parse_news_feed

_RSS2 = b"""<?xml version="1.0"?>
<rss version="2.0"><channel>
  <title>ZEIT</title>
  <item><title>Nato-Gipfel: Wer fuehrt?</title>
        <description>&lt;p&gt;Europas Chefs&lt;/p&gt; treffen sich.</description>
        <link>https://zeit.de/a</link></item>
  <item><title>Hitzewelle</title><description>Es wird heiss.</description></item>
  <item><title>Drittes</title><description>x</description></item>
</channel></rss>"""

# RDF / RSS 1.0 (NDR style): items are siblings of channel under rdf:RDF.
_RDF = b"""<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns="http://purl.org/rss/1.0/">
  <channel><title>NDR Hamburg</title></channel>
  <item><title>Bittere Pillen: Hamburgs Haushalt</title><description>Sparen und Investieren.</description></item>
  <item><title>Halbmarathon abgesagt</title><description>Wegen Hitze.</description></item>
</rdf:RDF>"""


def test_parse_rss2_strips_html_and_limits():
    out = parse_news_feed("ZEIT", _RSS2, limit=2)
    assert [h.title for h in out] == ["Nato-Gipfel: Wer fuehrt?", "Hitzewelle"]
    assert out[0].summary == "Europas Chefs treffen sich."  # HTML stripped
    assert out[0].source == "ZEIT"
    assert out[0].link == "https://zeit.de/a"


def test_parse_rdf_finds_items_under_root():
    out = parse_news_feed("NDR · Hamburg", _RDF, limit=5)
    assert [h.title for h in out] == ["Bittere Pillen: Hamburgs Haushalt", "Halbmarathon abgesagt"]
    assert out[0].source == "NDR · Hamburg"


class _FakeResp:
    def __init__(self, content):
        self.content = content
        self.status_code = 200


class _FakeHttp:
    async def get(self, url, **kwargs):
        return _FakeResp(_RSS2 if "zeit" in url else _RDF)


@pytest.mark.asyncio
async def test_fetch_headlines_interleaves_feeds():
    feeds = [
        KioskNewsFeedConfig(id="zeit", label="ZEIT", url="https://zeit.example/all"),
        KioskNewsFeedConfig(id="ndr", label="NDR · Hamburg", url="https://ndr.example/hh"),
    ]
    out = await fetch_headlines(_FakeHttp(), feeds, per_feed=2)
    # Round-robin: ZEIT, NDR, ZEIT, NDR
    assert [h.source for h in out] == ["ZEIT", "NDR · Hamburg", "ZEIT", "NDR · Hamburg"]
    assert out[0].title == "Nato-Gipfel: Wer fuehrt?"
    assert out[1].title == "Bittere Pillen: Hamburgs Haushalt"
