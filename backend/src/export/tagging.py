"""
ID3 rewrite on the bundled COPY of a track (MOO-86).

The DJ software reads metadata out of the file itself, so the copy that lands
on the stick must carry our clean DB metadata (MOO-82 edits, MOO-85 enrichment,
MOO-87 analysis) rather than whatever the original file was tagged with. This
NEVER touches an original: /music is read-only and file-tag writeback is
MOO-75's job -- retag_copy() is only ever called on a staged copy.

Frames we do not set are left exactly as they were, which is what preserves the
Serato GEOB cue/beatgrid frames an incoming file may already carry (we do not
interpret them; we just do not destroy them).
"""
from mutagen.id3 import ID3, ID3NoHeaderError, TALB, TBPM, TCON, TDRC, TIT2, TKEY
from mutagen.id3 import TPE1, TRCK

from src.utils.keys import key_forms


def track_bpm(song):
    """Tag BPM wins, analyzer fills the gap (MOO-87 D5 precedence)."""
    return song.bpm or song.bpm_detected


def track_key(song):
    return song.musical_key or song.key_detected


def retag_copy(path, song, position, fmt):
    """
    Rewrite [path]'s ID3 tags from the [song] row. MP3 only -- any other
    container is left byte-identical (its original tags still travel with it).
    Returns True when tags were written.
    """
    if not path.lower().endswith(".mp3"):
        return False
    try:
        tags = ID3(path)
    except ID3NoHeaderError:
        tags = ID3()

    def put(frame_cls, value):
        if value not in (None, ""):
            tags.setall(frame_cls.__name__, [frame_cls(encoding=3, text=[str(value)])])

    put(TIT2, song.title)
    put(TPE1, song.artist)
    put(TALB, song.album)
    put(TCON, song.genre)
    put(TRCK, position)
    put(TDRC, song.year)

    bpm = track_bpm(song)
    if bpm:
        put(TBPM, "{:.2f}".format(float(bpm)))

    keys = key_forms(track_key(song))
    if keys:
        # Serato browses the Camelot wheel; Traktor/rekordbox read standard
        # notation and derive their own wheel from it.
        put(TKEY, keys["camelot"] if fmt == "serato" else keys["standard"])

    tags.save(path, v2_version=3)
    return True
