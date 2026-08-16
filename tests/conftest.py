"""Shared pytest fixtures.

Tests call the Dispatcher directly — no subprocess, no stdio — and assert on
return values. This keeps tests fast and the transport layer thin.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

# Configure data dir before importing prismapi so first-touch picks it up.
_test_root = Path(tempfile.gettempdir()) / "prismapi-test"
if _test_root.exists():
    shutil.rmtree(_test_root)
_test_root.mkdir(parents=True)
os.environ["PRISMAPI_DATA_DIR"] = str(_test_root)

import pytest  # noqa: E402

from prismapi.config import get_settings  # noqa: E402
from prismapi.db import base as db_base  # noqa: E402
from prismapi.db.base import Base, get_engine, get_sessionmaker  # noqa: E402
from prismapi.db import models  # noqa: E402, F401
from prismapi.rpc import Dispatcher  # noqa: E402
from prismapi.services.identity import upsert_local_identity  # noqa: E402


def _reset_engine() -> None:
    db_base._engine = None
    db_base._sessionmaker = None
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
async def _isolated_db() -> AsyncIterator[None]:
    """Fresh DB file per test, engine disposed inside the test's own loop.

    Disposing at teardown matters: resetting the module-global engine without
    closing it leaves aiosqlite worker threads racing a closed event loop.
    """
    if _test_root.exists():
        for child in _test_root.iterdir():
            if child.is_file():
                child.unlink()
            else:
                shutil.rmtree(child)
    _reset_engine()
    yield
    if db_base._engine is not None:
        await db_base._engine.dispose()


@pytest.fixture
async def dispatcher() -> AsyncIterator[Dispatcher]:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield Dispatcher()


@pytest.fixture
async def local_identity() -> AsyncIterator[dict]:
    """Provision a logged-in local identity for tests that need one."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = get_sessionmaker()
    async with Session() as session:
        identity = await upsert_local_identity(
            session,
            last_name="Nasser",
            orcid=None,
            email="gerard@example.edu",
            institution="Example University",
        )
    yield {
        "id": str(identity.id),
        "display_name": identity.display_name,
        "email": identity.email,
    }
