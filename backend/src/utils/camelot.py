"""
Best-effort mapping between musical key notations and the Camelot wheel.

MP3 key tags (TKEY) come in many flavors: Camelot codes ("8A"), compact
standard notation ("Am", "F#m", "Ab"), or verbose ("A minor", "Ab major").
DJs browse by Camelot code, so we derive it where we can and never fail on
a notation we do not recognize (MOO-65).
"""
import re

# (tonic, mode) -> Camelot code, including enharmonic spellings.
CAMELOT_BY_KEY = {
    ("g#", "minor"): "1A",
    ("ab", "minor"): "1A",
    ("b", "major"): "1B",
    ("d#", "minor"): "2A",
    ("eb", "minor"): "2A",
    ("f#", "major"): "2B",
    ("gb", "major"): "2B",
    ("a#", "minor"): "3A",
    ("bb", "minor"): "3A",
    ("c#", "major"): "3B",
    ("db", "major"): "3B",
    ("f", "minor"): "4A",
    ("g#", "major"): "4B",
    ("ab", "major"): "4B",
    ("c", "minor"): "5A",
    ("d#", "major"): "5B",
    ("eb", "major"): "5B",
    ("g", "minor"): "6A",
    ("a#", "major"): "6B",
    ("bb", "major"): "6B",
    ("d", "minor"): "7A",
    ("f", "major"): "7B",
    ("a", "minor"): "8A",
    ("c", "major"): "8B",
    ("e", "minor"): "9A",
    ("g", "major"): "9B",
    ("b", "minor"): "10A",
    ("d", "major"): "10B",
    ("f#", "minor"): "11A",
    ("gb", "minor"): "11A",
    ("a", "major"): "11B",
    ("c#", "minor"): "12A",
    ("db", "minor"): "12A",
    ("e", "major"): "12B",
}

_CAMELOT_PATTERN = re.compile(r"^(1[0-2]|0?[1-9])\s*([ABab])$")
# Open Key notation (Traktor et al.): 1-12 + m (minor) / d (dur = major).
# Same wheel as Camelot rotated by 7: Open Key 1m = Am = Camelot 8A (MOO-87).
_OPENKEY_PATTERN = re.compile(r"^(1[0-2]|0?[1-9])\s*([MmDd])$")
_STANDARD_PATTERN = re.compile(r"^([A-Ga-g])\s*([#♯b♭]?)\s*(.*)$")

_MINOR_SUFFIXES = {"m", "min", "min.", "minor", "-", "moll"}
_MAJOR_SUFFIXES = {"", "maj", "maj.", "major", "dur"}


def to_camelot(raw):
    """
    Returns the Camelot code ("1A".."12B") for a raw key tag, or None when
    the notation is unknown. Never raises.
    """
    if not raw:
        return None
    value = str(raw).strip()

    match = _CAMELOT_PATTERN.match(value)
    if match:
        return "{}{}".format(int(match.group(1)), match.group(2).upper())

    match = _OPENKEY_PATTERN.match(value)
    if match:
        number = (int(match.group(1)) + 6) % 12 + 1  # rotate by +7 on the wheel
        letter = "A" if match.group(2).lower() == "m" else "B"
        return "{}{}".format(number, letter)

    match = _STANDARD_PATTERN.match(value)
    if not match:
        return None
    letter, accidental, suffix = match.groups()
    tonic = letter.lower()
    if accidental in ("#", "♯"):
        tonic += "#"
    elif accidental in ("b", "♭"):
        tonic += "b"

    # An exact trailing "M" conventionally means major ("AM"), while the
    # usual lowercase "m" ("Am") means minor.
    if suffix == "M":
        mode = "major"
    elif suffix.strip().lower() in _MINOR_SUFFIXES:
        mode = "minor"
    elif suffix.strip().lower() in _MAJOR_SUFFIXES:
        mode = "major"
    else:
        return None
    return CAMELOT_BY_KEY.get((tonic, mode))


def key_variants(camelot):
    """
    All the raw key notations that best-effort map to the given Camelot
    code, for case-insensitive filtering. Includes the code itself.
    """
    variants = {camelot}
    if len(camelot) == 2:  # zero-padded form some taggers emit, e.g. "08A"
        variants.add("0" + camelot)
    # The Open Key spelling of the same wheel position (inverse of the +7
    # rotation in to_camelot), e.g. Camelot 8A -> Open Key 1m.
    open_number = (int(camelot[:-1]) + 4) % 12 + 1
    open_letter = "m" if camelot[-1] == "A" else "d"
    open_key = "{}{}".format(open_number, open_letter)
    variants.add(open_key)
    if open_number < 10:
        variants.add("0" + open_key)
    for (tonic, mode), code in CAMELOT_BY_KEY.items():
        if code != camelot:
            continue
        name = tonic.capitalize()
        if mode == "minor":
            variants.update(
                {
                    name + "m",
                    name + "min",
                    name + " min",
                    name + "minor",
                    name + " minor",
                }
            )
        else:
            variants.update(
                {name, name + "maj", name + " maj", name + "major", name + " major"}
            )
    return sorted(variants)
