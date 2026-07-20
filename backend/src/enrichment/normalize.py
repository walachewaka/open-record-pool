"""
Normalization + fuzzy similarity for Beatport track matching (MOO-85).

Pure stdlib (difflib.SequenceMatcher only -- no new fuzzy-matching
dependency, per the issue's ground rules). This is a sibling of
src/utils/normalize.py (MOO-90), which decides recording IDENTITY (is this
the same recording -- used for dedup); this module decides SEARCH INPUT and
MATCH SCORING against an external catalog -- a different job, kept in its
own module so a change to one never risks the other's behavior.
"""
import re
import unicodedata
from difflib import SequenceMatcher

# Same mix-word vocabulary as src/utils/normalize.py, plus Beatport's own
# "Original Mix" default is handled separately below.
_MIX_WORDS = (
    "remix",
    "mix",
    "edit",
    "dub",
    "version",
    "extended",
    "radio",
    "club",
    "instrumental",
    "rework",
    "bootleg",
    "vip",
)
_MIX_PATTERN = re.compile(
    r"\(([^()]*\b(?:{})\b[^()]*)\)\s*$".format("|".join(_MIX_WORDS)),
    re.IGNORECASE,
)
_NON_WORD = re.compile(r"[^\w\s]", re.UNICODE)
_WHITESPACE = re.compile(r"\s+")

DEFAULT_MIX_NAME = "original mix"


def normalize(text):
    """Lowercase, de-accent (Unicode NFKD), strip punctuation (except
    parens, handled by split_mix before this runs), collapse whitespace."""
    if not text:
        return ""
    value = unicodedata.normalize("NFKD", str(text))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower()
    value = _NON_WORD.sub(" ", value)
    return _WHITESPACE.sub(" ", value).strip()


def split_mix(title):
    """
    (base_title, mix_name) from a raw local title: a trailing "(... mix
    word ...)" group is the mix name (both already normalized); a title with
    no such group defaults to "original mix" (Beatport's own convention for
    untagged tracks), so an untagged local track still compares cleanly
    against a Beatport "Original Mix" candidate.
    """
    if not title:
        return "", DEFAULT_MIX_NAME
    match = _MIX_PATTERN.search(title)
    if match:
        mix_name = normalize(match.group(1)) or DEFAULT_MIX_NAME
        base = title[: match.start()]
    else:
        mix_name = DEFAULT_MIX_NAME
        base = title
    return normalize(base), mix_name


def similarity(a, b):
    """
    Symmetric best-effort string similarity in [0, 1]: the plain
    SequenceMatcher ratio, or the ratio with each string's words
    alphabetized (so "A & B" matches "B & A"), whichever is higher. Two
    empty strings are a perfect match (nothing to disagree on); one empty
    and one non-empty never scores above 0.
    """
    norm_a = normalize(a)
    norm_b = normalize(b)
    if not norm_a and not norm_b:
        return 1.0
    if not norm_a or not norm_b:
        return 0.0
    direct = SequenceMatcher(None, norm_a, norm_b).ratio()
    scrambled = SequenceMatcher(
        None, " ".join(sorted(norm_a.split())), " ".join(sorted(norm_b.split()))
    ).ratio()
    return max(direct, scrambled)
