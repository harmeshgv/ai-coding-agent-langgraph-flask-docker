"""
Asynchronous Trello API client.

This module provides a set of asynchronous functions to interact with the
Trello API for common operations like fetching lists and cards, moving cards,
and adding comments. It uses `httpx` for async HTTP requests and is
designed to be used within the agent's workflow.
"""

import logging

import httpx

logger = logging.getLogger(__name__)


def get_safe_url(url: str, params: dict) -> str:
    """
    Erstellt eine URL für das Logging, bei der sensitive Parameter maskiert sind.
    """
    # Wir bauen die volle URL inkl. Params nach, um sie zu parsen
    req = httpx.Request("GET", url, params=params)
    parsed_url = req.url

    # Wir kopieren die Query-Parameter, aber überschreiben die Secrets
    new_query_params = []
    for key, value in parsed_url.params.items():
        if key in ["key", "token"]:
            new_query_params.append((key, "SECRET"))
        else:
            new_query_params.append((key, value))

    # URL mit sicherem Query-String zurückgeben
    return str(parsed_url.copy_with(params=new_query_params))


async def get_all_trello_lists(sys_config: dict) -> list[dict]:
    """Fetches all lists for the configured Trello board."""
    env = sys_config.get("env")
    if not env:
        raise ValueError("Environment not found in sys_config")

    url = f"https://api.trello.com/1/boards/{sys_config.get('trello_board_id')}/lists"
    headers = {"Accept": "application/json"}
    query = {"key": env.get("TRELLO_API_KEY"), "token": env.get("TRELLO_TOKEN")}

    logger.info("Trello GET: %s", get_safe_url(url, query))
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, params=query)

    if response.status_code != 200:
        raise RuntimeError(f"Failed to fetch lists: {response.text}")

    data = response.json()
    return [{"name": list_item["name"], "id": list_item["id"]} for list_item in data]


async def get_all_trello_cards(list_id: str, sys_config: dict) -> list[dict]:
    """Fetches all cards from a specific Trello list."""
    env = sys_config.get("env")
    if not env:
        raise ValueError("Environment not found in sys_config")

    url = f"https://api.trello.com/1/lists/{list_id}/cards"
    headers = {"Accept": "application/json"}
    query = {"key": env.get("TRELLO_API_KEY"), "token": env.get("TRELLO_TOKEN")}

    logger.info("Trello GET: %s", get_safe_url(url, query))
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, params=query)

    if response.status_code != 200:
        raise RuntimeError(f"Failed to fetch cards: {response.text}")

    data = response.json()
    return [
        {"id": card["id"], "name": card["name"], "desc": card["desc"]} for card in data
    ]


async def move_trello_card_to_list(card_id: str, list_id: str, sys_config: dict):
    """
    Move a Trello card to a specified list.

    Args:
        card_id (str): The ID of the card to move.
        list_id (str): The ID of the target list.
        sys_config (dict): The system configuration containing Trello API credentials.

    Raises:
        ValueError: If the environment is not found in sys_config.
        RuntimeError: If the card move operation fails.
    """
    env = sys_config.get("env")
    if not env:
        raise ValueError("Environment not found in sys_config")

    url = f"https://api.trello.com/1/cards/{card_id}"
    headers = {"Accept": "application/json"}
    query = {
        "idList": list_id,
        "key": env.get("TRELLO_API_KEY"),
        "token": env.get("TRELLO_TOKEN"),
    }

    logger.info("Trello PUT: %s", get_safe_url(url, query))
    async with httpx.AsyncClient() as client:
        response = await client.put(url, headers=headers, params=query)

    if response.status_code != 200:
        raise RuntimeError(
            f"Failed to move card {card_id} to list {list_id}: {response.text}"
        )


async def move_trello_card_to_named_list(
    card_id: str, list_name: str, sys_config: dict
) -> str:
    """
    Helper that resolves the Trello list ID by name and moves the
    given card to that list. Returns the resolved list ID.
    """
    trello_lists = await get_all_trello_lists(sys_config)
    target_list = next(
        (data for data in trello_lists if data["name"] == list_name), None
    )

    if not target_list:
        raise ValueError(f"Trello list '{list_name}' not found on configured board")

    target_list_id = target_list["id"]
    logger.info("Found %s list id: %s", list_name, target_list_id)
    await move_trello_card_to_list(card_id, target_list_id, sys_config)

    return target_list_id


async def add_comment_to_trello_card(card_id: str, comment: str, sys_config: dict):
    """Adds a comment to a specified Trello card."""
    env = sys_config.get("env")
    if not env:
        raise ValueError("Environment not found in sys_config")

    url = f"https://api.trello.com/1/cards/{card_id}/actions/comments"
    headers = {"Accept": "application/json"}
    query = {
        "text": comment,
        "key": env.get("TRELLO_API_KEY"),
        "token": env.get("TRELLO_TOKEN"),
    }

    logger.info("Trello POST: %s", get_safe_url(url, query))
    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, params=query)

    if response.status_code != 200:
        raise RuntimeError(
            f"Failed to add a comment to card {card_id}: {response.text}"
        )


async def get_trello_card_comments(card_id: str, sys_config: dict) -> list[dict]:
    """
    Fetches all comments for the provided Trello card ID.
    """
    env = sys_config.get("env")
    if not env:
        raise ValueError("Environment not found in sys_config")

    url = f"https://api.trello.com/1/cards/{card_id}/actions"
    headers = {"Accept": "application/json"}
    query = {
        "filter": "commentCard",
        "key": env.get("TRELLO_API_KEY"),
        "token": env.get("TRELLO_TOKEN"),
    }

    logger.info("Trello GET: %s", get_safe_url(url, query))
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, params=query)

    if response.status_code != 200:
        raise RuntimeError(
            f"Failed to fetch comments for card {card_id}: {response.text}"
        )

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


async def get_trello_card_list_moves(card_id: str, sys_config: dict) -> list[dict]:
    """
    Fetches all list move actions (updateCard:idList) for the provided Trello card ID.
    """
    env = sys_config.get("env")
    if not env:
        raise ValueError("Environment not found in sys_config")

    url = f"https://api.trello.com/1/cards/{card_id}/actions"
    headers = {"Accept": "application/json"}
    query = {
        "filter": "updateCard:idList",
        "key": env.get("TRELLO_API_KEY"),
        "token": env.get("TRELLO_TOKEN"),
    }

    logger.info("Trello GET: %s", get_safe_url(url, query))
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, params=query)

    if response.status_code != 200:
        raise RuntimeError(
            f"Failed to fetch list moves for card {card_id}: {response.text}"
        )

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
