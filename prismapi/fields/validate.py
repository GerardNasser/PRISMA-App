"""CLI: validate every field config against the schema. Used by CI."""

from __future__ import annotations

import sys

from prismapi.fields.loader import field_registry


def main() -> int:
    try:
        field_registry.load()
    except ValueError as exc:
        print(f"FIELD CONFIG VALIDATION FAILED:\n{exc}", file=sys.stderr)
        return 1
    configs = field_registry.all()
    print(f"OK: {len(configs)} field config(s) validated.")
    for c in configs:
        print(f"  - {c.id} (v{c.version})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
