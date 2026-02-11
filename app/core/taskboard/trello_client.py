"""
Asynchronous Trello API client.

This module provides a set of asynchronous functions to interact with the
Trello API for common operations like fetching lists and cards, moving cards,
and adding comments. It uses `httpx` for async HTTP requests and is
designed to be used within the agent's workflow.
"""

import logging

import httpx

from app.core.localdb.models import AgentSettings

logger = logging.getLogger(__name__)


def get_safe_url(url: str, params: dict) -> str:
    """
    Creates a URL for logging with sensitive parameters masked.
    """
    # Build the full URL including params to parse it
    req = httpx.Request("GET", url, params=params)
    parsed_url = req.url

    # Copy the query parameters, but overwrite the secrets
    new_query_params = []
    for key, value in parsed_url.params.items():
        if key in ["key", "token"]:
            new_query_params.append((key, "SECRET"))
        else:
            new_query_params.append((key, value))

    # Return URL with safe query string
    return str(parsed_url.copy_with(params=new_query_params))


async def get_all_trello_lists(agent_settings: AgentSettings) -> list[dict]:
    """Fetches all lists for the configured Trello board."""
    task_system = agent_settings.get_task_system("trello")
    board_id = task_system.board_id if task_system else None

    url = f"https://api.trello.com/1/boards/{board_id}/lists"
    headers = {"Accept": "application/json"}
    query = {"key": task_system.api_key, "token": task_system.token} if task_system else {}

    logger.debug("Trello GET: %s", get_safe_url(url, query))
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, params=query)

    if response.status_code != 200:
        raise RuntimeError(f"Failed to fetch lists: {response.text}")

    data = response.json()
    return [{"name": list_item["name"], "id": list_item["id"]} for list_item in data]


async def get_all_trello_cards(list_id: str, agent_settings: AgentSettings) -> list[dict]:
    """Fetches all cards from a specific Trello list."""
    task_system = agent_settings.get_task_system("trello")

    url = f"https://api.trello.com/1/lists/{list_id}/cards"
    headers = {"Accept": "application/json"}
    query = {"key": task_system.api_key, "token": task_system.token} if task_system else {}

    logger.debug("Trello GET: %s", get_safe_url(url, query))
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, params=query)

    if response.status_code != 200:
        raise RuntimeError(f"Failed to fetch cards: {response.text}")

    data = response.json()
    return [{"id": card["id"], "name": card["name"], "desc": card["desc"]} for card in data]


async def get_trello_card(card_id: str, agent_settings: AgentSettings) -> dict:
    """Fetch details for a single Trello card including its list metadata."""
    task_system = agent_settings.get_task_system("trello")
    if not task_system:
        raise RuntimeError("Trello task system is not configured")

    url = f"https://api.trello.com/1/cards/{card_id}"
    headers = {"Accept": "application/json"}
    query = {
        "fields": "name,desc,idList,url",
        "list": "true",
        "key": task_system.api_key,
        "token": task_system.token,
    }

    logger.debug("Trello GET: %s", get_safe_url(url, query))
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, params=query)

    if response.status_code != 200:
        raise RuntimeError(f"Failed to fetch card {card_id}: {response.text}")

    data = response.json()
    list_info = data.get("list") or {}
    return {
        "id": data.get("id", card_id),
        "name": data.get("name", ""),
        "desc": data.get("desc", ""),
        "url": data.get("url", ""),
        "list_id": data.get("idList", ""),
        "list_name": list_info.get("name", ""),
    }


async def move_trello_card_to_list(card_id: str, list_id: str, agent_settings: AgentSettings):
    """
    Move a Trello card to a specified list.

    Args:
        card_id (str): The ID of the card to move.
        list_id (str): The ID of the target list.
        agent_settings (AgentSettings): The agent configuration containing Trello API credentials.

    Raises:
        ValueError: If the environment is not found in agent_settings.
        RuntimeError: If the card move operation fails.
    """
    task_system = agent_settings.get_task_system("trello")
    url = f"https://api.trello.com/1/cards/{card_id}"
    headers = {"Accept": "application/json"}
    query = {
        "idList": list_id,
        "key": task_system.api_key if task_system else None,
        "token": task_system.token if task_system else None,
    }

    logger.debug("Trello PUT: %s", get_safe_url(url, query))
    async with httpx.AsyncClient() as client:
        response = await client.put(url, headers=headers, params=query)

    if response.status_code != 200:
        raise RuntimeError(f"Failed to move card {card_id} to list {list_id}: {response.text}")


async def move_trello_card_to_named_list(
    card_id: str, list_name: str, agent_settings: AgentSettings
) -> str:
    """
    Helper that resolves the Trello list ID by name and moves the
    given card to that list. Returns the resolved list ID.
    """
    trello_lists = await get_all_trello_lists(agent_settings)
    target_list = next((data for data in trello_lists if data["name"] == list_name), None)

    if not target_list:
        raise ValueError(f"Trello list '{list_name}' not found on configured board")

    target_list_id = target_list["id"]
    logger.info("Found %s list id: %s", list_name, target_list_id)
    await move_trello_card_to_list(card_id, target_list_id, agent_settings)

    return target_list_id


async def add_comment_to_trello_card(card_id: str, comment: str, agent_settings: AgentSettings):
    """Adds a comment to a specified Trello card."""
    task_system = agent_settings.get_task_system("trello")
    url = f"https://api.trello.com/1/cards/{card_id}/actions/comments"
    headers = {"Accept": "application/json"}
    query = {
        "text": comment,
        "key": task_system.api_key if task_system else None,
        "token": task_system.token if task_system else None,
    }

    logger.debug("Trello POST: %s", get_safe_url(url, query))
    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, params=query)

    if response.status_code != 200:
        raise RuntimeError(f"Failed to add a comment to card {card_id}: {response.text}")


async def get_trello_card_comments(card_id: str, agent_settings: AgentSettings) -> list[dict]:
    """
    Fetches all comments for the provided Trello card ID.
    """
    task_system = agent_settings.get_task_system("trello")
    url = f"https://api.trello.com/1/cards/{card_id}/actions"
    headers = {"Accept": "application/json"}
    query = {
        "filter": "commentCard",
        "key": task_system.api_key if task_system else None,
        "token": task_system.token if task_system else None,
    }

    logger.debug("Trello GET: %s", get_safe_url(url, query))
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, params=query)

    if response.status_code != 200:
        raise RuntimeError(f"Failed to fetch comments for card {card_id}: {response.text}")

    data = response.json()
    return [
        {
            "id": action.get("id"),
            "text": action.get("data", {}).get("text", ""),
            "member_creator": action.get("memberCreator", {}).get("fullName"),
            "date": action.get("date"),
        }
        for action in data
    ]


async def get_trello_card_list_moves(card_id: str, agent_settings: AgentSettings) -> list[dict]:
    """
    Fetches all list move actions (updateCard:idList) for the provided Trello card ID.
    """
    task_system = agent_settings.get_task_system("trello")
    url = f"https://api.trello.com/1/cards/{card_id}/actions"
    headers = {"Accept": "application/json"}
    query = {
        "filter": "updateCard:idList",
        "key": task_system.api_key if task_system else None,
        "token": task_system.token if task_system else None,
    }

    logger.debug("Trello GET: %s", get_safe_url(url, query))
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, params=query)

    if response.status_code != 200:
        raise RuntimeError(f"Failed to fetch list moves for card {card_id}: {response.text}")

    data = response.json()
    return [
        {
            "id": action.get("id"),
            "date": action.get("date"),
            "list_before": action.get("data", {}).get("listBefore", {}).get("name"),
            "list_after": action.get("data", {}).get("listAfter", {}).get("name"),
        }
        for action in data
    ]


async def create_trello_card(
    name: str, description: str, list_name: str, agent_settings: AgentSettings
) -> dict:
    """
    Creates a new Trello card in the specified list.

    Args:
        name (str): The title/name of the card.
        description (str): The description/body of the card.
        list_name (str): The name of the list to create the card in.
        agent_settings (AgentSettings): The agent configuration containing Trello API credentials.

    Returns:
        dict: The created card data including id, name, and url.

    Raises:
        ValueError: If the environment is not found or list name is invalid.
        RuntimeError: If the card creation fails.
    """
    trello_lists = await get_all_trello_lists(agent_settings)
    target_list = next((data for data in trello_lists if data["name"] == list_name), None)

    if not target_list:
        raise ValueError(f"Trello list '{list_name}' not found on configured board")

    list_id = target_list["id"]
    logger.info("Creating card in list '%s' (id: %s)", list_name, list_id)

    task_system = agent_settings.get_task_system("trello")
    url = "https://api.trello.com/1/cards"
    headers = {"Accept": "application/json"}
    query = {
        "idList": list_id,
        "name": name,
        "desc": description,
        "key": task_system.api_key if task_system else None,
        "token": task_system.token if task_system else None,
    }

    logger.info("Trello POST: %s", get_safe_url(url, query))
    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, params=query)

    if response.status_code != 200:
        raise RuntimeError(f"Failed to create card: {response.text}")

    data = response.json()
    return {
        "id": data.get("id"),
        "name": data.get("name"),
        "url": data.get("url"),
        "list": list_name,
    }
