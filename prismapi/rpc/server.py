"""Stdio JSON-RPC server.

Reads newline-delimited JSON from stdin, dispatches via `Dispatcher`,
writes newline-delimited JSON responses to stdout. Logs go to stderr.

Entry point: `python -m prismapi.rpc.server` (also bound as a console script
`prismapi-rpc` in pyproject.toml).
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any

from prismapi.db import models  # noqa: F401 — register tables with Base.metadata
from prismapi.db.base import Base, get_engine
from prismapi.rpc.dispatcher import Dispatcher
from prismapi.rpc.errors import INVALID_REQUEST, PARSE_ERROR, RpcError

log = logging.getLogger("prismapi.rpc.server")


def _write_frame(obj: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(obj, default=str, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def _success(rid: str | None, result: Any) -> dict[str, Any]:
    return {"id": rid, "result": result}


def _error(rid: str | None, code: int, message: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"id": rid, "error": {"code": code, "message": message, "data": data or {}}}


async def _ensure_schema() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _serve() -> None:
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="[prismapi-rpc] %(levelname)s %(name)s — %(message)s",
    )
    await _ensure_schema()
    dispatcher = Dispatcher()
    log.info("ready (methods=%d)", len(dispatcher.methods()))
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)

    while True:
        line = await reader.readline()
        if not line:
            break
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            _write_frame(_error(None, PARSE_ERROR, f"Bad JSON: {exc}"))
            continue
        rid = payload.get("id")
        method = payload.get("method")
        params = payload.get("params") or {}
        if not isinstance(method, str):
            _write_frame(_error(rid, INVALID_REQUEST, "Missing or non-string method"))
            continue
        try:
            result = await dispatcher.call(method, params)
            _write_frame(_success(rid, result))
        except RpcError as exc:
            _write_frame(_error(rid, exc.code, exc.message, exc.data))
        except Exception as exc:
            log.exception("Unhandled error in dispatch")
            _write_frame(_error(rid, INVALID_REQUEST, str(exc)))


def main() -> int:
    try:
        asyncio.run(_serve())
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
