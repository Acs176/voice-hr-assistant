"""Typed runtime settings loaded from environment / .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    livekit_url: str
    livekit_api_key: str
    livekit_api_secret: str

    openai_api_key: str
    deepgram_api_key: str
    eleven_api_key: str
    # Fallback providers — optional. Without a key the provider is skipped (no fallback for
    # that stage); the plugin raises at construction if built without one, so we don't.
    cartesia_api_key: str | None = None  # TTS fallback
    google_api_key: str | None = None  # LLM fallback

    llm_model: str = "gpt-5.4-mini"
    stt_model: str = "nova-3"
    stt_language: str = "multi"
    tts_model: str = "eleven_multilingual_v2"
    tts_voice_id: str = "EXAVITQu4vr4xnSDxMaL"  # ElevenLabs "Sarah" — multilingual, warm

    sessions_dir: Path = Path("sessions")

    # Langfuse tracing — optional. Leave the keys unset to disable (tracing becomes a no-op).
    # Defaults target a locally self-hosted instance (see docker-compose.langfuse.yml).
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "http://localhost:3000"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # fields populated from env
