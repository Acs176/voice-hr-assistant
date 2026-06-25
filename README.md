# cs-voice

Voice support agent for Orbio (HR platform).

## Stack

- **LiveKit Agents** — voice loop, WebRTC, turn detection
- **Deepgram Nova-3** — multilingual STT
- **ElevenLabs Flash v2.5** — TTS
- **OpenAI gpt-4o-mini** — LLM
- **Silero VAD** + LiveKit multilingual turn detector

## Setup

```bash
uv sync
cp .env.example .env   # fill in keys
uv run python agent.py download-files   # one-time: pulls VAD + turn-detector weights
```

Get a LiveKit Cloud project (free tier is fine), grab URL/key/secret. API keys from OpenAI, Deepgram, ElevenLabs.

## Run

Dev mode (hot reload, talks to a LiveKit room):

```bash
uv run python agent.py dev
```

Then open the [LiveKit Agents Playground](https://agents-playground.livekit.io), connect to your project, and talk to it.
