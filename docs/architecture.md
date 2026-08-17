# Architecture

PrismAPI is a single-process desktop app. One `python app.py` starts a
CustomTkinter window; the engine — SQLite models, services, and an RPC
dispatcher — runs inside the same process, without a web server, a
sidecar process, or Docker. Nothing listens on any port; the only
network traffic is outbound HTTPS to bibliographic APIs (PubMed, OpenAlex,
CrossRef) when you run a search.

Two earlier designs (a FastAPI web platform, then a Tauri shell with a
Python sidecar) were abandoned before this beta. If you find references to
`apps/api`, uvicorn, Redis, Tauri, or a "renderer", they are fossils —
delete them on sight.

## Process layout

```
app.py
└── gui.main.PrismAPIApp (Tk main loop)
    └── gui.rpc_client.RpcClient
        ├── background thread running one asyncio loop
        └── prismapi.rpc.dispatcher.Dispatcher   ← same object the tests use
            └── prismapi.rpc.handlers.*          ← ~55 registered methods
                └── prismapi.services.*          ← business logic
                    └── prismapi.db.*            ← SQLAlchemy async + aiosqlite
```

The GUI calls the dispatcher in-process. Quick calls go through
`RpcClient.call`, which blocks the Tk thread for the few milliseconds a
SQLite read takes. Slow operations — dedup, RIS import, statefile
export/preview/merge — go through `PrismAPIApp.rpc_bg`, which submits the
coroutine to the background loop and polls the future with `after()`, so
the window stays responsive.

`prismapi/rpc/server.py` is a stdio JSON-RPC server around the same
dispatcher. The GUI does not use it; it exists for driving the engine from
another process (or another language) if that is ever needed.

## The dispatcher contract

Handlers are `async def` functions registered with `@rpc("group.method")`.
The dispatcher validates params against each handler's pydantic model,
opens one `AsyncSession` per call, commits inside the handler (services
commit when their unit of work is done), and rolls back on error. Errors
surface as `RpcError` with JSON-RPC-style codes (`prismapi/rpc/errors.py`).

Tests call the dispatcher directly (`tests/conftest.py`) — no subprocess,
no HTTP. Anything the GUI can do, a test can do through the same interface.

## Data model

One SQLite file holds everything. The main tables, in workflow order:

- `identities`, `projects`, `project_members` — who and what. Exactly one
  identity has `is_local=True`.
- `protocols`, `codebooks` (+ `codebook_rules`) — versioned rows; every
  save inserts the next version, nothing is edited in place.
- `searches`, `records` — each search run persists its exact query, filter
  set, status, and hits. Failed runs are recorded too, since PRISMA-S asks
  for every attempt.
- `record_clusters`, `record_cluster_members` — dedup output; screening,
  extraction, and RoB all key on clusters, not raw records.
- `screening_decisions`, `conflict_resolutions` — per (cluster, reviewer,
  stage) decisions, stages `title_abstract` and `full_text`.
- `extractions`, `rob_assessments` — per (cluster, reviewer) rows.
- `audit_log`, `judgment_calls` — append-only trail.
- `snapshots`, plus soft-delete columns everywhere — the safety layers.

`PRAGMA foreign_keys=ON` is set on every connection, and cluster deletion
cascades into screening/extraction/RoB rows. That is why `dedup.run`
refuses to reset clusters once screening work exists unless forced, and
takes a snapshot first when it is.

## Phase gates

`prismapi/domain/phases.py` defines the phase order and pure gate logic;
`prismapi/services/phase_completion.py` builds the `GateState` snapshot
from the database (which raters have finished title/abstract, which
clusters advanced to full text, whether any extraction is submitted, and
so on). The `phases.state` RPC returns one `{phase, open, reason}` entry
per phase, and the project sidebar renders locks from it. A locked phase
explains itself when clicked.

## Field configs

`prismapi/fields/registry/` holds one YAML per (field, review type) pair,
validated on startup against `_schema.json`. A config decides the
reporting checklist, registries, databases, extraction template,
risk-of-bias tool (with optional per-design overrides via
`tool_by_choice`), effect sizes, synthesis modules, publication-bias
methods, and certainty framework. Projects pin the config version they
were created with. See `docs/field-config-spec.md` for the authoring
guide.

## State files

Collaboration works by exchanging `.prismaproj` bundles — deterministic
zips with a checksummed manifest. Import is preview-then-merge, with a
snapshot taken before any write. `docs/architecture/state-files.md`
documents the format and the merge rules.

## Packaging

`build.py` drives PyInstaller: `.app` plus `.dmg` (via `hdiutil`) on
macOS, a single-file `.exe` on Windows. The spec file is generated as a
side effect and is not a build input. Bundles are unsigned until
code-signing certificates exist. There is no CI pipeline yet; releases
are built by hand.

## Not built yet

Synthesis (pooling, forest/funnel plots), publication-bias diagnostics,
GRADE summary-of-findings tables, and manuscript export. The sidebar
phases stop at risk of bias; `synthesis` and `report` gates exist in the
domain model but have no screens.
