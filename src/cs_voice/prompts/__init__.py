"""Prompt loading. Prompts live as .md files alongside this module."""

from __future__ import annotations

from importlib.resources import files


def load_prompt(name: str) -> str:
    return (files(__name__) / f"{name}.md").read_text(encoding="utf-8")
