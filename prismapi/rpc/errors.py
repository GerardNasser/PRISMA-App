"""JSON-RPC error envelope.

We borrow JSON-RPC 2.0 error codes for the standard set and use application
codes from 1000 up for our own conditions.
"""

from __future__ import annotations

from typing import Any

# Standard JSON-RPC 2.0 codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# Application codes
NOT_FOUND = 1404
CONFLICT = 1409
FORBIDDEN = 1403
VALIDATION = 1422
IDENTITY_NEEDED = 1001
ADAPTER_FAILURE = 2000
STATEFILE_SCHEMA_MISMATCH = 3000


class RpcError(Exception):
    """Carries an RPC error envelope. Handlers raise this; the dispatcher
    serialises it as `{"error": {...}}` on stdout."""

    def __init__(self, code: int, message: str, data: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data or {}

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "data": self.data}
