from __future__ import annotations

from dotenv import load_dotenv
from livekit import agents
from livekit.agents import Agent, AgentSession, RoomInputOptions
from livekit.plugins import deepgram, elevenlabs, openai, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel

load_dotenv()

PERSONA = """\
You are Mar, a friendly support agent for Orbio, an HR platform for frontline workers.
You help employees with onboarding, payroll, scheduling, and document questions.

Style:
- Speak like a person on a phone call. Short sentences. Contractions. No lists, no markdown.
- One question at a time. Wait for the answer before asking the next thing.
- If you don't understand, say so plainly and ask again.
"""


class SupportAgent(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=PERSONA)


async def entrypoint(ctx: agents.JobContext) -> None:
    session = AgentSession(
        stt=deepgram.STT(model="nova-3", language="multi"),
        llm=openai.LLM(model="gpt-4o-mini"),
        tts=elevenlabs.TTS(model="eleven_flash_v2_5"),
        vad=silero.VAD.load(),
        turn_detection=MultilingualModel(),
    )

    await session.start(
        agent=SupportAgent(),
        room=ctx.room,
        room_input_options=RoomInputOptions(),
    )

    await session.generate_reply(
        instructions="Greet the caller as Mar from Orbio support and ask how you can help."
    )


if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
