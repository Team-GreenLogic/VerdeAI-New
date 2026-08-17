import json
import pytest

from verdeai_shared.llm.openrouter_client import complete
from verdeai_shared.settings import settings

from tests.eval.faithfulness import COMPLETENESS_PROMPT, FAITHFULNESS_PROMPT

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
