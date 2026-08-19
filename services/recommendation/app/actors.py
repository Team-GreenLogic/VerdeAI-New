"""Recommendation service — aio-pika message handler."""

import aio_pika
from aio_pika import IncomingMessage
from loguru import logger

from verdeai_shared.db.mongo import get_database
from verdeai_shared.db.repositories.iso_versions import DEFAULT_VERSION_ID
from verdeai_shared.db.repositories.result_store import ResultStoreRepository
from verdeai_shared.messaging.connection import get_channel
from verdeai_shared.messaging.events import AnalysisGapsReady, AnalysisRecommendationsReady

from app.pipeline.generate_recommendations import generate_recommendations

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

    # AnalysisGapsReady doesn't carry version_id/profile_id — look them up once so
    # clause/state-template lookups and org-profile evidence isolation inside
    # generate_recommendations hit the correct version and org profile.
    analysis_doc = await db.analyses.find_one(
        {"analysis_id": analysis_id}, {"version_id": 1, "profile_id": 1}
    )
    version_id = analysis_doc.get("version_id", DEFAULT_VERSION_ID) if analysis_doc else DEFAULT_VERSION_ID
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
        return

    total = len(gap_results)
    for i, gap_result in enumerate(gap_results, 1):
        clause_id = gap_result.get("clause_id", "?")
        try:
            await generate_recommendations(db, tenant_id, profile_id, analysis_id, gap_result, version_id=version_id)
            logger.info(
                "Recommendations generated",
                clause_id=clause_id,
                progress=f"{i}/{total}",
            )
        except Exception as exc:
            logger.error(
                "Failed to generate recommendations for clause",
                clause_id=clause_id,
                error=str(exc),
            )

    await _publish_recommendations_ready(AnalysisRecommendationsReady(
        tenant_id=tenant_id,
        analysis_id=analysis_id,
    ))
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
