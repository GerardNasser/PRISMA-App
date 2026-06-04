from __future__ import annotations

from pydantic import BaseModel, Field


class DecisionIn(BaseModel):
    cluster_id: str
    stage: str = Field(pattern=r"^(title_abstract|full_text)$")
    decision: str = Field(pattern=r"^(include|exclude|maybe)$")
    exclusion_code: str | None = None
    notes: str | None = None
    confidence: int = Field(default=3, ge=1, le=5)


class DecisionOut(BaseModel):
    id: str
    cluster_id: str
    reviewer_id: str
    stage: str
    decision: str
    exclusion_code: str | None
    notes: str | None
    confidence: int


class ConflictResolutionIn(BaseModel):
    cluster_id: str
    stage: str = Field(pattern=r"^(title_abstract|full_text)$")
    final_decision: str = Field(pattern=r"^(include|exclude)$")
    rationale: str = Field(min_length=1)


class ConflictResolutionOut(BaseModel):
    id: str
    cluster_id: str
    stage: str
    final_decision: str
    rationale: str


class IRRReport(BaseModel):
    stage: str
    n_items: int
    n_reviewers: int
    alpha_binary: float | None
    fleiss_kappa: float | None
    cohens_kappa: float | None
    percent_agreement: float | None
    interpretation: str | None
    conflicts: list[str]
