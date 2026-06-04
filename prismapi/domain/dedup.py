"""De-duplication: pure-Python algorithms operating on Record DTOs.

Strategy (in order; later only catches what earlier missed):
1. DOI exact (case-insensitive, normalized prefix-stripped).
2. PMID exact.
3. Normalized (title + year): lowercased, ASCII-folded, punctuation stripped,
   collapsed whitespace; title must be >= 10 chars; year must match exactly.
4. Fuzzy: rapidfuzz token-set ratio on titles >= threshold AND
   author surname Jaccard >= threshold AND |year diff| <= 1.

Each match emits `(record_id, cluster_id, match_reason, match_score)`. The
canonical record per cluster is the first one assigned (often the most
metadata-rich, which we can rank by completeness).
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from dataclasses import dataclass

from rapidfuzz import fuzz


@dataclass(frozen=True)
class RecordSnapshot:
    id: uuid.UUID
    title: str
    year: int | None
    doi: str | None
    pmid: str | None
    authors: str | None
    completeness: int  # higher = more fields populated


@dataclass(frozen=True)
class MatchDecision:
    record_id: uuid.UUID
    cluster_key: str  # arbitrary deterministic key used while clustering
    method: str
    score: float


_DOI_PREFIX_RE = re.compile(r"^(?:https?://)?(?:dx\.)?doi\.org/", re.IGNORECASE)
_PUNCT_RE = re.compile(r"[^\w\s]+")
_WS_RE = re.compile(r"\s+")


def normalize_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    stripped = _DOI_PREFIX_RE.sub("", doi.strip()).lower()
    return stripped or None


def normalize_pmid(pmid: str | None) -> str | None:
    if not pmid:
        return None
    digits = re.sub(r"\D", "", pmid)
    return digits or None


def normalize_title(title: str) -> str:
    folded = unicodedata.normalize("NFKD", title)
    folded = folded.encode("ascii", "ignore").decode("ascii")
    folded = _PUNCT_RE.sub(" ", folded.lower())
    folded = _WS_RE.sub(" ", folded).strip()
    return folded


def _author_surnames(authors: str | None) -> set[str]:
    if not authors:
        return set()
    surnames: set[str] = set()
    for chunk in re.split(r"[;,]", authors):
        chunk = chunk.strip()
        if not chunk:
            continue
        # Take the first all-letter token as surname proxy (works for both
        # "Smith, J" and "Smith J" and "J Smith").
        tokens = re.findall(r"[A-Za-z][A-Za-z'-]+", chunk)
        if not tokens:
            continue
        # Prefer the longest token, since initials are 1 letter.
        longest = max(tokens, key=len)
        if len(longest) > 1:
            surnames.add(longest.lower())
    return surnames


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def cluster_records(
    snapshots: list[RecordSnapshot],
    *,
    fuzzy_title_threshold: int = 92,
    author_jaccard_threshold: float = 0.5,
    year_tolerance: int = 1,
) -> list[MatchDecision]:
    """Cluster records by exact then fuzzy keys. Deterministic order matters
    only for which record becomes canonical (first in input wins ties)."""
    # cluster_key -> canonical record_id
    canon: dict[str, uuid.UUID] = {}
    # record_id -> (cluster_key, method, score)
    decisions: list[MatchDecision] = []

    # Pass 1: DOI exact
    doi_index: dict[str, str] = {}
    pmid_index: dict[str, str] = {}
    norm_title_year_index: dict[tuple[str, int], str] = {}
    fuzzy_pool: list[RecordSnapshot] = []
    fuzzy_ids: set[uuid.UUID] = set()

    # Sort: more complete first, so canonical = richest record.
    ordered = sorted(snapshots, key=lambda s: (-s.completeness, str(s.id)))

    def _seed_indexes(snap: RecordSnapshot, key: str) -> None:
        ndoi = normalize_doi(snap.doi)
        npmid = normalize_pmid(snap.pmid)
        ntitle = normalize_title(snap.title) if snap.title else ""
        if ndoi:
            doi_index.setdefault(ndoi, key)
        if npmid:
            pmid_index.setdefault(npmid, key)
        if ntitle and snap.year and len(ntitle) >= 10:
            norm_title_year_index.setdefault((ntitle, snap.year), key)
        fuzzy_pool.append(snap)
        fuzzy_ids.add(snap.id)

    def _fuzzy_match(snap: RecordSnapshot, ntitle: str) -> tuple[RecordSnapshot, float] | None:
        if not ntitle:
            return None
        authors_a = _author_surnames(snap.authors)
        best: tuple[RecordSnapshot, float] | None = None
        for other in fuzzy_pool:
            if other.id == snap.id or not other.title:
                continue
            if snap.year and other.year and abs(snap.year - other.year) > year_tolerance:
                continue
            ratio = fuzz.token_set_ratio(ntitle, normalize_title(other.title))
            if ratio < fuzzy_title_threshold:
                continue
            authors_b = _author_surnames(other.authors)
            if authors_a and authors_b and _jaccard(authors_a, authors_b) < author_jaccard_threshold:
                continue
            score = ratio / 100.0
            if best is None or score > best[1]:
                best = (other, score)
        return best

    for snap in ordered:
        ndoi = normalize_doi(snap.doi)
        npmid = normalize_pmid(snap.pmid)
        ntitle = normalize_title(snap.title) if snap.title else ""

        # Step 1: DOI exact match against an existing cluster
        if ndoi and ndoi in doi_index:
            key = doi_index[ndoi]
            decisions.append(MatchDecision(snap.id, key, "doi", 1.0))
            continue
        # Step 2: PMID exact
        if npmid and npmid in pmid_index:
            key = pmid_index[npmid]
            decisions.append(MatchDecision(snap.id, key, "pmid", 1.0))
            continue
        # Step 3: normalized title + year exact
        if (
            ntitle
            and snap.year
            and len(ntitle) >= 10
            and (ntitle, snap.year) in norm_title_year_index
        ):
            key = norm_title_year_index[(ntitle, snap.year)]
            decisions.append(MatchDecision(snap.id, key, "title_year_norm", 0.98))
            continue
        # Step 4: fuzzy title + author + year-tolerant
        match = _fuzzy_match(snap, ntitle)
        if match is not None:
            other, score = match
            other_decision = next(d for d in decisions if d.record_id == other.id)
            decisions.append(MatchDecision(snap.id, other_decision.cluster_key, "fuzzy_title", score))
            continue

        # No match — new cluster. Seed all indexes for future records.
        if ndoi:
            key = f"doi:{ndoi}"
        elif npmid:
            key = f"pmid:{npmid}"
        elif ntitle and snap.year and len(ntitle) >= 10:
            key = f"ty:{ntitle}:{snap.year}"
        else:
            key = f"solo:{snap.id}"
        canon[key] = snap.id
        method = (
            "doi" if ndoi else "pmid" if npmid else "title_year_norm" if ntitle and snap.year else "solo"
        )
        decisions.append(MatchDecision(snap.id, key, method, 1.0 if method != "title_year_norm" else 0.98))
        _seed_indexes(snap, key)

    return decisions
