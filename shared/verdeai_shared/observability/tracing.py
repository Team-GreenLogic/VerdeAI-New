"""OpenTelemetry tracing setup."""

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource

from verdeai_shared.settings import settings


def configure_tracing(service_name: str | None = None) -> None:
    """Configure OpenTelemetry tracing. No-op if OTEL endpoint is not set."""
    if not settings.OTEL_EXPORTER_OTLP_ENDPOINT:
        return

    name = service_name or settings.SERVICE_NAME
    resource = Resource(attributes={"service.name": name})
    provider = TracerProvider(resource=resource)

    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        exporter = OTLPSpanExporter(endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT)
        provider.add_span_processor(BatchSpanProcessor(exporter))
    except ImportError:
        pass

    trace.set_tracer_provider(provider)
