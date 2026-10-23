"""File inspection tools with strict path validation and sandboxing for PyReview Agent."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Set


# Standard directories to ignore during project discovery
IGNORED_DIR_NAMES: Set[str] = {
    ".git",
    ".venv",
    "venv",
    "env",
    "ENV",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    "build",
    "dist",
    "node_modules",
    ".idea",
    ".vscode",
    "eggs",
    ".eggs",
    "*.egg-info",
}


class SecurityError(Exception):
    """Raised when an operation attempts to breach directory boundaries."""


class CodeInspector:
    """Provides sandboxed file inspection tools restricted to an authorized project directory."""

    def __init__(
        self,
        base_dir: str | Path,
        max_file_lines: int = 800,
        max_file_bytes: int = 200_000,
    ) -> None:
        """Initialize the CodeInspector with an authorized base directory.

        Args:
            base_dir: Root directory of the project to inspect.
            max_file_lines: Maximum lines to read from a single file.
            max_file_bytes: Maximum size in bytes allowed for reading.
        """
        raw_path = Path(base_dir)
        if not raw_path.exists():
            raise FileNotFoundError(f"Project directory does not exist: {base_dir}")
        if not raw_path.is_dir():
            raise NotADirectoryError(f"Provided path is not a directory: {base_dir}")

        # Resolve canonical absolute path to prevent symlink traversal
        self.base_dir: Path = raw_path.resolve()
        self.max_file_lines = max_file_lines
        self.max_file_bytes = max_file_bytes

    def _resolve_safe_path(self, relative_path: str | Path) -> Path:
        """Validate and resolve a path to ensure it remains strictly within base_dir.

        Args:
            relative_path: The user or agent provided path.

        Returns:
            Resolved safe Path instance.

        Raises:
            SecurityError: If the path attempts to escape the authorized directory.
        """
        clean_rel = str(relative_path).strip()
        # Combine base dir with relative path and resolve canonical location
        target = (self.base_dir / clean_rel).resolve()

        # Check if the target is within the base_dir boundary
        try:
            target.relative_to(self.base_dir)
        except ValueError as err:
            raise SecurityError(
                f"Access denied: path '{clean_rel}' escapes the authorized directory."
            ) from err

        return target

    def list_python_files(self, relative_subdir: str = ".") -> Dict[str, Any]:
        """List all Python (.py) files within an authorized directory, excluding ignored folders.

        Args:
            relative_subdir: Subdirectory relative to project root (default: ".").

        Returns:
            Dictionary containing list of relative file paths and metadata.
        """
        try:
            target_dir = self._resolve_safe_path(relative_subdir)
        except SecurityError as e:
            return {"error": str(e), "files": [], "total_files": 0}

        if not target_dir.exists():
            return {
                "error": f"Directory not found: '{relative_subdir}'",
                "files": [],
                "total_files": 0,
            }

        if not target_dir.is_dir():
            return {
                "error": f"Path is not a directory: '{relative_subdir}'",
                "files": [],
                "total_files": 0,
            }

        found_files: List[str] = []

        try:
            for item in sorted(target_dir.rglob("*.py")):
                # Check if any parent component is in ignored directories
                rel_to_base = item.relative_to(self.base_dir)
                parts = rel_to_base.parts

                # Skip files inside ignored directories
                if any(part in IGNORED_DIR_NAMES or part.endswith(".egg-info") for part in parts[:-1]):
                    continue

                if item.is_file():
                    found_files.append(rel_to_base.as_posix())

            return {
                "success": True,
                "base_directory": self.base_dir.as_posix(),
                "relative_subdir": relative_subdir,
                "total_files": len(found_files),
                "files": found_files,
            }
        except Exception as exc:
            return {"error": f"Failed to list files: {str(exc)}", "files": [], "total_files": 0}

    def read_python_file(self, file_path: str, max_lines: int | None = None) -> Dict[str, Any]:
        """Safely read the content of an authorized Python file with size limits.

        Args:
            file_path: Relative path to the file from the authorized project root.
            max_lines: Optional override for line reading limits.

        Returns:
            Dictionary containing file content, line counts, and status flags.
        """
        try:
            target_path = self._resolve_safe_path(file_path)
        except SecurityError as e:
            return {"error": str(e), "content": None}

        if not target_path.exists():
            return {
                "error": f"File does not exist: '{file_path}'",
                "content": None,
            }

        if not target_path.is_file():
            return {
                "error": f"Path is not a file: '{file_path}'",
                "content": None,
            }

        if target_path.suffix.lower() != ".py":
            return {
                "error": f"Unauthorized file extension '{target_path.suffix}'. Only .py files can be inspected.",
                "content": None,
            }

        # Check file size before reading to avoid memory exhaustion
        file_size = target_path.stat().st_size
        if file_size > self.max_file_bytes:
            return {
                "error": (
                    f"File exceeds maximum allowed size ({file_size} bytes > {self.max_file_bytes} bytes). "
                    "File was skipped for security and token limit reasons."
                ),
                "content": None,
            }

        limit_lines = max_lines if max_lines is not None else self.max_file_lines

        try:
            with target_path.open("r", encoding="utf-8", errors="replace") as f:
                lines = []
                is_truncated = False
                for idx, line in enumerate(f, start=1):
                    if idx > limit_lines:
                        is_truncated = True
                        break
                    lines.append(line)

            content = "".join(lines)
            return {
                "success": True,
                "file_path": target_path.relative_to(self.base_dir).as_posix(),
                "total_lines_read": len(lines),
                "is_truncated": is_truncated,
                "content": content,
            }
        except Exception as exc:
            return {
                "error": f"Error reading file '{file_path}': {str(exc)}",
                "content": None,
            }

    def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Dispatcher that executes an inspection tool by name and returns JSON string.

        Args:
            tool_name: Function name requested by the model.
            arguments: Parsed JSON arguments for the tool.

        Returns:
            JSON-serialized string of the execution result.
        """
        if tool_name == "list_python_files":
            subdir = arguments.get("relative_subdir", ".")
            result = self.list_python_files(relative_subdir=subdir)
            return json.dumps(result, ensure_ascii=False)

        elif tool_name == "read_python_file":
            file_path = arguments.get("file_path", "")
            max_lines = arguments.get("max_lines", None)
            result = self.read_python_file(file_path=file_path, max_lines=max_lines)
            return json.dumps(result, ensure_ascii=False)

        return json.dumps({"error": f"Unknown tool: '{tool_name}'"})


# OpenAI function calling definitions
OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_python_files",
            "description": (
                "List Python (.py) source files in the project. "
                "Excludes build artifacts, virtual environments (.venv), and hidden cache directories."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "relative_subdir": {
                        "type": "string",
                        "description": "Subdirectory relative to the authorized project root. Default is '.'.",
                        "default": ".",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_python_file",
            "description": (
                "Read the source code of a specified Python file within the authorized project directory. "
                "Returns the code along with line counts."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Relative path to the Python file from the project root.",
                    },
                    "max_lines": {
                        "type": "integer",
                        "description": "Maximum lines of code to read (optional).",
                    },
                },
                "required": ["file_path"],
            },
        },
    },
]
