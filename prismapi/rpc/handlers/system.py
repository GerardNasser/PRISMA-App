"""System-level RPC: health, version, method list."""

from __future__ import annotations

from prismapi import __version__
from prismapi.rpc.dispatcher import Dispatcher, rpc


@rpc("system.ping")
async def ping() -> dict:
    return {"pong": True, "version": __version__}


@rpc("system.methods")
async def methods() -> dict:
    return {"methods": Dispatcher.methods()}
