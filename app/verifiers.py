"""
Verifier abstraction for judging whether a claim is supported by page text.

This is the one genuinely probabilistic step in the pipeline - everything
upstream (csv_mapper, claim_parser, fetcher) is deterministic and testable
without touching an LLM. engine.py depends only on this ClaimVerifier
interface, never on a specific vendor SDK, mirroring
ai-personalization-engine's PersonalizationProvider pattern.
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod

from app.model_capabilities import build_thinking_kwarg, resolve_effort
from app.schema import MATCH, MISMATCH, UNVERIFIABLE, VerificationVerdict


class ClaimVerifier(ABC):
    """Implement this to plug in a different LLM vendor.

    A conforming implementation must:
      1. Accept a claim (dict of field name -> claimed value) and the fetched
         page's plain text.
      2. Return a VerificationVerdict with verdict set to exactly one of
         MATCH, MISMATCH, or UNVERIFIABLE (app.schema constants) - never
         invent a fourth value.
      3. Set UNVERIFIABLE when the page text doesn't contain enough
         information to confirm or deny the claim, rather than guessing.
      4. Report input_tokens/output_tokens from the provider's own usage
         reporting, for cost tracking. Return 0/0 if the vendor doesn't
         expose it.
    """

    @abstractmethod
    def verify(self, claim: dict[str, str], page_text: str) -> VerificationVerdict:
        raise NotImplementedError


SYSTEM_PROMPT = """You verify whether a claimed fact is actually supported by a piece of
source text. This is used to catch AI research-agent hallucinations before they reach a
live outreach sequence, so be strict and literal.

Rules:
- Judge ONLY against the page text you're given. Do not use outside knowledge about the
  company or event to fill gaps - if the page text doesn't say it, the page doesn't
  support it.
- verdict="MATCH" only if the page text clearly states or directly implies the claimed
  value. A vague or loosely related mention is not a match.
- verdict="MISMATCH" if the page text contradicts the claim, or states a materially
  different value (e.g. claim says "Series B", page says "Series A").
- verdict="UNVERIFIABLE" if the page text simply doesn't address the claim at all - don't
  force a MATCH or MISMATCH out of silence.
- checked_fields must list exactly which claim keys you evaluated to reach the verdict.
- confidence_note is one short sentence naming the specific text you relied on (or noting
  its absence for UNVERIFIABLE).
"""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": [MATCH, MISMATCH, UNVERIFIABLE]},
        "confidence_note": {
            "type": "string",
            "description": "One short sentence naming the page text the verdict is grounded in.",
        },
        "checked_fields": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Which claim keys were evaluated.",
        },
    },
    "required": ["verdict", "confidence_note", "checked_fields"],
    "additionalProperties": False,
}

DEFAULT_MODEL = "claude-sonnet-5"

# Page text is truncated before it reaches the prompt: verification only
# needs enough of the article to judge a handful of short factual claims,
# and an unbounded page (or one padded by a scraping artifact) shouldn't
# blow up cost per row.
MAX_PAGE_TEXT_CHARS = 8000


class ClaudeClaimVerifier(ClaimVerifier):
    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        enable_thinking: bool = False,
        effort: str | None = None,
    ):
        # Deferred import so the rest of the app (and its tests) don't require
        # the anthropic package or a key unless this verifier is actually used.
        import anthropic

        self.model = model or os.environ.get("CLAYGENT_VERIFIER_MODEL", DEFAULT_MODEL)
        self.enable_thinking = enable_thinking
        self.effort = effort
        self._client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    def verify(self, claim: dict[str, str], page_text: str) -> VerificationVerdict:
        claim_json = json.dumps(claim, ensure_ascii=False)
        truncated_page_text = page_text[:MAX_PAGE_TEXT_CHARS]

        output_config = {"format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}}
        resolved_effort = resolve_effort(self.model, self.enable_thinking, self.effort)
        if resolved_effort:
            output_config["effort"] = resolved_effort

        response = self._client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Claimed fact(s):\n{claim_json}\n\n"
                        f"Source page text:\n{truncated_page_text}"
                    ),
                }
            ],
            output_config=output_config,
            **build_thinking_kwarg(self.model, self.enable_thinking),
        )

        text = next(block.text for block in response.content if block.type == "text")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Claude returned malformed JSON (stop_reason={response.stop_reason!r}): "
                f"{e}. Raw text: {text!r}"
            ) from e

        return VerificationVerdict(
            verdict=data["verdict"],
            confidence_note=data["confidence_note"],
            checked_fields=data["checked_fields"],
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
