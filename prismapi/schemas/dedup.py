from __future__ import annotations

from pydantic import BaseModel


class DedupSummary(BaseModel):
    input: int
    output: int
    duplicates_removed: int
    reduction_pct: float
    by_method: dict[str, int]


class ClusterMember(BaseModel):
    record_id: str
    method: str
    score: float
    title: str


class ClusterOut(BaseModel):
    id: str
    canonical_record_id: str
    size: int
    method: str
    confidence: float
    members: list[ClusterMember]


class ManualMergeIn(BaseModel):
    cluster_ids: list[str]
    canonical_cluster_id: str | None = None
    notes: str | None = None
