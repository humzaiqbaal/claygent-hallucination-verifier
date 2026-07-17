"""
Deterministic parsing of a row's raw claim text into a structured claim.

Claygent is prompted to return JSON only, but it doesn't always comply - the
OneWell build hit this directly: Claygent occasionally returns a narrative
sentence instead of the requested JSON blob, silently breaking every
downstream JSON_EXTRACT formula relying on it. This module treats that as an
expected, reportable outcome (parse_error=True) rather than letting a
json.JSONDecodeError propagate and crash the batch.
"""

from __future__ import annotations

import json

from app.schema import ClaimExtraction


def parse_claim(raw_text: str) -> ClaimExtraction:
    """Parse a row's raw claim text as a JSON object.

    Only objects (not arrays, numbers, or bare strings) count as a valid
    claim - Claygent's contract is "return a JSON object", so anything else
    is treated the same as malformed JSON.
    """
    stripped = raw_text.strip()
    if not stripped:
        return ClaimExtraction(fields={}, parse_error=True, raw_text=raw_text)

    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return ClaimExtraction(fields={}, parse_error=True, raw_text=raw_text)

    if not isinstance(data, dict):
        return ClaimExtraction(fields={}, parse_error=True, raw_text=raw_text)

    # Only keep string-valued keys: those are what a downstream verifier can
    # meaningfully compare against page text. Nested objects/lists/numbers
    # are dropped rather than stringified, since coercing them risks
    # inventing a "claim" that isn't what Claygent actually said.
    string_fields = {k: v for k, v in data.items() if isinstance(v, str)}
    return ClaimExtraction(fields=string_fields, parse_error=False, raw_text=raw_text)
