"""
Main worker module for the AI agent.

This module contains the core asynchronous function that executes a single agent cycle,
from fetching tasks to running the graph.
"""

import asyncio
import json
import logging
import os
import sys
from contextlib import AsyncExitStack
from typing import Any

from core.models import AgentConfig
from cryptography.fernet import Fernet
from flask import Flask
from langchain.chat_models import BaseChatModel
from langgraph.graph import StateGraph

from agent.graph import create_workflow
from agent.llm_factory import get_llm
from agent.mcp_adapter import McpServerClient
from agent.system_mappings import SYSTEM_DEFINITIONS
from agent.utils import (
    ensure_repository_exists,
    get_workbench,
    get_workspace,
    log_agent_state,
    save_graph_as_mermaid,
    save_graph_as_png,
)

logger = logging.getLogger(__name__)


def _get_agent_config():
    """Loads the agent configuration."""
    config = AgentConfig.query.first()
    if not config or not config.is_active:
        logger.info("Agent is not active or not configured. Skipping cycle.")
        return None
    return config


def get_sys_config(config, encryption_key: Fernet) -> dict[str, Any] | None:
    """Loads and decrypts the agent configuration."""

    logger.info("Starting agent cycle for system: %s", config.task_system_type)
    if config.task_system_type not in SYSTEM_DEFINITIONS:
        logger.error("Task system '%s' not defined.", config.task_system_type)
        return None

    sys_config = ""
    try:
        sys_config = json.loads(
            encryption_key.decrypt(config.system_config_json.encode()).decode() or "{}"
        )
    except (TypeError, AttributeError, json.JSONDecodeError):
        logger.error("Could not parse or decrypt existing configuration.")
        return None

    return sys_config


async def run_agent_cycle_async(app: Flask, encryption_key: Fernet) -> None:
    """Runs one complete asynchronous cycle of the agent."""
    with app.app_context():
        config = _get_agent_config()
        if not config:
            return

        sys_config = get_sys_config(config, encryption_key)
        if not sys_config:
            return

        # Add the remote repo url to the sys_config
        sys_config["github_repo_url"] = config.github_repo_url

        task_env = os.environ.copy()
        task_env.update(sys_config.get("env", {}))

        logger.info("Workspace: %s", get_workspace())

        ensure_repository_exists(
            config.github_repo_url or "https://github.com/tom-test-user/test-repo.git",
            get_workspace(),
        )

        system_def = SYSTEM_DEFINITIONS[config.task_system_type]

        async with AsyncExitStack() as stack:
            # --- Start ALL MCP Servers ---
            git_mcp = McpServerClient(
                command=sys.executable,
                args=["-m", "mcp_server_git", "--repository", get_workspace()],
                env=os.environ.copy(),
            )
            task_mcp = McpServerClient(
                system_def["command"][0], system_def["command"][1:], env=task_env
            )

            await stack.enter_async_context(git_mcp)
            await stack.enter_async_context(task_mcp)

            # --- Agent Stack ---
            agent_stack = (
                "backend" if get_workbench() == "workbench-backend" else "frontend"
            )

            # --- LLM and Graph Creation ---
            llm_large: BaseChatModel = get_llm(sys_config, True)
            llm_small: BaseChatModel = get_llm(sys_config, False)
            workflow: StateGraph = create_workflow(
                llm_large,
                llm_small,
                sys_config,
                agent_stack,
            )

            # --- Graph Execution ---
            app_graph = workflow.compile()
            save_graph_as_png(app_graph)
            save_graph_as_mermaid(app_graph)
            logger.info("Executing graph...")
            final_state = await app_graph.ainvoke(
                {
                    "messages": [],
                    "next_step": "",
                    "trello_card_id": None,
                    "trello_list_id": None,
                    "trello_in_progress": False,
                    "agent_stack": agent_stack,
                },
                {"recursion_limit": 200},
            )
            log_agent_state(final_state)


def run_agent_cycle(app: Flask, encryption_key: Fernet) -> None:
    """Synchronous wrapper for the main async agent cycle."""
    try:
        asyncio.run(run_agent_cycle_async(app, encryption_key))
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Critical error in agent cycle: %s", e, exc_info=True)
