"""Mechanical pre-filter over the PFS registry's real (internal-only, never
surfaced) descriptions -- narrows ~17k codes down to a small candidate set
worth showing an LLM for the final semantic match. See code_candidates.py
for why this exists: the LLM's own memorized knowledge of specific/newer
CPT codes is unreliable (confirmed empirically -- it can confidently state a
wrong definition for a real code), so candidates should be found by
searching real data, not recalled from training.

TUNING NOTE (found empirically, not assumed): CMS's descriptions are
consistently, heavily abbreviated in a way that drops vowels and often
interior letters ("Img rta detc/mntr ds poc aly" for retinal-disease
autonomous point-of-care analysis). A "strip vowels, check substring"
match recovers real semantic hits (retina->rta, detection->detc,
analysis->aly all check out), but a single short (2-character) token match
is not reliable on its own -- e.g. "anes"/"upr"/"ant" (from an unrelated
anesthesia code) spuriously matched "diagnostic"/"interpret"/"primary" via
pure 2-character coincidence, at a rate high enough to pass a naive
threshold. Requiring longer stripped tokens (3+) to eliminate that
false positive also eliminates most of the real signal, since many genuine
abbreviations are themselves only 2 characters after stripping.

There is no single mechanical threshold that is both tight enough to reject
that class of noise and loose enough to keep the real signal -- so this
module is deliberately NOT the final decision-maker. It stays loose (favors
recall), and a separate LLM call (code_candidates.py) makes the actual
precision judgment against this pre-filtered, real, grounded shortlist --
which is then still subject to the existing hard verification step
regardless of what either step proposes.
"""

import re

_MIN_TOKEN_LEN = 3  # before vowel-stripping -- filters connector words (the/to/in/a)
_MIN_STRIPPED_LEN = 2  # after vowel-stripping
_MIN_MATCHING_TOKENS = 1  # deliberately loose -- see module docstring
_MAX_PREFILTER_RESULTS = 30  # keeps the downstream LLM call's input bounded

_VOWELS = frozenset("aeiou")


def _strip_vowels(word: str) -> str:
    return "".join(c for c in word if c not in _VOWELS)


def _stripped_tokens(text: str) -> list[str]:
    words = re.findall(r"[a-zA-Z]+", text.lower())
    return [
        stripped for stripped in (_strip_vowels(w) for w in words if len(w) >= _MIN_TOKEN_LEN)
        if len(stripped) >= _MIN_STRIPPED_LEN
    ]


def _match_count(query_stripped: list[str], description_stripped: list[str]) -> int:
    # Directional: the (typically abbreviated, shorter) description token
    # must be a substring of a (typically fuller) query token -- matches the
    # direction CMS's abbreviations actually compress in.
    return sum(1 for d in set(description_stripped) if any(d in q for q in query_stripped))


def find_candidates(query_text: str, descriptions: dict[str, str]) -> list[str]:
    """Returns up to _MAX_PREFILTER_RESULTS codes, ranked by match count --
    a pre-filter for an LLM to make the real judgment call on, not a final
    answer in itself."""
    query_stripped = _stripped_tokens(query_text)
    if not query_stripped:
        return []
    scored: list[tuple[int, str]] = []
    for code, description in descriptions.items():
        matches = _match_count(query_stripped, _stripped_tokens(description))
        if matches >= _MIN_MATCHING_TOKENS:
            scored.append((matches, code))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [code for _, code in scored[:_MAX_PREFILTER_RESULTS]]
