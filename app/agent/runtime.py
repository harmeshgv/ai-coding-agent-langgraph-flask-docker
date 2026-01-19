"""Runtime preparation helpers for the agent worker."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.agent.services.git_workspace import ensure_repository_exists
from app.agent.system_mappings import SYSTEM_DEFINITIONS
from app.agent.utils import get_codespace, get_workbench
from app.core.models import AgentConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentRuntimeContext:
    """Aggregated runtime inputs required to execute one agent cycle."""

    agent_config: AgentConfig
    task_env: Dict[str, str]
    agent_stack: str
    system_def: Dict[str, Any]


def prepare_runtime() -> Optional[AgentRuntimeContext]:
    """Build the runtime context needed by the agent worker."""
    config :AgentConfig = _get_agent_config()
    if not config:
        return None

    logger.info(
        "Agent config:\n%s",
        json.dumps(config.as_dict(), indent=2, default=str),
    )
    if not config.system_config:
        return None

    if not config.github_repo_url:
        logger.error("GitHub repository URL not provided.")
        return None

    config.system_config["github_repo_url"] = config.github_repo_url
    task_env = os.environ.copy()
    task_env.update(config.system_config.get("env", {}))

    logger.info("Codespace: %s", get_codespace())
    ensure_repository_exists(config.github_repo_url, get_codespace())

    if config.task_system_type not in SYSTEM_DEFINITIONS:
        logger.error("Task system '%s' not defined.", config.task_system_type)
        return None

    agent_stack = "backend" if get_workbench() == "workbench-backend" else "frontend"
    system_def = SYSTEM_DEFINITIONS[config.task_system_type]

    return AgentRuntimeContext(
        agent_config=config,
        task_env=task_env,
        agent_stack=agent_stack,
        system_def=system_def,
    )


def _get_agent_config() -> Optional[AgentConfig]:
    """Load the active agent configuration from the database."""
    config = AgentConfig.query.first()
    if not config or not config.is_active:
        logger.info("Agent is not active or not configured. Skipping cycle.")
        return None
    return config
