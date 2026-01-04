import logging
import os
import re
import shutil

from git import Repo
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

logger = logging.getLogger(__name__)


# Hilfsfunktion, um Redundanz zu vermeiden
def get_workspace():
    # Holt den Pfad aus der Env-Var, die wir im Docker-Compose gesetzt haben
    return os.environ.get("WORKSPACE", "/coding-agent-workspace")


def get_workbench():
    # Holt den Pfad aus der Env-Var, die wir im Docker-Compose gesetzt haben
    return os.environ.get("WORKBENCH", "")


def load_system_prompt(stack: str, role: str) -> str:
    """
    Lädt den System-Prompt basierend auf Stack und Rolle.
    z.B. stack="backend", role="coder" -> liest workbench/backend/systemprompt_coder.md
    """

    file_path = os.path.join("workbench", stack, f"systemprompt_{role}.md")

    logger.info(f"Loading system prompt: {file_path}")
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        # Fallback, falls Datei fehlt (wichtig für Robustheit!)
        logger.warning(f"WARNUNG: System Prompt not found: {file_path}")
        return "You are a helpful coding assistent."


def _estimate_tokens(messages: list[BaseMessage]) -> int:
    """Rough estimate of token count for messages (avg ~4 chars per token)."""
    total_chars = 0
    for msg in messages:
        if hasattr(msg, 'content') and msg.content:
            total_chars += len(str(msg.content))
        if hasattr(msg, 'tool_calls') and msg.tool_calls:
            total_chars += len(str(msg.tool_calls))
    return total_chars // 4


def filter_messages_for_llm(messages: list[BaseMessage], max_messages: int = 10) -> list[BaseMessage]:
    """
    Filters messages to keep only the most recent and relevant ones for LLM context.
    This reduces token usage by limiting the message history.
    
    Strategy:
    - Always keep the first HumanMessage (original task)
    - Keep the most recent complete conversation turns
    - Never break AI→Tool message pairs to maintain valid message order
    - Prevent orphaned ToolMessages that would violate API constraints
    
    :param messages: List of messages from state
    :param max_messages: Maximum number of messages to keep (excluding first task message)
    :return: Filtered list of messages
    """
    if not messages:
        return []
    
    original_count = len(messages)
    original_tokens = _estimate_tokens(messages)
    
    if len(messages) <= max_messages + 1:
        logger.debug(f"Message filter: {original_count} messages, ~{original_tokens} tokens (no filtering needed)")
        return messages
    
    # Find the first HumanMessage (original task)
    first_human_idx = None
    for idx, msg in enumerate(messages):
        if isinstance(msg, HumanMessage):
            first_human_idx = idx
            break
    
    # Start from the desired cutoff point
    recent_start_idx = max(0, len(messages) - max_messages)
    
    # Find a safe cut point by scanning forward to find a complete conversation boundary
    # Safe boundaries are: before HumanMessage, or before AIMessage that doesn't have tool_calls
    adjusted_start_idx = recent_start_idx
    
    for idx in range(recent_start_idx, len(messages)):
        msg = messages[idx]
        
        # Check if this is a safe starting point
        if isinstance(msg, HumanMessage):
            # Always safe to start from a HumanMessage
            adjusted_start_idx = idx
            break
        elif isinstance(msg, AIMessage):
            # Check if this AI message has tool calls
            has_tool_calls = bool(getattr(msg, 'tool_calls', None))
            if not has_tool_calls:
                # Safe to start from AIMessage without tool calls
                adjusted_start_idx = idx
                break
            else:
                # AIMessage with tool calls - need to check if all tool responses follow
                # Count expected tool responses
                num_tool_calls = len(getattr(msg, 'tool_calls', []))
                # Check if the next num_tool_calls messages are ToolMessages
                all_tools_present = True
                for j in range(1, num_tool_calls + 1):
                    if idx + j >= len(messages) or not isinstance(messages[idx + j], ToolMessage):
                        all_tools_present = False
                        break
                
                # If all tool responses are present, we can start from this AIMessage
                if all_tools_present:
                    adjusted_start_idx = idx
                    break
    
    recent_messages = messages[adjusted_start_idx:]
    
    # Ensure the message list doesn't end with an AIMessage without tool_calls
    # Mistral API requires the last message to be User or Tool (or Assistant with tool_calls)
    while recent_messages and isinstance(recent_messages[-1], AIMessage):
        ai_msg = recent_messages[-1]
        # If AIMessage has tool_calls, it's valid as last message
        if getattr(ai_msg, 'tool_calls', None):
            break
        # Otherwise, remove it
        recent_messages = recent_messages[:-1]
    
    # If we filtered everything out, return at least the last HumanMessage
    if not recent_messages and messages:
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                return [msg]
        # Fallback: return last message if no HumanMessage found
        return [messages[-1]] if messages else []
    
    # Keep first human message and recent messages
    if first_human_idx is not None and first_human_idx < adjusted_start_idx:
        # Include the first task message if it's not already in recent messages
        first_task = [messages[first_human_idx]]
        filtered_messages = first_task + recent_messages
    else:
        filtered_messages = recent_messages
    
    # Log token savings
    filtered_count = len(filtered_messages)
    filtered_tokens = _estimate_tokens(filtered_messages)
    saved_tokens = original_tokens - filtered_tokens
    saved_percentage = (saved_tokens / original_tokens * 100) if original_tokens > 0 else 0
    
    logger.info(
        f"Message filter: {original_count} → {filtered_count} messages "
        f"(~{original_tokens} → ~{filtered_tokens} tokens, "
        f"saved ~{saved_tokens} tokens / {saved_percentage:.1f}%)"
    )
    
    return filtered_messages


def sanitize_response(response: AIMessage) -> AIMessage:
    """
    Entfernt halluzinierte Tool-Calls (z.B. wenn der Name ein ganzer Satz ist).
    Verhindert API Fehler 3280 (Invalid function name).
    """
    # Wenn keine Tool Calls da sind oder es keine AI Message ist, einfach zurückgeben
    if not isinstance(response, AIMessage) or not response.tool_calls:
        return response

    valid_tools = []
    # Erlaubte Zeichen für Funktionsnamen: a-z, A-Z, 0-9, _, -
    name_pattern = re.compile(r"^[a-zA-Z0-9_-]+$")

    for tc in response.tool_calls:
        name = tc.get("name", "")
        # Check: Ist der Name im gültigen Format und nicht zu lang?
        if name_pattern.match(name) and len(name) < 64:
            valid_tools.append(tc)
        else:
            logger.warning(f"SANITIZER: Removed invalid tool call with name: '{name}'")

    # Das manipulierte Objekt zurückgeben
    response.tool_calls = valid_tools
    return response


def save_graph_as_png(graph):
    # 1. Die Bilddaten in einer Variable speichern (es sind Bytes)
    png_bytes = graph.get_graph().draw_mermaid_png()

    # 2. Datei im 'write binary' Modus ("wb") öffnen und speichern
    with open("workflow_graph.png", "wb") as f:
        f.write(png_bytes)

    print("Graph wurde als 'workflow_graph.png' gespeichert.")


def save_graph_as_mermaid(graph):
    # 1. Die Bilddaten in einer Variable speichern (es sind Bytes)
    mermaid_code = graph.get_graph().draw_mermaid()

    # 2. Datei im 'write binary' Modus ("wb") öffnen und speichern
    with open("workflow_graph.mmd", "w") as f:
        f.write(mermaid_code)

    print("Graph wurde als 'workflow_graph.mmd' gespeichert.")


def ensure_repository_exists(repo_url, work_dir):
    """
    Stellt sicher, dass work_dir ein valides Git-Repo ist.
    """
    # 1. Inhalt löschen, aber NICHT den Ordner selbst (wegen Mount)
    for filename in os.listdir(work_dir):
        file_path = os.path.join(work_dir, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            print(f"Failed to delete {file_path}. Reason: {e}")

    # 2. In das nun leere Verzeichnis klonen
    # Der Punkt '.' ist wichtig, damit git nicht einen Unterordner erstellt
    logger.info(f"Cloning repository {repo_url} into {work_dir}")
    Repo.clone_from(repo_url, work_dir)
