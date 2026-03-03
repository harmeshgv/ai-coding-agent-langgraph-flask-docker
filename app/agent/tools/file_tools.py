"""A collection of tools for the agent to interact with files"""

from dataclasses import dataclass
import fnmatch
import logging
import os

from langchain_core.tools import tool

from app.agent.utils import get_instance_dir, get_workspace

logger = logging.getLogger(__name__)


def _get_full_workspace_path(filepath: str) -> str:
    """Get full path for a file in the workspace.

    Args:
        filepath: Relative file path

    Returns:
        Full absolute path within workspace
    """
    return _get_full_path(get_workspace(), filepath)

def _get_full_instance_path(filepath: str) -> str:
    """Get full path for a file in the instance directory.

    Args:
        filepath: Relative file path

    Returns:
        Full absolute path within instance directory
    """
    return _get_full_path(get_instance_dir(), filepath)

def _get_full_path(base_path: str, filepath: str) -> str:
    """Construct and validate a full path within a base directory.

    This function ensures that the resulting path stays within the base directory
    by removing leading slashes and validating the resolved path.

    Args:
        base_path: Base directory path
        filepath: Relative file path (leading slashes will be stripped)

    Returns:
        Full absolute path if valid, error message if access denied
    """
    # Strip leading slashes to prevent absolute path injection
    clean_path = filepath.lstrip("/")
    full_path = os.path.join(base_path, clean_path)

    # Resolve symlinks and relative paths to prevent directory traversal
    full_path_real = os.path.realpath(full_path)
    path_real = os.path.realpath(base_path)

    # Verify the resolved path is within the base directory
    if not full_path_real.startswith(path_real):
        logger.warning(
            "Path traversal attempt blocked: %s is outside %s",
            full_path_real,
            path_real
        )
        return f"Access denied target file: {full_path_real} is not in path {path_real}"

    logger.debug("Validated path: %s -> %s", filepath, full_path_real)
    return full_path


def write_to_file_in_workspace(filepath: str, content: str):
    """Write content to a file in the workspace.

    Creates parent directories if they don't exist.

    Args:
        filepath: Relative path to the file
        content: Content to write

    Returns:
        Success message or error message
    """
    try:
        logger.debug("Writing to workspace file: %s", filepath)
        full_path = _get_full_workspace_path(filepath)

        # Create parent directories if needed
        parent_dir = os.path.dirname(full_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
            logger.debug("Ensured directory exists: %s", parent_dir)

        # Write content to file
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)

        logger.debug("Successfully wrote %d bytes to %s", len(content), full_path)
        return f"Successfully wrote to {full_path}"
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Failed to write file %s: %s", filepath, str(e))
        logger.debug("Write error stacktrace:", exc_info=True)
        return f"ERROR writing file: {str(e)}"

def write_to_file_in_instance_dir(filepath: str, content: str):
    """Write content to a file in the instance directory.

    Creates parent directories if they don't exist.

    Args:
        filepath: Relative path to the file
        content: Content to write

    Returns:
        Success message or error message
    """
    try:
        logger.debug("Writing to instance file: %s", filepath)
        full_path = _get_full_instance_path(filepath)

        # Create parent directories if needed
        parent_dir = os.path.dirname(full_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
            logger.debug("Ensured directory exists: %s", parent_dir)

        # Write content to file
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)

        logger.debug("Successfully wrote %d bytes to %s", len(content), full_path)
        return f"Successfully wrote to {full_path}"
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Failed to write instance file %s: %s", filepath, str(e))
        logger.debug("Write error stacktrace:", exc_info=True)
        return f"ERROR writing file: {str(e)}"


def read_file_in_workspace(filepath: str):
    """Read the content of a file from the workspace.

    Args:
        filepath: Relative path to the file

    Returns:
        File content, empty file message, or error message
    """
    try:
        logger.debug("Reading workspace file: %s", filepath)
        full_path = _get_full_workspace_path(filepath)

        # Check if file exists
        if not os.path.exists(full_path):
            logger.warning("File not found: %s", full_path)
            return (
                f"ERROR: File {full_path} does not exist. "
                + "(Current dir: {os.listdir(WORKSPACE)})"
            )

        # Read file content
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()

        if not content:
            logger.debug("File is empty: %s", full_path)
            return "(File is empty)"

        logger.debug("Successfully read %d bytes from %s", len(content), full_path)
        return content
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Failed to read file %s: %s", filepath, str(e))
        logger.debug("Read error stacktrace:", exc_info=True)
        return f"ERROR reading file: {str(e)}"


# Ignore patterns for directory traversal
IGNORE_PATTERNS = {
    ".git", ".gradle", "node_modules", "__pycache__",
    ".pytest_cache", ".venv", "venv", "build", "dist",
    "target", ".idea", ".vscode", "*.egg-info"
}


@dataclass
class _FileListingContext:
    """Context object for file listing operations.

    Groups related parameters to reduce function argument count and
    maintain state during directory traversal.

    Attributes:
        workspace: Absolute path to workspace directory
        max_files: Maximum number of files to collect
        pattern: Optional glob pattern for filtering files
        file_list: Accumulated list of matching file paths
        truncated: Flag indicating if max_files limit was reached
    """
    workspace: str
    max_files: int
    pattern: str | None
    file_list: list[str]
    truncated: bool = False


def _should_skip_directory(
        root: str, dirs: list[str], max_depth: int | None, start_depth: int
) -> bool:
    """Determine if a directory should be skipped during traversal.

    Filters out ignored directories and enforces max depth limit.
    Modifies the dirs list in-place to prevent os.walk from descending.

    Args:
        root: Current directory path being processed
        dirs: List of subdirectories (modified in-place)
        max_depth: Maximum recursion depth (None for unlimited)
        start_depth: Starting depth for relative depth calculation

    Returns:
        True if directory should be skipped, False otherwise
    """
    # Filter ignored directories in-place to prevent os.walk from descending
    original_count = len(dirs)
    dirs[:] = [d for d in dirs if d not in IGNORE_PATTERNS]

    if len(dirs) < original_count:
        logger.debug(
            "Filtered %d ignored directories from %s",
            original_count - len(dirs),
            root
        )

    # Check if current depth exceeds max_depth
    if max_depth is not None:
        current_depth = root.count(os.sep) - start_depth
        if current_depth >= max_depth:
            logger.debug("Max depth %d reached at %s", max_depth, root)
            dirs.clear()  # Prevent further descent
            return True

    # Skip directories containing ignored patterns in their path
    if any(pattern in root for pattern in IGNORE_PATTERNS):
        logger.debug("Skipping directory with ignored pattern: %s", root)
        return True

    return False


def _process_files_for_listing(root: str, files: list[str], ctx: _FileListingContext) -> None:
    """Process files in a directory for the file listing.

    Applies pattern filtering and enforces max_files limit.
    Updates the context object with matching files.

    Args:
        root: Current directory path
        files: List of files in the directory
        ctx: File listing context (modified in-place)
    """
    for file in files:
        # Check if we've reached the file limit
        if len(ctx.file_list) >= ctx.max_files:
            logger.debug(
                "Reached max_files limit (%d) at %s",
                ctx.max_files,
                root
            )
            ctx.truncated = True
            return

        # Construct relative path from workspace
        rel_path = os.path.relpath(os.path.join(root, file), ctx.workspace)

        # Apply pattern filter if specified
        if ctx.pattern and not fnmatch.fnmatch(rel_path, ctx.pattern):
            logger.debug("File %s does not match pattern %s", rel_path, ctx.pattern)
            continue

        # Add matching file to the list
        ctx.file_list.append(rel_path)
        logger.debug("Added file to list: %s", rel_path)


def _format_summary_result(dir_summary: dict[str, int]) -> str:
    """Format directory summary as a human-readable string.

    Args:
        dir_summary: Dictionary mapping directory paths to file counts

    Returns:
        Formatted summary string
    """
    if not dir_summary:
        logger.debug("No directories found for summary")
        return "No files found."

    # Build summary with sorted directory paths
    result = ["Directory Summary:"]
    for dir_path, count in sorted(dir_summary.items()):
        result.append(f"  {dir_path}: {count} files")

    logger.debug("Generated summary for %d directories", len(dir_summary))
    return "\n".join(result)


def _format_file_list_result(
        file_list: list[str], truncated: bool, max_files: int
) -> str:
    """Format file list as a human-readable string.

    Args:
        file_list: List of file paths
        truncated: Whether the list was truncated due to max_files limit
        max_files: Maximum number of files that were collected

    Returns:
        Formatted file list string with optional truncation notice
    """
    if not file_list:
        logger.debug("No files found to format")
        return "No files found."

    # Join file paths with newlines
    result = "\n".join(file_list)

    # Add truncation notice if applicable
    if truncated:
        logger.debug("File list truncated at %d files", max_files)
        result += (
            f"\n\n[TRUNCATED: Showing first {max_files} files. "
            f"Use max_files parameter to see more, or use summary=True for overview]"
        )
    else:
        logger.debug("Formatted %d files", len(file_list))

    return result


def _validate_directory_access(directory: str, workspace: str) -> str | None:
    """Validate that a directory is within the workspace.

    Prevents directory traversal attacks by ensuring the resolved path
    stays within the workspace boundaries.

    Args:
        directory: Relative directory path to validate
        workspace: Absolute workspace path

    Returns:
        Error message if access denied, None if access is valid
    """
    # Construct and resolve the target directory path
    target_dir = os.path.join(workspace, directory.lstrip("/"))
    target_dir_real = os.path.realpath(target_dir)
    workspace_real = os.path.realpath(workspace)

    # Verify the resolved path is within workspace
    if not target_dir_real.startswith(workspace_real):
        logger.warning(
            "Directory access denied: %s is outside workspace %s",
            target_dir_real,
            workspace_real,
        )
        return "Access denied"

    logger.debug("Directory access validated: %s", target_dir_real)
    return None


@tool
def read_file(filepath: str):
    """
    Reads the content of a file.
    """
    return read_file_in_workspace(filepath)


@tool
def list_files(
    directory: str = ".",
    max_files: int = 500,
    max_depth: int | None = None,
    summary: bool = False,
    pattern: str | None = None
):
    """
    Lists files in a directory (recursive).

    Args:
        directory: Directory to list (relative to workspace)
        max_files: Maximum number of files to return (default: 500)
        max_depth: Maximum depth to recurse (None = unlimited)
        summary: If True, return directory tree with counts instead of file list
        pattern: Optional glob pattern to filter files (e.g., "*.py", "src/**/*.java")
    """
    try:
        logger.info(
            "Listing files: directory=%s, max_files=%d, max_depth=%s, summary=%s, pattern=%s",
            directory,
            max_files,
            max_depth,
            summary,
            pattern
        )

        # Get workspace and validate directory access
        workspace = get_workspace()
        access_error = _validate_directory_access(directory, workspace)
        if access_error:
            return access_error

        # Prepare for directory traversal
        target_dir = os.path.join(workspace, directory.lstrip("/"))
        start_depth = os.path.realpath(target_dir).count(os.sep)
        dir_summary = {}
        ctx = _FileListingContext(
            workspace=workspace,
            max_files=max_files,
            pattern=pattern,
            file_list=[]
        )

        # Walk directory tree
        logger.debug("Starting directory walk from %s", target_dir)
        for root, dirs, files in os.walk(target_dir):
            # Check if directory should be skipped
            if _should_skip_directory(root, dirs, max_depth, start_depth):
                continue

            if summary:
                # Collect directory file counts for summary mode
                dir_summary[os.path.relpath(root, workspace)] = len(files)
            else:
                # Process files for listing mode
                _process_files_for_listing(root, files, ctx)
                if ctx.truncated:
                    logger.debug("File listing truncated at max_files=%d", max_files)
                    break

        # Format and return results
        if summary:
            logger.debug("Returning directory summary for %d directories", len(dir_summary))
            return _format_summary_result(dir_summary)

        logger.debug("Returning file list with %d files", len(ctx.file_list))
        return _format_file_list_result(ctx.file_list, ctx.truncated, max_files)

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Failed to list files in %s: %s", directory, str(e))
        logger.debug("List files error stacktrace:", exc_info=True)
        return str(e)



@tool
def write_to_file(filepath: str, content: str):
    """
    Writes content to a file.
    """
    return write_to_file_in_workspace(filepath, content)
