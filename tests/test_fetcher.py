"""
Unit tests for app.fetcher. Uses the requests_mock pytest fixture to patch
requests' transport adapter - no real network calls, deterministic.
"""

import requests

from app.fetcher import fetch_source

URL = "https://example.com/news/acme-series-b"

ARTICLE_HTML = """
<html><body><article>
<p>Acme Robotics announced today it has closed a $40 million Series B round
led by Northlight Ventures, with participation from three existing investors.
The company plans to use the funding to expand its warehouse automation
platform into new markets across North America and Europe over the next
eighteen months, according to a statement from the company's CEO.</p>
</article></body></html>
"""

PAYWALL_HTML = """
<html><body><p>Acme Robotics raises Series B.</p>
<p>Subscribe to continue reading this article and get unlimited access.</p>
</body></html>
"""

JS_SHELL_HTML = """
<html><body><div id="root"></div><script src="/bundle.js"></script></body></html>
"""


def test_fetch_source_ok_extracts_article_text(requests_mock):
    requests_mock.get(URL, text=ARTICLE_HTML, status_code=200)
    result = fetch_source(URL)
    assert result.status == "OK"
    assert "Acme Robotics" in result.page_text
    assert "Series B" in result.page_text


def test_fetch_source_non_200(requests_mock):
    requests_mock.get(URL, status_code=404)
    result = fetch_source(URL)
    assert result.status == "NON_200"
    assert "404" in result.detail


def test_fetch_source_timeout(requests_mock):
    requests_mock.get(URL, exc=requests.exceptions.Timeout)
    result = fetch_source(URL)
    assert result.status == "TIMEOUT"


def test_fetch_source_unreachable(requests_mock):
    requests_mock.get(URL, exc=requests.exceptions.ConnectionError)
    result = fetch_source(URL)
    assert result.status == "UNREACHABLE"


def test_fetch_source_paywalled(requests_mock):
    requests_mock.get(URL, text=PAYWALL_HTML, status_code=200)
    result = fetch_source(URL)
    assert result.status == "LIKELY_PAYWALLED"


def test_fetch_source_js_rendered_shell(requests_mock):
    requests_mock.get(URL, text=JS_SHELL_HTML, status_code=200)
    result = fetch_source(URL)
    assert result.status == "LIKELY_JS_RENDERED"


def test_fetch_source_empty_url_is_unreachable():
    result = fetch_source("")
    assert result.status == "UNREACHABLE"


def test_fetch_source_retries_once_on_timeout_then_succeeds(requests_mock):
    requests_mock.get(
        URL,
        [
            {"exc": requests.exceptions.Timeout},
            {"text": ARTICLE_HTML, "status_code": 200},
        ],
    )
    result = fetch_source(URL)
    assert result.status == "OK"
