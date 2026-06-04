"""Field-config registry loader.

Loads all YAML files under `registry/`, validates each against
`registry/_schema.json`, and exposes lookup by id or by (field, review_type).
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

REGISTRY_DIR = Path(__file__).parent / "registry"
SCHEMA_PATH = REGISTRY_DIR / "_schema.json"


@dataclass(frozen=True)
class FieldConfig:
    id: str
    version: str
    field: str
    review_type: str
    label: str
    summary: str
    data: dict[str, Any]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FieldConfig:
        return cls(
            id=data["id"],
            version=data["version"],
            field=data["field"],
            review_type=data["review_type"],
            label=data["label"],
            summary=data["summary"],
            data=data,
        )


class FieldRegistry:
    """Process-wide registry. Thread-safe lazy load with explicit reload."""

    def __init__(self, registry_dir: Path = REGISTRY_DIR, schema_path: Path = SCHEMA_PATH):
        self._registry_dir = registry_dir
        self._schema_path = schema_path
        self._configs: dict[str, FieldConfig] = {}
        self._validator: Draft202012Validator | None = None
        self._lock = threading.Lock()
        self._loaded = False

    def _build_validator(self) -> Draft202012Validator:
        schema = json.loads(self._schema_path.read_text())
        return Draft202012Validator(schema)

    def load(self) -> None:
        """Load and validate all YAMLs. Raises on validation error."""
        with self._lock:
            self._validator = self._build_validator()
            configs: dict[str, FieldConfig] = {}
            for yaml_path in sorted(self._registry_dir.glob("*.yaml")):
                if yaml_path.name.startswith("_"):
                    continue
                with yaml_path.open() as f:
                    data = yaml.safe_load(f)
                errors = sorted(self._validator.iter_errors(data), key=lambda e: e.path)
                if errors:
                    msgs = [f"  - {list(e.path)}: {e.message}" for e in errors]
                    raise ValueError(
                        f"Invalid field config in {yaml_path.name}:\n" + "\n".join(msgs)
                    )
                cfg = FieldConfig.from_dict(data)
                if cfg.id in configs:
                    raise ValueError(f"Duplicate field config id: {cfg.id}")
                configs[cfg.id] = cfg
            self._configs = configs
            self._loaded = True

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    def all(self) -> list[FieldConfig]:
        self._ensure_loaded()
        return list(self._configs.values())

    def by_id(self, config_id: str) -> FieldConfig | None:
        self._ensure_loaded()
        return self._configs.get(config_id)

    def by_field_and_type(self, field: str, review_type: str) -> FieldConfig | None:
        return self.by_id(f"{field}__{review_type}")

    def list_fields(self) -> list[str]:
        """Unique field clusters."""
        self._ensure_loaded()
        return sorted({c.field for c in self._configs.values()})

    def review_types_for(self, field: str) -> list[str]:
        self._ensure_loaded()
        return sorted(c.review_type for c in self._configs.values() if c.field == field)


field_registry = FieldRegistry()
