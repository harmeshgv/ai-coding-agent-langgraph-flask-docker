import logging
from sqlalchemy.exc import IntegrityError

from app.core.extensions import db
from app.core.localdb.models import AgentAction, AgentTask

logger = logging.getLogger(__name__)


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
