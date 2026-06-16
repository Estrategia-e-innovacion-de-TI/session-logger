"""Normalize Jupyter notebooks for code-only comparison."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def normalize_notebook(path_or_json: str | Path | dict[str, Any], include_outputs: bool = False) -> list[str]:
    """Return comparable code lines from a notebook.

    Markdown cells, volatile metadata, execution counts, and outputs are ignored
    by default. Outputs are included only when explicitly requested.
    """

    notebook = _load_notebook(path_or_json)
    lines: list[str] = []
    for index, cell in enumerate(notebook.get("cells", []), start=1):
        if cell.get("cell_type") != "code":
            continue
        source_lines = _source_to_lines(cell.get("source", []))
        if not source_lines:
            continue
        if lines:
            lines.append("")
        lines.append(f"# cell {index}")
        lines.extend(line.rstrip() for line in source_lines)
        if include_outputs:
            for output in cell.get("outputs", []):
                lines.extend(_output_to_lines(output))
    return lines


def normalize_notebook_text(path_or_json: str | Path | dict[str, Any], include_outputs: bool = False) -> str:
    return "\n".join(normalize_notebook(path_or_json, include_outputs=include_outputs))


def _load_notebook(path_or_json: str | Path | dict[str, Any]) -> dict[str, Any]:
    if isinstance(path_or_json, dict):
        return path_or_json
    path = Path(path_or_json)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    if isinstance(path_or_json, str):
        return json.loads(path_or_json)
    raise FileNotFoundError(f"Notebook not found: {path}")


def _source_to_lines(source: str | list[str]) -> list[str]:
    if isinstance(source, str):
        return source.splitlines()
    lines: list[str] = []
    for item in source:
        lines.extend(str(item).splitlines())
    return lines


def _output_to_lines(output: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for key in ("text", "data"):
        value = output.get(key)
        if isinstance(value, str):
            lines.extend(value.splitlines())
        elif isinstance(value, list):
            lines.extend(str(item).rstrip("\n") for item in value)
        elif isinstance(value, dict):
            for nested in value.values():
                if isinstance(nested, str):
                    lines.extend(nested.splitlines())
                elif isinstance(nested, list):
                    lines.extend(str(item).rstrip("\n") for item in nested)
    return lines
