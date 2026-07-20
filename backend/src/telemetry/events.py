"""
The frozen event taxonomy (MOO-83 D5).

Call sites use these helpers rather than emit() with raw kwargs, so a field
name can only be misspelled in one place. Every helper is total: a None user or
song degrades to a document with fewer fields, never an exception (emit() also
swallows, this is belt and braces).

Envelope common to every event (added by the emitter): @timestamp, event,
hour_of_day, day_of_week.
"""
from src.telemetry.emitter import emit

# Where a track came from, for import.track.
SOURCE_LIBRARY_SCAN = "library-scan"
SOURCE_UPLOAD = "upload"

# A play counts as "completed" (rather than skipped) from this fraction on.
COMPLETION_THRESHOLD = 0.85


def _field(song, name):
    """Songs rows and the raw record dicts the library scan builds (which have
    no id yet) are both valid inputs."""
    if isinstance(song, dict):
        return song.get(name)
    return getattr(song, name, None)


def _duration_ms(song):
    seconds = _field(song, "duration_seconds")
    if not seconds:
        return None
    return int(float(seconds) * 1000)


def _song_label(song):
    """ "Artist - Title": a precomputed keyword, so a top-tracks panel is one
    terms aggregation instead of a composite over two fields."""
    artist = (_field(song, "artist") or "").strip()
    title = (_field(song, "title") or "").strip()
    if artist and title:
        return "{} - {}".format(artist, title)
    return title or artist or None


def _song_fields(song):
    if song is None:
        return {}
    return {
        "song_id": _field(song, "id"),
        "song_label": _song_label(song),
        "artist": _field(song, "artist"),
        "genre": _field(song, "genre"),
        "duration_ms": _duration_ms(song),
    }


def _user_fields(user):
    if user is None:
        return {}
    return {
        "user_id": getattr(user, "id", None),
        "username": getattr(user, "username", None),
    }


def play_start(user, song):
    emit("play.start", **dict(_user_fields(user), **_song_fields(song)))


def play_end(user, song, position_ms, duration_ms, ended):
    """
    The beacon's classification (D6): completed if the player reached the end
    or got past COMPLETION_THRESHOLD; a skip otherwise.
    """
    completion = 0.0
    if duration_ms:
        completion = min(float(position_ms) / float(duration_ms), 1.0)
    complete = bool(ended) or completion >= COMPLETION_THRESHOLD
    fields = dict(_user_fields(user), **_song_fields(song))
    fields["duration_ms"] = duration_ms or fields.get("duration_ms")
    fields["position_ms"] = position_ms
    fields["listened_ms"] = position_ms
    fields["completion_pct"] = round(completion, 4)
    emit("play.complete" if complete else "play.skip", **fields)


def download(user, song, format, counted_against_quota):
    fields = dict(_user_fields(user), **_song_fields(song))
    fields["format"] = format
    fields["attrs"] = {"counted_against_quota": bool(counted_against_quota)}
    emit("download", **fields)


def search_query(user, query, filters, result_count, duration_ms, engine):
    """`query` is dropped by the emitter at TELEMETRY_LEVEL=basic."""
    emit(
        "search.query",
        query=query,
        filters={k: v for k, v in (filters or {}).items() if v is not None} or None,
        result_count=result_count,
        zero_results=not bool(result_count),
        duration_ms=duration_ms,
        engine=engine,
        **_user_fields(user),
    )


def api_request(method, route, status_code, duration_ms, user_id):
    emit(
        "api.request",
        method=method,
        route=route,
        status_code=status_code,
        duration_ms=duration_ms,
        user_id=user_id,
    )


def job_finished(job):
    """Emitted for every terminal jobs row, from whichever tier ran it."""
    duration_ms = None
    started = getattr(job, "started_at", None)
    finished = getattr(job, "finished_at", None)
    if started and finished:
        duration_ms = int((finished - started).total_seconds() * 1000)
    error = getattr(job, "error", None)
    emit(
        "job.finished",
        job_kind=getattr(job, "kind", None),
        job_status=getattr(job, "status", None),
        queue=getattr(job, "queue", None),
        duration_ms=duration_ms,
        error=(str(error)[:500] if error else None),
        attrs={"job_id": getattr(job, "id", None)},
    )


def import_track(song, source):
    fields = _song_fields(song)
    fields["source"] = source
    emit("import.track", **fields)


def enrichment_applied(song, source, fields):
    payload = _song_fields(song)
    payload["source"] = source
    payload["fields"] = list(fields or [])
    emit("enrichment.applied", **payload)


def export_crate(user, crate_id, format, track_count):
    emit(
        "export.crate",
        crate_id=crate_id,
        format=format,
        track_count=track_count,
        **_user_fields(user),
    )


def request_event(kind, request_id, source, user_id):
    """kind is one of created | approved | rejected | fulfilled."""
    emit(
        "request." + kind,
        request_id=request_id,
        source=source,
        user_id=user_id,
    )
