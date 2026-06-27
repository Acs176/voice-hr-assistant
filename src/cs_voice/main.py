"""Worker entrypoint: composes plugins, starts session, registers shutdown."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

from dotenv import load_dotenv
from livekit import agents
from livekit.agents import (
    AgentSession,
    AudioConfig,
    BackgroundAudioPlayer,
    BuiltinAudioClip,
    RoomInputOptions,
    inference,
    llm,
    stt,
    tts,
)
from livekit.plugins import cartesia, deepgram, elevenlabs, google, openai, silero

from cs_voice import rag
from cs_voice.agent import SupportAgent
from cs_voice.config import Settings, get_settings
from cs_voice.persistence import save_session
from cs_voice.state import SessionState
from cs_voice.summarizer import summarize
from cs_voice.tracing import setup_langfuse

load_dotenv()

log = logging.getLogger(__name__)


def _build_session(settings: Settings, vad: silero.VAD) -> AgentSession[None]:
    # Fallback providers are only added when their key is set
    llm_providers: list[llm.LLM[Any]] = [openai.LLM(model=settings.llm_model)]
    if settings.google_api_key:
        llm_providers.append(google.LLM(model="gemini-3.1-flash-lite"))

    tts_providers: list[tts.TTS[Any]] = [
        elevenlabs.TTS(model=settings.tts_model, voice_id=settings.tts_voice_id)
    ]
    if settings.cartesia_api_key:
        tts_providers.append(cartesia.TTS())

    return AgentSession(
        stt=stt.FallbackAdapter([
            deepgram.STT(
                model=settings.stt_model,
                language=settings.stt_language,
                numerals=True,
            ),
            # Whisper isn't streaming; FallbackAdapter needs every STT to stream, so
            # VAD-segment it into a StreamAdapter.
            stt.StreamAdapter(stt=openai.STT(), vad=vad),
        ]),
        llm=llm.FallbackAdapter(llm_providers),
        tts=tts.FallbackAdapter(tts_providers),
        vad=vad,
        turn_detection=inference.TurnDetector(),
        preemptive_generation=True,
    )


def prewarm(proc: agents.JobProcess) -> None:
    # Runs once per worker subprocess before any job lands. Heavy, reusable
    # loads go here so they're off the call's critical path. Index is built
    # at deploy time (`python -m cs_voice.rag`); load is sync + offline.
    try:
        t = time.perf_counter()
        proc.userdata["vad"] = silero.VAD.load()
        proc.userdata["retriever"] = rag.load_retriever(api_key=get_settings().openai_api_key)
        log.info("prewarm done in %.2fs", time.perf_counter() - t)
    except Exception:
        log.exception("prewarm failed; worker will not accept jobs")
        raise


async def entrypoint(ctx: agents.JobContext) -> None:
    settings = get_settings()
    state = SessionState()
    retriever = ctx.proc.userdata["retriever"]
    vad = ctx.proc.userdata["vad"]
    agent = SupportAgent(state, ctx, retriever)
    session_id = uuid.uuid4().hex[:8]

    tracer_provider = setup_langfuse(settings, metadata={"langfuse.session.id": session_id})

    session = _build_session(settings, vad)

    async def on_shutdown() -> None:
        # Caller is gone; bound the summary so a slow LLM can't eat the shutdown
        # drain window and skip save_session entirely.
        summary = None
        try:
            summary = await asyncio.wait_for(
                summarize(
                    session.history.to_dict().get("items", []),
                    state.snapshot(),
                    settings.llm_model,
                ),
                timeout=10.0,
            )
        except Exception as e:
            log.warning("summary skipped: %s", e)
        save_session(settings.sessions_dir, session_id, state, session, summary)
        if tracer_provider is not None:
            tracer_provider.force_flush()  # drain buffered spans before the worker exits

    ctx.add_shutdown_callback(on_shutdown)

    # delete_room() returns an already-scheduled asyncio.Future; we just need
    # to hold a reference so it isn't GC'd before the loop runs it.
    pending: set[asyncio.Future[Any]] = set()

    @ctx.room.on("participant_disconnected")
    def _on_participant_disconnected(_participant: object) -> None:
        fut = ctx.delete_room()
        pending.add(fut)
        fut.add_done_callback(pending.discard)

    await session.start(agent=agent, room=ctx.room, room_input_options=RoomInputOptions())

    background = BackgroundAudioPlayer(
        thinking_sound=[
            AudioConfig(BuiltinAudioClip.KEYBOARD_TYPING, volume=0.6),
            AudioConfig(BuiltinAudioClip.KEYBOARD_TYPING2, volume=0.7),
        ],
        ambient_sound=AudioConfig(BuiltinAudioClip.OFFICE_AMBIENCE, volume=0.6),
    )
    await background.start(room=ctx.room, agent_session=session)

    await session.say("Hi! You've reached Mar in HR at Orbio. How can I help you today?")


def main() -> None:
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))


if __name__ == "__main__":
    main()
