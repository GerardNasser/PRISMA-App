"""State-file RPC: export, preview_import, merge."""

from __future__ import annotations

import uuid
from pathlib import Path

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prismapi.db.models import Project, ProjectMember
from prismapi.rpc.dispatcher import rpc
from prismapi.rpc.errors import NOT_FOUND, VALIDATION, RpcError
from prismapi.services.snapshot import take_snapshot
from prismapi.statefile import (
    apply_merge,
    export_project,
    preview_import,
)


async def _assert_member(
    session: AsyncSession, project_id: uuid.UUID, identity_id: uuid.UUID
) -> Project:
    project = await session.get(Project, project_id)
    if project is None:
        raise RpcError(NOT_FOUND, "Project not found")
    if project.owner_identity_id == identity_id:
        return project
    member = await session.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.identity_id == identity_id,
        )
    )
    if member is None:
        raise RpcError(NOT_FOUND, "Project not found")
    return project


class StateExport(BaseModel):
    project_id: str
    output_path: str = Field(min_length=1)


@rpc("statefile.export")
async def export(
    params: StateExport, session: AsyncSession, identity_id: uuid.UUID
) -> dict:
    project = await _assert_member(session, uuid.UUID(params.project_id), identity_id)
    out = Path(params.output_path).expanduser()
    manifest = await export_project(session, project=project, output_path=out)
    return {
        "path": str(out),
        "manifest": manifest.model_dump(mode="json"),
    }


class StatePreview(BaseModel):
    input_path: str = Field(min_length=1)


@rpc("statefile.preview_import")
async def preview(params: StatePreview, session: AsyncSession) -> dict:
    path = Path(params.input_path).expanduser()
    if not path.exists():
        raise RpcError(VALIDATION, f"No such file: {path}")
    manifest, diff = await preview_import(session, path=path)
    return {
        "manifest": manifest.model_dump(mode="json"),
        "diff": diff.to_json(),
    }


class StateMerge(BaseModel):
    input_path: str
    resolutions: dict[str, str] = Field(default_factory=dict)
    take_pre_import_snapshot: bool = True


@rpc("statefile.merge")
async def merge(
    params: StateMerge, session: AsyncSession, identity_id: uuid.UUID
) -> dict:
    path = Path(params.input_path).expanduser()
    if not path.exists():
        raise RpcError(VALIDATION, f"No such file: {path}")
    manifest, diff = await preview_import(session, path=path)

    if params.take_pre_import_snapshot and diff.project_present_locally:
        project = await session.get(Project, uuid.UUID(manifest.project_id))
        if project is not None:
            await take_snapshot(
                session,
                project=project,
                kind="pre_import",
                label=f"Before importing {Path(params.input_path).name}",
                actor_identity_id=identity_id,
            )

    # Re-read the bundle for the merger.
    import json
    import zipfile

    with zipfile.ZipFile(path, "r") as zf:

        def _jsonl(name: str) -> list:
            try:
                return [
                    json.loads(line)
                    for line in zf.read(name).decode("utf-8").splitlines()
                    if line.strip()
                ]
            except KeyError:
                return []

        incoming = {
            "project": json.loads(zf.read("project.json")),
            "protocols": _jsonl("protocols.jsonl"),
            "pico_elements": _jsonl("pico_elements.jsonl"),
            "codebooks": _jsonl("codebooks.jsonl"),
            "codebook_rules": _jsonl("codebook_rules.jsonl"),
            "searches": _jsonl("searches.jsonl"),
            "records": _jsonl("records.jsonl"),
            "clusters": _jsonl("clusters.jsonl"),
            "cluster_members": _jsonl("cluster_members.jsonl"),
            "screenings": _jsonl("screenings.jsonl"),
            "conflict_resolutions": _jsonl("conflict_resolutions.jsonl"),
            "extractions": _jsonl("extractions.jsonl"),
            "rob": _jsonl("rob.jsonl"),
            "audit": _jsonl("audit.jsonl"),
            "judgments": _jsonl("judgments.jsonl"),
            "identities": _jsonl("identities.jsonl"),
        }

    try:
        summary = await apply_merge(
            session,
            manifest=manifest,
            preview=diff,
            incoming=incoming,
            resolutions=params.resolutions,
            actor_identity_id=identity_id,
        )
    except ValueError as exc:
        raise RpcError(VALIDATION, str(exc)) from exc

    return {
        "manifest": manifest.model_dump(mode="json"),
        "summary": summary,
    }
