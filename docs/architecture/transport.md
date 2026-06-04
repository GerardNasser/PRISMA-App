# Transport: stdio JSON-RPC

## Why not HTTP?

We don't want any TCP socket listening on the user's machine, ever. Even `127.0.0.1` carries audit-posture cost. Stdio is two pipes attached to a child process — there's literally no socket bound.

## Wire format

Newline-delimited JSON, one request per line, one response per line.

```
REQUEST:  {"id": "abc-123", "method": "projects.create", "params": {...}}
SUCCESS:  {"id": "abc-123", "result": {...}}
ERROR:    {"id": "abc-123", "error": {"code": 1422, "message": "...", "data": {...}}}
```

Notification frames (no `id`) are reserved for progress updates from long-running operations (search execution, dedup). The shell currently ignores them; the renderer subscribes via Tauri events when we wire that up.

## Error codes

We borrow JSON-RPC 2.0 standard codes for transport-level failures and use 1xxx-3xxx for application errors. See `apps/core/src/prismapi/rpc/errors.py`:

| Code | Meaning |
|---|---|
| -32700 | Parse error (malformed JSON) |
| -32600 | Invalid request envelope |
| -32601 | Method not found |
| -32602 | Invalid params (pydantic validation failure) |
| -32603 | Internal error (uncaught exception) |
| 1001   | IDENTITY_NEEDED — first-run flow must complete |
| 1403   | FORBIDDEN |
| 1404   | NOT_FOUND |
| 1409   | CONFLICT (e.g., slug taken) |
| 1422   | VALIDATION (semantic, not transport) |
| 2000   | ADAPTER_FAILURE (search adapter raised) |
| 3000   | STATEFILE_SCHEMA_MISMATCH |

## Spawn lifecycle

1. Tauri startup: `apps/desktop/src/sidecar.rs::SidecarBridge::spawn` runs `python -m prismapi.rpc.server` as a child process with `PYTHONUNBUFFERED=1`.
2. Two background tasks attach to stdout / stderr — stdout routes responses by `id`; stderr feeds the Tauri log so sidecar tracebacks survive.
3. `system.ping` is called up to 30× with 200ms back-off to confirm the sidecar is ready before any user interaction.
4. On window close, the bridge `start_kill()`s the child.

## Adding an RPC method

1. Pick a namespace: `projects.delete_member` style — period-separated, lowercase.
2. Add a handler in `apps/core/src/prismapi/rpc/handlers/<area>.py`:

   ```python
   from pydantic import BaseModel
   from prismapi.rpc.dispatcher import rpc

   class Params(BaseModel):
       project_id: str
       identity_id: str

   @rpc("projects.delete_member")
   async def delete_member(params: Params, session, identity_id):
       ...
   ```

3. The dispatcher introspects parameter names:
   - `params: SomeBaseModel` — auto-validated.
   - `session: AsyncSession` — auto-injected.
   - `identity_id: uuid.UUID` — current local identity (raises `IDENTITY_NEEDED` if no identity row exists).
4. Add a test in `apps/core/tests/test_<area>.py` calling `dispatcher.call("projects.delete_member", {...})`.

That's it — no router registration, no schema duplication. The renderer can call it immediately via `rpc("projects.delete_member", {...})`.
