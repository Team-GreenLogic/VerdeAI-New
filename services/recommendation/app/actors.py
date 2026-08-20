"""Recommendation service — aio-pika message handler."""

from datetime import UTC, datetime

import aio_pika
from aio_pika import IncomingMessage
from loguru import logger
from verdeai_shared.db.mongo import get_database
from verdeai_shared.db.repositories.iso_versions import DEFAULT_VERSION_ID
from verdeai_shared.db.repositories.result_store import ResultStoreRepository
from verdeai_shared.messaging.connection import get_channel
from verdeai_shared.messaging.events import (
    AnalysisGapsReady,
    AnalysisRecommendationsReady,
    PersonalizedRecommendationRequested,
)
from verdeai_shared.progress import emit

from app.pipeline.generate_recommendations import generate_recommendations
from app.pipeline.personalized_research import run_with_timeout

_GAP_DECISIONS = ("Met", "Insufficient Evidence")


async def handle_analysis_gaps_ready(message: IncomingMessage) -> None:
    """Deserialise an AnalysisGapsReady event and generate recommendations for all gap clauses."""
    raw = message.body.decode()
    try:
        event = AnalysisGapsReady.model_validate_json(raw)
    except Exception as exc:
        logger.error("Failed to parse AnalysisGapsReady event", error=str(exc), raw=raw)
        raise

    tenant_id = event.tenant_id
    analysis_id = event.analysis_id
    gap_count = event.gap_count

    logger.info(
        "Generating recommendations",
        tenant_id=tenant_id,
        analysis_id=analysis_id,
        gap_count=gap_count,
    )

    db = get_database()
    await db.analyses.update_one(
        {"tenant_id": tenant_id, "analysis_id": analysis_id},
        {"$set": {"recommendation_status": "running", "recommendation_error_count": 0}},
    )

    # AnalysisGapsReady doesn't carry version_id/profile_id — look them up once so
    # clause/state-template lookups and org-profile evidence isolation inside
    # generate_recommendations hit the correct version and org profile.
    analysis_doc = await db.analyses.find_one(
        {"tenant_id": tenant_id, "analysis_id": analysis_id},
        {"version_id": 1, "profile_id": 1},
    )
    version_id = (
        analysis_doc.get("version_id", DEFAULT_VERSION_ID)
        if analysis_doc
        else DEFAULT_VERSION_ID
    )
    profile_id = analysis_doc.get("profile_id", "") if analysis_doc else ""

    # Load all gap results and filter to actionable clauses
    all_results = await ResultStoreRepository(db, tenant_id).list_for_analysis(analysis_id)
    gap_results = [r for r in all_results if r.get("decision") not in _GAP_DECISIONS]

    if not gap_results:
        logger.info("No gap clauses to recommend for", analysis_id=analysis_id)
        await _publish_recommendations_ready(AnalysisRecommendationsReady(
            tenant_id=tenant_id,
            analysis_id=analysis_id,
        ))
        await db.analyses.update_one(
            {"tenant_id": tenant_id, "analysis_id": analysis_id},
            {"$set": {"recommendation_status": "complete", "recommendation_error_count": 0}},
        )
        return

    total = len(gap_results)
    error_count = 0
    for i, gap_result in enumerate(gap_results, 1):
        clause_id = gap_result.get("clause_id", "?")
        try:
            await generate_recommendations(
                db,
                tenant_id,
                profile_id,
                analysis_id,
                gap_result,
                version_id=version_id,
            )
            logger.info(
                "Recommendations generated",
                clause_id=clause_id,
                progress=f"{i}/{total}",
            )
        except Exception as exc:
            error_count += 1
            logger.error(
                "Failed to generate recommendations for clause",
                clause_id=clause_id,
                error=str(exc),
            )

    await _publish_recommendations_ready(AnalysisRecommendationsReady(
        tenant_id=tenant_id,
        analysis_id=analysis_id,
    ))
    await db.analyses.update_one(
        {"tenant_id": tenant_id, "analysis_id": analysis_id},
        {"$set": {
            "recommendation_status": "partial" if error_count else "complete",
            "recommendation_error_count": error_count,
        }},
    )
    logger.info("Recommendation generation complete", analysis_id=analysis_id, clauses=total)


async def _publish_recommendations_ready(event: AnalysisRecommendationsReady) -> None:
    try:
        channel = await get_channel()
        exchange = await channel.get_exchange("analyses")
        await exchange.publish(
            aio_pika.Message(
                body=event.model_dump_json().encode(),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key="analysis.recommendations.ready",
        )
        await channel.close()
    except Exception as exc:
        logger.warning("Failed to publish AnalysisRecommendationsReady", error=str(exc))


async def handle_personalized_recommendation_requested(message: IncomingMessage) -> None:
    """Run one bounded, persisted web research job."""
    event = PersonalizedRecommendationRequested.model_validate_json(message.body.decode())
    db = get_database()
    try:
        await run_with_timeout(db, event.tenant_id, event.run_id)
    except Exception as exc:
        logger.exception("Personalized recommendation research failed", run_id=event.run_id)
        try:
            await db.personalized_recommendation_runs.update_one(
                {"tenant_id": event.tenant_id, "run_id": event.run_id},
                {
                    "$set": {
                        "status": "failed",
                        "error": str(exc)[:500],
                        "updated_at": datetime.now(UTC),
                        "completed_at": datetime.now(UTC),
                    },
                    "$unset": {"active_profile_key": ""},
                },
            )
        except Exception as persist_exc:
            # Do not requeue a completed research attempt forever when only its
            # terminal-state write fails. Log it for operators and acknowledge
            # the message; recovery can then target the single run explicitly.
            logger.exception(
                "Failed to persist personalized recommendation failure",
                run_id=event.run_id,
                error=str(persist_exc),
            )
        try:
            await emit(
                event.tenant_id,
                event.run_id,
                "failed",
                "failed",
                "Research failed. You can generate another run.",
            )
        except Exception as emit_exc:
            logger.warning(
                "Failed to emit personalized recommendation failure progress",
                run_id=event.run_id,
                error=str(emit_exc),
            )
