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

from agent.utils import checkout_branch, get_workspace


logger = logging.getLogger(__name__)


def create_trello_fetch_node(sys_config: dict):
    async def trello_fetch(state: AgentState) -> dict:
        """
        Fetches the first task from the Trello board in a specified list.
        """
        logger.info(
            f"Fetching Trello lists of board id: {sys_config['trello_board_id']}"
        )

        try:
            incoming_list_name = sys_config["trello_readfrom_list"]
            in_progress_list_name = sys_config.get("trello_progress_list")

            # Try to fetch a card from the in-progress list first
            card_context = None
            if in_progress_list_name:
                card_context = await fetch_card_from_list(
                    in_progress_list_name, sys_config, move_to_progress=False
                )

            # If no card is found in the in-progress list, try the incoming list (moves card to in-progress)
            if not card_context:
                card_context = await fetch_card_from_list(
                    incoming_list_name, sys_config, move_to_progress=True
                )
                if not card_context:
                    return {"trello_card_id": None}

            card = card_context["card"]
            trello_list_id = card_context["trello_list_id"]
            trello_in_progress = card_context["trello_in_progress"]

            comments = await get_trello_card_comments(card["id"], sys_config)
            review_list_name = sys_config.get("trello_moveto_list")

            review_cutoff = await get_review_transition_timestamp(
                card["id"], review_list_name, sys_config
            )
            if review_cutoff:
                comments = filter_comments_after_timestamp(comments, review_cutoff)
            
            content = card.get("name", "") + "\n" + card.get("desc", "")
            if comments:
                content += "\n\n--- The Pull Request was rejected with the following comments: ---\n"
                for comment in reversed(comments):
                    author = comment.get("member_creator", "Unknown")
                    text = comment.get("text", "")
                    date = comment.get("date", "")
                    content += f"\n[{date}] {author}:\n{text}\n"
            
            logger.info(f"Processing card ID: {card['id']} - {card.get('name', '')}")
            
            git_branch = await get_existing_branch_for_card(card["id"], sys_config)
            
            if git_branch:
                logger.info(f"Checking out existing git branch: {git_branch} for card {card['id']} - {card.get('name', '')}")
                github_repo_url = sys_config.get("github_repo_url")
                checkout_branch(github_repo_url, git_branch, get_workspace())
            
            logger.info("Initial messages content: " + content)
            return {
                "trello_card_id": card["id"],
                "trello_card_name": card.get("name", ""),
                "messages": [
                    HumanMessage(content=content)
                ],
                "trello_list_id": trello_list_id,
                "trello_in_progress": trello_in_progress,
                "git_branch": git_branch,
            }
        except Exception as e:
            logger.error(f"Error fetching Trello cards: {e}")
            return {"trello_card_id": None}

    return trello_fetch

async def fetch_card_from_list(
    readfrom_list_name: str, sys_config: dict, move_to_progress: bool
) -> dict | None:
    trello_lists = await get_all_trello_lists(sys_config)
    read_from_list = next(
        (data for data in trello_lists if data["name"] == readfrom_list_name),
        None,
    )

    if not read_from_list:
        logger.warning(f"{readfrom_list_name} list not found")
        return None

    trello_readfrom_list_id = read_from_list["id"]
    logger.info(f"Found {readfrom_list_name} list id: {trello_readfrom_list_id}")

    cards = await get_all_trello_cards(trello_readfrom_list_id, sys_config)
    if not cards:
        logger.info(f"No open tasks found in {readfrom_list_name}.")
        return None

    card = cards[0]
    trello_list_id = trello_readfrom_list_id
    trello_progress_list_name = sys_config.get("trello_progress_list")
    trello_in_progress = readfrom_list_name == trello_progress_list_name

    if move_to_progress and trello_progress_list_name and not trello_in_progress:
        move_card_result = await move_card_to_in_progress(
            card["id"], trello_readfrom_list_id, sys_config
        )
        trello_list_id = move_card_result["trello_list_id"]
        trello_in_progress = move_card_result["trello_in_progress"]

    return {
        "card": card,
        "trello_list_id": trello_list_id,
        "trello_in_progress": trello_in_progress,
    }


async def move_card_to_in_progress(card_id: str, current_list_id: str, sys_config: dict) -> dict:
    """
    Moves the Trello card to the in-progress list before card processing begins.
    """
    trello_progress_list = sys_config.get("trello_progress_list")
    if not trello_progress_list:
        logger.warning("trello_progress_list not configured, skipping move to in-progress list")
    else:    
        logger.info(
            f"Moving card {card_id} to in-progress list: {trello_progress_list}"
        )

        try:
            progress_list_id = await move_trello_card_to_named_list(
                card_id, trello_progress_list, sys_config
            )
            return {
                "trello_list_id": progress_list_id,
                "trello_in_progress": True,
            }
        except ValueError as exc:
            logger.warning(f"Failed to move card to in-progress list: {exc}")
        except Exception as exc:
            logger.error(f"Failed to move card to in-progress list: {exc}")

    return {"trello_list_id": current_list_id, "trello_in_progress": False}


async def get_existing_branch_for_card(card_id: str, sys_config: dict) -> str | None:
    """
    Retrieves the existing git branch for a Trello card from the database.
    Returns None if no branch exists for this card.
    """
    try:
        from flask import current_app
        from core.repositories import get_branch_for_issue
        
        with current_app.app_context():
            branch_name = get_branch_for_issue(card_id)
            return branch_name
    except Exception as e:
        logger.warning(f"Failed to retrieve branch for card {card_id}: {e}")
        return None


async def get_review_transition_timestamp(
    card_id: str, review_list_name: str, sys_config: dict
) -> datetime | None:
    try:
        list_moves = await get_trello_card_list_moves(card_id, sys_config)
    except Exception as exc:
        logger.warning(
            f"Failed to fetch list moves for card {card_id}: {exc}. Including all comments."
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
        f"Card {card_id} last moved to '{review_list_name}' at {latest_review.isoformat()}."
    )
    return latest_review


def filter_comments_after_timestamp(
    comments: list[dict], cutoff: datetime
) -> list[dict]:
    filtered_comments = []
    for comment in comments:
        comment_ts = parse_trello_timestamp(comment.get("date"))
        if not comment_ts or comment_ts >= cutoff:
            filtered_comments.append(comment)
    return filtered_comments


def parse_trello_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None

    normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        logger.warning(f"Failed to parse Trello timestamp '{value}'")
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed
