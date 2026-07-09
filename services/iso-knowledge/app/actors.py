"""ISO Knowledge — message handler for version build requests."""

import redis.asyncio as aioredis
from aio_pika import IncomingMessage
from loguru import logger

from verdeai_shared.db.mongo import get_database
from verdeai_shared.db.repositories.iso_versions import ISOVersionsRepository
from verdeai_shared.messaging.events import IsoVersionBuildRequested
from verdeai_shared.settings import settings

from app.pipeline.build_version import BuildPaused, build_version


async def handle_iso_build_requested(message: IncomingMessage) -> None:
    """Deserialise an IsoVersionBuildRequested event and run the build pipeline."""
    raw = message.body.decode()
    try:
        event = IsoVersionBuildRequested.model_validate_json(raw)
    except Exception as exc:
        logger.error("Failed to parse IsoVersionBuildRequested", error=str(exc), raw=raw)
        raise

    version_id = event.version_id
    build_job_id = event.build_job_id
    tenant_id = event.tenant_id
    source_docs = event.source_docs

    logger.info("ISO version build started", version_id=version_id, build_job_id=build_job_id, docs=len(source_docs))

    db = get_database()
    redis: aioredis.Redis = aioredis.from_url(settings.REDIS_URL)  # type: ignore[type-arg]

    try:
        await build_version(
            db=db,
            version_id=version_id,
            build_job_id=build_job_id,
            tenant_id=tenant_id,
            source_docs=source_docs,
            redis_client=redis,
        )
        logger.info("ISO version build complete", version_id=version_id)
    except BuildPaused:
        logger.info("ISO version build paused cleanly", version_id=version_id, build_job_id=build_job_id)
        import json as _json
        paused_payload = _json.dumps({"stage": "paused", "status": "paused", "detail": "Build paused — resume to continue"})
        await redis.publish(f"glassbox.{tenant_id}.{build_job_id}", paused_payload)
        # Ack cleanly — do not re-raise; the checkpoint is in MongoDB
        return
    except Exception as exc:
        logger.error("ISO version build failed", version_id=version_id, error=str(exc))
        # Mark version with error so admin can see it in the UI
        try:
            await ISOVersionsRepository(db).update_status(
                version_id, "draft", extra={"build_error": str(exc)}
            )
        except Exception:
            pass

        # Emit failure event to the build job channel
        import json
        payload = json.dumps({"stage": "complete", "status": "failed", "detail": str(exc)})
        channel = f"glassbox.{tenant_id}.{build_job_id}"
        await redis.publish(channel, payload)
        raise
    finally:
        await redis.aclose()
