"""
Artist/title normalization for the recording identity model (MOO-90).

normalize_title splits the mix designation out of a title -- "Track
(Extended Mix)" -> ("track", "extended mix") -- because the mix name is the
line between "duplicate" and "different recording": an extended mix and a
radio edit are DIFFERENT recordings and must never merge. Pure stdlib.
"""
import re
import unicodedata

# A trailing (...) or [...] group counts as the mix designation only when it
# contains one of these words -- "(feat. X)" or "(Deluxe)" are not mixes.
_MIX_WORDS = (
    "remix",
    "mix",
    "edit",
    "dub",
    "version",
    "instrumental",
    "extended",
    "radio",
    "club",
    "original",
    "rework",
    "bootleg",
    "vip",
)
_MIX_PATTERN = re.compile(
    r"[\(\[]([^\(\)\[\]]*\b(?:{})\b[^\(\)\[\]]*)[\)\]]\s*$".format(
        "|".join(_MIX_WORDS)
    ),
    re.IGNORECASE,
)
_FEAT_PATTERN = re.compile(r"[\(\[]?\s*\b(?:feat|ft|featuring)[\s\.].*$", re.IGNORECASE)
_NON_WORD = re.compile(r"[^\w\s]", re.UNICODE)
_WHITESPACE = re.compile(r"\s+")


def _basic_norm(text):
    """Lowercase, de-accent, strip punctuation, collapse whitespace."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("&", " and ")
    text = _NON_WORD.sub(" ", text)
    text = _WHITESPACE.sub(" ", text).strip()
    if text.startswith("the "):
        text = text[4:]
    return text


def normalize_artist(value):
    """The normalized artist name, or "" for a missing tag."""
    if not value:
        return ""
    return _basic_norm(_FEAT_PATTERN.sub("", value))[:255]


def normalize_title(value):
    """
    (title_norm, mix_norm) for a raw title tag. The mix designation is the
    trailing parenthesized/bracketed group containing a mix word; a title
    without one is mix "original".
    """
    if not value:
        return "", "original"
    title = value
    mix = "original"
    match = _MIX_PATTERN.search(title)
    if match:
        mix = _basic_norm(match.group(1)) or "original"
        title = title[: match.start()]
    title = _FEAT_PATTERN.sub("", title)
    return _basic_norm(title)[:255], mix[:100]


def normalize_mix(value):
    """A raw mix designation ("Extended Mix") normalized, "" for empty."""
    if not value:
        return ""
    return _basic_norm(value)[:100]


def song_norms(artist, title):
    """The (artist_norm, title_norm, mix_norm) triple for a song's tags."""
    artist_norm = normalize_artist(artist)
    title_norm, mix_norm = normalize_title(title)
    return artist_norm, title_norm, mix_norm
