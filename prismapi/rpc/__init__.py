"""Stdio JSON-RPC: how the Python sidecar talks to Tauri.

Wire format (newline-delimited JSON, JSON-RPC 2.0-style envelope):

    REQUEST:  {"id": "...", "method": "...", "params": {...}}
    SUCCESS:  {"id": "...", "result": {...}}
    ERROR:    {"id": "...", "error": {"code": int, "message": "...", "data": {...}}}

The sidecar is single-flight by default — one request in, one response out.
Long-running ops emit `notification` frames (no `id` field) which the renderer
can subscribe to for progress reporting.

Read the tutorial at `docs/learning/python-sidecar-pattern.md` for a worked
walk-through of adding a new method.
"""

from prismapi.rpc.dispatcher import Dispatcher, rpc
from prismapi.rpc.errors import RpcError

__all__ = ["Dispatcher", "rpc", "RpcError"]
