"""Safety and deterministic behavior for personalized web research."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.pipeline.personalized_research import (
    OpenSERPClient,
    _assess_pages,
    _coverage,
    _extract_pages,
    _fallback_queries,
    _json_completion,
    _json_text,
    _normalize_query_plan,
    _peer_context,
    _select_results,
    _serp_quality,
    _synthesize,
    canonicalize_url,
    run_personalized_research,
)


def _run() -> dict:
    return {
        "profile_snapshot": {
            "org_name": "Rivermark Metal Finishing",
            "org_industry": "Metal Finishing & Surface Treatment",
            "org_size": "Medium",
            "org_location": "Colombo, Sri Lanka",
            "description": (
                "Rivermark Metal Finishing provides electroplating, powder coating, "
                "anodizing, and corrosion protection services."
            ),
        },
        "gaps": [{
            "reasoning": "Wastewater controls are not consistently documented.",
            "missing_evidence": ["Hazardous waste tracking records"],
        }],
        "baseline_recommendations": [{
            "recommendation_key": "6.1.2:abc",
            "clause_id": "6.1.2",
            "text": "Establish controls for significant environmental aspects.",
        }],
    }


def test_canonicalize_url_removes_fragment_and_rejects_private_targets() -> None:
    assert canonicalize_url("https://Example.com/report/#section") == "https://example.com/report"
    assert canonicalize_url("http://127.0.0.1/private") is None
    assert canonicalize_url("http://localhost:7000/ready") is None
    assert canonicalize_url("file:///etc/passwd") is None


def test_fallback_queries_are_grounded_in_profile_and_gaps() -> None:
    context = {
        "industry": "Textile manufacturing",
        "operational_context": "Produces dyed cotton garments",
        "region": "Sri Lanka",
    }
    queries = _fallback_queries(context)

    assert len(queries) == 4
    assert {row["category"] for row in queries} == {
        "peer_case_study",
        "process_practice",
        "technical_guidance",
        "regional_regulation",
    }
    assert "textile manufacturing" in queries[0]["query"]
    assert "Sri Lanka" in queries[3]["query"]


def test_peer_context_and_queries_never_expose_company_name() -> None:
    run = _run()
    context = _peer_context(run)
    plan = _normalize_query_plan(
        [
            {
                "category": "peer_case_study",
                "query": "Rivermark Metal Finishing environmental case study",
            }
        ],
        context,
        run["profile_snapshot"]["org_name"],
    )

    serialized_context = str(context).casefold()
    assert "rivermark metal finishing" not in serialized_context
    assert all(
        "rivermark" not in row["query"].casefold()
        for row in plan
    )
    assert len(plan) == 4


def test_serp_quality_rejects_generic_metal_results() -> None:
    query = "metal finishing pollution prevention guide"
    junk = [{"title": "Metal - Wikipedia", "snippet": "A metal is a chemical element."}]
    relevant = [{
        "title": "Metal Finishing Pollution Prevention Guide",
        "snippet": "Guidance for metal finishers and wastewater controls.",
    }]

    assert _serp_quality(query, junk) == 0
    assert _serp_quality(query, relevant) == 1


@pytest.mark.asyncio
async def test_openserp_retries_with_fallback_engines_for_misaligned_results() -> None:
    primary_response = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {
            "results": [{
                "type": "organic",
                "engine": "bing",
                "title": "Metal - Wikipedia",
                "snippet": "A metal is a chemical element.",
            }]
        },
    )
    fallback_response = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {
            "results": [{
                "type": "organic",
                "engine": "duckduckgo",
                "title": "Metal Finishing Pollution Prevention Guide",
                "snippet": "EPA guidance for metal finishers.",
            }]
        },
    )
    http_client = SimpleNamespace(
        get=AsyncMock(side_effect=[primary_response, fallback_response]),
        aclose=AsyncMock(),
    )

    with patch(
        "app.pipeline.personalized_research.httpx.AsyncClient",
        return_value=http_client,
    ):
        client = OpenSERPClient()
        results = await client.search("metal finishing pollution prevention guide")
        await client.close()

    assert results[0]["engine"] == "duckduckgo"
    assert http_client.get.await_count == 2
    assert http_client.get.await_args_list[0].kwargs["params"]["engines"] == "bing,google"
    assert (
        http_client.get.await_args_list[1].kwargs["params"]["engines"]
        == "duckduckgo,yandex"
    )


@pytest.mark.asyncio
async def test_result_selection_preserves_query_and_domain_diversity() -> None:
    results = [
        {
            "canonical_url": f"https://source-{index}.example/report",
            "title": f"Evidence {index}",
            "snippet": "Relevant environmental practice",
            "rank": 1,
            "query": f"query {index}",
            "query_category": category,
        }
        for index, category in enumerate(
            [
                "peer_case_study",
                "process_practice",
                "technical_guidance",
                "regional_regulation",
            ],
            start=1,
        )
    ]
    results.append({
        "canonical_url": "https://property.example/listing",
        "title": "Apartment for sale",
        "snippet": "Three bedrooms and two bathrooms",
        "rank": 1,
        "query": "regional query",
        "query_category": "regional_regulation",
    })
    model_result = {
        "evaluations": [{
            "url": results[0]["canonical_url"],
            "relevant": True,
            "score": 0.9,
            "source_type": "peer_case_study",
            "reason": "A concrete peer case study",
        }]
    }

    with patch(
        "app.pipeline.personalized_research._json_completion",
        new=AsyncMock(return_value=model_result),
    ):
        selected = await _select_results(results, _peer_context(_run()))

    assert len(selected) == 4
    assert "https://property.example/listing" not in selected
    assert {row["query_category"] for row in selected.values()} == {
        "peer_case_study",
        "process_practice",
        "technical_guidance",
        "regional_regulation",
    }


@pytest.mark.asyncio
async def test_follow_up_query_rejects_exact_company_search() -> None:
    run = _run()
    context = _peer_context(run)
    malicious_plan = {
        "queries": [{
            "category": "peer_case_study",
            "query": "Rivermark Metal Finishing Colombo environmental targets",
        }]
    }

    with patch(
        "app.pipeline.personalized_research._json_completion",
        new=AsyncMock(return_value=malicious_plan),
    ):
        sufficient, queries = await _coverage(run, context, [], [])

    assert not sufficient
    assert queries
    assert all(
        "rivermark" not in row["query"].casefold()
        for row in queries
    )


@pytest.mark.asyncio
async def test_coverage_requires_balanced_four_source_portfolio() -> None:
    retained = [
        {"domain": "regulator.example", "source_type": "regulatory"},
        {"domain": "peer-one.example", "source_type": "peer_case_study"},
        {"domain": "technical.example", "source_type": "technical"},
        {"domain": "peer-two.example", "source_type": "company_report"},
    ]

    sufficient, queries = await _coverage(_run(), _peer_context(_run()), retained, [])

    assert sufficient
    assert queries == []


@pytest.mark.asyncio
async def test_extraction_preserves_per_url_results_and_retries_only_html() -> None:
    html_url = "https://regulator.example/licensing"
    retry_url = "https://peer.example/environment"
    pdf_url = "https://regulator.example/guide.pdf"
    selected = [
        {"source_id": "source-1", "url": html_url, "status": "visiting"},
        {"source_id": "source-2", "url": retry_url, "status": "visiting"},
        {"source_id": "source-3", "url": pdf_url, "status": "visiting"},
    ]
    client = SimpleNamespace(
        extract=AsyncMock(return_value=[
            {
                "page_content": "",
                "metadata": {"source": pdf_url, "error": "HTML parser rejected PDF"},
            },
            {"page_content": "", "metadata": {"source": retry_url}},
            {
                "page_content": "Licensing requirements",
                "metadata": {"source": html_url, "title": "Licensing"},
            },
        ]),
        extract_one=AsyncMock(return_value={
            "page_content": "Peer environmental controls",
            "metadata": {"source": retry_url, "mode_used": "rendered"},
        }),
    )

    pages = await _extract_pages(client, selected)

    assert pages[html_url]["title"] == "Licensing"
    assert pages[retry_url]["content"] == "Peer environmental controls"
    assert client.extract_one.await_args.args == (retry_url,)
    assert selected[1]["attempt_count"] == 2
    assert selected[2]["status"] == "skipped"
    assert selected[2]["failure_code"] == "unsupported_pdf"
    assert pdf_url not in pages


@pytest.mark.asyncio
async def test_pdf_failure_plans_html_replacement_even_when_coverage_is_sufficient() -> None:
    retained = [
        {"domain": "regulator.example", "source_type": "regulatory"},
        {"domain": "peer-one.example", "source_type": "peer_case_study"},
        {"domain": "technical.example", "source_type": "technical"},
        {"domain": "peer-two.example", "source_type": "company_report"},
    ]
    failed = [{
        "source_id": "source-5",
        "failure_code": "unsupported_pdf",
        "query": "metal finishing pollution prevention guide",
        "query_category": "technical_guidance",
    }]

    sufficient, queries = await _coverage(
        _run(), _peer_context(_run()), retained, [], failed
    )

    assert not sufficient
    assert queries == [{
        "category": "technical_guidance",
        "query": "metal finishing pollution prevention guide HTML guide -filetype:pdf",
        "replacement_for_source_id": "source-5",
    }]
    assert failed[0]["replacement_query"] == queries[0]["query"]


@pytest.mark.asyncio
async def test_page_assessment_retries_only_missing_urls() -> None:
    pages = [
        {"url": f"https://source-{index}.example/page", "title": "Guide", "content": "Evidence"}
        for index in range(3)
    ]
    calls = 0

    async def partial_then_complete(system: str, user: str, max_tokens: int = 1800) -> dict:
        nonlocal calls
        del system, max_tokens
        calls += 1
        payload = json.loads(user)
        supplied = payload["pages"]
        if calls == 1:
            supplied = supplied[:2]
        return {"assessments": [{
            "url": page["url"],
            "relevant": True,
            "summary": "Useful evidence",
            "recommendation_keys": ["6.1.2:abc"],
        } for page in supplied]}

    with patch(
        "app.pipeline.personalized_research._json_completion",
        new=AsyncMock(side_effect=partial_then_complete),
    ):
        assessments = await _assess_pages(pages, _run(), _peer_context(_run()))

    assert calls == 2
    assert set(assessments) == {page["url"] for page in pages}


def test_json_payload_limit_never_returns_truncated_json() -> None:
    with pytest.raises(ValueError, match="payload exceeds"):
        _json_text({"content": "x" * 100}, limit=20)


def _synthesis_result(row: dict, source_ids: list[str] | None = None) -> dict:
    key = row["recommendation_key"]
    return {
        "recommendation_key": key,
        "personalized_text": (
            f"For Rivermark's metal-finishing operations, implement {row['text'].lower()}"
        ),
        "rationale": "This addresses the documented operational gap for a medium-sized finisher.",
        "action_steps": [
            "Assign an EMS owner and due date.",
            "Document the operating control and evidence template.",
            "Review completion and effectiveness each month.",
        ],
        "peer_practices": ["Comparable finishers track the control in an EMS register."],
        "source_ids": source_ids or [],
        "limited_web_evidence": not source_ids,
    }


@pytest.mark.asyncio
async def test_synthesis_batches_large_recommendation_sets_without_fallback_copying() -> None:
    run = _run()
    run["baseline_recommendations"] = [
        {
            "recommendation_key": f"6.1.2:key-{index}",
            "clause_id": "6.1.2",
            "text": f"Implement environmental control {index}.",
        }
        for index in range(17)
    ]
    retained = [{
        "source_id": "source-1",
        "url": "https://regulator.example/guide",
        "title": "Finishing guide",
        "recommendation_keys": [
            row["recommendation_key"] for row in run["baseline_recommendations"]
        ],
    }]

    async def complete_batch(system: str, user: str, max_tokens: int = 1800) -> dict:
        del system, max_tokens
        payload = json.loads(user)
        return {
            "recommendations": [
                _synthesis_result(row, ["source-1"])
                for row in payload["baseline_recommendations"]
            ]
        }

    mocked_complete = AsyncMock(side_effect=complete_batch)
    with patch(
        "app.pipeline.personalized_research._json_completion",
        new=mocked_complete,
    ):
        recommendations = await _synthesize(run, retained)

    assert len(recommendations) == 17
    assert mocked_complete.await_count == 3
    assert all(row["personalized_text"] != row["baseline_text"] for row in recommendations)
    assert all(len(row["action_steps"]) == 3 for row in recommendations)
    assert all(row["source_ids"] == ["source-1"] for row in recommendations)


@pytest.mark.asyncio
async def test_synthesis_retries_only_rows_missing_from_model_output() -> None:
    run = _run()
    run["baseline_recommendations"] = [
        {
            "recommendation_key": f"6.1.2:key-{index}",
            "clause_id": "6.1.2",
            "text": f"Implement environmental control {index}.",
        }
        for index in range(2)
    ]
    calls = 0

    async def partial_then_complete(system: str, user: str, max_tokens: int = 1800) -> dict:
        nonlocal calls
        del system, max_tokens
        calls += 1
        payload = json.loads(user)
        rows = payload["baseline_recommendations"]
        if calls == 1:
            rows = rows[:1]
        return {"recommendations": [_synthesis_result(row) for row in rows]}

    with patch(
        "app.pipeline.personalized_research._json_completion",
        new=AsyncMock(side_effect=partial_then_complete),
    ):
        recommendations = await _synthesize(run, [])

    assert calls == 2
    assert len(recommendations) == 2
    assert {row["recommendation_key"] for row in recommendations} == {
        "6.1.2:key-0",
        "6.1.2:key-1",
    }


@pytest.mark.asyncio
async def test_synthesis_fails_instead_of_publishing_unchanged_recommendations() -> None:
    with (
        patch(
            "app.pipeline.personalized_research._json_completion",
            new=AsyncMock(return_value={"recommendations": []}),
        ),
        pytest.raises(RuntimeError, match="generation was incomplete"),
    ):
        await _synthesize(_run(), [])


@pytest.mark.asyncio
async def test_pipeline_persists_diverse_peer_research_audit() -> None:
    run = {
        **_run(),
        "run_id": "run-1",
        "status": "queued",
    }

    class FakeRepository:
        def __init__(self) -> None:
            self.doc = run.copy()

        async def get(self, run_id: str) -> dict:
            assert run_id == "run-1"
            return self.doc

        async def update(self, run_id: str, **fields: object) -> None:
            assert run_id == "run-1"
            self.doc.update(fields)

    class FakeOpenSERPClient:
        async def search(self, query: str) -> list[dict]:
            slug = query.split()[0].casefold().replace("&", "and")
            return [{
                "url": f"https://{slug}.example/evidence",
                "title": query,
                "snippet": "Relevant peer evidence",
                "favicon": f"https://{slug}.example/favicon.ico",
                "rank": 1,
            }]

        async def extract(self, urls: list[str]) -> list[dict]:
            return [
                {"metadata": {"url": url, "title": url}, "page_content": "Evidence"}
                for url in urls
            ]

        async def close(self) -> None:
            return None

    query_plan = [
        {"category": category, "query": f"{category} metal finishing evidence"}
        for category in (
            "peer_case_study",
            "process_practice",
            "technical_guidance",
            "regional_regulation",
        )
    ]
    source_types = {
        "peer_case_study": "peer_case_study",
        "process_practice": "technical",
        "technical_guidance": "official_guidance",
        "regional_regulation": "regulatory",
    }

    async def select_results(
        results: list[dict], context: dict, domain_counts: object
    ) -> dict[str, dict]:
        del context, domain_counts
        return {
            row["canonical_url"]: {
                **row,
                "source_type": source_types[row["query_category"]],
            }
            for row in results
        }

    async def assess_pages(
        pages: list[dict], current_run: dict, context: dict
    ) -> dict[str, dict]:
        del current_run, context
        return {
            page["url"]: {
                "relevant": True,
                "summary": "Comparable environmental practice",
                "evidence": "Documented operational improvement",
                "credibility": "high",
                "source_type": source_types[query_plan[index]["category"]],
                "recommendation_keys": ["6.1.2:abc"],
            }
            for index, page in enumerate(pages)
        }

    repository = FakeRepository()
    with (
        patch(
            "app.pipeline.personalized_research.PersonalizedRecommendationRunsRepository",
            return_value=repository,
        ),
        patch(
            "app.pipeline.personalized_research.OpenSERPClient",
            return_value=FakeOpenSERPClient(),
        ),
        patch(
            "app.pipeline.personalized_research._plan_queries",
            new=AsyncMock(return_value=query_plan),
        ),
        patch(
            "app.pipeline.personalized_research._select_results",
            new=AsyncMock(side_effect=select_results),
        ),
        patch(
            "app.pipeline.personalized_research._assess_pages",
            new=AsyncMock(side_effect=assess_pages),
        ),
        patch(
            "app.pipeline.personalized_research._coverage",
            new=AsyncMock(return_value=(True, [])),
        ),
        patch(
            "app.pipeline.personalized_research._synthesize",
            new=AsyncMock(return_value=[{"limited_web_evidence": False}]),
        ),
        patch("app.pipeline.personalized_research.emit", new=AsyncMock()),
    ):
        await run_personalized_research(object(), "tenant-1", "run-1")

    assert repository.doc["status"] == "complete"
    assert repository.doc["research_strategy_version"] == "peer-context-v3"
    assert len(repository.doc["searches"]) == 4
    assert {row["category"] for row in repository.doc["searches"]} == {
        "peer_case_study",
        "process_practice",
        "technical_guidance",
        "regional_regulation",
    }
    assert repository.doc["retained_source_count"] == 4


@pytest.mark.asyncio
async def test_json_completion_always_mentions_json_for_provider_contract() -> None:
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"assessments": []}'))]
    )
    mocked_complete = AsyncMock(return_value=response)

    with patch(
        "app.pipeline.personalized_research.complete",
        new=mocked_complete,
    ):
        result = await _json_completion("Assess the supplied pages.", "{}")

    assert result == {"assessments": []}
    messages = mocked_complete.await_args.kwargs["messages"]
    assert "json" in messages[0]["content"].lower()
    assert mocked_complete.await_args.kwargs["response_format"] == {"type": "json_object"}
