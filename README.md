# PrismAPI

A desktop app for running PRISMA-2020-compliant systematic reviews and meta-analyses on your own machine. Pick your field and review type once; the app picks the reporting checklist, databases, risk-of-bias tool, extraction template, effect-size default, and certainty framework for you.

Version: **0.1.0-beta.1**
Platform: macOS. Windows and Linux builds are planned; `build.py` has a Windows path, but no Windows build has been made or tested yet.

---

## What's in this repo

| Path | What it is |
|---|---|
| `app.py` | App entry point. `python app.py` opens the GUI. |
| `gui/` | The desktop UI (CustomTkinter). Screens for onboarding, projects, the wizard, and the per-phase workspace. |
| `prismapi/` | The engine: SQLite models, services, RPC handlers, field-config registry. |
| `prismapi/fields/registry/` | 12 ready-to-use field configs (YAML) plus the JSON Schema that validates them. |
| `tests/` | The pytest suite (runs against the same dispatcher the GUI uses). |
| `tutorials/` | Jupyter notebooks teaching the PubMed, ScienceDirect, and Web of Science APIs. |
| `docs/` | Architecture notes, the field-config spec, and the PRISMA 2020 reference PDFs. |
| `build.py` | PyInstaller build for `.app` / `.dmg` (and, untested, `.exe`). |

The engine and GUI live in this one repo and run in the same process — no separate sidecar, no listening sockets, no Docker.

---

## Install

### From source

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

### Pre-built macOS bundle

Pre-built bundles are attached to GitHub Releases (they are build artifacts, not tracked in the repo). Unzip, drag `PrismAPI.app` into `/Applications`, and on first launch right-click → Open to get past Gatekeeper — the app isn't code-signed yet. You can also build your own bundle; see "Building from source" below.

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
3. **Choices** — Up-front questions the config asks, such as the primary study design. The design choice decides the risk-of-bias instrument (RoB 2 for randomised designs, ROBINS-I for non-randomised interventions, QUIPS for prognostic questions). Skipped if the config asks nothing.
4. **Reviewers** — How many reviewers per item, Krippendorff α target, Cohen κ target, conflict resolution strategy. Targets must be between 0 and 1.
5. **Enroll raters** — Name + ORCID/email + role (Lead or Rater) for each reviewer. Exactly one Lead. If you list yourself, the app knows — you're already enrolled as the owner.
6. **Details** — Project name, slug, description.
7. **Confirm** — Review and create.

Once created, the project pins the version of the field config it was created with. Future updates to that config won't silently change your in-flight review.

### Available field configs

The 12 configs that ship today:

| Field | Configs |
|---|---|
| Health | Intervention (RoB 2 / ROBINS-I by design), Observational, Diagnostic (QUADAS-2, Deeks' test), Omics |
| Preclinical | Animal (SYRCLE RoB) |
| Social | Economics, Education, Psychology (RoB 2 / ROBINS-I / QUIPS by design) |
| Environmental | Ecology (study-level RoB domains; ROSES reporting) |
| Engineering | SLR (Kitchenham-style) |
| Qualitative | Synthesis (meta-ethnography / thematic / framework) |
| General | Custom (generic PRISMA-2020 defaults, design-aware RoB) |

Each config drives: reporting checklist, registries, required and recommended databases, extraction-template fields, risk-of-bias tool, effect-size defaults and allowed list, synthesis modules, publication-bias requirements, certainty framework, and field-specific QRP warnings. See `docs/field-config-spec.md` for how to write one.

---

## Working inside a project

Each project opens to a sidebar of phases. Locked phases show a lock icon and explain why when you click them; they unlock automatically as you complete the phases before them.

- **Overview** — Pinned config summary: reporting, registry, required databases, RoB tool, effect-size default, certainty framework, branch choices, and any field-specific cautions.
- **Protocol** — Versioned protocol record (title, reviewer config, etc.). Earlier versions stay accessible.
- **Codebook** — Versioned extraction codebook.
- **Search** — Configure searches across the databases your field requires; the app can generate a runnable PubMed / OpenAlex / CrossRef script for the configuration. Failed search runs are recorded too — PRISMA-S wants the attempt, not just the wins.
- **De-duplicate** — Auto cluster + manual merge. Re-running dedup after screening has started warns you, takes a snapshot first, and never silently deletes decisions. Manual merges carry existing screening and extraction work over to the surviving cluster.
- **Title/abstract** — Screening with IRR (Krippendorff α + Cohen κ) against the thresholds you set in the wizard.
- **Full text** — Second screening pass over the studies that advanced. Full-text exclusions require a codebook reason (PRISMA 2020 item 16b).
- **Extraction** — Per-study extraction against the codebook. Saved work is shown when you revisit a study.
- **Risk of bias** — The tool your config (and design choice) selects: RoB 2, ROBINS-I, ROBINS-E, QUADAS-2, QUIPS, SYRCLE, and others. Saved judgements reload.
- **Share / import** — Export or import `.prismaproj` files (see below).

Projects can be moved to the trash from the Projects screen; they stay restorable for 30 days.

---

## Sharing work with collaborators

The exchange format is **`.prismaproj`** — a zip with `manifest.json` and JSONL files per table, including the project's member roster. Every file's SHA-256 is recorded in the manifest; a tampered, truncated, or padded bundle is rejected on import.

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
- **Snapshots** — Auto-taken before imports and forced dedup re-runs, plus manual any time. 10 auto-snapshots are kept; manual snapshots are unlimited.
- **Versioned protocol and codebook** — Every save is a new version, prior versions retained.

---

## Optional configuration

Set these as environment variables, or in a `.env` file in the directory you launch from (a `.env` is only read when launching from a terminal — the Finder doesn't give apps your shell's working directory):

| Variable | Purpose |
|---|---|
| `PRISMAPI_DATA_DIR` | Override the data directory. |
| `NCBI_EMAIL` | Sent with PubMed/E-utilities requests (NCBI asks for one). |
| `NCBI_API_KEY` | Higher PubMed rate limits. |
| `OPENALEX_EMAIL` | Joins the OpenAlex "polite pool" (faster, more reliable). |
| `PRISMAPI_TRASH_RETENTION_DAYS` | Trash retention (default 30). |
| `PRISMAPI_SNAPSHOT_AUTO_CAP` | Auto-snapshot cap (default 10). |

None of these are required to use the app.

The app only ever makes **outbound** HTTPS calls — to PubMed, OpenAlex, and CrossRef when you run searches. Nothing listens on any port. (The ScienceDirect and Web of Science tutorials talk to those APIs from your own notebook session; the app itself doesn't.)

---

## Building from source

Build a distributable from your local checkout:

```bash
pip install -r requirements.txt
python build.py            # macOS: builds .app + .dmg ; Windows: builds .exe (untested)
python build.py --no-dmg   # macOS only: skip the .dmg step
```

Output:

- macOS: `dist/PrismAPI.app` and `dist/PrismAPI.dmg`
- Windows: `dist/PrismAPI.exe` (build path exists; no Windows build has been verified)

The build uses PyInstaller and bundles the field-config YAMLs, the GUI, and the engine into one app. The PyInstaller spec file is generated during the build — it is not a checked-in input. Bundles are unsigned, so Gatekeeper (and SmartScreen, once Windows builds exist) will warn until code-signing certificates are added.

---

## Running the tests

```bash
pip install pytest pytest-asyncio
pytest -q
```

The suite covers the engine end to end: identity, projects, members, phase gates, screening (both stages), IRR, dedup safety, extraction, RoB tool selection, audit, snapshots, trash, statefile export/import/merge integrity, fields registry validation, and the search adapters. GUI logic is covered only where it's pure (screening-rule normalisation); the screens themselves are thin wrappers around the same RPC dispatcher the tests call directly.

---

## Tutorials

`tutorials/` has runnable Jupyter notebooks for the **PubMed**, **ScienceDirect**, and **Web of Science** APIs — useful if you want to understand or extend what the app does at runtime. See `tutorials/README.md` for per-notebook setup (PubMed uses an `.env` file; ScienceDirect needs a `config.json` with your Elsevier key; Web of Science takes its key in the notebook's config cell).

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
3. Fill in the ten required sections: reporting, registries, databases, extraction template, risk of bias, effect sizes, synthesis, publication bias, certainty, and modules.
4. Add any `branch_choices`, `qrp_warnings`, and `citations`.
5. Validate:

   ```bash
   python -m prismapi.fields.validate
   ```

The schema lives at `prismapi/fields/registry/_schema.json` (JSON Schema Draft 2020-12). It's enforced at startup, so a malformed YAML stops the app cleanly with an error message. The full authoring guide is `docs/field-config-spec.md`.

---

## What's not in this beta

- Synthesis / meta-analysis engine (forest plots, funnel plots, pooling) — planned.
- Publication-bias diagnostics — planned.
- GRADE summary-of-findings tables and manuscript export — planned.
- A conflict-resolution screen (conflicts are counted in the IRR panel; resolving them currently requires the RPC layer).
- Member management after project creation (add collaborators at creation, or merge their work via Share / import).
- Code-signing / notarisation — needs certificates.
- CI release builds — tests and lint run in GitHub Actions on every push; release bundles are still built by hand.

---

## License

GPL-3.0 — see `LICENSE`.
