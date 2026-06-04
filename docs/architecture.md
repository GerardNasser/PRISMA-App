# Architecture

## One-liner

A self-hostable, PRISMA-2020-compliant SR/MA platform where users pick their **field + review type**, and the rest of the application (form fields, databases, RoB tool, effect-size pipeline, synthesis modules, certainty framework, reporting checklist, manuscript template) is configured from a **declarative field-config registry**.

## Layout

```
apps/api/      FastAPI + SQLAlchemy + Alembic + RQ workers
apps/web/      Next.js + React + TypeScript
docs/          Architecture, methodology canon, field guides
legacy/        Prior assets preserved on disk
```

## Field-config registry

The heart of the system. Each `(field, review_type)` pair has a YAML config under `apps/api/src/prismapi/fields/registry/`. Each config is validated at startup (and in CI) against `_schema.json`.

A config declares:

- **Reporting** — primary checklist + extensions (PRISMA 2020, PRISMA-S, ROSES, JARS-Quant, STORMS, ARRIVE, MAER-Net …)
- **Registries** — primary + alternatives + suppressed (e.g., scoping reviews suppress PROSPERO)
- **Databases** — required + recommended + grey-lit flag + auto-injected search filters (Hooijmans animal filter, Cochrane RCT filter …)
- **Extraction template** — base (STORMS / ARRIVE / STROBE-nut / CHARMS / MAER-Net …) + custom fields with types
- **Risk of bias** — tool (RoB 2 / ROBINS-I / ROBINS-E / QUADAS-2 / SYRCLE / JBI per-design / Dybå-Dingsøyr / NOS-with-warning / custom) + domains + scale
- **Effect sizes** — default + allowed (SMD, log OR, PCC, lnRR, NMD, proportions, AUC, none-narrative)
- **Synthesis** — model default (REML / Schmidt-Hunter / RVE / multilevel / meta-aggregation / thematic) + modules enabled + HK adjustment + prediction interval
- **Publication bias** — required methods + default panel + mandatory flag (animal forces it on)
- **Certainty** — GRADE / CERQual / ConQual / NutriGrade / WWC tiers / narrative
- **Modules** — which top-level modules are enabled
- **Branch choices** — up-front user decisions that cascade (e.g., Schmidt-Hunter vs Hedges-Olkin for mgmt MA, pooling strategy for microbiome)
- **QRP warnings** — field-specific pitfalls surfaced in UI
- **Citations** + **verify flags** — provenance and items pending web verification

## Why this shape

- Adding a field is a **config change**, not a code change. Pull-requestable, code-reviewable, diffable.
- The same engine renders microbiome STORMS extraction and econ MAER-Net extraction without per-field code branches.
- Projects pin the version of the field config they were created with, so a future config update doesn't silently change an in-flight review.

## Tech choices

- **Python 3.12 / FastAPI / SQLAlchemy 2.0 async / Alembic / RQ / Pydantic v2** — backend.
- **Next.js 15 / React 19 / TypeScript** — frontend.
- **Postgres / Redis / MinIO (S3-compatible)** — local stack via docker-compose.
- **R sidecars** (later phases) — `metafor`, `MMUPHin`, `netmeta` for methods where Python lacks parity.

## Phasing

See `README.md`. Phase 0 ships the foundation + field registry skeleton with two canary configs (microbiome, economics). Each subsequent phase is additive.
