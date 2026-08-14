"""RPC handler exposing per-phase gate state for the sidebar lock UI."""

from __future__ import annotations

import uuid

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from prismapi.domain.phases import PHASE_ORDER, gate_satisfied
from prismapi.rpc.dispatcher import rpc
from prismapi.services.phase_completion import gate_state


class StateIn(BaseModel):
    project_id: uuid.UUID


@rpc("phases.state")
async def state(params: StateIn, session: AsyncSession) -> list[dict]:
    snap = await gate_state(session, params.project_id)
    result: list[dict] = []
    for phase in PHASE_ORDER:
        ok, reason = gate_satisfied(phase, snap)
        result.append({"phase": phase.value, "open": ok, "reason": reason})
    return result
