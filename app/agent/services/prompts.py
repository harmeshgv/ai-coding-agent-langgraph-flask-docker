"""Helpers for loading system prompts for each agent role and stack."""

from __future__ import annotations

import logging
import os


logger = logging.getLogger(__name__)

__all__ = ["load_system_prompt"]


def load_system_prompt(stack: str, role: str) -> str:
    """Load the system prompt for the given stack and role."""
    file_path = os.path.join("workbench", stack, f"systemprompt_{role}.md")
    logger.info("Loading system prompt: %s", file_path)
    try:
        with open(file_path, "r", encoding="utf-8") as handle:
            return handle.read()
    except FileNotFoundError:
        logger.warning("WARNUNG: System Prompt not found: %s", file_path)
        return "You are a helpful coding assistent."
