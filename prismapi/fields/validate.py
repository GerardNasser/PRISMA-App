"""CLI: validate every field config against the schema. Used by CI.

Beyond the JSON Schema, this cross-checks what the schema alone cannot:
every RoB tool a config names must actually be implemented (the schema's
tool enum is wider than BUILTIN_ROB_TOOLS, and a config naming an
unimplemented tool crashes at runtime while schema validation stays green),
and tool_by_choice maps must key off real branch-choice option values.
"""

from __future__ import annotations

import sys

from prismapi.fields.loader import FieldConfig, field_registry


def check_rob_tools(configs: list[FieldConfig]) -> list[str]:
    """Return the runtime-crash and dead-mapping errors schema misses."""
    from prismapi.services.extraction import BUILTIN_ROB_TOOLS

    errors: list[str] = []
    for c in configs:
        rob = c.data["risk_of_bias"]
        tools = {rob["tool"]}
        by_choice = rob.get("tool_by_choice") or {}
        tools |= set(by_choice.get("map", {}).values())
        for tool in sorted(tools):
            if tool == "CUSTOM":
                if not rob.get("domains"):
                    errors.append(f"{c.id}: tool CUSTOM requires domains")
            elif tool not in BUILTIN_ROB_TOOLS:
                errors.append(
                    f"{c.id}: tool {tool} has no builtin spec — rob.tool would crash"
                )
        if by_choice:
            options: set[str] = set()
            for bc in c.data.get("branch_choices", []):
                if bc["key"] == by_choice["choice_key"]:
                    options = {o["value"] for o in bc["options"]}
            unknown = set(by_choice.get("map", {})) - options
            if unknown:
                errors.append(
                    f"{c.id}: tool_by_choice keys {sorted(unknown)} are not values "
                    f"of branch choice '{by_choice['choice_key']}'"
                )
    return errors


def main() -> int:
    try:
        field_registry.load()
    except ValueError as exc:
        print(f"FIELD CONFIG VALIDATION FAILED:\n{exc}", file=sys.stderr)
        return 1
    configs = field_registry.all()
    errors = check_rob_tools(configs)
    if errors:
        print("FIELD CONFIG VALIDATION FAILED:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print(f"OK: {len(configs)} field config(s) validated.")
    for c in configs:
        print(f"  - {c.id} (v{c.version})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
