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
from app.agent.utils import get_workspace, save_state_to_instance
from app.core.config import get_env_settings
from app.core.localdb.agent_tasks_utils import update_db_task, read_db_task
from app.core.localdb.agent_actions_utils import create_db_agent_action

logger = logging.getLogger(__name__)


async def run_agent_cycle(runtime: RuntimeSetting) -> None:
    """Internal helper that orchestrates one graph execution."""
    async with AsyncExitStack() as stack:
        enable_mcp = get_env_settings().enable_mcp_servers

        if enable_mcp:
            git_mcp = McpServerClient(
                command=sys.executable,
                args=["-m", "mcp_server_git", "--repository", get_workspace()],
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
            "board_task": None,
            "board_task_comments": [],
            "agent_task": read_db_task(),
            "agent_stack": runtime.agent_stack,
            "agent_skill_level": runtime.agent_settings.agent_skill_level,
            "current_node": None,
            "current_tool_calls": [],
            "prompt": None,
            "system_prompt": None,
            "tech_stack": TECH_STACKS[runtime.agent_stack],
            "user_message": None,
        }
        # Config for threa level persistence
        thread_config: RunnableConfig = {
            "configurable": {"thread_id": "1"},
            "recursion_limit": 200,
        }

        # stream_mode="values" gibt uns den kompletten State nach jedem Node zurück
        async for current_state in app_graph.astream(
            inputs, config=thread_config, stream_mode="values", context=runtime.agent_settings
        ):
            if current_state["board_task"] and current_state["agent_task"]:
                save_state_to_instance(current_state)
                update_db_task(
                    task_id=current_state["board_task"].id,
                    task_name=current_state["board_task"].name,
                    task_description=current_state["board_task"].description,
                    task_type=current_state["agent_task"].task_type,
                    task_skill_level=current_state["agent_task"].task_skill_level,
                    task_skill_level_reasoning=current_state[
                        "agent_task"
                    ].task_skill_level_reasoning,
                    plan_state=current_state["agent_task"].plan_state,
                    working_state="working..."
                    if current_state["current_node"] != "task_update"
                    else "finished.",
                    user_message=current_state["user_message"]
                    if current_state["current_node"] == "task_update"
                    else "",
                )
                create_db_agent_action(
                    agent_task=current_state["agent_task"],
                    current_node=current_state["current_node"],
                    tool_calls=current_state["current_tool_calls"],
                )

        logger.info("Finish graph cycle.")
