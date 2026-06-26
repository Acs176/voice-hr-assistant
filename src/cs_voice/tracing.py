"""Langfuse tracing for the live agent, via LiveKit's native OpenTelemetry support."""

from __future__ import annotations

import logging

from langfuse import Langfuse
from livekit.agents.telemetry import set_tracer_provider
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.util.types import AttributeValue

from cs_voice.config import Settings

logger = logging.getLogger("cs_voice.tracing")


def setup_langfuse(
    settings: Settings, *, metadata: dict[str, AttributeValue] | None = None
) -> TracerProvider | None:
    """Wire LiveKit's OTel spans to Langfuse. Returns the provider (so the caller can
    force_flush() on shutdown), or None if tracing is disabled (keys not set)."""
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        logger.debug("langfuse keys not set — tracing disabled")
        return None

    provider = TracerProvider()
    set_tracer_provider(provider, metadata=metadata)
    Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
        tracer_provider=provider,
        should_export_span=lambda _span: True,  # LiveKit emits many spans; forward them all
    )
    logger.info("langfuse tracing enabled -> %s", settings.langfuse_host)
    return provider


if __name__ == "__main__":
    # Smoke test: emit one span and flush, so you can confirm endpoint + auth without a call.
    from opentelemetry import trace

    logging.basicConfig(level=logging.INFO)
    provider = setup_langfuse(Settings(), metadata={"langfuse.session.id": "smoke-test"})  # type: ignore[call-arg]
    if provider is None:
        raise SystemExit("langfuse keys not set — nothing to test")
    with trace.get_tracer("cs_voice.smoke").start_as_current_span("smoke-test-span"):
        pass
    provider.force_flush()
    print(f"flushed a test span to {Settings().langfuse_host} — check the Langfuse UI")  # type: ignore[call-arg]
