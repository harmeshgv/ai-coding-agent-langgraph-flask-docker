"""
Trello fetch node.

Fetches tasks from a Trello board, preparing them for processing by the agent.
"""

import logging

from datetime import datetime, timezone

from langchain_core.messages import HumanMessage

from agent.state import AgentState
from agent.trello_client import (
    get_all_trello_cards,
    get_all_trello_lists,
    get_trello_card_comments,
    get_trello_card_list_moves,
    move_trello_card_to_named_list,
)
from core.repositories import remove_issue_from_db

logger = logging.getLogger(__name__)


async def _get_card_context(sys_config: dict):
    incoming_list_name = sys_config["trello_readfrom_list"]
    in_progress_list_name = sys_config.get("trello_progress_list")

    # Try to fetch a card from the in-progress list first
    card_context = None
    if in_progress_list_name:
        card_context = await fetch_card_from_list(in_progress_list_name, sys_config)

    # If no card is found in the in-progress list, try the incoming
    # list (moves card to in-progress)
    if not card_context:
        card_context = await fetch_card_from_list(incoming_list_name, sys_config)
    return card_context


async def _ensure_card_in_progress(
    card_context: dict,
    card: dict,
    trello_progress_list_name: str | None,
    sys_config: dict,
) -> dict:
    """
    Moves the card to the in-progress list if needed, updating the card_context.
    """
    if not trello_progress_list_name:
        return card_context

    current_list_name = card_context["trello_list_name"]
    if current_list_name == trello_progress_list_name:
        return card_context

    remove_issue_from_db(card["id"])
    readfrom_list_id = card_context["trello_list_id"]
    move_card_result = await move_card_to_in_progress(
        card["id"], readfrom_list_id, sys_config
    )
    card_context["trello_list_id"] = move_card_result["trello_list_id"]
    return card_context


def create_trello_fetch_node(sys_config: dict):
    """Creates a Trello fetch node for the agent graph."""

    async def trello_fetch(state: AgentState) -> dict:  # pylint: disable=unused-argument
        """
        Fetches the first task from the Trello board in a specified list.
        """
        logger.info(
            "Fetching Trello lists of board id: %s", sys_config["trello_board_id"]
        )

        try:
            review_list_name = sys_config.get("trello_moveto_list")
            if not review_list_name:
                return {"trello_card_id": None}

            trello_progress_list_name = sys_config.get("trello_progress_list")

            card_context = await _get_card_context(sys_config)
            if not card_context:
                return {"trello_card_id": None}

            card = card_context["card"]

            card_context = await _ensure_card_in_progress(
                card_context, card, trello_progress_list_name, sys_config
            )

            comments = await get_trello_card_comments(card["id"], sys_config)

            review_cutoff = await get_review_transition_timestamp(
                card["id"], review_list_name, sys_config
            )
            if review_cutoff:
                comments = filter_comments_after_timestamp(comments, review_cutoff)

            content = card.get("name", "") + "\n" + card.get("desc", "")
            if comments:
                content += (
                    "\n\n--- The Pull Request was rejected with "
                    + "the following comments: ---\n"
                )
                for comment in reversed(comments):
                    author = comment.get("member_creator", "Unknown")
                    text = comment.get("text", "")
                    date = comment.get("date", "")
                    content += f"\n[{date}] {author}:\n{text}\n"

            logger.info("Processing card ID: %s - %s", card["id"], card.get("name", ""))
            logger.info("Initial messages content: %s", content)

            return {
                "trello_card_id": card["id"],
                "trello_card_name": card["name"],
                "messages": [HumanMessage(content=content)],
                "trello_list_id": card_context["trello_list_id"],
                "agent_summary": [],
            }
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Error fetching Trello cards: %s", e)
            return {"trello_card_id": None}

    return trello_fetch


async def fetch_card_from_list(readfrom_list_name: str, sys_config: dict) -> dict | None:
    """Fetch a card from a Trello list."""
    trello_lists = await get_all_trello_lists(sys_config)
    read_from_list = next(
        (data for data in trello_lists if data["name"] == readfrom_list_name),
        None,
    )

    if not read_from_list:
        logger.warning("%s list not found", readfrom_list_name)
        return None

    readfrom_list_id = read_from_list["id"]
    logger.info("Found %s list id: %s", readfrom_list_name, readfrom_list_id)

    cards = await get_all_trello_cards(readfrom_list_id, sys_config)
    if not cards:
        logger.info("No open tasks found in %s.", readfrom_list_name)
        return None

    card = cards[0]

    return {
        "card": card,
        "trello_list_id": readfrom_list_id,
        "trello_list_name": readfrom_list_name,
    }


async def move_card_to_in_progress(
    card_id: str, current_list_id: str, sys_config: dict
) -> dict:
    """
    Moves the Trello card to the in-progress list before card processing begins.
    """
    trello_progress_list = sys_config.get("trello_progress_list")
    if not trello_progress_list:
        logger.warning(
            "trello_progress_list not configured, skipping move to in-progress list"
        )
    else:
        logger.info(
            "Moving card %s to in-progress list: %s", card_id, trello_progress_list
        )

        try:
            progress_list_id = await move_trello_card_to_named_list(
                card_id, trello_progress_list, sys_config
            )
            return {
                "trello_list_id": progress_list_id,
            }
        except ValueError as e:
            logger.warning("Failed to move card to in-progress list: %s", e)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Failed to move card to in-progress list: %s", e)

    return {"trello_list_id": current_list_id}


async def get_review_transition_timestamp(
    card_id: str, review_list_name: str, sys_config: dict
) -> datetime | None:
    """Returns the timestamp of the last transition of a card to a review list."""
    try:
        list_moves = await get_trello_card_list_moves(card_id, sys_config)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning(
            "Failed to fetch list moves for card %s: %s. Including all comments.",
            card_id,
            e,
        )
        return None

    review_timestamps = [
        parse_trello_timestamp(move.get("date"))
        for move in list_moves
        if move.get("list_after") == review_list_name
    ]
    review_timestamps = [ts for ts in review_timestamps if ts]
    if not review_timestamps:
        return None

    latest_review = max(review_timestamps)
    logger.info(
        "Card %s last moved to '%s' at %s.",
        card_id,
        review_list_name,
        latest_review.isoformat(),
    )
    return latest_review


def filter_comments_after_timestamp(
    comments: list[dict], cutoff: datetime
) -> list[dict]:
    """Filters comments after a given timestamp."""
    filtered_comments = []
    for comment in comments:
        comment_ts = parse_trello_timestamp(comment.get("date"))
        if not comment_ts or comment_ts >= cutoff:
            filtered_comments.append(comment)
    return filtered_comments


def parse_trello_timestamp(value: str | None) -> datetime | None:
    """Parses a Trello timestamp string into a datetime object."""
    if not value:
        return None

    normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        logger.warning("Failed to parse Trello timestamp '%s'", value)
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed
