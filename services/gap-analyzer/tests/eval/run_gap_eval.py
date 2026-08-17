"""Offline gap-analysis accuracy evaluation.

Compares a completed analysis's persisted per-clause decisions against a
hand-labelled golden set, producing a confusion matrix (accuracy, per-class
precision/recall/F1, macro-F1) plus an LLM-judge faithfulness pass rate over
each clause's reasoning vs. its own cited evidence.

This is the accuracy measurement the validated pipeline (grade_evidence /
verify_grounding / reconcile — see app/pipeline/analyse_clause.py) is meant to
improve. Run it before and after a pipeline change on the same fixture tenant
to see the effect.

Usage (from services/gap-analyzer):
    python -m tests.eval.run_gap_eval --tenant <fixture-tenant> --analysis-id <id>
    python -m tests.eval.run_gap_eval --tenant <t> --analysis-id <id> --golden-set custom.json --report json

Prerequisites: a completed analysis for a fixture tenant with known, hand-reviewed
documents uploaded — see the placeholder labels and instructions in golden_set.json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

from verdeai_shared.settings import settings

from tests.eval.faithfulness import judge_faithfulness


async def _get_db() -> Any:
    """Connect to MongoDB (same connection the production service uses)."""
    import motor.motor_asyncio as motor

    client = motor.AsyncIOMotorClient(settings.MONGO_URI)
    return client[settings.MONGO_DB]


def load_golden_set(path: Path) -> dict[str, str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {item["clause_id"]: item["expected_decision"] for item in raw["labels"]}


async def fetch_results(db: Any, tenant_id: str, analysis_id: str) -> dict[str, dict[str, Any]]:
    cursor = db.result_store.find({"tenant_id": tenant_id, "analysis_id": analysis_id})
    rows = await cursor.to_list(length=None)
    return {r["clause_id"]: r for r in rows}


def confusion_matrix(golden: dict[str, str], actual: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Build a confusion matrix + per-class precision/recall/F1 + accuracy/macro-F1."""
    labels = sorted(set(golden.values()) | {row.get("decision", "Unknown") for row in actual.values()})
    matrix: dict[str, Counter[str]] = {label: Counter() for label in labels}
    per_class: dict[str, dict[str, int]] = {label: {"tp": 0, "fp": 0, "fn": 0} for label in labels}
    correct = 0

    for clause_id, expected in golden.items():
        row = actual.get(clause_id)
        got = row.get("decision", "MISSING") if row else "MISSING"
        matrix.setdefault(expected, Counter())[got] += 1
        per_class.setdefault(expected, {"tp": 0, "fp": 0, "fn": 0})
        per_class.setdefault(got, {"tp": 0, "fp": 0, "fn": 0})
        if got == expected:
            correct += 1
            per_class[expected]["tp"] += 1
        else:
            per_class[expected]["fn"] += 1
            per_class[got]["fp"] += 1

    total = len(golden)
    accuracy = correct / total if total else 0.0

    per_class_metrics: dict[str, dict[str, float]] = {}
    f1_scores: list[float] = []
    for label, counts in per_class.items():
        tp, fp, fn = counts["tp"], counts["fp"], counts["fn"]
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        per_class_metrics[label] = {
            "precision": precision, "recall": recall, "f1": f1, "support": tp + fn,
        }
        if tp + fn > 0:  # only count classes that actually appear in the golden set
            f1_scores.append(f1)
    macro_f1 = sum(f1_scores) / len(f1_scores) if f1_scores else 0.0

    return {
        "accuracy": accuracy,
        "macro_f1": macro_f1,
        "total": total,
        "correct": correct,
        "per_class": per_class_metrics,
        "matrix": {expected: dict(counts) for expected, counts in matrix.items()},
    }


async def run_faithfulness_pass(actual: dict[str, dict[str, Any]], clause_ids: list[str]) -> dict[str, Any]:
    """LLM-judge each clause's reasoning against the evidence text of its own citations."""
    scored: dict[str, Any] = {}
    passed = 0
    evaluated = 0

    for clause_id in clause_ids:
        row = actual.get(clause_id)
        if not row or not row.get("citations"):
            continue
        source = "\n\n".join(c.get("text", "") for c in row["citations"] if c.get("text"))
        if not source.strip():
            continue
        try:
            result = await judge_faithfulness(source, row.get("reasoning", ""))
        except Exception as exc:
            logger.warning("Faithfulness judge call failed", clause_id=clause_id, error=str(exc))
            continue
        evaluated += 1
        scored[clause_id] = result
        if result.get("faithful"):
            passed += 1

    pass_rate = passed / evaluated if evaluated else None
    return {"pass_rate": pass_rate, "evaluated": evaluated, "passed": passed, "per_clause": scored}


def _write_reports(
    out_dir: Path,
    timestamp: str,
    confusion: dict[str, Any],
    faithfulness: dict[str, Any],
    tenant_id: str,
    analysis_id: str,
    report_format: str,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tenant_id": tenant_id,
        "analysis_id": analysis_id,
        "confusion_matrix": confusion,
        "faithfulness": faithfulness,
    }
    json_path = out_dir / f"gap_eval_{timestamp}.json"
    json_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    logger.info(f"JSON report written to {json_path}")

    if report_format == "md":
        lines = [
            "# Gap Analysis Accuracy Report",
            f"**Date:** {payload['generated_at']}",
            f"**Tenant:** {tenant_id}  **Analysis:** {analysis_id}",
            "",
            f"**Accuracy:** {confusion['accuracy']:.1%}  ({confusion['correct']}/{confusion['total']})",
            f"**Macro F1:** {confusion['macro_f1']:.3f}",
            "",
            "## Per-Class Metrics",
            "",
            "| Decision | Precision | Recall | F1 | Support |",
            "|---|---|---|---|---|",
        ]
        for label, m in confusion["per_class"].items():
            lines.append(f"| {label} | {m['precision']:.2f} | {m['recall']:.2f} | {m['f1']:.2f} | {m['support']} |")

        lines += ["", "## Confusion Matrix (expected → actual)", ""]
        for expected, got_counts in confusion["matrix"].items():
            for got, n in got_counts.items():
                lines.append(f"- {expected} → {got}: {n}")

        lines += ["", "## Faithfulness (LLM judge vs. own cited evidence)"]
        if faithfulness["pass_rate"] is None:
            lines.append("No clauses with citations were available to judge.")
        else:
            lines.append(
                f"**Pass rate:** {faithfulness['pass_rate']:.1%} "
                f"({faithfulness['passed']}/{faithfulness['evaluated']})"
            )

        md_path = out_dir / f"gap_eval_{timestamp}.md"
        md_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info(f"Markdown report written to {md_path}")


async def main(
    tenant_id: str,
    analysis_id: str,
    golden_set_path: str | None,
    report_format: str,
) -> None:
    golden_path = Path(golden_set_path) if golden_set_path else Path(__file__).parent / "golden_set.json"
    golden = load_golden_set(golden_path)
    logger.info(f"Loaded {len(golden)} golden labels from {golden_path}")

    db = await _get_db()
    actual = await fetch_results(db, tenant_id, analysis_id)
    logger.info(f"Fetched {len(actual)} persisted results for analysis {analysis_id}")

    confusion = confusion_matrix(golden, actual)
    logger.info(f"Accuracy: {confusion['accuracy']:.1%}  Macro F1: {confusion['macro_f1']:.3f}")

    faithfulness = await run_faithfulness_pass(actual, list(golden.keys()))
    if faithfulness["pass_rate"] is not None:
        logger.info(
            f"Faithfulness pass rate: {faithfulness['pass_rate']:.1%} "
            f"({faithfulness['passed']}/{faithfulness['evaluated']})"
        )

    out_dir = Path(__file__).parent / "reports"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    _write_reports(out_dir, timestamp, confusion, faithfulness, tenant_id, analysis_id, report_format)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate gap-analysis accuracy against a golden set")
    parser.add_argument("--tenant", required=True, help="Fixture tenant_id whose analysis to evaluate")
    parser.add_argument("--analysis-id", required=True, help="Completed analysis_id to evaluate")
    parser.add_argument("--golden-set", default=None, help="Path to golden set JSON (default: eval/golden_set.json)")
    parser.add_argument("--report", default="md", choices=["json", "md"])
    args = parser.parse_args()

    asyncio.run(main(args.tenant, args.analysis_id, args.golden_set, args.report))
