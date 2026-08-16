"""RPC method registry + dispatcher.

Handlers register themselves with `@rpc("namespace.method")`. The dispatcher
looks up the handler at call time, validates params via the handler's pydantic
model (if declared), invokes it with an open AsyncSession, and serialises the
result. Errors are caught and converted to the wire envelope.
"""

from __future__ import annotations

import inspect
import logging
import typing
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, ValidationError

from prismapi.db.base import get_sessionmaker
from prismapi.rpc.errors import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    METHOD_NOT_FOUND,
    RpcError,
)

log = logging.getLogger("prismapi.rpc")


HandlerFn = Callable[..., Awaitable[Any]]


class _Registration:
    __slots__ = ("fn", "params_model", "wants_identity", "wants_session")

    def __init__(
        self,
        fn: HandlerFn,
        params_model: type[BaseModel] | None,
        wants_session: bool,
        wants_identity: bool,
    ) -> None:
        self.fn = fn
        self.params_model = params_model
        self.wants_session = wants_session
        self.wants_identity = wants_identity


_REGISTRY: dict[str, _Registration] = {}


def rpc(method: str) -> Callable[[HandlerFn], HandlerFn]:
    """Decorator: register a handler under the given dotted method name.

    Handlers may declare parameters by name:
      - `params: SomePydanticModel` — auto-validated against the wire `params`.
      - `session: AsyncSession`     — auto-injected open session.
      - `identity_id: uuid.UUID`    — auto-injected current local identity uuid.
    Any of these are optional.
    """

    def decorator(fn: HandlerFn) -> HandlerFn:
        if method in _REGISTRY:
            raise ValueError(f"Duplicate RPC method: {method}")
        sig = inspect.signature(fn)
        # Resolve PEP-563 string annotations to actual classes.
        try:
            hints = typing.get_type_hints(fn)
        except Exception:
            hints = {}
        params_model: type[BaseModel] | None = None
        wants_session = False
        wants_identity = False
        for name in sig.parameters:
            if name == "session":
                wants_session = True
            elif name == "identity_id":
                wants_identity = True
            elif name == "params":
                ann = hints.get("params")
                if isinstance(ann, type) and issubclass(ann, BaseModel):
                    params_model = ann
        _REGISTRY[method] = _Registration(fn, params_model, wants_session, wants_identity)
        return fn

    return decorator


class Dispatcher:
    """Resolves a (method, params) call to a handler invocation.

    Used both by the stdio server loop and by tests (call the dispatcher
    directly without spawning a process).
    """

    def __init__(self) -> None:
        # Import the handlers module so registration side-effects fire.
        from prismapi.rpc import handlers  # noqa: F401

    @staticmethod
    def methods() -> list[str]:
        return sorted(_REGISTRY)

    async def call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        reg = _REGISTRY.get(method)
        if reg is None:
            raise RpcError(METHOD_NOT_FOUND, f"Unknown method: {method}")
        kwargs: dict[str, Any] = {}
        if reg.params_model is not None:
            try:
                kwargs["params"] = reg.params_model.model_validate(params or {})
            except ValidationError as ex:
                raise RpcError(INVALID_PARAMS, "Invalid params", {"errors": ex.errors()}) from ex
        if reg.wants_identity:
            from prismapi.services.identity import current_identity_id

            kwargs["identity_id"] = await current_identity_id()
        if reg.wants_session:
            Session = get_sessionmaker()
            async with Session() as session:
                kwargs["session"] = session
                try:
                    return await reg.fn(**kwargs)
                except RpcError:
                    raise
                except Exception as exc:
                    log.exception("Handler %s failed", method)
                    raise RpcError(INTERNAL_ERROR, str(exc)) from exc
        try:
            return await reg.fn(**kwargs)
        except RpcError:
            raise
        except Exception as exc:
            log.exception("Handler %s failed", method)
            raise RpcError(INTERNAL_ERROR, str(exc)) from exc
