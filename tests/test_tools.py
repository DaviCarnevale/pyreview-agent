"""Automated tests for CodeInspector tools and safety constraints."""
from __future__ import annotations

import os
from pathlib import Path
import pytest

from agent.tools import CodeInspector, SecurityError


@pytest.fixture
def sample_project(tmp_path: Path) -> Path:
    """Create a temporary mock Python project structure for testing."""
    # Standard source files
    (tmp_path / "main.py").write_text("print('hello world')\n", encoding="utf-8")
    
    pkg_dir = tmp_path / "mypkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("# init\n", encoding="utf-8")
    (pkg_dir / "service.py").write_text(
        "def compute(x: int) -> int:\n    return x * 2\n", encoding="utf-8"
    )

    # Ignored directories
    venv_dir = tmp_path / ".venv" / "lib"
    venv_dir.mkdir(parents=True)
    (venv_dir / "hidden.py").write_text("# ignored venv\n", encoding="utf-8")

    git_dir = tmp_path / ".git" / "hooks"
    git_dir.mkdir(parents=True)
    (git_dir / "hook.py").write_text("# ignored git\n", encoding="utf-8")

    pycache_dir = tmp_path / "__pycache__"
    pycache_dir.mkdir()
    (pycache_dir / "cache.py").write_text("# ignored cache\n", encoding="utf-8")

    # Non-python files
    (tmp_path / "notes.txt").write_text("Some notes\n", encoding="utf-8")
    (tmp_path / "config.json").write_text('{"key": "val"}\n', encoding="utf-8")

    return tmp_path


def test_inspector_initialization_invalid_path():
    """Inspector should fail if directory doesn't exist or is a file."""
    with pytest.raises(FileNotFoundError):
        CodeInspector(base_dir="/non/existent/path/12345")

    with pytest.raises(NotADirectoryError):
        # Pass a file instead of directory
        this_file = Path(__file__).resolve()
        CodeInspector(base_dir=this_file)


def test_list_python_files_excludes_ignored_directories(sample_project: Path):
    """Ensure .git, .venv, and __pycache__ are strictly ignored."""
    inspector = CodeInspector(base_dir=sample_project)
    result = inspector.list_python_files()

    assert result["success"] is True
    files = result["files"]
    assert "main.py" in files
    assert "mypkg/__init__.py" in files
    assert "mypkg/service.py" in files

    # Verify exclusions
    for f in files:
        assert ".venv" not in f
        assert ".git" not in f
        assert "__pycache__" not in f
        assert f.endswith(".py")

    assert result["total_files"] == 3


def test_read_python_file_success(sample_project: Path):
    """Test reading an authorized Python file."""
    inspector = CodeInspector(base_dir=sample_project)
    result = inspector.read_python_file("mypkg/service.py")

    assert result["success"] is True
    assert "def compute(x: int) -> int:" in result["content"]
    assert result["total_lines_read"] == 2
    assert result["is_truncated"] is False


def test_read_python_file_non_existent(sample_project: Path):
    """Test reading a file that does not exist."""
    inspector = CodeInspector(base_dir=sample_project)
    result = inspector.read_python_file("ghost.py")

    assert "error" in result
    assert "does not exist" in result["error"]
    assert result["content"] is None


def test_read_non_python_file_rejected(sample_project: Path):
    """Test reading non-.py files is rejected for security/scope."""
    inspector = CodeInspector(base_dir=sample_project)
    result = inspector.read_python_file("notes.txt")

    assert "error" in result
    assert "Unauthorized file extension" in result["error"]


def test_path_traversal_prevention(sample_project: Path, tmp_path: Path):
    """Ensure path traversal attacks with ../ or absolute paths are blocked."""
    inspector = CodeInspector(base_dir=sample_project)

    # Attempt ../ escape
    result = inspector.read_python_file("../outside.py")
    assert "error" in result
    assert "escapes the authorized directory" in result["error"]

    # Attempt nested ../ escape
    result_nested = inspector.read_python_file("mypkg/../../outside.py")
    assert "error" in result_nested
    assert "escapes the authorized directory" in result_nested["error"]

    # Attempt listing with ../ escape
    result_list = inspector.list_python_files("../")
    assert "error" in result_list
    assert "escapes the authorized directory" in result_list["error"]


def test_symlink_escape_prevention(sample_project: Path, tmp_path_factory):
    """Ensure symlinks pointing outside the project root are rejected."""
    outside_dir = tmp_path_factory.mktemp("outside")
    secret_file = outside_dir / "secret.py"
    secret_file.write_text("SECRET_KEY = 'supersecret'\n", encoding="utf-8")

    # Create symlink inside sample_project pointing to secret_file outside
    symlink_path = sample_project / "evil_symlink.py"
    try:
        symlink_path.symlink_to(secret_file)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks not supported on this platform/filesystem.")

    inspector = CodeInspector(base_dir=sample_project)
    result = inspector.read_python_file("evil_symlink.py")

    assert "error" in result
    assert "escapes the authorized directory" in result["error"]
    assert result["content"] is None


def test_line_truncation(sample_project: Path):
    """Ensure max_lines limits the number of read lines and sets is_truncated."""
    long_file = sample_project / "long.py"
    long_file.write_text("\n".join(f"line_{i} = {i}" for i in range(100)), encoding="utf-8")

    inspector = CodeInspector(base_dir=sample_project, max_file_lines=20)
    result = inspector.read_python_file("long.py", max_lines=20)

    assert result["success"] is True
    assert result["total_lines_read"] == 20
    assert result["is_truncated"] is True


def test_max_file_bytes_limit(sample_project: Path):
    """Ensure files exceeding max_file_bytes are rejected."""
    big_file = sample_project / "big.py"
    big_file.write_text("x = 1\n" * 500, encoding="utf-8")

    inspector = CodeInspector(base_dir=sample_project, max_file_bytes=50)
    result = inspector.read_python_file("big.py")

    assert "error" in result
    assert "exceeds maximum allowed size" in result["error"]
    assert result["content"] is None


def test_execute_tool_dispatcher(sample_project: Path):
    """Test the JSON tool dispatcher."""
    inspector = CodeInspector(base_dir=sample_project)

    # Test list_python_files dispatcher
    out_list = inspector.execute_tool("list_python_files", {"relative_subdir": "."})
    assert '"success": true' in out_list
    assert '"main.py"' in out_list

    # Test read_python_file dispatcher
    out_read = inspector.execute_tool("read_python_file", {"file_path": "main.py"})
    assert '"success": true' in out_read
    assert "hello world" in out_read

    # Test unknown tool
    out_unknown = inspector.execute_tool("unknown_tool", {})
    assert "Unknown tool" in out_unknown
