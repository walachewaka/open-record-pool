"""
Chromaprint fingerprint comparison (MOO-90 D3 L3 / D4).

The MOO-87 analyzer stores each song's fingerprint as base64 of the raw
little-endian int32 stream (fpcalc -raw). similarity() compares two streams
by bit-error-rate at the best alignment offset; ngrams() produces the hashed
shingles behind the indexed candidate search. Pure stdlib, unit-testable
without any audio.
"""
import base64
import struct

# Compare at most this many leading items: chromaprint emits ~8 items per
# second, so 960 items cover ~2 minutes of audio -- plenty to separate
# identical recordings from different ones without unbounded work.
MAX_ITEMS = 960
# Alignment search window: re-encodes shift the stream by codec delay.
MAX_OFFSET = 64
# A comparison needs real overlap to mean anything.
MIN_OVERLAP_ITEMS = 400
MIN_OVERLAP_RATIO = 0.8

# ngram shingling (D4): hash 4 consecutive words, each masked to its top 24
# bits to tolerate low-bit noise, every 16 positions.
NGRAM_WORDS = 4
NGRAM_STRIDE = 16
NGRAM_MASK = 0xFFFFFF00

_FNV_OFFSET = 0xCBF29CE484222325
_FNV_PRIME = 0x100000001B3


def decode_fp(b64_text):
    """base64 -> list of unsigned int32 fingerprint items ([] on garbage)."""
    if not b64_text:
        return []
    try:
        raw = base64.b64decode(b64_text, validate=False)
    except Exception:
        return []
    count = len(raw) // 4
    if count == 0:
        return []
    return list(struct.unpack("<{}I".format(count), raw[: count * 4]))


def encode_fp(items):
    """The inverse of decode_fp, for fixtures and tests."""
    return base64.b64encode(struct.pack("<{}I".format(len(items)), *items)).decode(
        "ascii"
    )


def _popcount(value):
    return bin(value).count("1")


def similarity(fp_a, fp_b):
    """
    Fingerprint similarity in [0, 1]: 1 - 2 * BER at the best alignment
    offset, clamped at 0. Identical streams -> 1.0; unrelated audio hovers
    around BER 0.5 -> 0.0. Returns 0.0 when the overlap is too short to
    judge.
    """
    a = fp_a[:MAX_ITEMS]
    b = fp_b[:MAX_ITEMS]
    if not a or not b:
        return 0.0
    shorter = min(len(a), len(b))
    min_overlap = min(MIN_OVERLAP_ITEMS, int(shorter * MIN_OVERLAP_RATIO))
    if min_overlap < 1:
        return 0.0
    best = 0.0
    for offset in range(-MAX_OFFSET, MAX_OFFSET + 1):
        if offset >= 0:
            seg_a = a[offset:]
            seg_b = b
        else:
            seg_a = a
            seg_b = b[-offset:]
        overlap = min(len(seg_a), len(seg_b))
        if overlap < min_overlap:
            continue
        errors = 0
        for i in range(overlap):
            errors += _popcount(seg_a[i] ^ seg_b[i])
        ber = errors / (overlap * 32.0)
        score = 1.0 - 2.0 * ber
        if score > best:
            best = score
    return min(max(best, 0.0), 1.0)


def ngrams(fp):
    """
    The hashed shingle set of a fingerprint (D4): FNV-1a over 4 masked
    consecutive words at stride 16, folded into the signed BIGINT range so
    the values round-trip through PostgreSQL.
    """
    result = set()
    limit = min(len(fp), MAX_ITEMS) - NGRAM_WORDS + 1
    for start in range(0, max(limit, 0), NGRAM_STRIDE):
        end = start + NGRAM_WORDS
        value = _FNV_OFFSET
        for word in fp[start:end]:
            masked = word & NGRAM_MASK
            for shift in (0, 8, 16, 24):
                value ^= (masked >> shift) & 0xFF
                value = (value * _FNV_PRIME) & 0xFFFFFFFFFFFFFFFF
        if value >= 0x8000000000000000:
            value -= 0x10000000000000000
        result.add(value)
    return result
