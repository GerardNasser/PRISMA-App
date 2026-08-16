# API tutorials

Interactive, runnable walkthroughs of the per-database APIs the desktop
app talks to. Open a notebook in Jupyter, set up the credentials it needs,
and you can run a real search end to end while seeing every request and
response the app's generated scripts handle silently.

The runtime counterpart is the module
[`prismapi/services/search_scripts.py`](../prismapi/services/search_scripts.py):
when the Search screen generates `pubmed_search.py` (or
`openalex_search.py`, `crossref_search.py`), it follows the same request
shape and field parsing demonstrated here. The PubMed and ScienceDirect
notebooks are code-first with inline comments; the Web of Science notebook
adds step-by-step prose and screenshots.

## Per-database

| Database | Notebook | Setup |
|---|---|---|
| PubMed | [`pubmed/PubMed_API.ipynb`](pubmed/PubMed_API.ipynb) | `pip install -r requirements.txt`; copy `env_template` to `.env` |
| ScienceDirect (Elsevier) | [`sciencedirect/SciDir_API.ipynb`](sciencedirect/SciDir_API.ipynb) | `pip install elsapy`; create `config.json` with your API key (see the notebook's first cell) |
| Web of Science | [`wos/WoS_API.ipynb`](wos/WoS_API.ipynb) | Paste your Starter API key into the config cell; sample output in `example_processed_results.csv` |

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

This directory holds runnable Jupyter notebooks that each walk through one
database's API. New tutorials slot in as `tutorials/<database>/<name>.ipynb`
plus whatever requirements / env / sample-output files the notebook needs
to run.

What does not go here:

- The script templates the app generates at runtime — those live in
  `prismapi/services/search_scripts.py`.
- Methodology PDFs (PRISMA 2020 checklists, etc.) — those live in
  `docs/references/`.
- App documentation — `docs/`.
