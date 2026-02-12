"""
Main worker module for the AI agent.

This module contains the core asynchronous function that executes a single agent cycle,
from fetching tasks to running the graph.
"""

import logging
import sys
from contextlib import AsyncExitStack

from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph

from app.core.constants import TECH_STACKS
from app.agent.graph import create_workflow
from app.agent.mcp.adapter import McpServerClient
from app.agent.runtime import RuntimeSetting
from app.agent.services.graph_assets import save_graph_as_mermaid, save_graph_as_png
from app.agent.utils import get_codespace, save_state_to_workspace
from app.core.config import get_env_settings

logger = logging.getLogger(__name__)


async def run_agent_cycle(runtime: RuntimeSetting) -> None:
    """Internal helper that orchestrates one graph execution."""
    async with AsyncExitStack() as stack:
        enable_mcp = get_env_settings().enable_mcp_servers

        if enable_mcp:
            git_mcp = McpServerClient(
                command=sys.executable,
                args=["-m", "mcp_server_git", "--repository", get_codespace()],
                env=None,  # Uses default os.environ.copy() in adapter
            )
            await stack.enter_async_context(git_mcp)

            if runtime.mcp_system_def["command"]:
                active_task_system = runtime.agent_settings.get_active_task_system()
                if active_task_system:
                    task_mcp = McpServerClient(
                        runtime.mcp_system_def["command"][0],
                        runtime.mcp_system_def["command"][1:],
                        env={
                            "TRELLO_API_KEY": active_task_system.api_key,
                            "TRELLO_TOKEN": active_task_system.token,
                            "TRELLO_BASE_URL": active_task_system.base_url,
                        },
                    )
                    await stack.enter_async_context(task_mcp)
                else:
                    logger.warning("No active task system found for MCP server startup")
        else:
            logger.info("Skipping MCP server startup (ENABLE_MCP_SERVERS is disabled)")

        workflow: StateGraph = create_workflow(runtime)

        app_graph = workflow.compile()
        save_graph_as_png(app_graph)
        save_graph_as_mermaid(app_graph)
        logger.info("Executing graph cycle...")

        inputs = {
            "messages": [],
            "next_step": "",
            "task": None,
            "task_comments": [],
            "task_skill_level": None,
            "task_skill_level_reasoning": None,
            "agent_stack": runtime.agent_stack,
            "agent_skill_level": runtime.agent_settings.agent_skill_level,
            "plan_state": None,
            "current_node": None,
            "prompt": None,
            "system_prompt": None,
            "tech_stack": TECH_STACKS[runtime.agent_stack],
        }
        # Config for threa level persistence
        thread_config: RunnableConfig = {
            "configurable": {"thread_id": "1"},
            "recursion_limit": 200,
        }

        # stream_mode="values" gibt uns den kompletten State nach jedem Node zurück
        async for current_state in app_graph.astream(
            inputs, config=thread_config, stream_mode="values"
        ):
            if current_state["current_node"] and current_state["current_node"] != "task_fetch":
                save_state_to_workspace(current_state)

        logger.info("Finish graph cycle.")
