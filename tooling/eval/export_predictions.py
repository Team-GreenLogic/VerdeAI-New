"""Export analysis results as a predictions CSV for the benchmark's own scorer.

The five-company benchmark ships ``benchmark/score_predictions.py``, which expects
``pass_id,company_code,clause_id,predicted_class`` over all 190 rows and reports macro-F1 across
the 160 independent clause decisions (parents 6.1/6.2/7.4/7.5/9.1/9.2 are derived and scored
separately). Using their scorer rather than a local one keeps the number comparable to the
benchmark's published metric.

Reads ``tooling/eval/benchmark_tenants.json`` (written by ``tooling.benchmark_corpus``) for the
tenant/analysis id of each company, pulls decisions straight from ``result_store``, and maps
this system's decision vocabulary onto the benchmark's.

Usage:
    python -m tooling.eval.export_predictions --out predictions.csv
    python -m tooling.eval.export_predictions --out predictions.csv --analysis A=<id> --analysis B=<id>
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import httpx

MANIFEST = Path(__file__).parent / "benchmark_tenants.json"
PASSWORD = "benchmark-fixture-pw-2026"

# This system's decisions -> the benchmark's four classes.
DECISION_TO_GOLD = {
    "Met": "FULLY_MET",
    "Partially Met": "PARTIALLY_MET",
    "Not Met": "NOT_MET",
    "Insufficient Evidence": "INSUFFICIENT_EVIDENCE",
}
# A clause that errored or was never analysed has no opinion. The scorer requires a value for
# every row, and INSUFFICIENT_EVIDENCE is the honest one: it asserts no conformity finding.
# This inflates that class, so the export prints how many rows were filled this way — a run
# needing many of them is not a result worth reporting.
FALLBACK = "INSUFFICIENT_EVIDENCE"


def fetch_decisions(client: httpx.Client, email: str, analysis_id: str) -> dict[str, str]:
    """Pull per-clause decisions through the public API.

    Deliberately not a direct Mongo read: this is the same response path the UI consumes, so a
    field the endpoint fails to serialise shows up here rather than being silently absent from
    the report. That has already happened once, with slot_fills.
    """
    token = client.post("/auth/login", json={"email": email, "password": PASSWORD}).json()["access_token"]
    r = client.get(f"/analyses/{analysis_id}/results", headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    return {row["clause_id"]: row.get("decision", "") for row in r.json()}


def run(out: Path, gold_csv: Path, api: str, overrides: dict[str, str]) -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    companies: dict[str, Any] = manifest["companies"]

    # The gold file defines the exact (pass_id, clause_id) rows the scorer demands.
    with gold_csv.open(encoding="utf-8-sig") as fh:
        gold_rows = [
            {"pass_id": r["pass_id"], "company_code": r["company_code"], "clause_id": r["clause_id"]}
            for r in csv.DictReader(fh)
        ]

    per_company: dict[str, dict[str, str]] = {}
    with httpx.Client(base_url=api, timeout=120.0) as client:
        for code, entry in sorted(companies.items()):
            analysis_id = overrides.get(code) or entry.get("analysis_id")
            if not analysis_id:
                print(f"  {code}: no analysis_id — all rows will fall back")
                per_company[code] = {}
                continue
            per_company[code] = fetch_decisions(client, entry["email"], analysis_id)
            print(f"  {code}: {len(per_company[code])} clause results from {analysis_id[:8]}")

    fallback_used = 0
    unmapped: set[str] = set()
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["pass_id", "company_code", "clause_id", "predicted_class"])
        w.writeheader()
        for row in gold_rows:
            decision = per_company.get(row["company_code"], {}).get(row["clause_id"], "")
            mapped = DECISION_TO_GOLD.get(decision)
            if mapped is None:
                if decision:
                    unmapped.add(decision)
                mapped = FALLBACK
                fallback_used += 1
            w.writerow({**row, "predicted_class": mapped})

    print(f"\nwrote {out}  ({len(gold_rows)} rows)")
    if unmapped:
        print(f"  decisions with no gold equivalent (treated as {FALLBACK}): {sorted(unmapped)}")
    if fallback_used:
        pct = 100 * fallback_used / len(gold_rows)
        print(f"  {fallback_used} rows ({pct:.0f}%) had no usable decision and fell back to {FALLBACK}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Export predictions.csv for the benchmark scorer")
    ap.add_argument("--out", default="predictions.csv")
    ap.add_argument(
        "--gold",
        default=r"C:\Users\User\Downloads\ISO14001_Five_Company_Benchmark_v3_MASTER\benchmark\gold_labels_long.csv",
        help="Gold CSV, used only for its (pass_id, clause_id) row set",
    )
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument(
        "--analysis",
        action="append",
        default=[],
        metavar="CODE=ANALYSIS_ID",
        help="Override the manifest's analysis id for a company",
    )
    args = ap.parse_args()

    overrides = {}
    for item in args.analysis:
        code, _, aid = item.partition("=")
        overrides[code.strip().upper()] = aid.strip()

    run(Path(args.out), Path(args.gold), args.api, overrides)


if __name__ == "__main__":
    main()
