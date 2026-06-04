"""Field-registry RPC handlers."""

from __future__ import annotations

from prismapi.fields.loader import field_registry
from prismapi.rpc.dispatcher import rpc
from prismapi.rpc.errors import NOT_FOUND, RpcError


@rpc("fields.list")
async def list_() -> dict:
    return {
        "fields": [
            {"field": f, "review_types": field_registry.review_types_for(f)}
            for f in field_registry.list_fields()
        ]
    }


@rpc("fields.configs")
async def configs() -> dict:
    return {
        "configs": [
            {
                "id": c.id,
                "field": c.field,
                "review_type": c.review_type,
                "label": c.label,
                "summary": c.summary,
                "version": c.version,
            }
            for c in field_registry.all()
        ]
    }


from pydantic import BaseModel  # noqa: E402


class ConfigGet(BaseModel):
    config_id: str


@rpc("fields.config.get")
async def config_get(params: ConfigGet) -> dict:
    cfg = field_registry.by_id(params.config_id)
    if cfg is None:
        raise RpcError(NOT_FOUND, f"Unknown field config: {params.config_id}")
    return cfg.data
