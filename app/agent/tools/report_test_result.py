"""Tool for reporting the tester's final result."""

from langchain_core.tools import tool


@tool
def report_test_result(result: str, summary: str) -> str:
    """Return the final outcome of the testing phase."""
    return f"Test Process Completed. Result: {result}. Summary: {summary}"
