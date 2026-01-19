"""
Main worker module for the AI agent.

This module contains the core asynchronous function that executes a single agent cycle,
from fetching tasks to running the graph.
"""

import asyncio
import logging
import os
import sys
from contextlib import AsyncExitStack

from cryptography.fernet import Fernet
from flask import Flask
from langchain.chat_models import BaseChatModel
from langgraph.graph import StateGraph

from app.agent.graph import create_workflow
from app.agent.integrations.mcp.adapter import McpServerClient
from app.agent.runtime import AgentRuntimeContext, prepare_runtime
from app.agent.services.graph_assets import save_graph_as_mermaid, save_graph_as_png
from app.agent.services.llm_factory import get_llm
from app.agent.services.logging import log_agent_state
from app.agent.utils import get_codespace

logger = logging.getLogger(__name__)


async def run_agent_cycle_async(app: Flask, encryption_key: Fernet) -> None:
    """Runs one complete asynchronous cycle of the agent."""
    with app.app_context():
        runtime = prepare_runtime(encryption_key)
        if not runtime:
            return

        await _execute_agent_cycle(runtime)


async def _execute_agent_cycle(runtime: AgentRuntimeContext) -> None:
    """Internal helper that orchestrates one graph execution."""
    async with AsyncExitStack() as stack:
        enable_mcp = os.environ.get("ENABLE_MCP_SERVERS", "true").lower() not in {
            "false",
            "0",
            "no",
        }

        if enable_mcp:
            git_mcp = McpServerClient(
                command=sys.executable,
                args=["-m", "mcp_server_git", "--repository", get_codespace()],
                env=os.environ.copy(),
            )
            task_mcp = McpServerClient(
                runtime.system_def["command"][0],
                runtime.system_def["command"][1:],
                env=runtime.task_env,
            )

            await stack.enter_async_context(git_mcp)
            await stack.enter_async_context(task_mcp)
        else:
            logger.info("Skipping MCP server startup (ENABLE_MCP_SERVERS is disabled)")

        llm_large: BaseChatModel = get_llm(runtime.sys_config, True)
        llm_small: BaseChatModel = get_llm(runtime.sys_config, False)
        workflow: StateGraph = create_workflow(
            llm_large,
            llm_small,
            runtime.sys_config,
            runtime.agent_stack,
        )

        app_graph = workflow.compile()
        save_graph_as_png(app_graph)
        save_graph_as_mermaid(app_graph)
        logger.info("Executing graph...")
        final_state = await app_graph.ainvoke(
            {
                "messages": [],
                "next_step": "",
                "task_id": None,
                "task_name": None,
                "task_state_id": None,
                "agent_stack": runtime.agent_stack,
                "agent_skill_level": runtime.agent_config.agent_skill_level,
                "task_skill_level": None,
                "plan_state": None,
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
