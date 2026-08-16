"""Library of validated search filters.

Each filter is keyed by id and exposes per-adapter query fragments. Field
configs reference filter ids via `databases.auto_filters`; the search service
appends them as ANDed clauses to the user's query, scoped to adapters the
filter supports.

References:
- Hooijmans CR et al. 2010. Enhancing search efficiency by means of a search
  filter for finding all studies on animal experimentation in PubMed.
  Lab Anim 44(3):170–175.
- de Vries RBM et al. 2014. Updated version of the Embase search filter for
  animal studies. Lab Anim 48(1):88.
- Cochrane Highly Sensitive Search Strategy for identifying randomized trials
  in MEDLINE (Cochrane Handbook v6, Chapter 4 / Appendix 1).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SearchFilter:
    id: str
    label: str
    description: str
    citation: str | None = None
    # Map: adapter_id -> query fragment to AND into the user query.
    fragments: dict[str, str] = field(default_factory=dict)

    def fragment_for(self, adapter_id: str) -> str | None:
        return self.fragments.get(adapter_id)


def combine_query(query: str, fragments: list[str]) -> str:
    """AND filter fragments into a boolean query string.

    Fragments beginning with "NOT " become `(query) NOT (term)` — PubMed's
    NOT is a binary operator, so `AND (NOT term)` is not a safe encoding.

    OpenAlex fragments never come through here: they are filter-parameter
    expressions, not query syntax (see the openalex adapter).
    """
    out = query
    for f in fragments:
        if f.upper().startswith("NOT "):
            out = f"({out}) NOT ({f[4:]})"
        else:
            out = f"({out}) AND ({f})"
    return out


_LIBRARY: dict[str, SearchFilter] = {}


def _register(f: SearchFilter) -> None:
    if f.id in _LIBRARY:
        raise ValueError(f"Duplicate filter: {f.id}")
    _LIBRARY[f.id] = f


_register(
    SearchFilter(
        id="hooijmans_pubmed_animal",
        label="Hooijmans animal-studies filter (PubMed)",
        description="Sensitive search filter to retrieve animal studies from PubMed/MEDLINE.",
        citation="Hooijmans CR et al. 2010. Lab Anim 44(3):170-175.",
        fragments={
            # Compact form of the validated filter — uses MeSH + free-text.
            "pubmed": (
                "(animals[MeSH:noexp] OR animal experimentation[MeSH] OR models, animal[MeSH] "
                "OR mice[MeSH] OR rats[MeSH] OR rodentia[MeSH] OR primates[MeSH] OR "
                "dogs[MeSH] OR cats[MeSH] OR swine[MeSH] OR (animal[tiab] OR animals[tiab] OR "
                "mouse[tiab] OR mice[tiab] OR murine[tiab] OR rat[tiab] OR rats[tiab] OR "
                "rodent*[tiab] OR rabbit*[tiab] OR canine[tiab] OR feline[tiab] OR porcine[tiab] "
                "OR primate*[tiab] OR monkey*[tiab] OR baboon*[tiab]))"
            ),
        },
    )
)

_register(
    SearchFilter(
        id="de_vries_embase_animal",
        label="de Vries animal-studies filter (Embase)",
        description="Updated Embase search filter for animal studies.",
        citation="de Vries RBM et al. 2014. Lab Anim 48(1):88.",
        fragments={
            # Embase syntax (Emtree). When importing via RIS the filter is
            # documented but not auto-applied — record the intent.
            "ris_import": "(animal*:ti,ab,kw OR experimental animal/exp OR rodent/exp OR primate/exp)",
        },
    )
)

_register(
    SearchFilter(
        id="cochrane_rct_pubmed",
        label="Cochrane Highly Sensitive RCT filter (PubMed)",
        description="Cochrane Handbook v6 RCT filter for MEDLINE/PubMed.",
        citation="Cochrane Handbook v6, Chapter 4 / Appendix 1.",
        fragments={
            "pubmed": (
                "(randomized controlled trial[pt] OR controlled clinical trial[pt] OR "
                "randomized[tiab] OR placebo[tiab] OR randomly[tiab] OR trial[tiab] OR "
                "groups[tiab]) NOT (animals[mh] NOT humans[mh])"
            ),
        },
    )
)

# OpenAlex fragments are *filter parameter* expressions (language:en,
# type:!review), not query-string syntax — the adapter sends them via
# `filter=`, never inside `search=`, where they would match as literal text.
_register(
    SearchFilter(
        id="english_language",
        label="English language only",
        description=(
            "Restrict to English-language records. Use sparingly; many SR "
            "guidelines discourage language restrictions unless justified. "
            "CrossRef has no language filter, so this does not apply there."
        ),
        fragments={
            "pubmed": "english[lang]",
            "openalex": "language:en",
        },
    )
)

_register(
    SearchFilter(
        id="exclude_reviews",
        label="Exclude reviews",
        description="Exclude review article types (use during primary-study identification).",
        fragments={
            "pubmed": "NOT (review[pt] OR systematic review[pt])",
            "openalex": "type:!review",
        },
    )
)


def list_filters() -> list[SearchFilter]:
    return list(_LIBRARY.values())


def get_filter(filter_id: str) -> SearchFilter | None:
    return _LIBRARY.get(filter_id)
