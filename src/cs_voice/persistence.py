"""Session sink: writes one JSON file per call with state + transcript."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from livekit.agents import AgentSession

from cs_voice.state import SessionState


def save_session(
    sessions_dir: Path,
    session_id: str,
    state: SessionState,
    session: AgentSession[Any],
) -> Path:
    sessions_dir.mkdir(parents=True, exist_ok=True)
    path = sessions_dir / f"{session_id}.json"
    path.write_text(
        json.dumps(
            {
                "session_id": session_id,
                "complete": state.is_complete(),
                "state": state.model_dump(),
                "transcript": session.history.to_dict(),
            },
            indent=2,
        )
    )
    return path
