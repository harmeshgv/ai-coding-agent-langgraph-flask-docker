"""Tool for executing commands inside the Java development container."""

import logging

import docker
from docker.errors import APIError, NotFound
from langchain_core.tools import tool

from agent.utils import get_workbench, get_workspace

logger = logging.getLogger(__name__)

try:  # docker socket might be unavailable in some environments
    DOCKER_CLIENT = docker.from_env()
except Exception as exc:  # pylint: disable=broad-exception-caught
    logger.warning("No docker connection! %s", exc)
    DOCKER_CLIENT = None

MAX_TOOL_OUTPUT_CHARS = 20000


def _truncate_tool_output(output: str, limit: int = MAX_TOOL_OUTPUT_CHARS) -> str:
    """Truncate long command output while keeping the start and end."""
    if len(output) <= limit:
        return output

    half = limit // 2
    return (
        output[:half]
        + "\n... [output truncated to stay within prompt budget] ...\n"
        + output[-half:]
    )


@tool
def run_java_command(command: str) -> str:
    """Execute a shell command inside the Java container."""
    if not DOCKER_CLIENT:
        return "Error: Docker client not initialized. Is the socket mounted?"

    try:
        container = DOCKER_CLIENT.containers.get(get_workbench())

        if container.status != "running":
            return (
                f"Error: Container {get_workbench()} is not running "
                f"(Status: {container.status})."
            )

        logger.info("Executing in Java-Box: %s", command)

        exec_result = container.exec_run(command, workdir=get_workspace())
        output = exec_result.output.decode("utf-8")
        exit_code = exec_result.exit_code

        logger.debug("--- COMMAND OUTPUT (%s) ---%s\n---", command, output)
        output = _truncate_tool_output(output)

        if exit_code == 0:
            return f"✅ SUCCESS:\n{output}"
        return f"❌ FAILED (Exit Code {exit_code}):\n{output}"

    except NotFound:
        return (
            f"Error: Container '{get_workbench()}' not found. "
            "Please start the docker-compose setup."
        )
    except APIError as exc:
        return f"Docker API Error: {exc}"
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return f"System Error: {exc}"
