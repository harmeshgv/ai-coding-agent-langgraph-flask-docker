"""Runtime preparation helpers for the agent worker."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from langchain.chat_models import BaseChatModel

from app.agent.services.git_workspace import ensure_repository_exists
from app.agent.services.llm_factory import get_llm
from app.agent.system_mappings import MCP_SYSTEM_DEFINITIONS
from app.agent.utils import get_codespace, get_workbench
from app.core.models import AgentSettings, Task

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentRuntimeContext:
    """Aggregated runtime inputs required to execute one agent cycle."""

    agent_settings: AgentSettings
    agent_stack: str
    mcp_system_def: Dict[str, Any]
    db_task: Optional[Task]
    llm_large: BaseChatModel
    llm_small: BaseChatModel


def prepare_runtime() -> Optional[AgentRuntimeContext]:
    """Build the runtime context needed by the agent worker."""
    settings: AgentSettings | None = _get_agent_settings()
    if not settings:
        return None

    logger.info(
        "Agent settings:\n%s",
        json.dumps(settings.as_dict(), indent=2, default=str),
    )
    if not settings.github_repo_url:
        logger.error("GitHub repository URL not provided.")
        return None

    logger.info("Codespace: %s", get_codespace())
    ensure_repository_exists(settings.github_repo_url, get_codespace())

    if settings.task_system_type not in MCP_SYSTEM_DEFINITIONS:
        logger.error("Task system '%s' not defined.", settings.task_system_type)
        return None

    agent_stack = "backend" if get_workbench() == "workbench-backend" else "frontend"
    mcp_system_def = MCP_SYSTEM_DEFINITIONS[settings.task_system_type]

    db_task: Task | None = _get_db_task()

    return AgentRuntimeContext(
        agent_settings=settings,
        agent_stack=agent_stack,
        mcp_system_def=mcp_system_def,
        db_task=db_task,
        llm_large=get_llm(settings, True),
        llm_small=get_llm(settings, False),
    )


def _get_agent_settings() -> Optional[AgentSettings]:
    """Load the active agent settings from the database."""
    settings = AgentSettings.query.first()
    if not settings or not settings.is_active:
        logger.info("Agent is not active or not configured. Skipping cycle.")
        return None
    return settings


def _get_db_task() -> Optional[Task]:
    """Load the saved task from the database."""
    task = Task.query.first()
    if not task:
        logger.info("Agent has no current task.")
        return None
    logger.info("Current task found: %s-%s", task.task_id, task.task_name)
    return task
