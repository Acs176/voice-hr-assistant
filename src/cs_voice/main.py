"""Worker entrypoint: composes plugins, starts session, registers shutdown."""

from __future__ import annotations

import uuid

from dotenv import load_dotenv
from livekit import agents
from livekit.agents import AgentSession, RoomInputOptions
from livekit.plugins import deepgram, elevenlabs, openai, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel

from cs_voice.agent import SupportAgent
from cs_voice.config import Settings, get_settings
from cs_voice.persistence import save_session
from cs_voice.state import SessionState

load_dotenv()


def _build_session(settings: Settings) -> AgentSession[None]:
    return AgentSession(
        stt=deepgram.STT(model=settings.stt_model, language=settings.stt_language),
        llm=openai.LLM(model=settings.llm_model),
        tts=elevenlabs.TTS(model=settings.tts_model),
        vad=silero.VAD.load(),
        turn_detection=MultilingualModel(),
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

    await session.start(agent=agent, room=ctx.room, room_input_options=RoomInputOptions())
    await session.generate_reply(
        instructions="Greet the caller as Mar from Orbio support, and ask how you can help today."
    )


def main() -> None:
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))


if __name__ == "__main__":
    main()
