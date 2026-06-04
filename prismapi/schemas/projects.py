from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    slug: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$")
    description: str | None = None
    field_config_id: str = Field(min_length=1)
    branch_choices: dict = Field(default_factory=dict)


class ProjectOut(BaseModel):
    id: str
    name: str
    slug: str
    description: str | None
    field_config_id: str
    field_config_version: str
    branch_choices: dict
    owner_id: str
    created_at: datetime
    updated_at: datetime


class ProtocolPICO(BaseModel):
    P: str | None = None
    I: str | None = None
    C: str | None = None
    O: str | None = None
    T: str | None = None
    S: str | None = None


class ProtocolUpsert(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    background: str | None = None
    objectives: str | None = None
    research_questions: str | None = None
    pico: ProtocolPICO = Field(default_factory=ProtocolPICO)
    eligibility_criteria: dict = Field(default_factory=dict)
    search_strategy_notes: str | None = None
    registration_registry: str | None = None
    registration_id: str | None = None
    registration_url: str | None = None
    registration_status: str | None = None
    notes: str | None = None


class ProtocolOut(BaseModel):
    id: str
    project_id: str
    version: int
    title: str
    background: str | None
    objectives: str | None
    research_questions: str | None
    pico: dict
    eligibility_criteria: dict
    search_strategy_notes: str | None
    registration_registry: str | None
    registration_id: str | None
    registration_url: str | None
    registration_status: str | None
    notes: str | None
    created_at: datetime


class CodebookRuleIn(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    direction: str = Field(pattern=r"^(include|exclude|flag)$")
    category: str | None = None
    rationale: str = Field(min_length=1)
    examples: list[str] = Field(default_factory=list)


class CodebookUpsert(BaseModel):
    notes: str | None = None
    rules: list[CodebookRuleIn]


class CodebookRuleOut(CodebookRuleIn):
    id: str


class CodebookOut(BaseModel):
    id: str
    project_id: str
    version: int
    notes: str | None
    rules: list[CodebookRuleOut]
    created_at: datetime
