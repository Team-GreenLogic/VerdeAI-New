"""Gap Analyzer — aio-pika message handler."""

import aio_pika
import redis.asyncio as aioredis
from aio_pika import IncomingMessage
from loguru import logger

from verdeai_shared.db.mongo import get_database
from verdeai_shared.settings import settings
from verdeai_shared.db.repositories.iso_clauses import ISOClausesRepository
from verdeai_shared.db.repositories.result_store import ResultStoreRepository
from verdeai_shared.messaging.connection import get_channel
from verdeai_shared.messaging.events import AnalysisGapsReady, AnalysisRequested

from verdeai_shared.pipeline.missing_requests import generate_missing_requests
from verdeai_shared.pipeline.recommendations import generate_recommendations

from app.pipeline.analyse_clause import AnalysisPaused, analyse_clause
from app.progress import emit

_GAP_DECISIONS = ("Met", "Insufficient Evidence")


async def handle_analysis_requested(message: IncomingMessage) -> None:
    """Deserialise an AnalysisRequested event and run the full gap analysis pipeline."""
    raw = message.body.decode()
    try:
        event = AnalysisRequested.model_validate_json(raw)
    except Exception as exc:
        logger.error("Failed to parse AnalysisRequested event", error=str(exc), raw=raw)
        raise

    tenant_id = event.tenant_id
    analysis_id = event.analysis_id
    scope = event.scope

    db = get_database()

    # Atomically claim the analysis: only proceed if status is still "pending".
    # Prevents duplicate processing if the message is redelivered while another
    # worker already picked it up, and skips paused analyses that were paused
    # before the worker picked them up.
    claim = await db.analyses.find_one_and_update(
        {"analysis_id": analysis_id, "tenant_id": tenant_id, "status": "pending"},
        {"$set": {"status": "running"}},
    )
    if claim is None:
        doc = await db.analyses.find_one({"analysis_id": analysis_id})
        current_status = doc.get("status") if doc else "unknown"
        logger.info(
            "Analysis not claimable — skipping",
            analysis_id=analysis_id,
            status=current_status,
        )
        return  # ack the message cleanly

    logger.info(
        "Starting gap analysis",
        tenant_id=tenant_id,
        analysis_id=analysis_id,
        scope=scope,
    )

    # Resolve clause list
    all_clauses = await ISOClausesRepository(db).list_all()
    if scope == "full":
        clauses = all_clauses
    else:
        clause_map = {c["clause_id"]: c for c in all_clauses}
        clauses = [clause_map[cid] for cid in scope if cid in clause_map]

    if not clauses:
        logger.warning("No clauses to analyse", analysis_id=analysis_id)
        return

    # Resume support — skip clauses already persisted (handles crash + redelivery)
    existing = await ResultStoreRepository(db, tenant_id).list_for_analysis(analysis_id)
    done_ids = {r["clause_id"] for r in existing}
    if done_ids:
        logger.info(
            "Resuming analysis — skipping completed clauses",
            done=len(done_ids),
            remaining=len(clauses) - len(done_ids),
        )

    total = len(clauses)
    completed = len(done_ids)
    gap_count = sum(1 for r in existing if r.get("decision") != "Met")

    # One persistent Redis connection for the duration of the analysis.
    # Avoids the overhead of creating a new connection for every progress event
    # (especially important for high-frequency per-token thinking events).
    redis: aioredis.Redis = aioredis.from_url(settings.REDIS_URL)  # type: ignore[type-arg]
    try:
        await emit(tenant_id, analysis_id, "analysis", "running",
                   f"Analysing {total} clauses ({completed} already complete)",
                   completed=completed, total=total, gap_count=gap_count,
                   redis_client=redis)

        for clause in clauses:
            clause_id = clause.get("clause_id", "")

            if clause_id in done_ids:
                continue

            # Pause check before each clause
            doc = await db.analyses.find_one(
                {"analysis_id": analysis_id}, {"status": 1}
            )
            if doc and doc.get("status") == "paused":
                logger.info("Analysis paused — stopping cleanly", analysis_id=analysis_id)
                await emit(tenant_id, analysis_id, "analysis", "paused",
                           f"Paused after {completed}/{total} clauses",
                           redis_client=redis)
                return  # ack cleanly; resume will re-publish the event

            await emit(
                tenant_id, analysis_id, "thinking", "progress",
                f"Analysing clause {clause_id}…",
                clause_id=clause_id, completed=completed, total=total, gap_count=gap_count,
                redis_client=redis,
            )
            # Emit one static token immediately so the terminal shows on page reload
            # even while state_compare is running silently.
            await emit(
                tenant_id, analysis_id, "thinking_token", "progress",
                "Comparing organisational state…\n",
                clause_id=clause_id, redis_client=redis,
            )

            # Capture clause_id for the closure (safe — analyse_clause is awaited
            # before the next iteration, so clause_id is stable for this call).
            _cid = clause_id

            async def on_thinking(token: str, *, _id: str = _cid) -> None:
                await emit(
                    tenant_id, analysis_id, "thinking_token", "progress",
                    token, clause_id=_id, redis_client=redis,
                )

            try:
                result = await analyse_clause(db, tenant_id, analysis_id, clause,
                                              on_thinking=on_thinking)
                decision = result.get("decision", "Unknown")
                if decision != "Met":
                    gap_count += 1

                # Inject clause_id so shared pipeline functions can key on it
                result["clause_id"] = clause_id

                # Generate recommendations + missing requests immediately for gap clauses
                if decision not in _GAP_DECISIONS:
                    try:
                        await generate_recommendations(db, tenant_id, analysis_id, result)
                    except Exception as exc:
                        logger.warning("Recommendation generation failed", clause_id=clause_id, error=str(exc))
                    try:
                        await generate_missing_requests(db, tenant_id, analysis_id, result)
                    except Exception as exc:
                        logger.warning("Missing-requests generation failed", clause_id=clause_id, error=str(exc))

            except AnalysisPaused:
                logger.info("Analysis paused mid-clause", analysis_id=analysis_id, clause_id=clause_id)
                await emit(tenant_id, analysis_id, "analysis", "paused",
                           f"Paused during {clause_id} ({completed}/{total} clauses complete)",
                           redis_client=redis)
                return  # ack cleanly; resume will re-publish
            except Exception as exc:
                logger.error("Clause analysis failed", clause_id=clause_id, error=str(exc))
                decision = "Error"
                gap_count += 1

            completed += 1
            await emit(
                tenant_id, analysis_id, "clause", "progress",
                f"{clause_id}: {decision} ({completed}/{total})",
                clause_id=clause_id, decision=decision,
                completed=completed, total=total, gap_count=gap_count,
                redis_client=redis,
            )

        logger.info(
            "Gap analysis complete",
            tenant_id=tenant_id,
            analysis_id=analysis_id,
            clauses=total,
            gaps=gap_count,
        )

        await db.analyses.update_one(
            {"analysis_id": analysis_id, "tenant_id": tenant_id},
            {"$set": {"status": "complete", "gap_count": gap_count}},
        )

        await emit(tenant_id, analysis_id, "complete", "done",
                   f"Analysis complete — {gap_count} gaps found",
                   redis_client=redis)

        await _publish_gaps_ready(AnalysisGapsReady(
            tenant_id=tenant_id,
            analysis_id=analysis_id,
            gap_count=gap_count,
        ))

    except Exception as exc:
        logger.error("Gap analysis pipeline failed", analysis_id=analysis_id, error=str(exc))
        await db.analyses.update_one(
            {"analysis_id": analysis_id, "tenant_id": tenant_id},
            {"$set": {"status": "failed", "error": str(exc)}},
        )
        await emit(tenant_id, analysis_id, "complete", "failed", str(exc),
                   redis_client=redis)
        raise
    finally:
        await redis.aclose()


async def _publish_gaps_ready(event: AnalysisGapsReady) -> None:
    try:
        channel = await get_channel()
        exchange = await channel.get_exchange("analyses")
        await exchange.publish(
            aio_pika.Message(
                body=event.model_dump_json().encode(),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key="analysis.gaps.ready",
        )
        await channel.close()
    except Exception as exc:
        logger.warning("Failed to publish AnalysisGapsReady", error=str(exc))
