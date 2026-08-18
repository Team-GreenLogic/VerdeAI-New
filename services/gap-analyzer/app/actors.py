"""Gap Analyzer — aio-pika message handler."""

from datetime import datetime
from typing import Any

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
from verdeai_shared.retrieval.embedder import embed_query
from verdeai_shared.retrieval.hybrid import hybrid_retrieve

from app.pipeline.aggregation import aggregate_parent_decisions
from app.pipeline.analyse_clause import AnalysisPaused, analyse_clause, build_query_text
from app.progress import emit

_RECOMMENDATION_SKIP_DECISIONS = ("Met", "Insufficient Evidence")
_MISSING_REQUEST_SKIP_DECISIONS = ("Met",)


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
    version_id = event.version_id
    is_delta = event.mode == "delta"

    db = get_database()

    # Atomically claim the analysis.
    # First delivery:  only claim "pending" — prevents two healthy workers racing.
    # Redelivery:      also claim "running" — the previous worker crashed without
    #                  acking; RabbitMQ only sets redelivered=True after the consumer
    #                  disconnected, so re-claiming is safe. The done_ids checkpoint
    #                  below ensures already-completed clauses are skipped.
    allowed_statuses = ["pending", "running"] if message.redelivered else ["pending"]
    claim = await db.analyses.find_one_and_update(
        {"analysis_id": analysis_id, "tenant_id": tenant_id, "status": {"$in": allowed_statuses}},
        {"$set": {"status": "running"}},
    )
    if claim is None:
        doc = await db.analyses.find_one({"analysis_id": analysis_id})
        current_status = doc.get("status") if doc else "unknown"
        logger.info(
            "Analysis not claimable — skipping",
            analysis_id=analysis_id,
            status=current_status,
            redelivered=message.redelivered,
        )
        return  # ack the message cleanly

    logger.info(
        "Starting gap analysis",
        tenant_id=tenant_id,
        analysis_id=analysis_id,
        scope=scope,
    )

    # Resolve clause list for this version
    all_clauses = await ISOClausesRepository(db).list_all(version_id=version_id)
    if scope == "full":
        clauses = all_clauses
    else:
        clause_map = {c["clause_id"]: c for c in all_clauses}
        clauses = [clause_map[cid] for cid in scope if cid in clause_map]

    if not clauses:
        logger.warning("No clauses to analyse", analysis_id=analysis_id)
        return

    # Delta mode: copy the parent analysis's verdicts forward and figure out which
    # clauses were actually affected by evidence added/removed since the baseline.
    # Idempotent — safe on crash + redelivery. prior_verdicts feeds the re-run LLM
    # the previous reasoning as reference context.
    prior_verdicts: dict[str, dict[str, Any]] = {}
    if is_delta:
        baseline_at = event.baseline_at
        if baseline_at is None:
            parent_doc = await db.analyses.find_one({"analysis_id": event.parent_analysis_id})
            baseline_at = (parent_doc or {}).get("created_at")
        to_process_ids = await _prepare_delta(
            db, tenant_id, analysis_id, event.parent_analysis_id, baseline_at, clauses
        )
        parent_results = await ResultStoreRepository(db, tenant_id).list_for_analysis(
            event.parent_analysis_id or ""
        )
        prior_verdicts = {r["clause_id"]: r for r in parent_results}
        logger.info(
            "Delta analysis prepared",
            analysis_id=analysis_id,
            parent_analysis_id=event.parent_analysis_id,
            affected=len(to_process_ids),
            total=len(clauses),
        )
    else:
        # Resume support — skip clauses already persisted (handles crash + redelivery)
        done_ids = {r["clause_id"] for r in await ResultStoreRepository(db, tenant_id).list_for_analysis(analysis_id)}
        if done_ids:
            logger.info(
                "Resuming analysis — skipping completed clauses",
                done=len(done_ids),
                remaining=len(clauses) - len(done_ids),
            )
        to_process_ids = {c.get("clause_id", "") for c in clauses} - done_ids

    # Counters reflect the full clause set; already-persisted/copied clauses count as done.
    # Clauses being (re)processed are excluded from the initial gap tally — the loop
    # adds their fresh decisions — so a copied-then-re-run clause is not counted twice.
    existing = await ResultStoreRepository(db, tenant_id).list_for_analysis(analysis_id)
    total = len(clauses)
    completed = total - len(to_process_ids)
    gap_count = sum(
        1 for r in existing
        if r["clause_id"] not in to_process_ids and r.get("decision") != "Met"
    )

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

            if clause_id not in to_process_ids:
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

            # Persist current clause so a page reload can show the right clause number
            # even while no WS events are flowing (e.g. during silent state_compare).
            await db.analyses.update_one(
                {"analysis_id": analysis_id, "tenant_id": tenant_id},
                {"$set": {"current_clause_id": clause_id}},
            )

            await emit(
                tenant_id, analysis_id, "thinking", "progress",
                f"Analysing clause {clause_id}…",
                clause_id=clause_id, completed=completed, total=total, gap_count=gap_count,
                redis_client=redis,
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
                # Delta: a re-run replaces this clause's copied verdict + downstream,
                # so clear any stale recommendations/missing-requests first (otherwise
                # the idempotency guards in the generators would keep the old ones).
                if is_delta:
                    await db.recommendation_store.delete_many(
                        {"tenant_id": tenant_id, "analysis_id": analysis_id, "clause_id": clause_id}
                    )
                    await db.missing_request_store.delete_many(
                        {"tenant_id": tenant_id, "analysis_id": analysis_id, "clause_id": clause_id}
                    )

                result = await analyse_clause(db, tenant_id, analysis_id, clause,
                                              on_thinking=on_thinking,
                                              redis_client=redis,
                                              prior_verdict=prior_verdicts.get(clause_id))
                decision = result.get("decision", "Unknown")
                if decision != "Met":
                    gap_count += 1

                # Inject clause_id so shared pipeline functions can key on it
                result["clause_id"] = clause_id

                # Emit clause event immediately after persist so history is consistent
                # even if the service crashes during subsequent recommendation generation.
                completed += 1
                await emit(
                    tenant_id, analysis_id, "clause", "progress",
                    f"{clause_id}: {decision} ({completed}/{total})",
                    clause_id=clause_id, decision=decision,
                    completed=completed, total=total, gap_count=gap_count,
                    redis_client=redis,
                )

                # Generate recommendations + missing requests immediately for gap clauses.
                # Recommendations need a diagnosed gap (skipped for Insufficient Evidence);
                # missing-requirement drafts are exactly what Insufficient Evidence calls for,
                # so only "Met" skips those.
                if decision not in _RECOMMENDATION_SKIP_DECISIONS:
                    try:
                        await generate_recommendations(db, tenant_id, analysis_id, result, version_id=version_id)
                    except Exception as exc:
                        logger.warning("Recommendation generation failed", clause_id=clause_id, error=str(exc))
                if decision not in _MISSING_REQUEST_SKIP_DECISIONS:
                    try:
                        await generate_missing_requests(db, tenant_id, analysis_id, result, version_id=version_id)
                    except Exception as exc:
                        logger.warning("Missing-requests generation failed", clause_id=clause_id, error=str(exc))

                # Delta: mark this clause done so a redelivery won't re-run it.
                if is_delta:
                    await db.result_store.update_one(
                        {"tenant_id": tenant_id, "analysis_id": analysis_id, "clause_id": clause_id},
                        {"$set": {"delta_pending": False}},
                    )

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

        # ── Parent-clause aggregation ────────────────────────────────────────────
        # Each clause is analysed independently, so a parent can end up scored more
        # leniently than its own children. Derive parents deterministically from their
        # children before anything downstream reads the verdicts. Uses the full result
        # set (not just to_process_ids) so a delta run also re-derives parents that were
        # copied forward rather than re-analysed.
        all_results = await ResultStoreRepository(db, tenant_id).list_for_analysis(analysis_id)
        parent_updates = aggregate_parent_decisions(all_results)
        if parent_updates:
            by_clause = {r["clause_id"]: r for r in all_results if r.get("clause_id")}
            for cid, new_decision in parent_updates.items():
                previous = by_clause[cid].get("decision", "Unknown")
                note = (
                    chr(10) * 2
                    + f"[Parent aggregation: derived '{new_decision}' from sub-clause "
                    + f"verdicts; independent analysis of this clause said '{previous}'.]"
                )
                await ResultStoreRepository(db, tenant_id).upsert(
                    analysis_id, cid,
                    {"decision": new_decision,
                     "reasoning": (by_clause[cid].get("reasoning", "") + note)},
                )
                by_clause[cid]["decision"] = new_decision
                logger.info("Parent clause aggregated", clause_id=cid,
                            was=previous, now=new_decision)

                # In-loop generation already ran under the pre-aggregation decision, and the
                # gaps.ready consumers skip Met / Insufficient Evidence — so nothing else
                # would ever clean these up.
                if new_decision in ("Met", "Insufficient Evidence"):
                    await db.recommendation_store.delete_many(
                        {"tenant_id": tenant_id, "analysis_id": analysis_id, "clause_id": cid}
                    )
                if new_decision == "Met":
                    await db.missing_request_store.delete_many(
                        {"tenant_id": tenant_id, "analysis_id": analysis_id, "clause_id": cid}
                    )

            # The in-loop accumulator counted pre-aggregation decisions.
            gap_count = sum(1 for r in by_clause.values() if r.get("decision") != "Met")

        logger.info(
            "Gap analysis complete",
            tenant_id=tenant_id,
            analysis_id=analysis_id,
            clauses=total,
            gaps=gap_count,
            parents_aggregated=len(parent_updates),
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


_DELTA_CONTROL_KEYS = {"_id", "tenant_id", "analysis_id", "clause_id", "created_at", "delta_pending"}


async def _prepare_delta(
    db: Any,
    tenant_id: str,
    analysis_id: str,
    parent_analysis_id: str | None,
    baseline_at: datetime | None,
    clauses: list[dict[str, Any]],
) -> set[str]:
    """Copy the parent analysis forward and return the clause ids still needing a
    (re)analysis.

    Idempotent on redelivery, gated by a ``delta_prepared`` sentinel on the
    analysis doc (set only after the copy fully completes):
    - sentinel set  → derive the pending set from the ``delta_pending`` flags.
    - sentinel unset → (re)build the copy from scratch. This is safe because the
      per-clause loop only starts after this returns, so no analysed work can be
      clobbered; result_store copies are upserts and the downstream copy is reset
      first, so a partially-completed prior attempt leaves no duplicates."""
    result_repo = ResultStoreRepository(db, tenant_id)

    analysis_doc = await db.analyses.find_one({"analysis_id": analysis_id}, {"delta_prepared": 1})
    if analysis_doc and analysis_doc.get("delta_prepared"):
        existing_new = await result_repo.list_for_analysis(analysis_id)
        return {r["clause_id"] for r in existing_new if r.get("delta_pending")}

    parent_results = await result_repo.list_for_analysis(parent_analysis_id or "")
    affected = await _compute_affected_clauses(db, tenant_id, baseline_at, clauses, parent_results)

    # Reset any downstream artefacts a crashed prior attempt may have inserted
    # (insert_many is not idempotent) so re-running the copy can't duplicate them.
    await db.recommendation_store.delete_many({"tenant_id": tenant_id, "analysis_id": analysis_id})
    await db.missing_request_store.delete_many({"tenant_id": tenant_id, "analysis_id": analysis_id})

    # Copy every parent verdict into the new analysis; flag affected ones for re-run.
    copied_ids: set[str] = set()
    for r in parent_results:
        cid = r["clause_id"]
        copied_ids.add(cid)
        data = {k: v for k, v in r.items() if k not in _DELTA_CONTROL_KEYS}
        data["delta_pending"] = cid in affected
        await result_repo.upsert(analysis_id, cid, data)

    # Affected clauses with no parent verdict (new to the ISO version) get a durable
    # pending marker so a crash + redelivery still knows to analyse them.
    for cid in affected - copied_ids:
        await result_repo.upsert(analysis_id, cid, {"delta_pending": True})

    # Copy downstream artefacts only for clauses we are NOT re-running (affected
    # clauses regenerate their own recommendations/missing-requests).
    await _copy_downstream(db, tenant_id, parent_analysis_id, analysis_id, affected)

    # Mark preparation complete — subsequent redeliveries take the idempotent path.
    await db.analyses.update_one(
        {"analysis_id": analysis_id, "tenant_id": tenant_id},
        {"$set": {"delta_prepared": True}},
    )
    return affected


async def _compute_affected_clauses(
    db: Any,
    tenant_id: str,
    baseline_at: datetime | None,
    clauses: list[dict[str, Any]],
    parent_results: list[dict[str, Any]],
) -> set[str]:
    """Clauses affected by evidence added or removed since ``baseline_at``."""
    parent_by_clause = {r["clause_id"]: r for r in parent_results}
    affected: set[str] = set()

    # Clauses with no parent verdict (e.g. added to the ISO version since) → fresh.
    for c in clauses:
        cid = c.get("clause_id", "")
        if cid and cid not in parent_by_clause:
            affected.add(cid)

    # Category B — a document that supported the clause was removed/modified.
    if baseline_at is not None:
        removed_doc_ids = set(await db.chunks.distinct(
            "document_id",
            {"tenant_id": tenant_id, "superseded": True, "superseded_at": {"$gt": baseline_at}},
        ))
        if removed_doc_ids:
            for cid, r in parent_by_clause.items():
                if set(r.get("source_document_ids") or []) & removed_doc_ids:
                    affected.add(cid)

    # Category A — new evidence relevant to the clause. Runs cheap embed+retrieve
    # (no LLM) per clause; only clauses with enough relevant NEW chunks are re-run.
    for clause in clauses:
        cid = clause.get("clause_id", "")
        if not cid or cid in affected:
            continue
        try:
            query_text = build_query_text(clause)
            vector = await embed_query(query_text)
            chunks = await hybrid_retrieve(
                db, tenant_id, query_text, vector, created_after=baseline_at
            )
        except Exception as exc:
            logger.warning(
                "Delta detection retrieval failed — treating clause as affected",
                clause_id=cid, error=str(exc),
            )
            affected.add(cid)
            continue
        relevant = [
            c for c in chunks
            if c.get("rerank_score", 1.0) >= settings.RERANK_SCORE_THRESHOLD
        ]
        if len(relevant) >= settings.MIN_RELEVANT_CHUNKS:
            affected.add(cid)

    return affected


async def _copy_downstream(
    db: Any,
    tenant_id: str,
    parent_analysis_id: str | None,
    analysis_id: str,
    skip_clauses: set[str],
) -> None:
    """Copy parent recommendations + missing-requests forward for clauses that are
    not being re-analysed."""
    from verdeai_shared.db.repositories.missing_request_store import MissingRequestStoreRepository
    from verdeai_shared.db.repositories.recommendation_store import RecommendationStoreRepository

    control = {"_id", "tenant_id", "analysis_id", "created_at"}

    rec_repo = RecommendationStoreRepository(db, tenant_id)
    parent_recs = await rec_repo.list_for_analysis(parent_analysis_id or "")
    recs = [
        {k: v for k, v in r.items() if k not in control}
        for r in parent_recs if r.get("clause_id") not in skip_clauses
    ]
    await rec_repo.insert_many(analysis_id, recs)

    mr_repo = MissingRequestStoreRepository(db, tenant_id)
    parent_mr = await mr_repo.list_for_analysis(parent_analysis_id or "")
    items = [
        {k: v for k, v in r.items() if k not in control}
        for r in parent_mr if r.get("clause_id") not in skip_clauses
    ]
    await mr_repo.insert_many(analysis_id, items)


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
