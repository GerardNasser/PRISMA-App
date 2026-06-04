# API tutorials

Interactive, teachable versions of the per-database API pull scripts the
desktop app generates at runtime. Open any notebook in Jupyter, fill in
your credentials in `env_template`, and you can run a real search end to
end while seeing every request, response, and decision the runtime script
makes silently.

The runtime counterparts live under [`prismapi/services/search_scripts/`](../prismapi/services/search_scripts/):
when the Search screen generates `pubmed_search.py` (or `crossref_search.py`,
`openalex_search.py`, etc.), it follows the same request shape and field
parsing demonstrated here.

## Per-database

| Database | Notebook | Companion files |
|---|---|---|
| PubMed | [`pubmed/PubMed_API.ipynb`](pubmed/PubMed_API.ipynb) | `requirements.txt`, `env_template` |
| ScienceDirect (Elsevier) | [`sciencedirect/SciDir_API.ipynb`](sciencedirect/SciDir_API.ipynb) | — |
| Web of Science | [`wos/WoS_API.ipynb`](wos/WoS_API.ipynb) | `env_template`, `example_processed_results.csv`, `screenshots/` |

## Running a notebook

```bash
# 1. Stand up a Python env (3.11+).
python3 -m venv .venv
source .venv/bin/activate

# 2. Install the notebook's requirements (if it ships one).
pip install -r pubmed/requirements.txt   # PubMed example

# 3. Copy env_template → .env and fill in your API keys.
cp pubmed/env_template pubmed/.env
# edit pubmed/.env

# 4. Launch Jupyter.
pip install jupyterlab
jupyter lab pubmed/PubMed_API.ipynb
```

## What goes here vs. what doesn't

This directory holds **interactive teachable scripts** — Jupyter notebooks
that walk through one database's API with prose, intermediate prints, and
example output. New tutorials slot in as `tutorials/<database>/<name>.ipynb`
plus whatever requirements / env / sample-output files the notebook needs
to run.

What does **not** go here:

- The runtime per-database scripts the app generates → those live in
  `prismapi/services/search_scripts/`.
- Methodology PDFs (PRISMA 2020 checklists, etc.) → those live in
  `docs/references/`.
- App documentation → `docs/`.
