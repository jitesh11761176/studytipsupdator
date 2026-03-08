"""File management tools for the agent."""

from __future__ import annotations

import os
from typing import Any, Dict


def _read_file(file_path: str) -> str:
    """Read a file and return its content."""
    with open(file_path, "r", encoding="utf-8") as fh:
        return fh.read()


read_file_tool: Dict[str, Any] = {
    "name": "read_file",
    "description": "Read the contents of a local file",
    "parameters": {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Path to the file to read"},
        },
        "required": ["file_path"],
    },
    "execute": _read_file,
}


def _write_file(file_path: str, content: str, mode: str = "w") -> Dict[str, Any]:
    """Write content to a file."""
    os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
    with open(file_path, mode, encoding="utf-8") as fh:
        fh.write(content)
    return {"file_path": file_path, "bytes_written": len(content.encode("utf-8"))}


write_file_tool: Dict[str, Any] = {
    "name": "write_file",
    "description": "Write content to a local file (creates parent directories if needed)",
    "parameters": {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Path to the file to write"},
            "content": {"type": "string", "description": "Content to write to the file"},
            "mode": {"type": "string", "enum": ["w", "a"], "default": "w", "description": "'w' to overwrite, 'a' to append"},
        },
        "required": ["file_path", "content"],
    },
    "execute": _write_file,
}
