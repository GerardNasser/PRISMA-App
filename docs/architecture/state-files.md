# State files (`.prismaproj`)

A `.prismaproj` is a zip containing **everything needed to reconstruct one project's state on another install**.

## Layout

```
.prismaproj/
├── manifest.json              ← schema_version, project_id, exporter, sha256s
├── project.json               ← one project row (JSON, not JSONL)
├── identities.jsonl           ← every identity referenced anywhere
├── protocols.jsonl
├── pico_elements.jsonl
├── codebooks.jsonl
├── codebook_rules.jsonl
├── searches.jsonl
├── records.jsonl
├── clusters.jsonl
├── cluster_members.jsonl
├── screenings.jsonl
├── conflict_resolutions.jsonl
├── extractions.jsonl
├── rob.jsonl
├── audit.jsonl
├── judgments.jsonl
└── assets/                    ← PDFs and exports keyed by sha256 (reserved)
```

## Determinism

- Rows are sorted by stable key before serialisation (uuid string ascending).
- JSONL lines use sorted keys, no whitespace, and a trailing newline.
- The zip is built with a fixed mtime (`2020-01-01T00:00:00`).
- Identical project state → identical bytes → identical SHA-256.

This means you can verify "two installs hold the same state" by comparing bundle hashes, no diffing needed.

## Manifest

```json
{
  "schema_version": 1,
  "prismapi_version": "0.6.0-desktop",
  "project_id": "...",
  "project_name": "Plant microbiome MA",
  "project_field_config_id": "microbiome__16s_human",
  "project_field_config_version": "0.1.0",
  "exporter": {
    "id": "...",
    "last_name": "Nasser",
    "orcid": null,
    "email": "gerard@uncc.edu",
    "display_name": "Nasser (gerard@uncc.edu)"
  },
  "exported_at": "2026-05-13T17:42:11Z",
  "counts": { ... },
  "files": [
    { "relative_path": "records.jsonl", "sha256": "...", "size_bytes": 1742 },
    ...
  ]
}
```

The importer refuses any bundle whose `schema_version` differs from this build's `SCHEMA_VERSION` constant. Migration scripts for older versions are added to `apps/core/src/prismapi/statefile/migrations/` as the schema evolves.

## Merge rules

Most of the SR/MA data model is **naturally append-friendly** — each reviewer's decisions go in their own rows. Real conflicts only arise in a small set of cases:

| Table | Merge | Conflict class |
|---|---|---|
| `records` | Union by `(database, external_id)` | — |
| `clusters` | Recomputed | — |
| `searches` | Union by id | — |
| `screening_decisions` | Key `(cluster, reviewer, stage)` — different reviewers ➜ both stored | `screening_drift` (same reviewer, different decision across installs) |
| `extractions` | Key `(cluster, reviewer)` | `extraction_drift` |
| `rob_assessments` | Key `(cluster, reviewer)` | `rob_drift` |
| `conflict_resolutions` | Key `(cluster, stage)` | `arbitration_drift` (different arbiter on the same conflict) |
| `protocols` | Versioned, fast-forward | `protocol_parallel` (both installs bumped v(n) → v(n+1) with different bodies) |
| `codebooks` | Versioned, fast-forward | `codebook_parallel` |
| `identities` | Upsert by id | `identity_drift` (same id, divergent attributes) |
| `project` (metadata) | — | `project_metadata` (name / slug / branch_choices diverge) |
| `audit_log`, `judgment_calls` | Append-only union | — |

## Resolution choices the user can pick

For each surfaced conflict, the renderer offers one of:

- **keep_local** — discard the incoming row, retain what's already in the local DB.
- **keep_incoming** — overwrite local with the incoming value.
- **keep_both** — only valid for `protocol_parallel` / `codebook_parallel`. The incoming row is inserted as the *next* version after local, so both branches survive as version history.

Resolutions are passed back as a `{conflict_key: choice}` dict to `statefile.merge`. The merger refuses to proceed if any blocking conflict lacks a resolution.

## Pre-import snapshot

Every import takes a `pre_import` snapshot of the local project first (unless the caller opts out). If the merge goes sideways, restore from that snapshot via Settings → Snapshots.
