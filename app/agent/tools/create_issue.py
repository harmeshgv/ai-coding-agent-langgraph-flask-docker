"""Tool for creating implementation issues/cards in Trello."""

import logging

from langchain_core.tools import StructuredTool

from agent.integrations.trello_client import create_trello_card

logger = logging.getLogger(__name__)


def create_issue_tool(sys_config: dict, target_list: str) -> StructuredTool:
    """Factory that creates a tool for creating issue cards in Trello."""

    async def create_issue(
        title: str,
        instructions: str,
    ) -> str:
        """
        Creates a new Trello card with implementation instructions in the configured incoming list.
        Use this when the user requests to create a card for implementing the analysis findings.

        Args:
            title: A concise title for the implementation task.
            instructions: Detailed implementation instructions based on the analysis.

        Returns:
            Confirmation message with the card URL.
        """
        try:
            if not target_list:
                return "Error: target Trello list not configured"
            result = await create_trello_card(
                name=title,
                description=instructions,
                list_name=target_list,
                sys_config=sys_config,
            )

            logger.info(
                "Created implementation issue '%s' in list '%s'",
                result["name"],
                result["list"],
            )

            return (
                f"Successfully created implementation issue: '{result['name']}'\n"
                f"Card URL: {result['url']}\n"
                f"List: {result['list']}"
            )

        except ValueError as e:
            logger.error("Failed to create card: %s", str(e))
            return f"Error: {str(e)}"
        except RuntimeError as e:
            logger.error("Trello API error: %s", str(e))
            return f"Failed to create card: {str(e)}"

    return StructuredTool.from_function(
        coroutine=create_issue,
        name="create_issue",
        description=(
            "Creates a new Trello issue card with implementation instructions in the "
            f"'{target_list}' list. Use this when the user requests to create "
            "a card for implementing the analysis findings."
        ),
    )
