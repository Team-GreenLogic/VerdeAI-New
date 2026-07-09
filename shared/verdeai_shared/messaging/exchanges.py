"""Exchange and quorum queue declarations."""

import aio_pika
from aio_pika import Channel, ExchangeType

_QUORUM = {"x-queue-type": "quorum"}
_QUORUM_WITH_DLX = {
    **_QUORUM,
    "x-delivery-limit": 5,
}


async def declare_topology(channel: Channel) -> None:
    """Declare all exchanges, queues and bindings idempotently.

    Queue arguments must match definitions.json exactly or RabbitMQ will
    raise PRECONDITION_FAILED on re-declaration.
    """

    # --- documents exchange ---
    docs_ex = await channel.declare_exchange(
        "documents", ExchangeType.TOPIC, durable=True
    )
    docs_dlx = await channel.declare_exchange(
        "documents.dlx", ExchangeType.FANOUT, durable=True
    )

    docs_process_q = await channel.declare_queue(
        "documents.process",
        durable=True,
        arguments={**_QUORUM_WITH_DLX, "x-dead-letter-exchange": "documents.dlx"},
    )
    await docs_process_q.bind(docs_ex, routing_key="document.uploaded")

    docs_invalidate_q = await channel.declare_queue(
        "documents.invalidate",
        durable=True,
        arguments={**_QUORUM_WITH_DLX, "x-dead-letter-exchange": "documents.dlx"},
    )
    await docs_invalidate_q.bind(docs_ex, routing_key="document.deleted")

    docs_dlq = await channel.declare_queue(
        "documents.dlq", durable=True, arguments=_QUORUM
    )
    await docs_dlq.bind(docs_dlx)

    # --- analyses exchange ---
    ana_ex = await channel.declare_exchange(
        "analyses", ExchangeType.TOPIC, durable=True
    )
    ana_dlx = await channel.declare_exchange(
        "analyses.dlx", ExchangeType.FANOUT, durable=True
    )

    ana_run_q = await channel.declare_queue(
        "analyses.run",
        durable=True,
        arguments={**_QUORUM_WITH_DLX, "x-dead-letter-exchange": "analyses.dlx"},
    )
    await ana_run_q.bind(ana_ex, routing_key="analysis.requested")

    ana_recommend_q = await channel.declare_queue(
        "analyses.recommend",
        durable=True,
        arguments={**_QUORUM_WITH_DLX, "x-dead-letter-exchange": "analyses.dlx"},
    )
    await ana_recommend_q.bind(ana_ex, routing_key="analysis.gaps.ready")

    ana_missing_q = await channel.declare_queue(
        "analyses.missing",
        durable=True,
        arguments={**_QUORUM_WITH_DLX, "x-dead-letter-exchange": "analyses.dlx"},
    )
    await ana_missing_q.bind(ana_ex, routing_key="analysis.gaps.ready")

    ana_dlq = await channel.declare_queue(
        "analyses.dlq", durable=True, arguments=_QUORUM
    )
    await ana_dlq.bind(ana_dlx)

    # --- iso exchange ---
    iso_ex = await channel.declare_exchange(
        "iso", ExchangeType.TOPIC, durable=True
    )
    iso_dlx = await channel.declare_exchange(
        "iso.dlx", ExchangeType.FANOUT, durable=True
    )

    iso_cache_q = await channel.declare_queue(
        "iso.cache_bust",
        durable=True,
        arguments=_QUORUM,
    )
    await iso_cache_q.bind(iso_ex, routing_key="iso.#")

    iso_build_q = await channel.declare_queue(
        "iso.build",
        durable=True,
        arguments={**_QUORUM_WITH_DLX, "x-dead-letter-exchange": "iso.dlx"},
    )
    await iso_build_q.bind(iso_ex, routing_key="iso.build.requested")

    iso_dlq = await channel.declare_queue(
        "iso.dlq", durable=True, arguments=_QUORUM
    )
    await iso_dlq.bind(iso_dlx)
