"""Base abstractions for search adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SearchHit:
    external_id: str
    database: str
    title: str
    abstract: str | None = None
    authors: str | None = None
    journal: str | None = None
    year: int | None = None
    doi: str | None = None
    pmid: str | None = None
    publication_type: str | None = None
    language: str | None = None
    url: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class SearchAdapterError(RuntimeError):
    """Raised on adapter-level failures (HTTP, auth, parsing)."""


class SearchAdapter(ABC):
    """A search adapter binds a remote database to a uniform iteration protocol.

    Adapters are stateless aside from configuration (API keys read from env via
    `prismapi.config`). Each adapter must declare `id`, `label`, and `requires`
    (env keys needed). They yield `SearchHit` objects in batches.
    """

    id: str
    label: str
    requires: tuple[str, ...] = ()

    @abstractmethod
    async def search(
        self, query: str, *, max_results: int = 1000, filters: list[str] | None = None
    ) -> AsyncIterator[SearchHit]: ...


_REGISTRY: dict[str, SearchAdapter] = {}


def register_adapter(adapter: SearchAdapter) -> None:
    if adapter.id in _REGISTRY:
        raise ValueError(f"Adapter already registered: {adapter.id}")
    _REGISTRY[adapter.id] = adapter


def resolve_adapter(adapter_id: str) -> SearchAdapter:
    if adapter_id not in _REGISTRY:
        raise SearchAdapterError(f"Unknown adapter: {adapter_id}")
    return _REGISTRY[adapter_id]


def list_adapters() -> list[SearchAdapter]:
    return list(_REGISTRY.values())
