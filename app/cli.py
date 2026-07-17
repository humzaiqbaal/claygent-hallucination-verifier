"""
Command-line entry point for the Claygent verification agent.

Same engine.run_batch core as the MCP server (mcp_server.py) - this just
formats output for a terminal/CSV instead of an MCP tool response.

Usage:
    python -m app.cli export.csv --claim-columns funding_series,is_confirmed --source-column Link --out verified.csv
    python -m app.cli export.csv --claim-columns funding_series,is_confirmed --source-column Link --estimate-only

--claim-columns takes the already-extracted field columns from your Clay
export (whatever you manually selected in Claygent's side panel) - a real
Clay CSV export never has usable data in the raw Claygent-response column
itself, so there's no single "claim column" to point at.
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
    parser.add_argument(
        "--claim-columns",
        required=True,
        help="comma-separated columns holding the pre-extracted claim fields (e.g. funding_series,is_confirmed)",
    )
    parser.add_argument("--source-column", required=True, help="column holding the row's source URL")
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

    claim_columns = [c.strip() for c in args.claim_columns.split(",")]
    verifier = ClaudeClaimVerifier(model=args.model)

    batch = run_batch(
        rows,
        claim_columns=claim_columns,
        source_url_column=args.source_column,
        verifier=verifier,
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
