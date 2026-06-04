from __future__ import annotations

from pydantic import BaseModel, Field


class ExtractionIn(BaseModel):
    cluster_id: str
    payload: dict
    status: str = Field(default="draft", pattern=r"^(draft|submitted)$")
    notes: str | None = None


class ExtractionOut(BaseModel):
    id: str
    cluster_id: str
    reviewer_id: str
    template_base: str
    payload: dict
    status: str
    notes: str | None


class RoBJudgement(BaseModel):
    judgement: str
    justification: str | None = None


class RoBIn(BaseModel):
    cluster_id: str
    judgements: dict[str, RoBJudgement]
    overall: str | None = None
    notes: str | None = None


class RoBOut(BaseModel):
    id: str
    cluster_id: str
    reviewer_id: str
    tool: str
    judgements: dict
    overall: str | None
    notes: str | None


class TemplateField(BaseModel):
    key: str
    label: str
    type: str
    options: list[str] | None = None
    group: str | None = None
    required: bool = False
    help: str | None = None


class ExtractionTemplate(BaseModel):
    base: str
    fields: list[TemplateField]


class RoBToolSpec(BaseModel):
    tool: str
    label: str
    domains: list[dict]
    scale: list[str]
    warning: str | None = None
