"""Runtime preparation helpers for the agent worker."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

from core.models import AgentConfig
from cryptography.fernet import Fernet

from agent.core.system_mappings import SYSTEM_DEFINITIONS
from agent.services.git_workspace import ensure_repository_exists
from agent.utils import get_workbench, get_workspace

logger = logging.getLogger(__name__)

DEFAULT_REPO = "https://github.com/tom-test-user/test-repo.git"


@dataclass(frozen=True)
class AgentRuntimeContext:
    """Aggregated runtime inputs required to execute one agent cycle."""

    agent_config: AgentConfig
    sys_config: Dict[str, Any]
    task_env: Dict[str, str]
    agent_stack: str
    system_def: Dict[str, Any]


def prepare_runtime(encryption_key: Fernet) -> Optional[AgentRuntimeContext]:
    """Build the runtime context needed by the agent worker."""
    config = _get_agent_config()
    if not config:
        return None

    sys_config = _get_sys_config(config, encryption_key)
    if not sys_config:
        return None

    sys_config["github_repo_url"] = config.github_repo_url
    task_env = os.environ.copy()
    task_env.update(sys_config.get("env", {}))

    logger.info("Workspace: %s", get_workspace())
    ensure_repository_exists(config.github_repo_url or DEFAULT_REPO, get_workspace())

    if config.task_system_type not in SYSTEM_DEFINITIONS:
        logger.error("Task system '%s' not defined.", config.task_system_type)
        return None

    agent_stack = "backend" if get_workbench() == "workbench-backend" else "frontend"
    system_def = SYSTEM_DEFINITIONS[config.task_system_type]

    return AgentRuntimeContext(
        agent_config=config,
        sys_config=sys_config,
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


def _get_sys_config(config: AgentConfig, encryption_key: Fernet) -> Optional[Dict[str, Any]]:
    """Decrypt and parse the JSON payload stored for the task system."""
    logger.info("Starting agent cycle for system: %s", config.task_system_type)
    sys_config_raw = config.system_config_json or "{}"
    try:
        decrypted = encryption_key.decrypt(sys_config_raw.encode()).decode()
        return json.loads(decrypted or "{}")
    except (TypeError, AttributeError, json.JSONDecodeError) as exc:
        logger.error("Could not parse or decrypt existing configuration: %s", exc)
        return None
