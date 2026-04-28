"""WebSocket glass-box endpoint and WS ticket issuance."""

import json
import uuid

import redis.asyncio as aioredis
from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from loguru import logger

from verdeai_shared.auth.tenant import CurrentPrincipal
from verdeai_shared.settings import settings

from app.config import settings as gw_settings
from app.schemas.documents import WSTicketResponse

router = APIRouter(tags=["websocket"])

_TICKET_PREFIX = "ws_ticket:"


def _redis() -> aioredis.Redis:  # type: ignore[type-arg]
    return aioredis.from_url(settings.REDIS_URL, decode_responses=True)


@router.post("/ws/ticket", response_model=WSTicketResponse)
async def issue_ws_ticket(principal: CurrentPrincipal) -> WSTicketResponse:
    """Issue a single-use WebSocket auth ticket (30 s TTL).

    WebSocket clients cannot send Authorization headers, so they obtain a
    short-lived ticket here and pass it as a query param when connecting.
    """
    ticket = str(uuid.uuid4())
    ttl = gw_settings.WS_TICKET_TTL_SECONDS
    r = _redis()
    try:
        await r.setex(f"{_TICKET_PREFIX}{ticket}", ttl, principal.tenant_id)
    finally:
        await r.aclose()
    return WSTicketResponse(ticket=ticket, expires_in=ttl)


@router.websocket("/ws/jobs/{job_id}")
async def ws_jobs(
    websocket: WebSocket,
    job_id: str,
    ticket: str = Query(...),
) -> None:
    """Subscribe to glass-box progress events for a job.

    Authenticates via a single-use ticket obtained from POST /ws/ticket.
    Forwards Redis pubsub messages on channel glassbox.{tenant_id}.{job_id}
    until a terminal event (status=done|failed) arrives or the client disconnects.
    """
    # Validate and consume the ticket (single-use)
    r = _redis()
    try:
        tenant_id: str | None = await r.getdel(f"{_TICKET_PREFIX}{ticket}")
    finally:
        await r.aclose()

    if not tenant_id:
        await websocket.close(code=4001)
        return

    await websocket.accept()
    channel = f"glassbox.{tenant_id}.{job_id}"
    logger.info("WS client connected", job_id=job_id, tenant_id=tenant_id)

    r_sub = _redis()
    pubsub = r_sub.pubsub()
    try:
        await pubsub.subscribe(channel)

        async for raw_message in pubsub.listen():
            if raw_message["type"] != "message":
                continue

            data_str: str = raw_message["data"]
            try:
                await websocket.send_text(data_str)
            except WebSocketDisconnect:
                break

            # Check for terminal event
            try:
                payload = json.loads(data_str)
                if payload.get("status") in ("done", "failed", "deduped"):
                    break
            except (json.JSONDecodeError, AttributeError):
                pass

    except WebSocketDisconnect:
        logger.info("WS client disconnected", job_id=job_id)
    except Exception as exc:
        logger.error("WS error", job_id=job_id, error=str(exc))
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()
        await r_sub.aclose()
        try:
            await websocket.close()
        except Exception:
            pass
        logger.info("WS connection closed", job_id=job_id)
