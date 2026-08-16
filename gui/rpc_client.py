"""Synchronous wrapper around the in-process async dispatcher.

CustomTkinter runs on the Tk main loop (sync). The prismapi handlers are
async. We run a single background asyncio loop in a worker thread and submit
coroutines via `run_coroutine_threadsafe`. This keeps the UI responsive even
for slow ops (search, dedup) without requiring asyncio expertise in the GUI
code.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any

from prismapi.db import models  # noqa: F401 — register tables with metadata
from prismapi.db.base import Base, get_engine
from prismapi.rpc.dispatcher import Dispatcher
from prismapi.rpc.errors import RpcError


class RpcClient:
    """One per app run."""

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._loop.run_forever, daemon=True, name="prismapi-loop"
        )
        self._thread.start()
        # Eager schema bootstrap so first-run UI doesn't hit "no such table".
        self._call_coro(self._bootstrap())
        self._dispatcher = Dispatcher()

    async def _bootstrap(self) -> None:
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(self._patch_columns)

    @staticmethod
    def _patch_columns(sync_conn) -> None:
        """Lightweight forward-only migration for columns we've added since
        v0.6. ``create_all`` only creates missing TABLES — it never touches
        existing tables, so a DB carried over from a previous bundle would be
        missing newer columns. This patches the few we've added.
        """
        from sqlalchemy import inspect, text

        inspector = inspect(sync_conn)

        def has_column(table: str, col: str) -> bool:
            try:
                return any(c["name"] == col for c in inspector.get_columns(table))
            except Exception:
                return False

        # Added 2026-05-13: protocols.reviewer_config (n_reviewers, α/κ
        # thresholds, conflict strategy).
        if has_column("protocols", "id") and not has_column("protocols", "reviewer_config"):
            sync_conn.execute(text(
                "ALTER TABLE protocols ADD COLUMN reviewer_config JSON NOT NULL DEFAULT '{}'"
            ))

    def _call_coro(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result()

    def call(self, method: str, params: dict | None = None) -> Any:
        return self._call_coro(self._dispatcher.call(method, params or {}))

    def call_async(self, method: str, params: dict | None = None):
        """Returns a `concurrent.futures.Future` you can poll with `done()`."""
        return asyncio.run_coroutine_threadsafe(
            self._dispatcher.call(method, params or {}), self._loop
        )

    def shutdown(self) -> None:
        try:
            self._loop.call_soon_threadsafe(self._loop.stop)
        except Exception:
            pass


__all__ = ["RpcClient", "RpcError"]
