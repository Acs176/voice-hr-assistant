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

    llm_model: str = "gpt-4o-mini"
    stt_model: str = "nova-3"
    stt_language: str = "multi"
    tts_model: str = "eleven_multilingual_v2"
    tts_voice_id: str = "EXAVITQu4vr4xnSDxMaL"  # ElevenLabs "Sarah" — multilingual, warm

    sessions_dir: Path = Path("sessions")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # fields populated from env
