"""Offline RAGAS evaluation for the VerdeAI Chat RAG pipeline.

This script runs INDEPENDENTLY from the production API.
It connects to your MongoDB, runs the RAG pipeline on a test dataset,
and scores the results using RAGAS metrics.

Usage:
    cd services/chat-rag
    python -m scripts.run_ragas_eval                       # uses default test_dataset.json
    python -m scripts.run_ragas_eval --dataset path/to.json  # custom dataset
    python -m scripts.run_ragas_eval --report md             # markdown report

Prerequisites:
    pip install ragas datasets langchain-openai
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Ensure the project packages are importable ──────────────────────
# When running as `python -m scripts.run_ragas_eval` from services/chat-rag,
# we need the shared package on the path.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]  # VerdeAI-New-main
_SHARED_DIR = _PROJECT_ROOT / "shared"
if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))

from loguru import logger  # noqa: E402

# ── Import the RAG pipeline pieces ──────────────────────────────────
from verdeai_shared.settings import settings  # noqa: E402
from verdeai_shared.retrieval.embedder import embed_query  # noqa: E402
from verdeai_shared.retrieval.hybrid import hybrid_retrieve  # noqa: E402
from verdeai_shared.llm.openrouter_client import complete  # noqa: E402


# ====================================================================
# 1.  TEST DATASET
# ====================================================================

DEFAULT_DATASET: list[dict[str, Any]] = [
    # ── Replace these with REAL questions from your domain ──
    {
        "question": "What is ISO 14001 and what does it cover?",
        "ground_truth": (
            "ISO 14001 is an international standard for environmental management "
            "systems (EMS). It specifies the requirements for establishing, "
            "implementing, maintaining, and continually improving an environmental "
            "management system."
        ),
    },
    {
        "question": "What are the key steps for conducting a gap analysis?",
        "ground_truth": (
            "Key steps include: identifying the standard's requirements, "
            "assessing current compliance status, documenting gaps between "
            "current state and requirements, and creating an action plan "
            "with priorities and timelines to close the gaps."
        ),
    },
    {
        "question": "How should an organization handle non-conformances?",
        "ground_truth": (
            "Organizations should identify non-conformances, take corrective "
            "action to eliminate the root cause, implement preventive measures, "
            "and document the entire process including follow-up verification."
        ),
    },
]


# ====================================================================
# 2.  RUN THE RAG PIPELINE ON EACH QUESTION
# ====================================================================

async def _get_db():
    """Connect to MongoDB (same connection the production service uses)."""
    import motor.motor_asyncio as motor

    client = motor.AsyncIOMotorClient(settings.MONGO_URI)
    return client[settings.MONGO_DB]


async def _run_pipeline_on_question(
    db: Any,
    tenant_id: str,
    question: str,
) -> dict[str, Any]:
    """Execute the retrieval + generation pipeline for a single question.

    Returns:
        {
            "question": str,
            "answer": str,
            "contexts": list[str],   # the retrieved chunk texts
        }
    """
    # ── Step 1: Embed ────────────────────────────────────────────────
    try:
        query_vector = await embed_query(question)
    except Exception as exc:
        logger.warning("Embedding failed for eval question", error=str(exc))
        return {"question": question, "answer": "[embedding failed]", "contexts": []}

    # ── Step 2: Retrieve ─────────────────────────────────────────────
    chunks: list[dict[str, Any]] = []
    if query_vector:
        try:
            chunks = await hybrid_retrieve(db, tenant_id, question, query_vector)
        except Exception as exc:
            logger.warning("Retrieval failed for eval question", error=str(exc))

    contexts = [
        f"{c.get('context_preamble', '')}\n\n{c.get('text', '')}".strip()
        for c in chunks
    ]

    # ── Step 3: Generate answer (non-streaming for eval) ─────────────
    evidence = "\n\n---\n\n".join(
        f"[Chunk {i+1}]\n{ctx}" for i, ctx in enumerate(contexts)
    )
    user_content = question
    if evidence:
        user_content += f"\n\n--- Retrieved document evidence ---\n{evidence}"

    messages = [
        {"role": "system", "content": "You are VerdeAI, an ESG compliance assistant. Answer using only the provided evidence."},
        {"role": "user", "content": user_content},
    ]

    try:
        response = await complete(
            model=settings.CHAT_MODEL,
            messages=messages,
            temperature=0.3,
            max_tokens=1024,
        )
        answer = response.choices[0].message.content or ""
    except Exception as exc:
        logger.error("LLM call failed during eval", error=str(exc))
        answer = "[generation failed]"

    return {
        "question": question,
        "answer": answer,
        "contexts": contexts,
    }


# ====================================================================
# 3.  SCORE WITH RAGAS
# ====================================================================

def run_ragas_evaluation(
    results: list[dict[str, Any]],
    ground_truths: list[str],
) -> dict[str, Any]:
    """Run RAGAS evaluation and return metric scores.

    This function uses the RAGAS library to compute:
    - context_precision   → Are retrieved chunks relevant?
    - context_recall      → Were all needed chunks found?
    - faithfulness        → Is the answer grounded in context?
    - answer_relevancy    → Does the answer address the question?
    """
    from datasets import Dataset
    from ragas import evaluate
    from ragas.metrics import (
        answer_relevancy,
        context_precision,
        context_recall,
        faithfulness,
    )

    # RAGAS expects a HuggingFace Dataset with these columns
    eval_data = {
        "question": [r["question"] for r in results],
        "answer": [r["answer"] for r in results],
        "contexts": [r["contexts"] for r in results],
        "ground_truth": ground_truths,
    }
    dataset = Dataset.from_dict(eval_data)

    # Run evaluation — RAGAS uses an LLM judge internally.
    # It defaults to OpenAI gpt-3.5-turbo. You can override with:
    #   from langchain_openai import ChatOpenAI
    #   llm = ChatOpenAI(model="gpt-4o-mini")
    #   evaluate(dataset, metrics=[...], llm=llm)
    score = evaluate(
        dataset,
        metrics=[
            context_precision,
            context_recall,
            faithfulness,
            answer_relevancy,
        ],
    )

    return score.to_pandas().to_dict()


# ====================================================================
# 4.  REPORT GENERATION
# ====================================================================

def _write_json_report(scores: dict, output_path: Path) -> None:
    """Write scores as a JSON file."""
    output_path.write_text(json.dumps(scores, indent=2, default=str), encoding="utf-8")
    logger.info(f"JSON report written to {output_path}")


def _write_markdown_report(
    scores: dict,
    results: list[dict[str, Any]],
    output_path: Path,
) -> None:
    """Write a human-readable Markdown report."""
    lines = [
        "# RAGAS Evaluation Report",
        f"**Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"**Model:** {settings.CHAT_MODEL}",
        f"**Questions evaluated:** {len(results)}",
        "",
        "## Aggregate Scores",
        "",
        "| Metric | Score |",
        "|--------|-------|",
    ]

    # Compute averages from the per-row scores
    metric_names = ["context_precision", "context_recall", "faithfulness", "answer_relevancy"]
    for metric in metric_names:
        values = list(scores.get(metric, {}).values())
        avg = sum(values) / len(values) if values else 0.0
        lines.append(f"| {metric.replace('_', ' ').title()} | {avg:.2%} |")

    lines += [
        "",
        "## Per-Question Detail",
        "",
    ]

    for i, result in enumerate(results):
        lines.append(f"### Q{i+1}: {result['question']}")
        lines.append(f"- **Chunks retrieved:** {len(result['contexts'])}")
        lines.append(f"- **Answer preview:** {result['answer'][:200]}...")
        for metric in metric_names:
            val = scores.get(metric, {}).get(i, "N/A")
            if isinstance(val, float):
                val = f"{val:.2%}"
            lines.append(f"- **{metric}:** {val}")
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info(f"Markdown report written to {output_path}")


# ====================================================================
# 5.  MAIN
# ====================================================================

async def main(
    dataset_path: str | None = None,
    tenant_id: str = "eval-tenant",
    report_format: str = "json",
) -> None:
    # Load dataset
    if dataset_path and Path(dataset_path).exists():
        raw = json.loads(Path(dataset_path).read_text(encoding="utf-8"))
        test_data = raw if isinstance(raw, list) else raw.get("questions", [])
        logger.info(f"Loaded {len(test_data)} questions from {dataset_path}")
    else:
        test_data = DEFAULT_DATASET
        logger.info(f"Using default dataset with {len(test_data)} questions")

    # Connect to DB
    db = await _get_db()
    logger.info("Connected to MongoDB for evaluation")

    # Run pipeline on each question
    results: list[dict[str, Any]] = []
    ground_truths: list[str] = []

    for i, item in enumerate(test_data):
        logger.info(f"[{i+1}/{len(test_data)}] Evaluating: {item['question'][:80]}...")
        result = await _run_pipeline_on_question(db, tenant_id, item["question"])
        results.append(result)
        ground_truths.append(item["ground_truth"])

    logger.info("Pipeline execution complete. Running RAGAS scoring...")

    # Score with RAGAS
    try:
        scores = run_ragas_evaluation(results, ground_truths)
    except ImportError as exc:
        logger.error(
            f"RAGAS import failed: {exc}. "
            "Install with: pip install ragas datasets langchain-openai"
        )
        # Still save raw results even if RAGAS isn't installed
        scores = {"error": str(exc)}

    # Write report
    output_dir = Path(__file__).parent / "reports"
    output_dir.mkdir(exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    if report_format == "md":
        output_path = output_dir / f"ragas_report_{timestamp}.md"
        _write_markdown_report(scores, results, output_path)
    else:
        output_path = output_dir / f"ragas_report_{timestamp}.json"
        _write_json_report(scores, output_path)

    # Also save raw results for debugging
    raw_path = output_dir / f"raw_results_{timestamp}.json"
    raw_path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    logger.info(f"Raw pipeline results saved to {raw_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run RAGAS evaluation on the VerdeAI RAG pipeline")
    parser.add_argument("--dataset", type=str, default=None, help="Path to test dataset JSON file")
    parser.add_argument("--tenant", type=str, default="eval-tenant", help="Tenant ID to use for retrieval")
    parser.add_argument("--report", type=str, default="json", choices=["json", "md"], help="Output format")
    args = parser.parse_args()

    asyncio.run(main(dataset_path=args.dataset, tenant_id=args.tenant, report_format=args.report))
