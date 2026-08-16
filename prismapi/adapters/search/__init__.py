"""Search adapter registry."""

# Import for registration side-effects.
from prismapi.adapters.search import (  # noqa: F401
    crossref,
    openalex,
    pubmed,
    ris_import,
)
from prismapi.adapters.search.base import (
    SearchAdapter,
    SearchAdapterError,
    SearchHit,
    list_adapters,
    register_adapter,
    resolve_adapter,
)

__all__ = [
    "SearchAdapter",
    "SearchAdapterError",
    "SearchHit",
    "list_adapters",
    "register_adapter",
    "resolve_adapter",
]
