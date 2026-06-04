# PrismAPI

A field-aware, PRISMA-2020-compliant systematic review + meta-analysis **desktop application** that runs entirely on your machine. No cloud. No listening sockets.

Pick your field and review type once. The app configures the rest: which reporting checklist applies, which databases to search, which risk-of-bias tool to render, which effect size to default to, which publication-bias panel is mandatory, which certainty framework to use, and which manuscript template to export.

## Why a desktop app, no ports

- All review data lives in a single SQLite file at `~/Library/Application Support/PrismAPI/prismapi.db` (macOS), `%APPDATA%/PrismAPI` (Windows), or `~/.local/share/PrismAPI` (Linux).
- The Python sidecar talks to the Tauri shell over **stdio JSON-RPC**, never TCP — no `127.0.0.1` socket is opened. Outbound HTTPS to PubMed / OpenAlex / CrossRef etc. is normal; nothing listens.
- Collaboration is by **`.prismaproj`** exchange: a deterministic, content-addressed zip you hand to a colleague. Imports surface a non-destructive diff with conflict resolution before anything is applied.

## Status

Branch `desktop-migration` is the current working line. Steps A–E (foundation → renderer) are green; F (matrix CI packaging) and G (learning docs) are sketched.

| # | Scope | State |
|---|---|---|
| A | Tear down web-app transport (FastAPI, docker-compose, auth) | ✅ |
| B | Sidecar core: SQLite, Identity, stdio JSON-RPC, 46 handlers | ✅ |
| C | `.prismaproj` export / preview-import / merge with conflict rules | ✅ |
| Safety | Soft-delete, trash, snapshots, confirmation dialogs, exit guard | ✅ wired in core |
| D | Tauri Rust shell + sidecar bridge | ✅ |
| E | Vite + React + Tailwind renderer (onboarding, wizard, screening, extraction, share, settings) | ✅ |
| F | CI matrix → `.dmg` / `.msi` / `.AppImage` bundles | — not in this beta |
| G | Architecture + learning docs | in progress |
| 6+ | Synthesis engine, pub-bias, GRADE reporting, microbiome subsystem | future |

## Architecture at a glance

```
┌──────────────────────────┐
│  Tauri webview (Vite)    │   no network, no global fetch
│  React + Tailwind + RPC  │
└────────────┬─────────────┘
             │ invoke("rpc", {method, params})  ← Tauri IPC (in-process)
┌────────────┴─────────────┐
│  Tauri Rust shell        │   spawns child process, drains stderr to log
└────────────┬─────────────┘
             │ newline-delimited JSON over stdin/stdout
┌────────────┴─────────────┐
│  Python sidecar          │
│  domain + services       │   ← SQLAlchemy 2.0 async over SQLite (WAL)
│  field configs (YAML)    │   ← strict JSON-Schema validation at startup
│  adapters/search/*       │   ← PubMed, OpenAlex, CrossRef, RIS import
└──────────────────────────┘
```

No TCP. No HTTP server. The renderer cannot fetch arbitrary URLs (Tauri allowlist locks the network surface to outbound HTTPS via the Python sidecar's adapters).

## Layout

```
apps/
  core/        Python sidecar  (FastAPI removed; stdio JSON-RPC)
  desktop/     Tauri Rust shell (bridges renderer ↔ sidecar)
  renderer/    Vite + React + Tailwind + shadcn-style components
docs/          Architecture and learning material; PRISMA reference PDFs under docs/references/
tutorials/     Interactive teachable API-pull notebooks per database (PubMed, ScienceDirect, Web of Science) — companions to the runtime scripts under prismapi/services/search_scripts/
```

## Run (dev)

```
make desktop      # full app: webview + Rust shell + Python sidecar
make renderer     # renderer-only at http://localhost:5173 (no shell)
make core         # sidecar standalone (talk to it over stdin/stdout)
make smoke        # send {system.ping} to the sidecar and verify it replies
make test         # 55 sidecar tests
```

## Build releases

CI matrix-builds `.dmg` (macOS arm + x86), `.msi` (Windows), `.AppImage` (Linux) on push to `main`. Unsigned for v1 — both Gatekeeper and SmartScreen will warn until you add code-signing certificates (Apple Developer Program $99/yr; Windows Authenticode ~$200/yr).

## Identity, exports, merges

First run asks for **last name + at least one of (ORCID, affiliate email)**. That identity travels with every `.prismaproj` export so collaborators see your name on your work, and import-time matching keys on ORCID first, email second.

A `.prismaproj` is a zip with `manifest.json` + JSONL files per table + an `assets/` folder. SHA-256 of every file inside is recorded in the manifest; the importer refuses a tampered bundle. Imports never mutate the local DB until you accept the diff. Parallel codebook / protocol bumps surface as conflicts you resolve before merge.

## Safety layers

1. **Auto-commit per action** — there is no "unsaved buffer."
2. **Soft delete + Trash** — 30-day retention; emptying requires typing `DELETE`.
3. **Confirmation dialogs** — friction calibrated to blast radius.
4. **Project snapshots** — auto on-open, pre-import, pre-migration; manual any time. 10-snapshot auto-cap plus unlimited manual.
5. **Exit guard** — blocks quit while async ops are mid-flight or imports are unresolved.
6. **Undo stack** — keyboard Cmd/Ctrl-Z within a session, on top of Trash + Snapshots.

## License

See `LICENSE`.
