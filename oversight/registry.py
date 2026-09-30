"""Derives an Action's risk metadata from the tool name and its params.

In a real deployment the agent only proposes (tool, params, description); nobody
hands us honest risk labels. The registry supplies defaults per tool and
param-inspecting rules that can only ever raise risk.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .policy import DIMENSIONS, Policy, PolicyError
from .schema import Action


@dataclass(frozen=True)
class Rule:
    name: str
    tools: tuple[str, ...] | None
    param_regex: dict[str, re.Pattern[str]]
    any_param_regex: re.Pattern[str] | None
    param_gte: dict[str, float]
    set: dict[str, str]

    def matches(self, tool: str, params: dict[str, Any]) -> bool:
        if self.tools is not None and tool not in self.tools:
            return False
        for k, rx in self.param_regex.items():
            if k not in params or not rx.search(str(params[k])):
                return False
        if self.any_param_regex and not self.any_param_regex.search(json.dumps(params, sort_keys=True)):
            return False
        for k, v in self.param_gte.items():
            x = params.get(k)
            if not isinstance(x, (int, float)) or x < v:
                return False
        return True


class ToolRegistry:
    def __init__(self, policy: Policy, tools: dict[str, dict[str, str]], unknown: dict[str, str], rules: list[Rule]):
        self.policy = policy
        self.tools = tools
        self.unknown = unknown
        self.rules = rules
        for name, meta in [*tools.items(), ("unknown_tool", unknown)]:
            self._validate(name, meta, full=True)
        for r in rules:
            self._validate(r.name, r.set, full=False)

    def _validate(self, name: str, meta: dict[str, str], full: bool) -> None:
        if full and set(meta) != set(DIMENSIONS):
            raise PolicyError(f"{name}: needs exactly {DIMENSIONS}")
        for k, v in meta.items():
            if k not in DIMENSIONS:
                raise PolicyError(f"{name}: unknown dimension {k}")
            self.policy.weight(k, v)

    @classmethod
    def load(cls, path: str | Path, policy: Policy) -> ToolRegistry:
        raw = yaml.safe_load(Path(path).read_text())
        rules = []
        for r in raw.get("rules") or []:
            tool = r.get("tool")
            rules.append(
                Rule(
                    name=r["name"],
                    tools=None if tool is None else tuple([tool] if isinstance(tool, str) else tool),
                    param_regex={k: re.compile(v) for k, v in (r.get("param_regex") or {}).items()},
                    any_param_regex=re.compile(r["any_param_regex"]) if r.get("any_param_regex") else None,
                    param_gte=dict(r.get("param_gte") or {}),
                    set=dict(r["set"]),
                )
            )
        return cls(policy, raw["tools"], raw["unknown_tool"], rules)

    def to_action(self, id: str, tool: str, params: dict[str, Any], description: str) -> Action:
        known = tool in self.tools
        meta = dict(self.tools[tool] if known else self.unknown)
        notes = [] if known else [f"unknown tool {tool!r}: conservative defaults"]
        for rule in self.rules:
            if not rule.matches(tool, params):
                continue
            raised = []
            for dim, value in rule.set.items():
                if self.policy.weight(dim, value) > self.policy.weight(dim, meta[dim]):
                    meta[dim] = value
                    raised.append(f"{dim}={value}")
            if raised:
                notes.append(f"rule {rule.name}: {', '.join(raised)}")
        return Action(id=id, tool=tool, description=description, params=params, notes=tuple(notes), **meta)
