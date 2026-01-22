"""
Defines the agent_skill_level node for the agent graph.

This node is responsible for the analysis which skill level must have the agent
to complete the task. It uses a specialized LLM call to classify the user's request
and decide the skill level (junior or senior).
"""

import logging
from typing import Any, Dict, Literal

from langchain_core.exceptions import OutputParserException
from langchain_core.messages import SystemMessage
from pydantic import BaseModel, Field

from app.agent.services.summaries import append_agent_summary
from app.agent.state import AgentState

logger = logging.getLogger(__name__)

AGENT_SKILL_LEVEL_SYSTEM = """
# ROLE
You are a **Technical Lead** in a software development team.
Your objective is to analyze a given coding task and classify its skill level to assign
it to the correct developer profile.

# CLASSIFICATION CATEGORIES

## 1. Junior Developer Level
Assign 'junior' if the task meets these criteria:
- **Scope:** Isolated to a single file or method.
- **Type:** Simple bug fixes (NPE, typos), text changes, CSS adjustments, adding a simple unit test, or basic CRUD operations.
- **Ambiguity:** The instructions are explicit and step-by-step.
- **Risk:** Low risk of breaking the overall system architecture.
- **Dependencies:** No new libraries or complex dependency management required.

## 2. Senior Developer Level
Assign 'senior' if the task meets these criteria:
- **Scope:** Affects multiple modules, requires architectural changes, or cross-cutting concerns (logging, security, transaction management).
- **Type:** Refactoring, performance optimization, concurrency/threading, database schema migrations, or integrating external 3rd-party APIs.
- **Ambiguity:** The task is vague (e.g., "Improve performance") and requires investigation or design decisions.
- **Risk:** High risk of regression or side effects.
- **Knowledge:** Requires deep understanding of frameworks (e.g., Spring Boot internals, React Lifecycle nuances).

# INPUT FORMAT
You will receive a `TASK_TITLE` and a `TASK_DESCRIPTION`.

# OUTPUT FORMAT
You must return a valid JSON object with exactly two fields:
1. `reasoning`: A short sentence explaining why you chose the category.
2. `classification`: The result string, which must be exactly "junior" or "senior".

# EXAMPLES

**Input:**
Title: "Fix typo in Login Button"
Description: "The button says 'Logni' instead of 'Login'."
**Output:**
{
  "reasoning": "Simple text change in UI, isolated scope.",
  "classification": "junior"
}

**Input:**
Title: "Implement JWT Authentication"
Description: "Secure all API endpoints using JWT tokens and add role-based access control."
**Output:**
{
  "reasoning": "Involves security, architectural changes across multiple endpoints, and understanding of auth flows.",
  "classification": "senior"
}

**Input:**
Title: "Add age validation"
Description: "User age must be > 18 in the registration service."
**Output:**
{
  "reasoning": "Basic logic check in a single service method.",
  "classification": "junior"
}"""


def has_required_skill_level(task_skill_level, agent_skill_level):
    """True if the agent has the required skill level for the task otherwise False"""
    if task_skill_level == "senior" and agent_skill_level == "junior":
        return False
    return True


# pylint: disable=too-few-public-methods
class SkillLevelResult(BaseModel):
    """Represents the result of the agent skill level analysis."""

    reasoning: str = Field(description="Why this classification was chosen")
    classification: Literal["junior", "senior"] = Field(
        description="Must be 'junior' or 'senior'"
    )


def create_agent_skill_level_node(llm):
    """
    Factory function that creates the coder skill level node for the agent graph.

    Args:
        llm: The language model to be used for routing decisions.

    Returns:
        A function that represents the coder skill level node.
    """
    structured_llm = llm.with_structured_output(SkillLevelResult, method="json_mode")

    async def agent_skill_level_node(state: AgentState) -> Dict[str, Any]:
        # Router only needs the original task to make routing decision
        task = state["messages"][0].content
        messages = [SystemMessage(content=AGENT_SKILL_LEVEL_SYSTEM)] + [task]

        try:
            response = await structured_llm.ainvoke(messages)
            logger.info(
                "Skill Level Decision: %s (%s)",
                response.classification,
                response.reasoning,
            )
            summary_entries = list(state.get("agent_summary") or [])
            if not has_required_skill_level(
                response.classification, state["agent_skill_level"]
            ):
                comment = (
                    f"Agent skill level is {state['agent_skill_level']}, "
                    + f"but task requires {response.classification} because:\n\n"
                    + f"{response.reasoning}"
                )
                summary_entries = append_agent_summary(
                    summary_entries, "agent_skill_level", comment
                )
            return {
                "task_skill_level": response.classification,
                "agent_summary": summary_entries,
                "current_node": "agent_skill_level",
            }
        except OutputParserException as e:
            logger.warning(
                "agent_skill_level_node produced invalid JSON: %s",
                e,
            )
            return {"task_skill_level": "junior"}

    return agent_skill_level_node
