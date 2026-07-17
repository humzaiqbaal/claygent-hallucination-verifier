"""
Deterministic fetch of a row's source URL.

Real-world source links are messy: dead, slow, paywalled, or rendered
client-side so the HTML response has no article text in it. This module's
job is only to fetch and classify that messiness into a FetchResult status -
it never judges whether the page supports a claim, that's verifiers.py.
"""

from __future__ import annotations

import requests
import trafilatura

from app.schema import FetchResult

DEFAULT_TIMEOUT_SECONDS = 10
MAX_RETRIES = 1
USER_AGENT = "claygent-verifier/0.1 (+portfolio project; re-verifies Claygent citations)"

# Below this many characters of extracted article text, treat the page as
# effectively empty - too short to usefully judge a claim against, and a
# strong signal the page is either JS-rendered (nothing server-rendered) or
# paywalled (only a teaser survived extraction).
MIN_USEFUL_TEXT_CHARS = 200

PAYWALL_MARKERS = (
    "subscribe to continue reading",
    "subscribe to read",
    "this content is for subscribers",
    "already a subscriber",
    "create a free account to continue",
)


def fetch_source(url: str, session: requests.Session | None = None) -> FetchResult:
    """Fetch `url` and classify the outcome.

    `session` is injectable purely for testing (a fake/mock session with no
    real network access) - production callers can omit it and a plain
    `requests` call is made per fetch.
    """
    if not url or not url.strip():
        return FetchResult(status="UNREACHABLE", detail="no source URL provided")

    request = session.get if session is not None else requests.get
    headers = {"User-Agent": USER_AGENT}

    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = request(url, headers=headers, timeout=DEFAULT_TIMEOUT_SECONDS)
            break
        except requests.Timeout as e:
            last_error = e
            continue
        except requests.RequestException as e:
            return FetchResult(status="UNREACHABLE", detail=str(e))
    else:
        return FetchResult(status="TIMEOUT", detail=str(last_error))

    if response.status_code != 200:
        return FetchResult(status="NON_200", detail=f"HTTP {response.status_code}")

    html = response.text
    extracted = trafilatura.extract(html) or ""
    page_text = extracted.strip()

    if len(page_text) < MIN_USEFUL_TEXT_CHARS:
        lowered = html.lower()
        if any(marker in lowered for marker in PAYWALL_MARKERS):
            return FetchResult(status="LIKELY_PAYWALLED", detail="paywall marker text found in page")
        return FetchResult(
            status="LIKELY_JS_RENDERED",
            detail=f"only {len(page_text)} chars of article text extracted",
        )

    return FetchResult(status="OK", page_text=page_text)
