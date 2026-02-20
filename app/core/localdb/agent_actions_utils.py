import logging
from sqlalchemy.exc import IntegrityError

from app.core.extensions import db
from app.core.localdb.models import AgentAction, AgentTask
from sqlalchemy import select

logger = logging.getLogger(__name__)


def read_db_agent_actions(agent_task: AgentTask) -> list[AgentAction]:
    """Get the last task from the database."""
    stmt = (
        select(AgentAction)
        .where(AgentAction.task_id == agent_task.id)
        .order_by(AgentAction.id.asc())
    )
    return db.session.execute(stmt).scalars().all()


def create_db_agent_action(
    agent_task: AgentTask, current_node: str | None, tool_calls: list[dict] | None
):
    """insert agent state into sqlalchemy database"""
    if current_node is None or not tool_calls:
        return None

    try:
        for tool_call in tool_calls:
            name = tool_call.get("name", "unknown")
            logger.debug(
                "Creating agent state in database for current_node: %s tool: %s",
                current_node,
                name,
            )
            args = tool_call.get("args", {}) or {}
            arg0_name = ""
            arg0_value = ""
            if args and name in ["read_file", "write_to_file", "run_command"]:
                arg0_name, arg0_value = next(iter(args.items()))

            last_agent_action = get_last_agent_action()
            if (
                last_agent_action
                and last_agent_action.current_node == current_node
                and last_agent_action.tool_name == name
                and last_agent_action.tool_arg0_name == arg0_name
                and last_agent_action.tool_arg0_value == arg0_value
            ):
                return
            new_agent_action = AgentAction(
                task_id=agent_task.id,
                current_node=current_node,
                tool_name=name,
                tool_arg0_name=arg0_name,
                tool_arg0_value=arg0_value,
            )
            db.session.add(new_agent_action)
            db.session.commit()
        return

    except IntegrityError as e:
        # Happens if task_id (unique=True) is already assigned
        db.session.rollback()
        logging.error("Error creating agent action: %s", e)
        return None
    except Exception as e:  # pylint: disable=broad-exception-caught
        db.session.rollback()
        logging.error("Error creating agent action: %s", e)
        return None


def get_last_agent_action() -> AgentAction | None:
    """Get the last task from the database."""
    stmt = select(AgentAction).order_by(AgentAction.id.desc())
    return db.session.execute(stmt).scalar()
