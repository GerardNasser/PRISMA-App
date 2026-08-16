"""Manifest schema for `.prismaproj` files.

The manifest is the first file inside the zip and bears:
- the schema version (refuse-import on major mismatch),
- the project UUID + label,
- the exporting reviewer's identity,
- a SHA-256 hash for every other file (so a half-downloaded zip fails fast).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

SCHEMA_VERSION = 1


class UnsupportedSchemaError(RuntimeError):
    """Raised when a `.prismaproj` declares a schema_version we can't read."""


class IdentityRef(BaseModel):
    id: str
    last_name: str
    orcid: str | None = None
    email: str | None = None
    display_name: str


class FileChecksum(BaseModel):
    relative_path: str
    sha256: str
    size_bytes: int


class ManifestCounts(BaseModel):
    """Quick-summary counts; the importer cross-checks against actual rows."""

    protocols: int = 0
    codebooks: int = 0
    records: int = 0
    clusters: int = 0
    searches: int = 0
    screenings: int = 0
    extractions: int = 0
    rob: int = 0
    audit: int = 0
    judgments: int = 0
    identities: int = 0
    members: int = 0
    assets: int = 0


class Manifest(BaseModel):
    schema_version: int = SCHEMA_VERSION
    prismapi_version: str
    project_id: str
    project_name: str
    project_field_config_id: str
    project_field_config_version: str
    exporter: IdentityRef
    exported_at: datetime
    parent_state_sha256: str | None = None
    counts: ManifestCounts = Field(default_factory=ManifestCounts)
    files: list[FileChecksum] = Field(default_factory=list)
