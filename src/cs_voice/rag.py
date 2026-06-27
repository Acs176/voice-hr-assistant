"""Tiny RAG over the HR knowledge base.

Markdown docs in prompts/kb are chunked by `##` section, embedded once, and cached
to disk (kb_index.json) keyed by a content hash — so the index rebuilds only when
the KB changes. Search is in-memory cosine over a few dozen vectors.

Async-first, because the live agent is the primary caller. `best()` applies the
similarity threshold: it returns None when nothing clears the bar, which is the
"don't invent — route instead" signal the agent acts on.

The `Retriever` protocol is the deliberate seam: swap InMemoryEmbeddingRetriever
for a pgvector/Pinecone-backed one when the KB outgrows memory, without touching
callers. That's the only abstraction here on purpose.

Build/refresh the committed index (needs network + OPENAI_API_KEY):
    python -m cs_voice.rag
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

_PKG = Path(__file__).parent
KB_DIR = _PKG / "prompts" / "kb"
INDEX_PATH = _PKG / "prompts" / "kb_index.json"
EMBED_MODEL = "text-embedding-3-small"
THRESHOLD = 0.30  # cosine floor for a confident answer; below this the agent routes


@dataclass(frozen=True)
class Chunk:
    source: str  # doc stem, e.g. "payroll" — used as the citation
    section: str  # the `##` heading
    text: str  # "<section>. <body>", what actually gets embedded


@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    score: float  # cosine similarity in [-1, 1]


class Retriever(Protocol):
    async def search(self, query: str, k: int = 3) -> list[Hit]: ...
    async def best(self, query: str) -> Hit | None: ...


# --- chunking -------------------------------------------------------------

def chunk_markdown(path: Path) -> list[Chunk]:
    source = path.stem
    chunks: list[Chunk] = []
    section: str | None = None
    buf: list[str] = []

    def flush() -> None:
        if section and (body := " ".join(" ".join(buf).split())):
            chunks.append(Chunk(source, section, f"{section}. {body}"))

    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            flush()
            section, buf = line[3:].strip(), []
        elif line.startswith("# "):
            continue  # doc title, not a section
        else:
            buf.append(line)
    flush()
    return chunks


def load_chunks(kb_dir: Path = KB_DIR) -> list[Chunk]:
    return [c for p in sorted(kb_dir.glob("*.md")) for c in chunk_markdown(p)]


def _content_hash(chunks: list[Chunk], model: str) -> str:
    h = hashlib.sha256(model.encode())
    for c in chunks:
        h.update(c.text.encode())
    return h.hexdigest()[:16]


# --- embedding ------------------------------------------------------------

def _client(api_key: str | None = None) -> object:
    from openai import AsyncOpenAI

    return AsyncOpenAI(api_key=api_key or os.environ["OPENAI_API_KEY"])


async def _embed(client: object, model: str, texts: list[str]) -> NDArray[np.float32]:
    resp = await client.embeddings.create(model=model, input=texts)  # type: ignore[attr-defined]
    vecs = np.array([d.embedding for d in resp.data], dtype=np.float32)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)  # normalize → cosine = dot
    return vecs


# --- index build / load ---------------------------------------------------

async def build_index(
    *, kb_dir: Path = KB_DIR, index_path: Path = INDEX_PATH,
    model: str = EMBED_MODEL, api_key: str | None = None,
) -> Path:
    chunks = load_chunks(kb_dir)
    vecs = await _embed(_client(api_key), model, [c.text for c in chunks])
    index_path.write_text(
        json.dumps(
            {
                "hash": _content_hash(chunks, model),
                "model": model,
                "chunks": [asdict(c) for c in chunks],
                "vectors": vecs.tolist(),
            }
        )
    )
    return index_path


class InMemoryEmbeddingRetriever:
    def __init__(self, chunks: list[Chunk], vectors: NDArray[np.float32], client: object, model: str):
        self._chunks = chunks
        self._vectors = vectors
        self._client = client
        self._model = model

    async def search(self, query: str, k: int = 3) -> list[Hit]:
        q = (await _embed(self._client, self._model, [query]))[0]
        sims = self._vectors @ q
        top = np.argsort(-sims)[:k]
        return [Hit(self._chunks[i], float(sims[i])) for i in top]

    async def best(self, query: str) -> Hit | None:
        """Top hit if it clears THRESHOLD, else None (the agent should route)."""
        hits = await self.search(query, k=1)
        return hits[0] if hits and hits[0].score >= THRESHOLD else None


def load_retriever(
    *, kb_dir: Path = KB_DIR, index_path: Path = INDEX_PATH,
    model: str = EMBED_MODEL, api_key: str | None = None,
) -> InMemoryEmbeddingRetriever:
    """Load the committed index. Sync + offline — no network at boot.
    Raises if the index is missing or stale: rebuild it at deploy time with
    `python -m cs_voice.rag` (needs network + OPENAI_API_KEY)."""
    if not index_path.exists():
        raise RuntimeError(
            f"KB index not found at {index_path}. Build it with: python -m cs_voice.rag"
        )
    data = json.loads(index_path.read_text())
    want = _content_hash(load_chunks(kb_dir), model)
    if data.get("hash") != want:
        raise RuntimeError(
            f"KB index at {index_path} is stale (hash mismatch). "
            "Rebuild with: python -m cs_voice.rag"
        )
    chunks = [Chunk(**c) for c in data["chunks"]]
    vectors = np.array(data["vectors"], dtype=np.float32)
    return InMemoryEmbeddingRetriever(chunks, vectors, _client(api_key), data["model"])


if __name__ == "__main__":
    print("built", asyncio.run(build_index()))
