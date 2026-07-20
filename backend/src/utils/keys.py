"""
Musical-key notations the DJ exporters need (MOO-86).

Every DJ ecosystem spells the same wheel position differently: Serato browses
in Camelot ("8A"), Traktor writes Open Key text ("1m") plus its own 0-23
integer, rekordbox wants standard notation ("Am"). We normalize whatever the
tag/analyzer gave us to Camelot with utils/camelot.py, then read the other
spellings off one table.

Pure, no IO, never raises.
"""
from src.utils.camelot import to_camelot

# Camelot code -> (standard, open key, Traktor MUSICAL_KEY int).
# The Traktor int is chromatic: majors C=0..B=11, minors Cm=12..Bm=23.
KEY_FORMS = {
    "1A": ("Abm", "6m", 20),
    "1B": ("B", "6d", 11),
    "2A": ("Ebm", "7m", 15),
    "2B": ("F#", "7d", 6),
    "3A": ("Bbm", "8m", 22),
    "3B": ("Db", "8d", 1),
    "4A": ("Fm", "9m", 17),
    "4B": ("Ab", "9d", 8),
    "5A": ("Cm", "10m", 12),
    "5B": ("Eb", "10d", 3),
    "6A": ("Gm", "11m", 19),
    "6B": ("Bb", "11d", 10),
    "7A": ("Dm", "12m", 14),
    "7B": ("F", "12d", 5),
    "8A": ("Am", "1m", 21),
    "8B": ("C", "1d", 0),
    "9A": ("Em", "2m", 16),
    "9B": ("G", "2d", 7),
    "10A": ("Bm", "3m", 23),
    "10B": ("D", "3d", 2),
    "11A": ("F#m", "4m", 18),
    "11B": ("A", "4d", 9),
    "12A": ("C#m", "5m", 13),
    "12B": ("E", "5d", 4),
}


def key_forms(raw):
    """
    Every spelling of [raw]'s key, or None when the notation is unknown:
    {"camelot", "standard", "open_key", "traktor_int"}.
    """
    camelot = to_camelot(raw)
    if camelot not in KEY_FORMS:
        return None
    standard, open_key, traktor_int = KEY_FORMS[camelot]
    return {
        "camelot": camelot,
        "standard": standard,
        "open_key": open_key,
        "traktor_int": traktor_int,
    }
