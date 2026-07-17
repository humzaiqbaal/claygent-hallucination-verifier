"""
MCP entry point for the Claygent verification agent.

Same engine.run_batch core as the CLI (cli.py) - this just exposes it as an
MCP tool an agent (Claude Code, Cursor, etc.) can call directly against a
Clay export CSV, instead of a human running a terminal command. The tool
body below is intentionally thin: it maps arguments, calls engine.run_batch,
and formats the result - no verification logic lives here.

Run standalone with:
    python -m app.mcp_server

Or wire into a client's .mcp.json, e.g.:
    {"mcpServers": {"claygent-verifier": {"command": "python", "args": ["-m", "app.mcp_server"]}}}
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from app.csv_mapper import parse_csv_rows
from app.engine import run_batch, write_csv_output
from app.verifiers import DEFAULT_MODEL, ClaudeClaimVerifier

mcp = FastMCP("claygent-verifier")


@mcp.tool()
def verify_claygent_csv(
    csv_path: str,
    claim_column: str,
    source_url_column: str,
    claim_fields: list[str] | None = None,
    model: str = DEFAULT_MODEL,
    out_path: str | None = None,
) -> dict:
    """Re-verify Claygent claims in a Clay export CSV against each row's source URL.

    For every row: parses the claim column as JSON (flagging MALFORMED_JSON if
    Claygent didn't return valid JSON), fetches the source_url_column's URL
    (flagging FETCH_FAILED if unreachable/paywalled/JS-rendered), and asks
    Claude whether the fetched page text actually supports the claim
    (MATCH / MISMATCH / UNVERIFIABLE).

    Args:
        csv_path: path to the Clay export CSV.
        claim_column: column holding the Claygent claim JSON blob.
        source_url_column: column holding the row's source URL.
        claim_fields: optional list of claim keys to verify (default: all string fields).
        model: Claude model to use for verification.
        out_path: if given, writes the verified CSV (original columns plus
            verification_* columns) to this path.

    Returns:
        A summary dict: row_count, verdict_counts, estimated_cost_usd, and
        out_path if one was written.
    """
    with open(csv_path, encoding="utf-8") as f:
        rows = parse_csv_rows(f.read())

    if not rows:
        return {"error": f"no rows found in {csv_path!r}"}

    verifier = ClaudeClaimVerifier(model=model)
    batch = run_batch(
        rows,
        claim_column=claim_column,
        source_url_column=source_url_column,
        verifier=verifier,
        claim_fields=claim_fields,
    )

    result = {
        "row_count": len(batch.results),
        "verdict_counts": batch.verdict_counts(),
        "estimated_cost_usd": batch.estimated_cost(model),
    }

    if out_path:
        csv_text = write_csv_output(rows, batch)
        with open(out_path, "w", encoding="utf-8", newline="") as f:
            f.write(csv_text)
        result["out_path"] = out_path

    return result


if __name__ == "__main__":
    mcp.run()
