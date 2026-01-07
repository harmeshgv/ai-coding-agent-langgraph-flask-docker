import logging

from langchain_core.messages import HumanMessage

from agent.state import AgentState
from agent.trello_client import (
    get_all_trello_cards,
    get_all_trello_lists,
    get_trello_card_comments,
    move_trello_card_to_named_list,
)


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
            
            content = card.get("name", "") + "\n" + card.get("desc", "")
            if comments:
                content += "\n\n--- Recent Trello Comments ---\n"
                for comment in reversed(comments):
                    author = comment.get("member_creator", "Unknown")
                    text = comment.get("text", "")
                    date = comment.get("date", "")
                    content += f"\n[{date}] {author}:\n{text}\n"
            
            logger.info(f"Processing card ID: {card['id']} - {card.get('name', '')}")
            logger.info("Content: " + content)
            return {
                "trello_card_id": card["id"],
                "messages": [
                    HumanMessage(content=content)
                ],
                "trello_list_id": trello_list_id,
                "trello_in_progress": trello_in_progress,
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
