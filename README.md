# Claygent Verification Agent

Takes a Clay export CSV and re-checks every Claygent-generated claim against
its row's own source URL before that data reaches a live outreach sequence.
Ships two interfaces (CLI, MCP server) over one shared verification engine.

## Why this exists

Clay's built-in AI research agent, Claygent, hallucinates: it fabricates
dates, misattributes facts, and sometimes ignores its own "return JSON only"
instruction and returns a narrative sentence instead. I hit this directly
building a news/fundraising signal monitor for a client's Clay workflow -
Claygent occasionally broke every downstream field extraction on a row by
not returning valid JSON, and there was no way to tell a real hallucination
from a correct extraction without manually re-checking the source article.
Clay has no systematic fix for this; their own support response is "try a
different integration."

This tool is that manual re-check, automated: take Claygent's claim, fetch
the same source URL a human would click to verify it, and ask an independent
model whether the page actually supports the claim. It's built to fail
loudly, not quietly - a row with nothing usefully extracted, a source that
can't be fetched, or a page that doesn't address the claim all produce their
own distinct, reportable outcome (`NO_CLAIM_DATA`, `FETCH_FAILED`,
`UNVERIFIABLE`) instead of being silently skipped or forced into a MATCH.

## Schema-agnostic by design (and why there's no single "claim column")

There's no fixed Clay export format to conform to, and there's no single
"claim column" to point this tool at - a real Clay CSV export never carries
the raw Claygent response with data in it; that column always exports blank.
The only columns with real values are the ones manually selected from
Claygent's side panel (click the response cell, pick which JSON keys become
their own table columns). So this tool takes a **list** of pre-extracted
claim columns, whatever names and however many your export happens to have,
and treats a row where every one of those columns is blank as the real-world
signature of a failed extraction (`NO_CLAIM_DATA`) - not a JSON parse error,
since there's never any raw JSON in the export to parse in the first place.
`app/csv_mapper.py` never hardcodes a specific client's schema.

## Architecture

```
app/
  schema.py            : shared dataclasses passed between every stage
  csv_mapper.py         : deterministic - CSV parsing + configurable multi-column claim mapping
  claim_parser.py        : deterministic - drops blank claim columns, flags NO_CLAIM_DATA if all blank
  fetcher.py              : deterministic - fetch source URL -> page text, with failure taxonomy
  verifiers.py             : ClaimVerifier interface + ClaudeClaimVerifier (the one LLM call)
  model_capabilities.py     : per-model thinking/effort quirks (copied from the sibling
                              ai-personalization-engine project, kept in sync manually)
  engine.py                  : batch orchestration + cost estimation, depends only on
                                the ClaimVerifier interface, never a vendor SDK directly
  cli.py                      : thin CLI, single CSV in, verified CSV out
  mcp_server.py                 : thin MCP tool, same engine.run_batch() call as the CLI
tests/
  test_csv_mapper.py    : multi-column mapping, arbitrary/missing headers
  test_claim_parser.py   : blank-column filtering incl. the all-blank NO_CLAIM_DATA case
  test_fetcher.py          : fetch failure taxonomy (dead link, timeout, paywall, JS shell)
  test_engine.py             : full orchestration against a FakeClaimVerifier double
  fixtures/                    : synthetic CSVs modeled on real Clay export column shapes,
                                  including a blank raw-response column for realism
```

`engine.py` never imports `anthropic` or `requests` directly - only the
`ClaimVerifier` interface and the deterministic modules above it. The CLI
and MCP server both call `engine.run_batch()` and nothing else, so they
can't drift out of sync with each other; adding a third interface (e.g. a
future Sheets add-on) means writing a thin wrapper, not new verification
logic.

## Cost-aware by design

`--estimate-only` gives a rough pre-flight cost estimate, based on a
character-count heuristic, before any API calls are made:

```bash
python -m app.cli export.csv --claim-columns funding_series,is_confirmed --source-column Link --estimate-only
# 3 rows, estimated cost for model claude-sonnet-5: ~$0.0071
```

Every real run also reports actual token usage and dollar cost per batch,
same credit-conscious pattern as the other tools in this portfolio.

## Running it

```bash
python -m venv .venv
.venv/Scripts/activate        # .venv/bin/activate on macOS/Linux
pip install -r requirements.txt

export ANTHROPIC_API_KEY=sk-ant-...   # required for real runs, not for tests

# CLI
python -m app.cli export.csv --claim-columns funding_series,is_confirmed --source-column Link --out verified.csv

# MCP server (wire into a client's .mcp.json, or run standalone)
python -m app.mcp_server
```

Example `.mcp.json` entry for Claude Code / Cursor:

```json
{"mcpServers": {"claygent-verifier": {"command": "python", "args": ["-m", "app.mcp_server"]}}}
```

Input CSV needs, at minimum, one or more pre-extracted claim columns and a
source-URL column - any names, any count, pointed to explicitly. The raw
Claygent-response column, if your export even has one, is expected to be
blank and is simply ignored:

```csv
company_name,claygent_extraction,funding_series,is_confirmed,source_url
Acme Robotics,,Series B,CONFIRMED,https://example.com/news/acme-series-b
```

Output CSV is the same rows plus `verification_verdict`,
`verification_detail`, `verification_confidence_note`, and
`verification_checked_fields` columns.

## Tests

```bash
pip install pytest requests-mock
python -m pytest tests/ -v
```

33 unit tests, no Anthropic API key, no real network calls (`requests_mock`
intercepts the transport layer for fetcher/engine tests, and raises on any
URL that wasn't explicitly registered - so a test can't silently succeed by
hitting the real internet). They verify multi-column claim mapping, blank-
column filtering (including the all-blank `NO_CLAIM_DATA` case), the fetch
failure taxonomy, and the full engine orchestration against a
`FakeClaimVerifier` double. They do not verify actual LLM judgment quality -
whether
`ClaudeClaimVerifier` correctly distinguishes MATCH from MISMATCH on real
page text needs a real API key and human review on real claims, which is a
manual smoke-testing step, not something covered by the automated suite.

**Manual smoke test not yet run in this environment**: no `ANTHROPIC_API_KEY`
was available when this was built, so `ClaudeClaimVerifier`, the CLI's
non-`--estimate-only` path, and the MCP tool's real verification call are
untested against the live API. Run the CLI once against a real CSV with a
real key to close this gap - see "Known limitations" below.

## Test data

`tests/fixtures/` contains only synthetic data: invented company names,
invented URLs, modeled on the real column shapes seen in an actual client
Clay export but with no real client data. No `Employers/` client CSVs were
used in the test suite or in this README, by deliberate choice - see the
project's build plan for the reasoning.

## Known limitations

- **No raw-JSON-blob path.** This tool assumes claim data always arrives as
  N pre-extracted columns, since that's what a real Clay export produces.
  If some future Clay export config somehow does carry a real JSON blob with
  data in it, this tool won't parse it - you'd need to select the fields
  into their own columns first, the same way you already do for a normal
  Clay export.
- **Manual smoke test against the live Claude API hasn't been run yet** in
  this build environment - see "Tests" above. This is the single biggest gap
  before treating this as demo-ready.
- **Cost estimates are heuristics.** The pre-flight estimate uses a
  ~4-characters-per-token approximation, not the API's real tokenizer.
- **Model pricing table is a static, manually-maintained reference**
  (`MODEL_PRICING_PER_MILLION` in `app/engine.py`). Verify at
  anthropic.com/pricing before relying on it for real budgeting.
- **Paywall/JS-rendered detection is heuristic**, not exhaustive: it flags
  pages with very little extracted article text and, for paywalls, a known
  marker phrase. A paywall or JS site that doesn't match either signal will
  likely just extract as thin real text and get judged UNVERIFIABLE by the
  LLM stage instead of being caught earlier - a reasonable fallback, but not
  the same as a purpose-built paywall detector.
- **One retry on timeout, one vendor implemented.** `fetcher.py` retries a
  timeout once before giving up; `ClaimVerifier` has one working
  implementation (Claude). The interface is vendor-agnostic, but no second
  implementation has been written.
- **No non-technical interface yet.** This ships CLI + MCP only. A
  Sheets/Clay-native interface for GTM operators who aren't in a terminal is
  planned as later work, not built here.
- **No case-study writeup yet.** A demo writeup for `job-hunting/Portfolio/case-studies/`
  is planned as later work, once the live-API smoke test above has actually
  been run and its real output can be shown.
