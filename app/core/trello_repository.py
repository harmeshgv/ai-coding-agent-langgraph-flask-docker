"""
Database repository functions for managing issues and their corresponding branches.
"""

from typing import Optional

from core.extensions import db
from core.models import Issue


def get_branch_for_issue(issue_id: str) -> Optional[str]:
    """
    Retrieves the branch name associated with an issue ID.
    Returns None if no mapping exists.
    """
    issue = Issue.query.filter_by(trello_card_id=issue_id).first()
    return issue.branch_name if issue else None


def upsert_issue(
    issue_id: str, issue_name: str, branch_name: str, repo_url: str | None = None
) -> Issue:
    """
    Creates or updates an Issue record for an issue.
    If an issue with the given card_id exists, updates it; otherwise creates a new one.
    """
    issue = Issue.query.filter_by(trello_card_id=issue_id).first()

    if issue:
        issue.card_name = issue_name
        issue.branch_name = branch_name
        if repo_url:
            issue.repo_url = repo_url
    else:
        issue = Issue(
            trello_card_id=issue_id,
            card_name=issue_name,
            branch_name=branch_name,
            repo_url=repo_url,
        )
        db.session.add(issue)

    db.session.commit()
    return issue


def get_issue_by_card_id(card_id: str) -> Optional[Issue]:
    """
    Retrieves the full Issue record for a given Trello card ID.
    Returns None if no mapping exists.
    """
    return Issue.query.filter_by(trello_card_id=card_id).first()


def remove_issue_from_db(card_id: str) -> bool:
    """
    Removes an Issue record from the database by Trello card ID.

    Args:
        card_id (str): The Trello card ID of the issue to remove.

    Returns:
        bool: True if an issue was found and deleted, False otherwise.
    """
    issue = Issue.query.filter_by(trello_card_id=card_id).first()

    if issue:
        db.session.delete(issue)
        db.session.commit()
        return True

    return False
