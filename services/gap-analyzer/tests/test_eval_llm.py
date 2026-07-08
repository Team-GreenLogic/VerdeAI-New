import json
import pytest

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

@pytest.mark.asyncio
async def test_llm_judge_catches_hallucination():
    """Test that the LLM judge can correctly identify an unfaithful (hallucinated) output."""
    source_doc = "The company ACME Corp uses 100% renewable energy (solar and wind) for all its global offices."
    generated_analysis = "ACME Corp has a compliance gap because they rely heavily on coal power for their offices."
    
    response = await complete(
        model=settings.PRIMARY_REASONING_MODEL,
        messages=[
            {"role": "system", "content": FAITHFULNESS_PROMPT},
            {"role": "user", "content": f"SOURCE DOCUMENT:\n{source_doc}\n\nGENERATED ANALYSIS:\n{generated_analysis}"}
        ],
        response_format={"type": "json_object"},
        name="eval_faithfulness"
    )
    result = json.loads(response.choices[0].message.content)
    
    assert result["faithful"] is False, "Judge failed to catch the hallucination about coal."
    assert "coal" in result["reason"].lower() or "renewable" in result["reason"].lower()


@pytest.mark.asyncio
async def test_llm_judge_verifies_faithful_output():
    """Test that the LLM judge correctly passes a faithful output."""
    source_doc = "The company ACME Corp uses 100% renewable energy for all its offices."
    generated_analysis = "ACME Corp is compliant in terms of energy usage as all offices are powered by renewable energy."
    
    response = await complete(
        model=settings.PRIMARY_REASONING_MODEL,
        messages=[
            {"role": "system", "content": FAITHFULNESS_PROMPT},
            {"role": "user", "content": f"SOURCE DOCUMENT:\n{source_doc}\n\nGENERATED ANALYSIS:\n{generated_analysis}"}
        ],
        response_format={"type": "json_object"},
        name="eval_faithfulness"
    )
    result = json.loads(response.choices[0].message.content)
    
    assert result["faithful"] is True, "Judge incorrectly flagged a faithful output."


@pytest.mark.asyncio
async def test_llm_judge_catches_incompleteness():
    """Test that the LLM judge correctly identifies an incomplete analysis."""
    requirement = "The organization must establish, implement, maintain and continually improve an environmental management system."
    generated_analysis = "The organization has established an environmental management system."
    
    response = await complete(
        model=settings.PRIMARY_REASONING_MODEL,
        messages=[
            {"role": "system", "content": COMPLETENESS_PROMPT},
            {"role": "user", "content": f"REQUIREMENT STANDARD:\n{requirement}\n\nGENERATED ANALYSIS:\n{generated_analysis}"}
        ],
        response_format={"type": "json_object"},
        name="eval_completeness"
    )
    result = json.loads(response.choices[0].message.content)
    
    assert result["complete"] is False, "Judge failed to catch that 'continually improve' was missing."
    assert "improve" in result["reason"].lower() or "maintain" in result["reason"].lower()
