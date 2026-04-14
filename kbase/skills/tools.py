"""Skill Tool framework — typed, validated, permission-gated tools.

Each tool is a rich contract (inspired by Claude Code's harness engineering):
  schema validation → validate_input → call → result budget
"""
import json
from typing import Any, Optional
from pathlib import Path


class SkillTool:
    """Base class for all skill tools."""

    name: str = ""
    description: str = ""
    input_schema: dict = {}
    is_read_only: bool = False
    max_result_chars: int = 8000

    def validate_input(self, params: dict) -> dict:
        """Validate and normalize input. Override in subclass."""
        return params

    def call(self, params: dict) -> str:
        """Execute the tool. Override in subclass."""
        raise NotImplementedError

    def execute(self, params: dict) -> str:
        """Full pipeline: validate → call → truncate."""
        params = self.validate_input(params)
        result = self.call(params)
        if len(result) > self.max_result_chars:
            result = result[:self.max_result_chars] + f"\n... (truncated, {len(result)} chars total)"
        return result

    def to_schema(self) -> dict:
        """Export as LLM tool schema."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.input_schema,
        }


# ── Tool Registry ──────────────────────────────────────────────

_registry: dict[str, SkillTool] = {}


def register_tool(tool: SkillTool):
    _registry[tool.name] = tool
    return tool


def get_tool(name: str) -> Optional[SkillTool]:
    return _registry.get(name)


def get_all_tools() -> list[SkillTool]:
    return list(_registry.values())


def get_tool_schemas(names: list[str] = None) -> list[dict]:
    """Get schemas for specified tools (or all if names=None)."""
    tools = [_registry[n] for n in names if n in _registry] if names else get_all_tools()
    return [t.to_schema() for t in tools]
