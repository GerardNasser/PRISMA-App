from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SearchRun(BaseModel):
    database: str
    query: str = Field(min_length=1)
    applied_filters: list[str] = Field(default_factory=list)
    max_results: int = Field(default=1000, ge=1, le=10000)
    options: dict = Field(default_factory=dict)
    payload: str | None = None  # for ris_import


class SearchOut(BaseModel):
    id: str
    project_id: str
    database: str
    query_string: str
    applied_filters: list[str]
    status: str
    error: str | None
    hit_count: int
    executed_at: datetime | None
    created_at: datetime


class RecordOut(BaseModel):
    id: str
    search_id: str
    database: str
    external_id: str
    doi: str | None
    pmid: str | None
    title: str
    abstract: str | None
    authors: str | None
    journal: str | None
    year: int | None
    publication_type: str | None
    language: str | None
    url: str | None


class PairwiseMatrixRequest(BaseModel):
    groups: list[list[str]] = Field(min_length=2)


class PairwiseMatrixResponse(BaseModel):
    pairs: list[list[str]]


class SearchFilterOut(BaseModel):
    id: str
    label: str
    description: str
    citation: str | None
    supported_adapters: list[str]


class SearchAdapterOut(BaseModel):
    id: str
    label: str
    requires: list[str]
