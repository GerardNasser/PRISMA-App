# PrismAPI

A desktop app for running PRISMA-2020-compliant systematic reviews and meta-analyses on your own machine. Pick your field and review type once; the app picks the reporting checklist, databases, risk-of-bias tool, extraction template, effect-size default, and certainty framework for you.

Version: **0.1.0-beta.1**
Platform: macOS and Windows (Linux from source)

---

## What's in this repo

| Path | What it is |
|---|---|
| `app.py` | App entry point. `python app.py` opens the GUI. |
| `gui/` | The desktop UI (CustomTkinter). Screens for onboarding, projects, the wizard, and the per-phase workspace. |
| `prismapi/` | The engine: SQLite models, services, RPC handlers, field-config registry. |
| `prismapi/fields/registry/` | 12 ready-to-use field configs (YAML) plus the JSON Schema that validates them. |
| `tests/` | 89 tests against the engine. |
| `tutorials/` | Jupyter notebooks teaching the PubMed, ScienceDirect, and Web of Science APIs. |
| `docs/` | Architecture notes and the PRISMA 2020 reference PDFs. |
| `build.py`, `PrismAPI.spec` | PyInstaller build for `.app` / `.exe` / `.dmg`. |
| `dist/PrismAPI-0.1.0-beta.1-macos.zip` | Pre-built macOS bundle, ready to run. |

The engine and GUI both live in this one repo and run in the same process — no separate sidecar, no listening sockets, no Docker.

---

## Install

### macOS — pre-built bundle

1. Unzip `dist/PrismAPI-0.1.0-beta.1-macos.zip`.
2. Drag `PrismAPI.app` into `/Applications` (or run it from wherever you unzipped).
3. First launch: Gatekeeper will warn — right-click → Open → Open. The app isn't code-signed for v1.

### From source (macOS, Windows, Linux)

Requires **Python 3.11+**.

```bash
git clone <this repo>
cd PRISMA-App

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt
python app.py
```

That's it — no database to set up, no migrations to run, no env file required. The app creates its own SQLite database on first launch.

---

## First run — identity

You'll be asked for:

- **Last name** (required)
- **ORCID** *or* **affiliate email** (at least one — needed to attribute your work in shared project files)
- **Institution** (optional)

This stays on your machine. It only leaves your machine if you choose to export a project and hand it to a collaborator.

---

## Creating a project

Click **+ New project** on the Projects screen. The wizard has 7 steps:

1. **Field** — Health, Preclinical, Social, Environmental, Engineering, Qualitative, or Custom.
2. **Review type** — e.g. Intervention RCT, Observational, Diagnostic, Omics. (Skipped if the field has only one option.)
3. **Choices** — Up-front branching the config asks for (skipped if the config has none).
4. **Reviewers** — How many reviewers per item, Krippendorff α target, Cohen κ target, conflict resolution strategy.
5. **Enroll raters** — Name + ORCID/email + role (Lead or Rater) for each reviewer. Exactly one Lead.
6. **Details** — Project name, slug, description.
7. **Confirm** — Review and create.

Once created, the project pins the version of the field config it was created with. Future updates to that config won't silently change your in-flight review.

### Available field configs

The 12 configs that ship today:

| Field | Configs |
|---|---|
| Health | Intervention (RCTs), Observational, Diagnostic, Omics |
| Preclinical | Animal (SYRCLE RoB) |
| Social | Economics, Education, Psychology |
| Environmental | Ecology |
| Engineering | SLR (Kitchenham-style) |
| Qualitative | Synthesis (meta-ethnography / thematic / framework) |
| General | Custom (generic PRISMA-2020 defaults) |

Each config drives: reporting checklist, registries, required and recommended databases, extraction-template fields, risk-of-bias tool, effect-size defaults and allowed list, synthesis modules, publication-bias requirements, certainty framework, and field-specific QRP warnings.

---

## Working inside a project

Each project opens to a sidebar of phases:

- **Overview** — Pinned config summary: reporting, registry, required databases, RoB tool, effect-size default, certainty framework, branch choices, and any field-specific cautions.
- **Protocol** — Versioned protocol record (title, reviewer config, etc.). Earlier versions stay accessible.
- **Codebook** — Versioned extraction codebook.
- **Search** — Configure searches across the databases your field requires; the app can generate a runnable PubMed / OpenAlex / CrossRef script for the configuration.
- **De-duplicate** — Auto cluster + manual merge.
- **Title/abstract** — Screening with IRR (Krippendorff α + Cohen κ) and conflict resolution against the thresholds you set in the wizard.
- **Extraction** — Per-study extraction against the codebook.
- **Risk of bias** — The right tool for your config (RoB 2, ROBINS-I, SYRCLE, QUADAS-2, etc.).
- **Share / import** — Export or import `.prismaproj` files (see below).

Locked phases show a lock icon and tell you why they're locked when you click them.

---

## Sharing work with collaborators

The exchange format is **`.prismaproj`** — a zip with `manifest.json`, JSONL files per table, and an `assets/` folder. Every file's SHA-256 is recorded in the manifest, so a tampered bundle is rejected on import.

**Export.** Project → Share → Export. Pick a path. Hand the file to your collaborator however you like.

**Import.** Project → Share → Choose file. The app shows a non-destructive **preview**: counts of new items, plus any conflicts (e.g. parallel protocol bumps) — each conflict needs a `keep_local` / `keep_incoming` / `keep_both` resolution. Nothing is written to your database until you click **Apply merge**.

A snapshot is taken automatically before any merge.

---

## Where your data lives

The OS owns the data directory:

| OS | Path |
|---|---|
| macOS | `~/Library/Application Support/PrismAPI/` |
| Windows | `%APPDATA%\PrismAPI\` |
| Linux | `~/.local/share/PrismAPI/` |

Inside it:

- `prismapi.db` — SQLite database (everything: projects, members, codebooks, protocols, screening decisions, extractions, RoB, snapshots, trash).
- `snapshots/` — Project snapshots.
- `projects/` — Per-project assets.

Override with the `PRISMAPI_DATA_DIR` environment variable if you want it somewhere else.

### Safety

- **Soft delete + Trash** — Deleted projects sit in the trash for 30 days. Emptying requires typing `DELETE`.
- **Snapshots** — Auto-taken before imports, plus manual any time. 10 auto-snapshots are kept; manual snapshots are unlimited.
- **Versioned protocol and codebook** — Every save is a new version, prior versions retained.

---

## Optional configuration

Either as environment variables or in a `.env` next to `app.py`:

| Variable | Purpose |
|---|---|
| `PRISMAPI_DATA_DIR` | Override the data directory. |
| `NCBI_EMAIL` | Sent with PubMed/E-utilities requests (NCBI asks for one). |
| `NCBI_API_KEY` | Higher PubMed rate limits. |
| `OPENALEX_EMAIL` | Joins the OpenAlex "polite pool" (faster, more reliable). |
| `PRISMAPI_TRASH_RETENTION_DAYS` | Trash retention (default 30). |
| `PRISMAPI_SNAPSHOT_AUTO_CAP` | Auto-snapshot cap (default 10). |
| `LLM_ADVISORY_ENABLED` | Turn on advisory LLM hints (off by default). |
| `GOOGLE_API_KEY` | Needed if `LLM_ADVISORY_ENABLED=true`. |

None of these are required to use the app.

The app only ever makes **outbound** HTTPS calls — to PubMed, OpenAlex, CrossRef, ScienceDirect, Web of Science. Nothing listens on any port.

---

## Building from source

Build a distributable from your local checkout:

```bash
pip install -r requirements.txt
python build.py            # macOS: builds .app + .dmg ; Windows: builds .exe
python build.py --no-dmg   # macOS only: skip the .dmg step
```

Output:

- macOS: `dist/PrismAPI.app` and `dist/PrismAPI.dmg`
- Windows: `dist/PrismAPI.exe`

The build uses PyInstaller and bundles the field-config YAMLs, the GUI, and the engine into one app. Bundles are unsigned — both Gatekeeper (macOS) and SmartScreen (Windows) will warn until you add code-signing certificates.

---

## Running the tests

```bash
pip install pytest pytest-asyncio
pytest -q
```

89 tests cover the engine: identity, projects, members, screening, IRR, dedup, extraction, RoB, audit, snapshots, trash, statefile export/import/merge, fields registry validation, and the search adapters.

The GUI is intentionally not unit-tested — it's a thin synchronous wrapper around the same RPC dispatcher the tests hit directly.

---

## Tutorials

`tutorials/` has interactive Jupyter notebooks that walk through the **PubMed**, **ScienceDirect**, and **Web of Science** APIs end-to-end — useful if you want to understand or extend what the app does at runtime.

```bash
cd tutorials
python3 -m venv .venv && source .venv/bin/activate
pip install jupyterlab
pip install -r pubmed/requirements.txt
cp pubmed/env_template pubmed/.env       # then edit pubmed/.env
jupyter lab pubmed/PubMed_API.ipynb
```

---

## Adding a new field config

1. Copy any YAML in `prismapi/fields/registry/` as a starting point.
2. Set `id: <field>__<review_type>`, `version`, `effective_date`, `label`, `summary`.
3. Fill in the eight required sections: reporting, registries, databases, extraction template, risk-of-bias tool, effect sizes, synthesis, publication bias, certainty.
4. Add any `qrp_warnings` and `citations`.
5. Validate:

   ```bash
   python -m prismapi.fields.validate
   ```

The schema lives at `prismapi/fields/registry/_schema.json` (JSON Schema Draft 2020-12). It's enforced at startup, so a malformed YAML stops the app cleanly with an error message.

---

## What's not in this beta

- Synthesis / meta-analysis engine (forest plots, funnel plots, pooling) — planned.
- Publication-bias diagnostics — planned.
- GRADE summary-of-findings tables and manuscript export — planned.
- Code-signing / notarisation — needs certificates.
- CI matrix releases — not wired up.

---

## License

See `LICENSE`.