# cs-voice

Voice support agent for Orbio (HR platform).

## Stack

- **LiveKit Agents** — voice loop, WebRTC, turn detection
- **Deepgram Nova-3** — multilingual STT
- **ElevenLabs Flash v2.5** — TTS
- **OpenAI gpt-4o-mini** — LLM
- **Silero VAD** + LiveKit multilingual turn detector

## Layout

```
src/cs_voice/
  main.py         entrypoint, wires plugins + session
  agent.py        SupportAgent + slot-recording tools
  state.py        Slot, SessionState, enums
  parsing.py      deterministic value parsers
  persistence.py  per-session JSON sink
  config.py       typed settings (pydantic-settings)
  prompts/        markdown prompts + loader
tests/            pytest, unit tests against pure modules
sessions/         gitignored runtime dumps
```

## Setup

```bash
make install
cp .env.example .env   # fill in keys
uv run cs-voice download-files   # one-time: VAD + turn-detector weights
```

Get a LiveKit Cloud project, grab URL/key/secret. API keys from OpenAI, Deepgram, ElevenLabs.

## Run

```bash
make run
```

Then open the [LiveKit Agents Playground](https://agents-playground.livekit.io), connect to your project, and talk to it.

## Develop

```bash
make test     # pytest
make lint     # ruff + mypy
make format   # ruff format + autofix
```
