"""LLM-judge faithfulness check — promoted out of test_eval_llm.py so both the
unit tests and the gap-analysis eval harness (run_gap_eval.py) share one prompt.
"""

from __future__ import annotations

import json
from typing import Any

from verdeai_shared.llm.openrouter_client import complete
from verdeai_shared.settings import settings

FAITHFULNESS_PROMPT = """
You are an expert AI evaluator.
You will be provided with a SOURCE DOCUMENT and a GENERATED ANALYSIS.
Your task is to determine if the GENERATED ANALYSIS is faithful to the SOURCE DOCUMENT.
Faithful means all claims, facts, and gaps in the GENERATED ANALYSIS are supported by the SOURCE DOCUMENT.
If there is a hallucination or an unsupported claim, output FAITHFUL: False. Otherwise, output FAITHFUL: True.

Return your answer strictly in the following JSON format:
{
    "faithful": boolean,
    "reason": "short explanation of why"
}
"""

COMPLETENESS_PROMPT = """
You are an expert AI evaluator.
You will be provided with a REQUIREMENT STANDARD and a GENERATED ANALYSIS.
Your task is to determine if the GENERATED ANALYSIS addresses all parts of the REQUIREMENT STANDARD.
If the analysis misses any key part of the standard, output COMPLETE: False. Otherwise, output COMPLETE: True.

Return your answer strictly in the following JSON format:
{
    "complete": boolean,
    "reason": "short explanation of why"
}
"""


async def judge_faithfulness(source_document: str, generated_analysis: str) -> dict[str, Any]:
    """Ask the LLM judge whether ``generated_analysis`` is faithful to ``source_document``.

    Returns {"faithful": bool, "reason": str}.
    """
    response = await complete(
        model=settings.PRIMARY_REASONING_MODEL,
        messages=[
            {"role": "system", "content": FAITHFULNESS_PROMPT},
            {"role": "user", "content": f"SOURCE DOCUMENT:\n{source_document}\n\nGENERATED ANALYSIS:\n{generated_analysis}"},
        ],
        response_format={"type": "json_object"},
        name="eval_faithfulness",
    )
    return json.loads(response.choices[0].message.content)  # type: ignore[no-any-return]
