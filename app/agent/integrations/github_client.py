"""
Asynchronous GitHub Projects v2 API client.

This module provides a set of asynchronous functions to interact with the
GitHub GraphQL API for GitHub Projects v2 operations like fetching project
columns, items, moving items between columns, and adding comments.
It uses `httpx` for async HTTP requests.
"""

import logging
import os
from typing import Any, Optional

import httpx

from app.core.models import AgentSettings

logger = logging.getLogger(__name__)

GITHUB_GRAPHQL_ENDPOINT = "/graphql"


def _get_github_token(agent_settings: Optional[AgentSettings] = None) -> str:
    """Get GitHub token from config or environment variable.

    Args:
        agent_settings: Optional agent configuration containing token.

    Returns:
        GitHub PAT token.

    Raises:
        ValueError: If no token is available.
    """
    if agent_settings:
        task_system = agent_settings.get_task_system("github")
        if task_system and task_system.token:
            return task_system.token

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise ValueError(
            "GitHub token not configured. Set GITHUB_TOKEN environment variable "
            "or provide a token in the GitHub Projects configuration."
        )
    return token


def _get_base_url(agent_settings: AgentSettings) -> str:
    """Get the GitHub API base URL from config or default."""
    task_system = agent_settings.get_task_system("github")
    if task_system and task_system.base_url:
        return task_system.base_url.rstrip("/")
    return "https://api.github.com"


def _get_graphql_url(agent_settings: AgentSettings) -> str:
    """Get the full GraphQL endpoint URL."""
    return f"{_get_base_url(agent_settings)}{GITHUB_GRAPHQL_ENDPOINT}"


async def _execute_graphql(
    query: str,
    variables: dict[str, Any],
    agent_settings: AgentSettings,
) -> dict[str, Any]:
    """Execute a GraphQL query against the GitHub API."""
    url = _get_graphql_url(agent_settings)
    token = _get_github_token(agent_settings)

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    payload = {"query": query, "variables": variables}

    logger.info("GitHub GraphQL POST: %s", url)
    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=payload, timeout=30.0)

    if response.status_code != 200:
        raise RuntimeError(f"GitHub GraphQL request failed: {response.text}")

    data = response.json()
    if "errors" in data:
        error_messages = [e.get("message", str(e)) for e in data["errors"]]
        raise RuntimeError(f"GitHub GraphQL errors: {'; '.join(error_messages)}")

    return data


async def get_project_id(
    owner: str,
    project_number: int,
    agent_settings: AgentSettings,
) -> str:
    """
    Fetch the project node ID for a GitHub Project v2.

    Args:
        owner: The user or organization that owns the project.
        project_number: The project number (visible in the URL).
        agent_settings: Agent configuration containing GitHub settings.

    Returns:
        The project node ID (e.g., "PVT_kwDOBxxxxxx").

    Raises:
        RuntimeError: If the project is not found or API call fails.
    """
    query = """
    query($owner: String!, $number: Int!) {
        user(login: $owner) {
            projectV2(number: $number) {
                id
                title
            }
        }
    }
    """

    variables = {"owner": owner, "number": project_number}

    try:
        data = await _execute_graphql(query, variables, agent_settings)
        project = data.get("data", {}).get("user", {}).get("projectV2")

        if project:
            logger.info(
                "Found user project: %s (id: %s)", project["title"], project["id"]
            )
            return project["id"]
    except RuntimeError:
        pass

    query_org = """
    query($owner: String!, $number: Int!) {
        organization(login: $owner) {
            projectV2(number: $number) {
                id
                title
            }
        }
    }
    """

    data = await _execute_graphql(query_org, variables, agent_settings)
    project = data.get("data", {}).get("organization", {}).get("projectV2")

    if project:
        logger.info("Found org project: %s (id: %s)", project["title"], project["id"])
        return project["id"]

    raise RuntimeError(
        f"GitHub Project #{project_number} not found for owner '{owner}'"
    )


async def get_project_columns(agent_settings: AgentSettings) -> list[dict[str, str]]:
    """
    Fetch all columns (status field options) from the GitHub Project.

    Returns:
        List of dicts with 'id' and 'name' keys for each column.
    """
    task_system = agent_settings.get_task_system("github")
    project_id = task_system.board_id if task_system else None

    query = """
    query($projectId: ID!) {
        node(id: $projectId) {
            ... on ProjectV2 {
                field(name: "Status") {
                    ... on ProjectV2SingleSelectField {
                        id
                        options {
                            id
                            name
                        }
                    }
                }
            }
        }
    }
    """

    variables = {"projectId": project_id}
    data = await _execute_graphql(query, variables, agent_settings)

    field = data.get("data", {}).get("node", {}).get("field", {})
    options = field.get("options", [])

    return [{"id": opt["id"], "name": opt["name"]} for opt in options]


async def get_status_field_id(agent_settings: AgentSettings) -> str:
    """Get the ID of the Status field for the project."""
    task_system = agent_settings.get_task_system("github")
    project_id = task_system.board_id if task_system else None

    query = """
    query($projectId: ID!) {
        node(id: $projectId) {
            ... on ProjectV2 {
                field(name: "Status") {
                    ... on ProjectV2SingleSelectField {
                        id
                    }
                }
            }
        }
    }
    """

    variables = {"projectId": project_id}
    data = await _execute_graphql(query, variables, agent_settings)

    field = data.get("data", {}).get("node", {}).get("field", {})
    field_id = field.get("id")

    if not field_id:
        raise RuntimeError("Status field not found in project")

    return field_id


async def get_items_from_column(
    column_name: str,
    agent_settings: AgentSettings,
) -> list[dict[str, Any]]:
    """
    Fetch all items from a specific column (status) in the GitHub Project.

    Args:
        column_name: The name of the column/status to fetch items from.
        agent_settings: Agent configuration.

    Returns:
        List of item dicts with id, title, body, url, and content info.
    """
    task_system = agent_settings.get_task_system("github")
    project_id = task_system.board_id if task_system else None

    query = """
    query($projectId: ID!, $cursor: String) {
        node(id: $projectId) {
            ... on ProjectV2 {
                items(first: 100, after: $cursor) {
                    pageInfo {
                        hasNextPage
                        endCursor
                    }
                    nodes {
                        id
                        fieldValueByName(name: "Status") {
                            ... on ProjectV2ItemFieldSingleSelectValue {
                                name
                                optionId
                            }
                        }
                        content {
                            ... on Issue {
                                id
                                number
                                title
                                body
                                url
                            }
                            ... on DraftIssue {
                                id
                                title
                                body
                            }
                        }
                    }
                }
            }
        }
    }
    """

    all_items: list[dict[str, Any]] = []
    cursor: Optional[str] = None

    while True:
        variables = {"projectId": project_id, "cursor": cursor}
        data = await _execute_graphql(query, variables, agent_settings)

        items_data = data.get("data", {}).get("node", {}).get("items", {})
        nodes = items_data.get("nodes", [])

        for node in nodes:
            status_field = node.get("fieldValueByName", {})
            status_name = status_field.get("name") if status_field else None

            if status_name == column_name:
                content = node.get("content", {}) or {}
                all_items.append(
                    {
                        "id": node["id"],
                        "content_id": content.get("id", ""),
                        "title": content.get("title", ""),
                        "body": content.get("body", ""),
                        "url": content.get("url", ""),
                        "number": content.get("number"),
                    }
                )

        page_info = items_data.get("pageInfo", {})
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")

    return all_items


async def get_project_item(
    item_id: str,
    agent_settings: AgentSettings,
) -> dict[str, Any]:
    """Fetch a single project item with its status metadata."""
    query = """
    query($itemId: ID!) {
        node(id: $itemId) {
            ... on ProjectV2Item {
                id
                fieldValueByName(name: "Status") {
                    ... on ProjectV2ItemFieldSingleSelectValue {
                        optionId
                        name
                    }
                }
                content {
                    __typename
                    ... on Issue {
                        id
                        title
                        body
                        url
                    }
                    ... on DraftIssue {
                        id
                        title
                        body
                    }
                }
            }
        }
    }
    """

    variables = {"itemId": item_id}
    data = await _execute_graphql(query, variables, agent_settings)

    node = data.get("data", {}).get("node")
    if not node:
        raise RuntimeError(f"GitHub project item {item_id} not found")

    status_field = node.get("fieldValueByName") or {}
    content = node.get("content") or {}

    return {
        "id": node.get("id", item_id),
        "title": content.get("title", ""),
        "body": content.get("body", ""),
        "url": content.get("url", ""),
        "state_id": status_field.get("optionId", ""),
        "state_name": status_field.get("name", ""),
    }


async def move_item_to_column(
    item_id: str,
    column_id: str,
    agent_settings: AgentSettings,
) -> None:
    """
    Move a project item to a different column (status).

    Args:
        item_id: The project item node ID.
        column_id: The target column/status option ID.
        agent_settings: Agent configuration.
    """
    task_system = agent_settings.get_task_system("github")
    project_id = task_system.board_id if task_system else None
    field_id = await get_status_field_id(agent_settings)

    mutation = """
    mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $optionId: String!) {
        updateProjectV2ItemFieldValue(
            input: {
                projectId: $projectId
                itemId: $itemId
                fieldId: $fieldId
                value: { singleSelectOptionId: $optionId }
            }
        ) {
            projectV2Item {
                id
            }
        }
    }
    """

    variables = {
        "projectId": project_id,
        "itemId": item_id,
        "fieldId": field_id,
        "optionId": column_id,
    }

    await _execute_graphql(mutation, variables, agent_settings)
    logger.info("Moved item %s to column %s", item_id, column_id)


async def move_item_to_named_column(
    item_id: str,
    column_name: str,
    agent_settings: AgentSettings,
) -> str:
    """
    Move a project item to a column identified by name.

    Returns:
        The ID of the target column.
    """
    columns = await get_project_columns(agent_settings)
    target_column = next((col for col in columns if col["name"] == column_name), None)

    if not target_column:
        raise ValueError(f"Column '{column_name}' not found in project")

    await move_item_to_column(item_id, target_column["id"], agent_settings)
    return target_column["id"]


async def _resolve_to_issue_id(
    node_id: str,
    agent_settings: AgentSettings,
) -> str:
    """
    Resolve a node ID to an Issue ID.

    If the node_id is a ProjectV2Item, extract the content Issue ID.
    If it's already an Issue ID, return it as-is.

    Args:
        node_id: Either an Issue ID or ProjectV2Item ID
        agent_settings: Agent configuration

    Returns:
        The Issue ID

    Raises:
        RuntimeError: If the node cannot be resolved to an Issue
    """
    query = """
    query($nodeId: ID!) {
        node(id: $nodeId) {
            __typename
            ... on Issue {
                id
            }
            ... on ProjectV2Item {
                content {
                    ... on Issue {
                        id
                    }
                }
            }
        }
    }
    """

    variables = {"nodeId": node_id}
    data = await _execute_graphql(query, variables, agent_settings)

    node = data.get("data", {}).get("node", {})
    if not node:
        raise RuntimeError(f"Could not resolve node {node_id}")

    node_type = node.get("__typename")

    # If it's already an Issue, return its ID
    if node_type == "Issue":
        return node.get("id", node_id)

    # If it's a ProjectV2Item, extract the Issue ID from content
    if node_type == "ProjectV2Item":
        content = node.get("content", {})
        issue_id = content.get("id")
        if issue_id:
            return issue_id
        raise RuntimeError(f"ProjectV2Item {node_id} does not have an Issue as content")

    raise RuntimeError(
        f"Node {node_id} is neither an Issue nor a ProjectV2Item (type: {node_type})"
    )


async def add_comment_to_issue(
    issue_id: str,
    comment: str,
    agent_settings: AgentSettings,
) -> None:
    """
    Add a comment to a GitHub issue or project item.

    Args:
        issue_id: Either an Issue ID or ProjectV2Item ID.
        comment: The comment text to add.
        agent_settings: Agent configuration.
    """
    # First, resolve the ID to get the actual Issue ID if it's a ProjectV2Item
    resolved_issue_id = await _resolve_to_issue_id(issue_id, agent_settings)

    mutation = """
    mutation($issueId: ID!, $body: String!) {
        addComment(input: { subjectId: $issueId, body: $body }) {
            commentEdge {
                node {
                    id
                }
            }
        }
    }
    """

    variables = {"issueId": resolved_issue_id, "body": comment}
    await _execute_graphql(mutation, variables, agent_settings)
    logger.info("Added comment to issue %s", resolved_issue_id)


async def get_issue_comments(
    issue_id: str,
    agent_settings: AgentSettings,
) -> list[dict[str, Any]]:
    """
    Fetch all comments for a GitHub issue or project item.

    Args:
        issue_id: Either an Issue ID or ProjectV2Item ID

    Returns:
        List of comment dicts with id, text, author, and date.
    """
    query = """
    query($issueId: ID!) {
        node(id: $issueId) {
            ... on Issue {
                comments(first: 100) {
                    nodes {
                        id
                        body
                        author {
                            login
                        }
                        createdAt
                    }
                }
            }
            ... on ProjectV2Item {
                content {
                    ... on Issue {
                        comments(first: 100) {
                            nodes {
                                id
                                body
                                author {
                                    login
                                }
                                createdAt
                            }
                        }
                    }
                }
            }
        }
    }
    """

    variables = {"issueId": issue_id}
    data = await _execute_graphql(query, variables, agent_settings)

    node = data.get("data", {}).get("node", {})

    # Try to get comments directly (if it's an Issue)
    comments = node.get("comments", {}).get("nodes", [])

    # If no comments found, try to get from ProjectV2Item content
    if not comments:
        content = node.get("content", {})
        comments = content.get("comments", {}).get("nodes", [])

    return [
        {
            "id": c["id"],
            "text": c["body"],
            "member_creator": c.get("author", {}).get("login", "unknown"),
            "date": c["createdAt"],
        }
        for c in comments
    ]


async def get_item_status_history(
    item_id: str,
    agent_settings: AgentSettings,
) -> list[dict[str, Any]]:
    """
    Fetch status change history for a project item.

    Note: GitHub Projects v2 doesn't have a direct API for field change history.
    This returns an empty list as a placeholder - status moves would need to be
    tracked via issue timeline events or external logging.
    """
    logger.warning(
        "GitHub Projects v2 doesn't provide direct status change history. Item: %s",
        item_id,
    )
    return []


async def create_draft_issue(
    title: str,
    body: str,
    column_name: str,
    agent_settings: AgentSettings,
) -> dict[str, Any]:
    """
    Create a new draft issue in the GitHub Project.

    Args:
        title: The title of the draft issue.
        body: The body/description of the draft issue.
        column_name: The column to create the issue in.
        agent_settings: Agent configuration.

    Returns:
        Dict with id, title, and column info.
    """
    task_system = agent_settings.get_task_system("github")
    project_id = task_system.board_id if task_system else None

    mutation = """
    mutation($projectId: ID!, $title: String!, $body: String!) {
        addProjectV2DraftIssue(
            input: {
                projectId: $projectId
                title: $title
                body: $body
            }
        ) {
            projectItem {
                id
            }
        }
    }
    """

    variables = {
        "projectId": project_id,
        "title": title,
        "body": body,
    }

    data = await _execute_graphql(mutation, variables, agent_settings)
    item_id = data["data"]["addProjectV2DraftIssue"]["projectItem"]["id"]

    await move_item_to_named_column(item_id, column_name, agent_settings)

    return {
        "id": item_id,
        "title": title,
        "url": "",
        "column": column_name,
    }


def get_project_id_sync(
    owner: str,
    project_number: str,
    base_url: str = "https://api.github.com",
    api_token: Optional[str] = None,
) -> str:
    """
    Synchronous version of get_project_id for use during configuration save.

    Args:
        owner: The user or organization that owns the project.
        project_number: The project number.
        base_url: GitHub API base URL.
        api_token: Optional GitHub PAT. Falls back to GITHUB_TOKEN env var.

    Returns:
        The project node ID.

    Raises:
        RuntimeError: If the project is not found.
    """
    if api_token:
        token = api_token
    else:
        token = _get_github_token()
    url = f"{base_url.rstrip('/')}{GITHUB_GRAPHQL_ENDPOINT}"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    query_user = """
    query($owner: String!, $number: Int!) {
        user(login: $owner) {
            projectV2(number: $number) {
                id
                title
            }
        }
    }
    """

    variables = {"owner": owner, "number": project_number}

    with httpx.Client() as client:
        response = client.post(
            url,
            headers=headers,
            json={"query": query_user, "variables": variables},
            timeout=30.0,
        )

    if response.status_code == 200:
        data = response.json()
        if "errors" not in data:
            project = data.get("data", {}).get("user", {}).get("projectV2")
            if project:
                logger.info(
                    "Found user project: %s (id: %s)", project["title"], project["id"]
                )
                return project["id"]

    query_org = """
    query($owner: String!, $number: Int!) {
        organization(login: $owner) {
            projectV2(number: $number) {
                id
                title
            }
        }
    }
    """

    with httpx.Client() as client:
        response = client.post(
            url,
            headers=headers,
            json={"query": query_org, "variables": variables},
            timeout=30.0,
        )

    if response.status_code != 200:
        raise RuntimeError(f"GitHub API request failed: {response.text}")

    data = response.json()
    if "errors" in data:
        error_messages = [e.get("message", str(e)) for e in data["errors"]]
        raise RuntimeError(f"GitHub API errors: {'; '.join(error_messages)}")

    project = data.get("data", {}).get("organization", {}).get("projectV2")
    if project:
        logger.info("Found org project: %s (id: %s)", project["title"], project["id"])
        return project["id"]

    raise RuntimeError(
        f"GitHub Project #{project_number} not found for owner '{owner}'"
    )
