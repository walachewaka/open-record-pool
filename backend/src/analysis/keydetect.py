"""
Musical key detection (MOO-87 D1): a time-averaged chromagram correlated
against the 24 Krumhansl-Schmuckler major/minor key profiles. The winning
rotation names the key in compact standard notation ("C", "F#m") so the
existing src/utils/camelot.py maps it to the Camelot wheel unchanged.

numpy is imported lazily inside detect_key: this module is imported by the
worker task path only, and the Python 3.7 harness venv (which mocks the
engine seam) must be able to import the package without numpy installed.
"""

PITCH_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Krumhansl-Schmuckler key profiles (probe-tone ratings), tonic first.
MAJOR_PROFILE = [
    6.35,
    2.23,
    3.48,
    2.33,
    4.38,
    4.09,
    2.52,
    5.19,
    2.39,
    3.66,
    2.29,
    2.88,
]
MINOR_PROFILE = [
    6.33,
    2.68,
    3.52,
    5.38,
    2.60,
    3.53,
    2.54,
    4.75,
    3.98,
    2.69,
    3.34,
    3.17,
]


def detect_key(chroma_mean):
    """
    (key, confidence) for a length-12 time-averaged chroma vector (index 0 =
    C). The key is "C".."B" for major and "Cm".."Bm" for minor; confidence is
    the winning Pearson correlation. Returns (None, None) on a degenerate
    (constant/empty) chroma vector.
    """
    import numpy

    chroma = numpy.asarray(chroma_mean, dtype=numpy.float64).flatten()
    if chroma.shape[0] != 12 or float(numpy.std(chroma)) == 0.0:
        return (None, None)

    major = numpy.asarray(MAJOR_PROFILE)
    minor = numpy.asarray(MINOR_PROFILE)
    best_key = None
    best_corr = None
    for tonic in range(12):
        rotated = numpy.roll(chroma, -tonic)
        for profile, suffix in ((major, ""), (minor, "m")):
            corr = float(numpy.corrcoef(rotated, profile)[0, 1])
            if best_corr is None or corr > best_corr:
                best_corr = corr
                best_key = PITCH_NAMES[tonic] + suffix
    return (best_key, best_corr)
