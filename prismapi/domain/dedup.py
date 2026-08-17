"""De-duplication: pure-Python algorithms operating on Record DTOs.

Strategy (in order; later only catches what earlier missed):
1. DOI exact (case-insensitive, normalized prefix-stripped).
2. PMID exact.
3. Normalized (title + year): lowercased, ASCII-folded, punctuation stripped,
   collapsed whitespace; title must be >= 10 chars; year must match exactly.
4. Fuzzy: rapidfuzz token-SORT ratio on titles >= threshold AND
   author surname Jaccard >= threshold AND |year diff| <= 1. Sort ratio, not
   set ratio: set ratio scores 100 whenever one title's tokens are a subset
   of the other's ("Effects of X" vs "Effects of X: a randomized trial"),
   which merges a paper with its own follow-up.

Fuzzy comparison is blocked by publication year (a record is only compared
against records within `year_tolerance`, plus year-less records), so the
pass stays near-linear on real corpora instead of O(n²).

Every clustered record seeds the identifier indexes, so a later record can
match any member of a cluster, not only its founder.

Each match emits `(record_id, cluster_id, match_reason, match_score)`. The
canonical record per cluster is the first one assigned (the most
metadata-rich, since input is ordered by completeness).
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
    decisions: list[MatchDecision] = []

    doi_index: dict[str, str] = {}
    pmid_index: dict[str, str] = {}
    norm_title_year_index: dict[tuple[str, int], str] = {}
    # Year-blocked fuzzy pool. None holds year-less records, which are
    # candidates for every comparison.
    # Bucket entries carry the pre-normalized title: normalizing every
    # candidate on every probe dominated the fuzzy pass at scale.
    fuzzy_buckets: dict[int | None, list[tuple[RecordSnapshot, str, str]]] = {}

    # Sort: more complete first, so canonical = richest record.
    ordered = sorted(snapshots, key=lambda s: (-s.completeness, str(s.id)))

    def _seed_indexes(snap: RecordSnapshot, key: str) -> None:
        """Make every clustered record matchable, not only cluster founders."""
        ndoi = normalize_doi(snap.doi)
        npmid = normalize_pmid(snap.pmid)
        ntitle = normalize_title(snap.title) if snap.title else ""
        if ndoi:
            doi_index.setdefault(ndoi, key)
        if npmid:
            pmid_index.setdefault(npmid, key)
        if ntitle and snap.year and len(ntitle) >= 10:
            norm_title_year_index.setdefault((ntitle, snap.year), key)
        fuzzy_buckets.setdefault(snap.year, []).append((snap, key, ntitle))

    def _fuzzy_candidates(year: int | None) -> list[tuple[RecordSnapshot, str, str]]:
        if year is None:
            out: list[tuple[RecordSnapshot, str, str]] = []
            for bucket in fuzzy_buckets.values():
                out.extend(bucket)
            return out
        out = list(fuzzy_buckets.get(None, []))
        for y in range(year - year_tolerance, year + year_tolerance + 1):
            out.extend(fuzzy_buckets.get(y, []))
        return out

    def _fuzzy_match(snap: RecordSnapshot, ntitle: str) -> tuple[str, float] | None:
        if not ntitle:
            return None
        authors_a = _author_surnames(snap.authors)
        best: tuple[str, float] | None = None
        for other, other_key, other_ntitle in _fuzzy_candidates(snap.year):
            if other.id == snap.id or not other_ntitle:
                continue
            ratio = fuzz.token_sort_ratio(ntitle, other_ntitle)
            if ratio < fuzzy_title_threshold:
                continue
            authors_b = _author_surnames(other.authors)
            if authors_a and authors_b and _jaccard(authors_a, authors_b) < author_jaccard_threshold:
                continue
            score = ratio / 100.0
            if best is None or score > best[1]:
                best = (other_key, score)
        return best

    for snap in ordered:
        ndoi = normalize_doi(snap.doi)
        npmid = normalize_pmid(snap.pmid)
        ntitle = normalize_title(snap.title) if snap.title else ""

        # Step 1: DOI exact match against an existing cluster
        if ndoi and ndoi in doi_index:
            key = doi_index[ndoi]
            decisions.append(MatchDecision(snap.id, key, "doi", 1.0))
            _seed_indexes(snap, key)
            continue
        # Step 2: PMID exact
        if npmid and npmid in pmid_index:
            key = pmid_index[npmid]
            decisions.append(MatchDecision(snap.id, key, "pmid", 1.0))
            _seed_indexes(snap, key)
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
            _seed_indexes(snap, key)
            continue
        # Step 4: fuzzy title + author + year-tolerant
        match = _fuzzy_match(snap, ntitle)
        if match is not None:
            match_key, score = match
            decisions.append(MatchDecision(snap.id, match_key, "fuzzy_title", score))
            _seed_indexes(snap, match_key)
            continue

        # No match — new cluster. The method label mirrors the key actually
        # used, including the >= 10-char title guard.
        if ndoi:
            key, method, score = f"doi:{ndoi}", "doi", 1.0
        elif npmid:
            key, method, score = f"pmid:{npmid}", "pmid", 1.0
        elif ntitle and snap.year and len(ntitle) >= 10:
            key, method, score = f"ty:{ntitle}:{snap.year}", "title_year_norm", 0.98
        else:
            key, method, score = f"solo:{snap.id}", "solo", 1.0
        decisions.append(MatchDecision(snap.id, key, method, score))
        _seed_indexes(snap, key)

    return decisions
