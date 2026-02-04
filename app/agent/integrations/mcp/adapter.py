"""
This module serves as a bridge between MCP (Multi-Tool Co-routine Protocol)
servers and the LangChain framework.

It provides the `McpServerClient` class, which performs the following main functions:
- Starts any MCP-compliant server as a subprocess via standard I/O (stdio).
- Establishes an asynchronous session with the server.
- Retrieves the tools provided by the MCP server.
- Dynamically converts these tools into LangChain-compatible `StructuredTool` objects.
  During this process, argument schemas (Pydantic models) are generated at runtime
  from the JSON schemas of the MCP tools.
- Encapsulates tool calls so they can be executed asynchronously within LangChain agents,
  delegating the calls to the MCP server.

The main purpose is to make external tools, written in any language that adheres to the
MCP standard, seamlessly usable within a Python-based LangChain agent.
"""

import json
from contextlib import AsyncExitStack

# LangChain / Pydantic Imports
from langchain_core.tools import StructuredTool

# MCP Imports
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import Field, create_model


# --- GENERIC CLASS ---
class McpServerClient:
    """
    A generic client that connects to ONE arbitrary MCP server
    and provides its tools for LangChain.
    """

    def __init__(self, command: str, args: list[str], env: dict | None = None):
        """
        :param command: The command to start (e.g., "uv", "npx", sys.executable)
        :param args: Arguments for the command (e.g., ["mcp-server-git", ...])
        :param env: Environment variables (optional, defaults to os.environ.copy())
        """
        self.server_params = StdioServerParameters(
            command=command, args=args, env=env
        )
        self.exit_stack = AsyncExitStack()
        self.session = None

    async def __aenter__(self):
        """Starts the server and the session."""
        try:
            read, write = await self.exit_stack.enter_async_context(
                stdio_client(self.server_params)
            )
            self.session = await self.exit_stack.enter_async_context(
                ClientSession(read, write)
            )
            await self.session.initialize()
            return self
        except Exception as e:
            # If the server doesn't start, clean up and re-raise the error
            await self.exit_stack.aclose()
            raise RuntimeError(
                f"Failed to start MCP Server ({self.server_params.command}): {e}"
            ) from e

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Cleans up and stops the server."""
        await self.exit_stack.aclose()

    async def get_langchain_tools(self):
        """Fetches tools from the server and converts them."""
        if not self.session:
            raise RuntimeError("MCP Session not started.")

        mcp_tools_list = await self.session.list_tools()
        langchain_tools = []

        for tool_schema in mcp_tools_list.tools:
            lc_tool = self._convert_to_langchain_tool(tool_schema)
            langchain_tools.append(lc_tool)

        return langchain_tools

    async def call_tool(self, tool_name: str, **kwargs):
        """Calls a tool directly and returns the raw result."""
        import logging
        logger = logging.getLogger(__name__)
        logger.debug(
            "STEP 1 - START: Calling tool '%s' with arguments: %s", tool_name, kwargs
        )
        if not self.session:
            raise RuntimeError("MCP Session not started.")
        try:
            # Execute the tool call via the MCP session
            result = await self.session.call_tool(tool_name, arguments=kwargs)

            logger.debug(
                "STEP 1 - SUCCESS: Tool responded! Data type: %s", type(result)
            )
            logger.debug("STEP 1 - RAW DATA PREVIEW: %s", str(result)[:500])

            # Check for errors
            if result.isError:
                error_message = "Unknown error"
                if result.content and result.content[0].type == "text":
                    error_message = result.content[0].text
                raise RuntimeError(f"Error calling tool '{tool_name}': {error_message}")

            # Extract and return the content
            if result.content:
                content_item = result.content[0]
                if content_item.type == "application/json":
                    return content_item.json
                if content_item.type == "text":
                    try:
                        # Attempt to parse the text as JSON
                        return json.loads(content_item.text)
                    except json.JSONDecodeError:
                        # If it fails, return the raw text as a fallback
                        return content_item.text

            return None

        except Exception as e:
            logger.error("STEP 1 - ERROR: Tool call failed. Reason: %s", e)
            raise RuntimeError(f"Failed to call tool '{tool_name}': {e}") from e

    def _convert_to_langchain_tool(self, tool_schema):
        """Converts MCP schema to LangChain tool."""
        tool_name = tool_schema.name
        tool_desc = tool_schema.description or "No description."

        fields = {}
        input_schema = tool_schema.inputSchema or {}
        properties = input_schema.get("properties", {})
        required_fields = input_schema.get("required", [])

        for field_name, field_info in properties.items():
            field_type = str
            json_type = field_info.get("type")
            if json_type == "integer":
                field_type = int
            elif json_type == "boolean":
                field_type = bool
            elif json_type == "array":
                field_type = list[str]

            if field_name in required_fields:
                fields[field_name] = (
                    field_type,
                    Field(description=field_info.get("description", "")),
                )
            else:
                fields[field_name] = (
                    field_type | None,
                    Field(default=None, description=field_info.get("description", "")),
                )

        args_model = create_model(f"{tool_name}Args", **fields)

        async def tool_func(**kwargs):
            try:
                if not self.session:
                    raise RuntimeError(
                        "MCP Session not connected. Ensure the client is used within "
                        + "an 'async with' block."
                    )

                # Path injection for Git Server (special case, could be externalized)
                if "repo_path" in kwargs:
                    kwargs["repo_path"] = "/app/work_dir"

                result = await self.session.call_tool(tool_name, arguments=kwargs)

                output_text = []
                if hasattr(result, "content") and result.content:
                    for content in result.content:
                        if content.type == "text":
                            output_text.append(content.text)
                        else:
                            output_text.append(f"[{content.type} content]")

                if hasattr(result, "isError") and result.isError:
                    return f"ERROR executing {tool_name}: {', '.join(output_text)}"

                final = "\n".join(output_text)
                return (
                    final
                    if final.strip()
                    else f"Tool {tool_name} executed successfully."
                )

            except Exception as e:  # pylint: disable=broad-exception-caught
                return f"EXCEPTION in tool {tool_name}: {str(e)}"

        return StructuredTool.from_function(
            func=None,
            coroutine=tool_func,
            name=tool_name,
            description=tool_desc,
            args_schema=args_model,
        )
