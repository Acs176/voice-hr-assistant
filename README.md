# cs-voice

Voice HR agent for Orbio. Mar takes calls from employees, answers common HR
questions from a knowledge base, and collects + routes anything that needs a
person.

## Stack

- **LiveKit Agents** — voice loop, WebRTC, turn detection
- **Deepgram Nova-3** — multilingual STT
- **ElevenLabs Multilingual v2** — TTS
- **OpenAI** — LLM (`gpt-5.4-mini`) + embeddings (`text-embedding-3-small`)
- **Silero VAD** + LiveKit **audio turn detector**

## Layout

```
src/cs_voice/
  main.py         entrypoint, wires plugins + session, loads retriever
  agent.py        SupportAgent + tools (lookup_hr_info, slot recording)
  rag.py          KB chunking, embedding, cached index, retriever
  state.py        Slot, SessionState, enums
  parsing.py      deterministic value parsers (employee ID)
  persistence.py  per-session JSON sink (state + transcript)
  config.py       typed settings (pydantic-settings)
  prompts/        persona.md, prompt loader
  prompts/kb/     HR knowledge base (markdown) + cached kb_index.json
tests/            pytest, unit + retrieval eval
sessions/         gitignored runtime dumps
```

## How it works

Each call runs the LiveKit voice loop (VAD → STT → turn detection → LLM → TTS).
`SupportAgent` drives the conversation through `persona.md` and a set of tools.

Mar triages every call into **answer** vs **route**:

- **Answer** — for a general HR question she calls `lookup_hr_info`, which
  embeds the question and does cosine search over the knowledge base. If the top
  match clears the similarity threshold she answers from it and cites the source;
  no employee ID needed.
- **Route** — for an issue (or when the lookup finds nothing) she collects four
  slots — employee ID, category, description, urgency — and hands off. The
  employee ID uses a deterministic parser + two-step readback/confirm. Urgency is
  inferred, never read out as a "low/medium/high" menu.

When a lookup misses, the question already gave her the description and category,
so the pivot to routing only asks for what's still missing.

### Knowledge base / RAG

`rag.py` chunks each KB doc by `##` section, embeds the chunks once, and caches
the vectors to `prompts/kb_index.json` keyed by a content hash — so the index
rebuilds only when the KB changes. Search is in-memory cosine; `best()` applies
`THRESHOLD` and returns `None` below it, which is the agent's "don't invent,
route instead" signal.

```bash
uv run python -m cs_voice.rag        # (re)build the cached index
uv run pytest tests/test_retrieval.py # offline chunking + Q->source eval
```

## Design decisions

- **Answer + route, not just intake.** Most HR calls are FAQs; answering them on
  the call deflects tickets and only routes what needs a human.
- **No vector DB.** A few dozen chunks fit in memory; cosine is microseconds. The
  `Retriever` protocol is the one deliberate abstraction — the seam to swap in
  pgvector/Pinecone when the KB outgrows memory.
- **Committed index.** The eval and CI run offline; embedding the KB is a build
  step, not a startup dependency.
- **Async-first retrieval.** The live agent is the primary caller, so `rag.py`
  uses `AsyncOpenAI` throughout.
- **Deterministic ID parsing** over asking the LLM to transcribe digits — voice
  gets digits wrong, so parse + read back + confirm.

## Setup

```bash
make install
cp .env.example .env   # fill in keys
uv run cs-voice download-files   # one-time: VAD + turn-detector weights
```

LiveKit Cloud project for URL/key/secret. API keys from OpenAI, Deepgram,
ElevenLabs.

## Run

```bash
make run
```

Then open the [LiveKit Agents Playground](https://agents-playground.livekit.io),
connect to your project, and talk to it.

## Develop

```bash
make test     # pytest
make lint     # ruff + mypy
make format   # ruff format + autofix
```
