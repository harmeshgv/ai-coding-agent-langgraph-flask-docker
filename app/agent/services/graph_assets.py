"""Utilities for persisting LangGraph visualizations."""

from __future__ import annotations


def save_graph_as_png(graph) -> None:
    """Persist the compiled LangGraph as a PNG asset."""
    png_bytes = graph.get_graph().draw_mermaid_png()
    with open("workflow_graph.png", "wb") as handle:
        handle.write(png_bytes)


def save_graph_as_mermaid(graph) -> None:
    """Persist the compiled LangGraph as Mermaid markup."""
    mermaid_code = graph.get_graph().draw_mermaid()
    with open("workflow_graph.mmd", "w", encoding="utf-8") as handle:
        handle.write(mermaid_code)
