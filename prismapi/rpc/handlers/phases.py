"""RPC handler exposing per-phase gate state for the sidebar lock UI."""

from __future__ import annotations

import uuid

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from prismapi.db.models import (
    Project,
    ProjectMember,
    Protocol,
    Record,
    RecordCluster,
)
from prismapi.domain.phases import PHASE_ORDER, GateState, gate_satisfied
from prismapi.rpc.dispatcher import rpc


class StateIn(BaseModel):
    project_id: uuid.UUID


async def _snapshot(session: AsyncSession, project_id: uuid.UUID) -> GateState:
    project_exists = await session.scalar(
        select(func.count(Project.id)).where(Project.id == project_id)
    )
    n_raters = await session.scalar(
        select(func.count(ProjectMember.id)).where(ProjectMember.project_id == project_id)
    )
    has_protocol = (await session.scalar(
        select(func.count(Protocol.id)).where(Protocol.project_id == project_id)
    )) > 0
    n_records = await session.scalar(
        select(func.count(Record.id)).where(Record.project_id == project_id)
    )
    n_clusters = await session.scalar(
        select(func.count(RecordCluster.id)).where(RecordCluster.project_id == project_id)
    )
    return GateState(
        project_exists=bool(project_exists),
        n_raters=n_raters or 0,
        has_protocol=has_protocol,
        n_records=n_records or 0,
        n_clusters=n_clusters or 0,
        n_ta_done_raters=0,
        n_ft_done_raters=0,
        has_extraction=False,
        has_rob=False,
        has_synthesis=False,
    )


@rpc("phases.state")
async def state(params: StateIn, session: AsyncSession) -> list[dict]:
    snap = await _snapshot(session, params.project_id)
    result: list[dict] = []
    for phase in PHASE_ORDER:
        ok, reason = gate_satisfied(phase, snap)
        result.append({"phase": phase.value, "open": ok, "reason": reason})
    return result
