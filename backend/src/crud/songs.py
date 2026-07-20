"""
CRUD operations for songs.
"""
from tortoise.exceptions import IntegrityError
from tortoise.expressions import F, Q
from tortoise.functions import Coalesce

from src.analysis import dispatch
from src.database.models import Songs
from src.extract import musicfiles
from src.search import outbox
from src.telemetry import events
from src.utils.camelot import key_variants, to_camelot

# Scale rules (MOO-77): bulk DB work is batched, __in lists are chunked.
_BATCH_SIZE = 1000


def _chunks(values, size=_BATCH_SIZE):
    for start in range(0, len(values), size):
        end = start + size
        yield values[start:end]


async def sync_songs_from_disk(progress_cb=None):
    """
    Scans the music volume and synchronizes the songs table with it (#5).

    The synchronization is idempotent -- running it again against an
    unchanged volume changes nothing:
    - a new song on disk is inserted (batched bulk_create — MOO-77),
    - an already-known song gets its tags and file info refreshed; files
      whose size and mtime both match the stored row are skipped without
      being read at all (the unchanged fast path — MOO-77),
    - duplicate files of the same song collapse into a single row (#9);
      the first file in path order is kept as the canonical one,
    - songs whose files disappeared from the volume are deleted (chunked).

    [progress_cb], when given, is awaited as progress_cb(files_done,
    files_total_estimate) every 1000 files (the estimate is the current
    database row count — exact on a rescan, low on a first import).

    The sync only ever manages "library" rows (files on the read-only /music
    volume). Uploaded songs live on other volumes and are never touched here,
    so scanning /music can never delete an upload (MOO-71).
    """
    # Preload the library fingerprints as tuples (never model instances):
    # {path: (size, mtime)} feeds the unchanged fast path in the scanner and
    # {path/dedup: row info} lets the upsert loop below decide new-vs-known
    # in memory instead of two queries per file (MOO-77).
    known_rows = await Songs.filter(source="library").values_list(
        "file_path", "file_size_bytes", "file_mtime", "id", "dedup_key"
    )
    known_fingerprints = {row[0]: (row[1], row[2]) for row in known_rows}
    db_path_to_id = {row[0]: row[3] for row in known_rows}
    db_dedup_to_id = {row[4]: row[3] for row in known_rows}
    db_path_to_dedup = {row[0]: row[4] for row in known_rows}
    row_keys_by_id = {row[3]: {"path": row[0], "dedup": row[4]} for row in known_rows}
    files_total_estimate = len(known_rows)

    songs_on_disk = {}  # dedup_key -> full record, or None for unchanged rows
    seen_paths = set()
    files_parsed = 0
    duplicates_skipped = 0
    async for record in musicfiles.scan_music_files(known=known_fingerprints):
        files_parsed += 1
        if record.get("unchanged"):
            path = record["file_path"]
            seen_paths.add(path)
            dedup_key = db_path_to_dedup[path]
            if dedup_key in songs_on_disk:
                duplicates_skipped += 1
            else:
                songs_on_disk[dedup_key] = None
        elif record["dedup_key"] in songs_on_disk:
            duplicates_skipped += 1
            seen_paths.add(record["file_path"])
        else:
            songs_on_disk[record["dedup_key"]] = record
            seen_paths.add(record["file_path"])
        if progress_cb is not None and files_parsed % 1000 == 0:
            await progress_cb(files_parsed, files_total_estimate)

    # Deletions: database paths no longer on disk, deleted in id chunks —
    # never a single __in list with a million elements (MOO-77).
    missing_ids = [
        song_id for path, song_id in db_path_to_id.items() if path not in seen_paths
    ]
    for chunk in _chunks(missing_ids):
        # NOT the statement's rowcount: sqlite counts the ON DELETE CASCADE
        # track_analysis children (MOO-87) into it, Postgres does not.
        await Songs.filter(id__in=chunk).delete()
    deleted = len(missing_ids)

    created = 0
    updated = 0
    updated_ids = []
    to_create = []
    # Analyzer pass-1 facts by dedup key (MOO-87): popped off the record so
    # they never hit the Songs columns, handed to dispatch after the writes.
    technical_by_dedup = {}
    analysis_targets = []  # (song_id, technical) for created/updated rows
    for dedup_key, record in songs_on_disk.items():
        if record is None:
            continue  # unchanged fast path: nothing to write
        technical_by_dedup[dedup_key] = record.pop("technical", None)
        song_id = db_dedup_to_id.get(dedup_key)
        if song_id is None:
            # The tags of a known file may have changed, giving it a new
            # dedup key: match on the file path so we update that row instead
            # of violating its unique constraint.
            song_id = db_path_to_id.get(record["file_path"])
        if song_id is None:
            to_create.append(record)
            continue
        song = await Songs.get_or_none(id=song_id)
        if song is None:
            to_create.append(record)
            continue
        # Field locks (MOO-85 D4): a field owned by a manual edit or an
        # applied enrichment is never overwritten from file tags by a
        # rescan (this is the fix for the MOO-71/72 quirk where DB edits
        # were silently reverted by the next /music scan). Precedence:
        # manual > beatport > file tag.
        locked_fields = song.field_locks or {}
        changed = False
        for field, value in record.items():
            if field in locked_fields:
                continue
            if getattr(song, field) != value:
                setattr(song, field, value)
                changed = True
        if changed:
            await song.save()
            updated += 1
            updated_ids.append(song_id)
            analysis_targets.append((song_id, technical_by_dedup.get(dedup_key)))
            # Keep the in-memory maps truthful: a retagged file frees its old
            # dedup key (and possibly path), so a later file that now owns
            # that key is created instead of clobbering this row.
            keys = row_keys_by_id[song_id]
            if keys["dedup"] != record["dedup_key"]:
                db_dedup_to_id.pop(keys["dedup"], None)
                db_dedup_to_id[record["dedup_key"]] = song_id
                keys["dedup"] = record["dedup_key"]
            if keys["path"] != record["file_path"]:
                db_path_to_id.pop(keys["path"], None)
                db_path_to_id[record["file_path"]] = song_id
                keys["path"] = record["file_path"]

    for chunk in _chunks(to_create):
        try:
            await Songs.bulk_create([Songs(**record) for record in chunk])
            created += len(chunk)
        except IntegrityError:
            # A rare conflict (e.g. a library file colliding with an uploaded
            # row's dedup key): fall back to row-by-row for this chunk so one
            # bad record cannot fail a million-file import.
            for record in chunk:
                try:
                    await Songs.create(**record)
                    created += 1
                except IntegrityError:
                    print(
                        "[extract] skipping conflicting record for "
                        + record["file_path"]
                    )

    if progress_cb is not None:
        await progress_cb(files_parsed, max(files_total_estimate, files_parsed))

    # Search outbox hooks (MOO-79): record every song this sync touched so the
    # drain refreshes ES. Created rows are looked up by dedup key (bulk_create
    # returns no ids); everything below is never-raise and PG-only.
    created_keys = [record["dedup_key"] for record in to_create]
    created_pairs = []
    for chunk in _chunks(created_keys):
        created_pairs.extend(
            await Songs.filter(dedup_key__in=chunk).values_list("dedup_key", "id")
        )
    created_ids = [pair[1] for pair in created_pairs]
    await outbox.enqueue_many(created_ids + updated_ids, "upsert")
    await outbox.enqueue_many(missing_ids, "delete")
    await outbox.nudge_drain()

    # Telemetry (MOO-83): one import.track per newly created row, so the
    # library-growth panels have a source breakdown. ids come from the lookup
    # above (bulk_create returns none).
    id_by_dedup = dict(created_pairs)
    for record in to_create:
        events.import_track(
            dict(record, id=id_by_dedup.get(record["dedup_key"])),
            events.SOURCE_LIBRARY_SCAN,
        )

    # Analyzer hooks (MOO-87): pass-1 facts land immediately, pass 2 is
    # queued on orp:heavy for every created/updated song. In inline mode
    # the enqueue runs the analysis in-process (mocked in harnesses).
    for dedup_key, song_id in created_pairs:
        analysis_targets.append((song_id, technical_by_dedup.get(dedup_key)))
    analysis_enqueued = 0
    for song_id, technical in analysis_targets:
        await dispatch.ensure_analysis_row(song_id, technical)
        if await dispatch.enqueue_analysis(song_id) is not None:
            analysis_enqueued += 1

    # Beatport enrichment (MOO-85 D7): best-effort, gated on the
    # integrations.beatport_auto_enrich instance setting (default off) and
    # the provider being enabled; never raises, never blocks a scan.
    try:
        from src.enrichment.service import maybe_auto_enqueue

        await maybe_auto_enqueue([song_id for song_id, _technical in analysis_targets])
    except Exception:
        pass

    return {
        "files_parsed": files_parsed,
        "duplicates_skipped": duplicates_skipped,
        "songs_created": created,
        "songs_updated": updated,
        "songs_deleted": deleted,
        "songs_total": await Songs.all().count(),
        "analysis_enqueued": analysis_enqueued,
    }


def filter_songs(
    search=None,
    bpm_min=None,
    bpm_max=None,
    key=None,
    genres=None,
    published_only=True,
    year_min=None,
    year_max=None,
    bitrate_min=None,
    source=None,
):
    """
    Returns a Songs queryset, optionally filtered by a free-text search (#10)
    against the title, artist, album, genre, and label (MOO-94) -- a
    key-shaped query ("8A",
    "Am") additionally matches every notation of that musical key and a
    numeric query matches songs whose BPM rounds to it (MOO-69) -- and by the
    extended library filters (MOO-65): a BPM range, a musical key (Camelot or
    raw notation, matching every notation that maps to the same Camelot
    code), and a multi-genre selection.

    Member listings only surface published tracks (MOO-71): published_only
    filters to status="published"; the admin content view passes False.

    BPM- and key-shaped matching runs on the COALESCEd tag-then-detected
    expressions (MOO-87 D5): the curated tag always wins, the analyzer's
    detected value fills gaps, so detected-only tracks are filterable. The
    bpm_eff/key_eff annotations are backed by the expression indexes from
    migration 10 and are also what the route sorts on for sort=bpm.
    """
    query = Songs.all().annotate(
        bpm_eff=Coalesce("bpm", F("bpm_detected")),
        key_eff=Coalesce("musical_key", F("key_detected")),
    )
    if published_only:
        # Members see published tracks (MOO-71) and only the canonical
        # version of each recording (MOO-90) -- superseded/quarantined
        # versions stay admin-only.
        query = query.filter(status="published", version_status="canonical")
    if search:
        text = search.strip()
        search_filter = (
            Q(title__icontains=text)
            | Q(artist__icontains=text)
            | Q(album__icontains=text)
            | Q(genre__icontains=text)
            | Q(label__icontains=text)
        )
        camelot = to_camelot(text)
        if camelot:
            for variant in key_variants(camelot):
                search_filter = search_filter | Q(key_eff__iexact=variant)
        try:
            bpm_value = float(text)
        except ValueError:
            bpm_value = None
        if bpm_value is not None:
            search_filter = search_filter | Q(
                bpm_eff__gte=bpm_value - 0.5, bpm_eff__lt=bpm_value + 0.5
            )
        query = query.filter(search_filter)
    if bpm_min is not None:
        query = query.filter(bpm_eff__gte=bpm_min)
    if bpm_max is not None:
        query = query.filter(bpm_eff__lte=bpm_max)
    if key:
        camelot = to_camelot(key)
        variants = set(key_variants(camelot)) if camelot else set()
        variants.add(key.strip())
        key_filter = Q(key_eff__iexact=key.strip())
        for variant in variants:
            key_filter = key_filter | Q(key_eff__iexact=variant)
        query = query.filter(key_filter)
    if genres:
        genre_filter = Q(genre__iexact=genres[0])
        for genre in genres[1:]:
            genre_filter = genre_filter | Q(genre__iexact=genre)
        query = query.filter(genre_filter)
    # Additive facet filters (MOO-79): used by the /search degraded-mode SQL
    # fallback; the legacy /songs route does not expose them.
    if year_min is not None:
        query = query.filter(year__gte=year_min)
    if year_max is not None:
        query = query.filter(year__lte=year_max)
    if bitrate_min is not None:
        query = query.filter(bitrate_kbps__gte=bitrate_min)
    if source:
        query = query.filter(source=source)
    return query
