"""Search adapter registry."""

from prismapi.adapters.search.base import (
    SearchAdapter,
    SearchAdapterError,
    SearchHit,
    list_adapters,
    register_adapter,
    resolve_adapter,
)

# Import for registration side-effects.
from prismapi.adapters.search import (  # noqa: F401
    crossref,
    openalex,
    pubmed,
    ris_import,
)

__all__ = [
    "SearchAdapter",
    "SearchAdapterError",
    "SearchHit",
    "list_adapters",
    "register_adapter",
    "resolve_adapter",
]
