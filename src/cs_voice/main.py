"""Worker entrypoint: composes plugins, starts session, registers shutdown."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from dotenv import load_dotenv
from livekit import agents
from livekit.agents import AgentSession, RoomInputOptions, inference
from livekit.plugins import deepgram, elevenlabs, openai, silero

from cs_voice.agent import SupportAgent
from cs_voice.config import Settings, get_settings
from cs_voice.persistence import save_session
from cs_voice.state import SessionState

load_dotenv()


def _build_session(settings: Settings) -> AgentSession[None]:
    return AgentSession(
        stt=deepgram.STT(
            model=settings.stt_model,
            language=settings.stt_language,
            numerals=True,
        ),
        llm=openai.LLM(model=settings.llm_model),
        tts=elevenlabs.TTS(model=settings.tts_model, voice_id=settings.tts_voice_id),
        vad=silero.VAD.load(),
        turn_detection=inference.TurnDetector(),
        preemptive_generation=True,
    )


async def entrypoint(ctx: agents.JobContext) -> None:
    settings = get_settings()
    state = SessionState()
    agent = SupportAgent(state, ctx)
    session_id = uuid.uuid4().hex[:8]

    session = _build_session(settings)

    async def on_shutdown() -> None:
        save_session(settings.sessions_dir, session_id, state, session)

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
    await session.say("Hi! You've reached Mar in HR at Orbio. How can I help you today?")


def main() -> None:
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))


if __name__ == "__main__":
    main()
