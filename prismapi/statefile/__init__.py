"""`.prismaproj` state files — the collaboration primitive.

Each `.prismaproj` is a zip bundle containing one project's full state:
manifest + per-table JSONL + content-addressed asset blobs. Exporters write
them; importers read them; mergers reconcile two installs.

See `docs/learning/the-statefile-format.md` for the wire-format walkthrough
and `docs/architecture/state-files.md` for the row-level merge semantics.
"""

from prismapi.statefile.diff import (
    Conflict,
    DiffPreview,
    compute_diff,
)
from prismapi.statefile.exporter import export_project
from prismapi.statefile.importer import preview_import, validate_manifest
from prismapi.statefile.merger import apply_merge
from prismapi.statefile.schema import (
    SCHEMA_VERSION,
    Manifest,
    UnsupportedSchemaError,
)

__all__ = [
    "Conflict",
    "DiffPreview",
    "Manifest",
    "SCHEMA_VERSION",
    "UnsupportedSchemaError",
    "apply_merge",
    "compute_diff",
    "export_project",
    "preview_import",
    "validate_manifest",
]
