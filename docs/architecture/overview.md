# Architecture overview

## Three layers

1. **Renderer** (`apps/renderer/`) — Vite + React 18 + Tailwind. Pure UI. Cannot reach the network on its own.
2. **Shell** (`apps/desktop/`) — Tauri (Rust). Owns the window, spawns the sidecar, bridges IPC.
3. **Sidecar** (`apps/core/`) — Python 3.12. SQLAlchemy 2.0 async over SQLite. Owns all business logic.

Communication is one Tauri command: `rpc(method: string, params: Value)`. Inside the shell, that gets serialised as a newline-delimited JSON-RPC request over the sidecar's stdin and the response is read back from stdout. There are no other channels. No TCP sockets are opened anywhere.

## Why this shape

- **Single-user, file-based**: every install owns one SQLite file. No DB server, no migrations service, no remote auth.
- **Audit-friendly**: every state change writes an `AuditLog` row. Every methodological judgment goes into `JudgmentCall`. The Python sidecar is the only thing that mutates state; the renderer is purely a view.
- **Collaboration without a server**: `.prismaproj` files exchange project state. The merger is deterministic and surfaces conflicts as data, not as silent overrides.
- **Field-aware everything**: the YAML files under `apps/core/src/prismapi/fields/registry/` are the spec. They drive forms, defaults, validation, and reporting requirements without ever touching the codebase.

## Where the data lives

| Layer | Where |
|---|---|
| App data root | macOS `~/Library/Application Support/PrismAPI`, Windows `%APPDATA%/PrismAPI`, Linux `~/.local/share/PrismAPI` |
| Local SQLite (WAL) | `<app data>/prismapi.db` |
| Project snapshots | `<app data>/snapshots/<project_uuid>/<timestamp>-<label>.prismaproj` |
| Project assets | `<app data>/projects/<project_uuid>/` |

`PRISMAPI_DATA_DIR` overrides the root for development and tests.

## What the renderer cannot do

- Cannot fetch arbitrary URLs (Tauri allowlist locks `shell` to `https?://` open-in-browser only).
- Cannot read or write outside the OS app-data directory plus user-selected files via dialog (fs allowlist scope).
- Cannot bypass the RPC contract — every state mutation goes through a typed handler that audits, snapshots when relevant, and commits in a transaction.

## Phases that aren't built yet

Phases 6 (synthesis), 7 (publication bias), 8 (certainty + reporting), 9 (microbiome SRA/DADA2/MMUPHin pipeline). All of them ride on the same dispatcher + service layer pattern. Adding a new analysis is: write a domain function, write a service that wires it up + audits it, register a handler with `@rpc(...)`, render a screen.
