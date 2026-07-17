"""
Command-line entry point for the Claygent verification agent.

Same engine.run_batch core as the MCP server (mcp_server.py) - this just
formats output for a terminal/CSV instead of an MCP tool response.

Usage:
    python -m app.cli export.csv --claim-column claygent_extraction --source-column Link --out verified.csv
    python -m app.cli export.csv --claim-column claygent_extraction --source-column Link --estimate-only
"""

from __future__ import annotations

import argparse
import sys

from app.engine import estimate_batch_cost, run_batch, write_csv_output
from app.csv_mapper import parse_csv_rows
from app.verifiers import DEFAULT_MODEL, ClaudeClaimVerifier


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Re-verify Claygent claims against their row's source URL before they hit a live sequence."
    )
    parser.add_argument("csv_path", help="path to the Clay export CSV")
    parser.add_argument("--claim-column", required=True, help="column holding the Claygent claim JSON")
    parser.add_argument("--source-column", required=True, help="column holding the row's source URL")
    parser.add_argument(
        "--claim-fields",
        help="comma-separated claim keys to verify (default: all string fields in the claim)",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Claude model to use (default: {DEFAULT_MODEL})")
    parser.add_argument("--out", help="path to write the verified CSV (default: print a summary only)")
    parser.add_argument(
        "--estimate-only", action="store_true", help="print a rough cost estimate and exit, no API calls"
    )
    args = parser.parse_args()

    with open(args.csv_path, encoding="utf-8") as f:
        rows = parse_csv_rows(f.read())

    if not rows:
        print("No rows found in CSV.", file=sys.stderr)
        return 1

    if args.estimate_only:
        estimate = estimate_batch_cost(rows, args.model)
        if estimate is None:
            print(f"No pricing data for model {args.model!r} - cannot estimate cost.")
        else:
            print(f"{len(rows)} rows, estimated cost for model {args.model}: ~${estimate:.4f}")
        return 0

    claim_fields = [f.strip() for f in args.claim_fields.split(",")] if args.claim_fields else None
    verifier = ClaudeClaimVerifier(model=args.model)

    batch = run_batch(
        rows,
        claim_column=args.claim_column,
        source_url_column=args.source_column,
        verifier=verifier,
        claim_fields=claim_fields,
    )

    counts = batch.verdict_counts()
    print(f"\n{len(batch.results)} rows verified:")
    for verdict, count in sorted(counts.items()):
        print(f"  {verdict:<15} {count}")
    cost = batch.estimated_cost(args.model)
    if cost is not None:
        print(f"  actual cost:    ~${cost:.4f} ({batch.total_input_tokens} in / {batch.total_output_tokens} out tokens)")

    if args.out:
        csv_text = write_csv_output(rows, batch)
        with open(args.out, "w", encoding="utf-8", newline="") as f:
            f.write(csv_text)
        print(f"\nWrote {args.out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
