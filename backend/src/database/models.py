"""
Our database table models.
"""
from tortoise import fields, models


class Users(models.Model):
    """
    Model for our users table.

    The admin console (MOO-71) adds a role (owner/admin/curator/member), an
    informational plan (free/pro/crew), an account status
    (active/suspended/pending/invited), and an email. Roles gate the admin
    surface via the permission matrix; suspended users cannot log in or use
    the API. These layer on top of the ADMIN_USERNAME bootstrap gating and do
    not replace it: the configured admin is promoted to Owner on start.
    """

    id = fields.IntField(pk=True)
    username = fields.CharField(max_length=20, unique=True)
    full_name = fields.CharField(max_length=50, null=True)
    email = fields.CharField(max_length=255, null=True)
    password = fields.CharField(max_length=128, null=True)
    role = fields.CharField(max_length=20, default="member")
    plan = fields.CharField(max_length=20, default="free")
    status = fields.CharField(max_length=20, default="active")
    created_at = fields.DatetimeField(auto_now_add=True)
    modified_at = fields.DatetimeField(auto_now=True)


class Notes(models.Model):
    """
    Model for our notes table.
    """

    id = fields.IntField(pk=True)
    title = fields.CharField(max_length=225)
    content = fields.TextField()
    author = fields.ForeignKeyField("models.Users", related_name="note")
    created_at = fields.DatetimeField(auto_now_add=True)
    modified_at = fields.DatetimeField(auto_now=True)

    def __str__(self):
        return f"{self.title}, {self.author_id} on {self.created_at}"


class Songs(models.Model):
    """
    Model for our songs table: one row per unique song found on the music
    volume (#5). Duplicate files of the same song share a single row,
    identified by dedup_key (#9).
    """

    id = fields.IntField(pk=True)
    title = fields.CharField(max_length=255, null=True)
    artist = fields.CharField(max_length=255, null=True)
    album = fields.CharField(max_length=255, null=True)
    genre = fields.CharField(max_length=100, null=True)
    # Record label / publisher from the ID3 TPUB tag (MOO-94). Nullable:
    # most home-ripped files carry no publisher tag.
    label = fields.CharField(max_length=255, null=True)
    year = fields.IntField(null=True)
    track_number = fields.IntField(null=True)
    bpm = fields.FloatField(null=True)
    musical_key = fields.CharField(max_length=20, null=True)
    duration_seconds = fields.FloatField(null=True)
    bitrate_kbps = fields.IntField(null=True)
    file_path = fields.CharField(max_length=1024, unique=True)
    file_size_bytes = fields.BigIntField(null=True)
    checksum_md5 = fields.CharField(max_length=32, null=True)
    # Content address of the file in the sharded /library tree (MOO-77).
    # Only populated for files written through src/utils/storage.py; legacy
    # /music and /uploads rows keep it null until a later backfill.
    checksum_sha256 = fields.CharField(max_length=64, null=True)
    # POSIX mtime at the last scan (MOO-77). With file_size_bytes it forms
    # the unchanged-file fast path: a rescan skips hashing and tag parsing
    # for files whose size and mtime both match.
    file_mtime = fields.FloatField(null=True)
    dedup_key = fields.CharField(max_length=64, unique=True)
    # Extended ID3 capture (MOO-79): full-fidelity metadata for the search
    # index. All nullable/defaulted -- existing rows fill in on the next scan.
    album_artist = fields.CharField(max_length=255, null=True)  # TPE2
    composer = fields.CharField(max_length=255, null=True)  # TCOM
    comment = fields.TextField(null=True)  # first COMM frame
    disc_number = fields.IntField(null=True)  # TPOS
    codec = fields.CharField(max_length=20, null=True)  # "mp3" today
    has_artwork = fields.BooleanField(default=False)  # any APIC frame
    txxx_frames = fields.JSONField(null=True)  # sanitized {desc: text}
    # Moderation status (MOO-71). Existing library rows default to published;
    # only published tracks are surfaced to members. Uploaded tracks may enter
    # as pending when approval is required.
    status = fields.CharField(max_length=20, default="published")
    # Where the file lives: "library" (the read-only /music volume, managed by
    # the extraction sync) or "upload" (the writable uploads volume). The sync
    # only ever inserts/deletes library rows, so uploads are never wiped.
    source = fields.CharField(max_length=20, default="library")
    uploaded_by = fields.ForeignKeyField(
        "models.Users",
        related_name="uploaded_songs",
        null=True,
        on_delete=fields.SET_NULL,
    )
    # Analyzer read-model (MOO-87): detected values denormalized from
    # track_analysis so list/filter queries never join. Tag values in
    # bpm/musical_key always win; these fill gaps (D5 precedence).
    bpm_detected = fields.FloatField(null=True)
    key_detected = fields.CharField(max_length=20, null=True)
    waveform_ready = fields.BooleanField(default=False)
    # Recording-level dedup (MOO-90): each songs row is one VERSION of a
    # recording. recording_id is null for implicit single-version recordings
    # (a Recordings row is created lazily when a second version appears or an
    # external ID is learned). version_status gates member visibility:
    # everything member-facing filters to "canonical". Files are NEVER moved
    # or deleted by dedup -- these are pure DB statuses.
    recording = fields.ForeignKeyField(
        "models.Recordings",
        related_name="versions",
        null=True,
        on_delete=fields.SET_NULL,
    )
    version_status = fields.CharField(max_length=20, default="canonical")
    # canonical | superseded | quarantined | pending_review
    quality_breakdown = fields.JSONField(null=True)  # MOO-90 D5 score detail
    # Canonical provider URL a fetched track came from (MOO-78). Null for
    # library/upload rows; feeds the metadata editor and enrichment (MOO-84/85).
    source_url = fields.CharField(max_length=2048, null=True)
    # Denormalized normalized identity for the dedup candidate prefilter
    # (MOO-90 D4); populated at scan/upload time and lazily by the workers.
    artist_norm = fields.CharField(max_length=255, null=True)
    title_norm = fields.CharField(max_length=255, null=True)
    # Beatport metadata enrichment (MOO-85). beatport_track_id is denormalized
    # from the matched SongEnrichment candidate for fast joins/lookups.
    # field_locks records which fields are DB-owned:
    # {field_name: "manual" | "beatport"}. A /music rescan (sync_songs_from_disk)
    # skips any field present here so a curator's edit or an applied
    # enrichment survives the next scan (precedence: manual > beatport > file
    # tag -- this is the fix for the MOO-71/72 "rescan clobbers DB edits"
    # quirk, scoped to owned fields only).
    beatport_track_id = fields.BigIntField(null=True)
    field_locks = fields.JSONField(null=True)
    # Album art managed by the metadata editor (MOO-82). artwork_path points at
    # the normalized display copy in the sharded /library/art tree (never at a
    # /music file); has_artwork stays the "the file carries an APIC frame" flag
    # from extraction, so a song can have embedded art and no managed copy.
    artwork_path = fields.CharField(max_length=1024, null=True)
    artwork_source = fields.CharField(max_length=20, null=True)
    # embedded | upload | beatport
    artwork_width = fields.IntField(null=True)
    artwork_height = fields.IntField(null=True)
    isrc = fields.CharField(max_length=15, null=True)  # TSRC
    created_at = fields.DatetimeField(auto_now_add=True)
    modified_at = fields.DatetimeField(auto_now=True)

    def __str__(self):
        return f"{self.artist} - {self.title} ({self.file_path})"


class Recordings(models.Model):
    """
    The dedup unit (MOO-90): one row per specific mix/edit of a track. An
    extended mix and a radio edit are DIFFERENT recordings, never merged.
    Carries the normalized identity, every known external platform ID, and
    the pointer to the current canonical version among its songs rows.
    """

    id = fields.IntField(pk=True)
    artist_norm = fields.CharField(max_length=255)
    title_norm = fields.CharField(max_length=255)
    mix_norm = fields.CharField(max_length=100, default="original")
    duration_seconds = fields.FloatField(null=True)  # canonical version's
    # Deliberately a raw int, NOT an FK: songs.recording_id already points
    # the other way and Tortoise cannot generate schemas with a cyclic FK
    # pair. The hand-written migration still declares the real REFERENCES
    # ... ON DELETE SET NULL at the database level.
    canonical_song_id = fields.IntField(null=True)
    isrc = fields.CharField(max_length=15, null=True)
    musicbrainz_id = fields.CharField(max_length=36, null=True)
    beatport_id = fields.CharField(max_length=32, null=True)
    spotify_id = fields.CharField(max_length=32, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    modified_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "recordings"

    def __str__(self):
        return f"{self.artist_norm} - {self.title_norm} ({self.mix_norm})"


class RecordingLinks(models.Model):
    """
    Fingerprint-overlapping but different-duration recording pairs (MOO-90
    D3 L4): the radio edit vs its extended mix. Stored as related_cut so the
    relationship is visible in the admin UI and the pair is never re-raised
    as a duplicate. Invariant: recording_a_id < recording_b_id.
    """

    id = fields.IntField(pk=True)
    recording_a = fields.ForeignKeyField(
        "models.Recordings", related_name="links_a", on_delete=fields.CASCADE
    )
    recording_b = fields.ForeignKeyField(
        "models.Recordings", related_name="links_b", on_delete=fields.CASCADE
    )
    kind = fields.CharField(max_length=20, default="related_cut")
    similarity = fields.FloatField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "recording_links"
        unique_together = (("recording_a", "recording_b"),)


class DuplicateCandidates(models.Model):
    """
    One row per detected duplicate pair (MOO-90). Certain/confident matches
    are auto-resolved (status auto_resolved) with the decision recorded;
    borderline matches wait for an admin (pending); backfill dry-runs write
    proposed rows that change nothing. Invariant: song_a_id < song_b_id, so
    a pair can never be raised twice.
    """

    id = fields.IntField(pk=True)
    song_a = fields.ForeignKeyField(
        "models.Songs", related_name="dup_as_a", on_delete=fields.CASCADE
    )
    song_b = fields.ForeignKeyField(
        "models.Songs", related_name="dup_as_b", on_delete=fields.CASCADE
    )
    recording = fields.ForeignKeyField(
        "models.Recordings",
        related_name="candidates",
        null=True,
        on_delete=fields.SET_NULL,
    )
    layer = fields.CharField(max_length=20)  # checksum|pcm_hash|fingerprint|metadata
    similarity = fields.FloatField(null=True)  # raw L3 fingerprint similarity
    confidence = fields.FloatField()  # L5-adjusted confidence
    duration_delta = fields.FloatField(null=True)
    status = fields.CharField(max_length=20, default="pending")
    # proposed (dry-run) | pending | auto_resolved | confirmed | rejected
    suggested_winner = fields.ForeignKeyField(
        "models.Songs",
        related_name="dup_suggested",
        null=True,
        on_delete=fields.SET_NULL,
    )
    resolution = fields.JSONField(null=True)  # {action, winner_song_id, ...}
    resolved_by = fields.ForeignKeyField(
        "models.Users",
        related_name="dup_resolutions",
        null=True,
        on_delete=fields.SET_NULL,
    )
    created_at = fields.DatetimeField(auto_now_add=True)
    resolved_at = fields.DatetimeField(null=True)

    class Meta:
        table = "duplicate_candidates"
        unique_together = (("song_a", "song_b"),)


class FingerprintNgrams(models.Model):
    """
    The local fingerprint similarity index (MOO-90 D4): hashed 4-word shingles
    of each song's chromaprint stream. Songs sharing >= 2 ngrams become
    fingerprint-comparison candidates, so matching stays indexed at
    millions-of-songs scale -- never an O(n) fingerprint sweep.
    """

    id = fields.BigIntField(pk=True)
    song = fields.ForeignKeyField(
        "models.Songs", related_name="fp_ngrams", on_delete=fields.CASCADE
    )
    ngram = fields.BigIntField()

    class Meta:
        table = "fingerprint_ngrams"


class SearchOutbox(models.Model):
    """
    Transactional outbox for the Elasticsearch sync (MOO-79). Writers insert
    a row per song-affecting change; the search_drain_outbox worker job builds
    fresh docs from PG and bulk-writes them to ES. PG is the source of truth;
    ES is rebuildable from this table + the songs table at all times.
    """

    id = fields.BigIntField(pk=True)
    # Deliberately a raw int, NOT an FK: delete ops must outlive the song row.
    song_id = fields.IntField()
    op = fields.CharField(max_length=10)  # "upsert" | "delete"
    attempts = fields.IntField(default=0)
    last_error = fields.TextField(null=True)
    enqueued_at = fields.DatetimeField(auto_now_add=True)
    processed_at = fields.DatetimeField(null=True)

    class Meta:
        table = "search_outbox"


class TrackAnalysis(models.Model):
    """
    One row per song: everything the ingestion analyzer derived from the
    audio itself (MOO-87). Authoritative store; songs.bpm_detected /
    key_detected / waveform_ready are denormalized copies. MOO-90 consumes
    fingerprint / fingerprint_sha256 / pcm_sha256 / quality_flags.
    """

    id = fields.BigIntField(pk=True)
    song = fields.OneToOneField(
        "models.Songs", related_name="analysis", on_delete=fields.CASCADE
    )
    checksum_sha256 = fields.CharField(max_length=64, null=True)  # bytes analyzed
    analyzer_version = fields.IntField(default=1)
    field_versions = fields.JSONField(default=dict)
    pass1_status = fields.CharField(max_length=10, default="pending")
    # pending | running | succeeded | failed
    pass2_status = fields.CharField(max_length=10, default="pending")
    pass1_at = fields.DatetimeField(null=True)
    pass2_at = fields.DatetimeField(null=True)
    error = fields.TextField(null=True)
    # --- pass 1: container / technical ---
    codec = fields.CharField(max_length=20, null=True)  # "mp3"
    container = fields.CharField(max_length=20, null=True)  # "mpeg"
    sample_rate_hz = fields.IntField(null=True)
    channels = fields.SmallIntField(null=True)
    bitrate_mode = fields.CharField(max_length=8, null=True)  # "cbr"|"vbr"
    encoder = fields.CharField(max_length=120, null=True)
    art_present = fields.BooleanField(default=False)
    art_format = fields.CharField(max_length=10, null=True)  # "jpeg"|"png"
    art_width = fields.IntField(null=True)
    art_height = fields.IntField(null=True)
    art_bytes = fields.IntField(null=True)
    tags_json = fields.JSONField(null=True)  # full frame dump
    # --- pass 2: audio analysis ---
    decode_ok = fields.BooleanField(null=True)
    bpm_detected = fields.FloatField(null=True)
    key_detected = fields.CharField(max_length=20, null=True)  # "Am", "F#m", ...
    key_confidence = fields.FloatField(null=True)
    bpm_mismatch = fields.BooleanField(null=True)
    key_mismatch = fields.BooleanField(null=True)
    loudness_lufs = fields.FloatField(null=True)  # integrated, EBU R128
    loudness_range = fields.FloatField(null=True)  # LRA
    true_peak_dbtp = fields.FloatField(null=True)
    cue_in_s = fields.FloatField(null=True)  # leading silence end
    cue_out_s = fields.FloatField(null=True)  # trailing silence start
    waveform_peaks_count = fields.IntField(null=True)  # 1000 when written
    fingerprint = fields.TextField(null=True)  # chromaprint base64
    fingerprint_algo = fields.CharField(max_length=30, null=True)
    fingerprint_sha256 = fields.CharField(max_length=64, null=True)
    pcm_sha256 = fields.CharField(max_length=64, null=True)
    spectral_cutoff_hz = fields.IntField(null=True)
    quality_flags = fields.JSONField(default=dict)
    created_at = fields.DatetimeField(auto_now_add=True)
    modified_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "track_analysis"

    def __str__(self):
        return f"analysis of song {self.song_id} [{self.pass2_status}]"


class Crates(models.Model):
    """
    Model for our crates table: a crate is a user-owned playlist (MOO-65).
    """

    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=100)
    description = fields.TextField(null=True)  # MOO-84: playlist description
    color = fields.CharField(max_length=16, null=True)
    # MOO-84: content-addressed cover under /library/art/<aa>/<bb>/<sha256>.<ext>;
    # null falls back to the client-rendered color collage.
    cover_path = fields.CharField(max_length=1024, null=True)
    public = fields.BooleanField(default=False)
    share_token = fields.CharField(max_length=64, unique=True)
    # MOO-86: the DJ software this crate is exported for by default
    # (serato | traktor | rekordbox | null). Picked at creation, switchable
    # later; any crate can still be exported to any format on demand.
    dj_target = fields.CharField(max_length=20, null=True)
    owner = fields.ForeignKeyField(
        "models.Users", related_name="crates", on_delete=fields.CASCADE
    )
    created_at = fields.DatetimeField(auto_now_add=True)
    modified_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "crates"

    def __str__(self):
        return f"{self.name} (owner {self.owner_id})"


class CrateTracks(models.Model):
    """
    Model for the ordered song membership of a crate (MOO-65).
    """

    id = fields.IntField(pk=True)
    crate = fields.ForeignKeyField(
        "models.Crates", related_name="tracks", on_delete=fields.CASCADE
    )
    song = fields.ForeignKeyField(
        "models.Songs", related_name="crate_tracks", on_delete=fields.CASCADE
    )
    position = fields.IntField()
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "crate_tracks"
        unique_together = (("crate", "song"),)


class Favorites(models.Model):
    """
    Model for per-user song favorites (MOO-65).
    """

    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField(
        "models.Users", related_name="favorites", on_delete=fields.CASCADE
    )
    song = fields.ForeignKeyField(
        "models.Songs", related_name="favorites", on_delete=fields.CASCADE
    )
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "favorites"
        unique_together = (("user", "song"),)


class PlayEvents(models.Model):
    """
    Model for play events: one row every time a user starts playback of a
    song (MOO-65). Aggregated into per-song play counts and charts.
    """

    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField(
        "models.Users", related_name="play_events", on_delete=fields.CASCADE
    )
    song = fields.ForeignKeyField(
        "models.Songs", related_name="play_events", on_delete=fields.CASCADE
    )
    played_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "play_events"


class Downloads(models.Model):
    """
    Model for the download history: one row per download of a song by a
    user (MOO-65). Re-downloads of a song the user already has are recorded
    with counted_against_quota=False, so they never double-count against the
    monthly download quota.
    """

    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField(
        "models.Users", related_name="downloads", on_delete=fields.CASCADE
    )
    song = fields.ForeignKeyField(
        "models.Songs", related_name="downloads", on_delete=fields.CASCADE
    )
    format = fields.CharField(max_length=10, default="mp3")
    counted_against_quota = fields.BooleanField(default=True)
    downloaded_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "downloads"


class RolePermissions(models.Model):
    """
    The persisted permission matrix, one row per non-owner role (MOO-71).

    permissions is a {permission_key: bool} map. The Owner role is never
    stored here: its permissions are locked on and resolved in code. A missing
    row falls back to the coded defaults, so the matrix works before it has
    ever been edited.
    """

    id = fields.IntField(pk=True)
    role = fields.CharField(max_length=20, unique=True)
    permissions = fields.JSONField(default=dict)
    created_at = fields.DatetimeField(auto_now_add=True)
    modified_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "role_permissions"


class Jobs(models.Model):
    """
    One row per background job (MOO-77). Postgres is the source of truth for
    job state: Redis/arq is transport only and can be wiped without losing
    user-visible state. In inline mode (WORKERS_ENABLED=false) the task runs
    in-process and the row is terminal by the time the API responds.
    """

    id = fields.BigIntField(pk=True)
    kind = fields.CharField(max_length=50)  # e.g. "scan_library"
    status = fields.CharField(max_length=20, default="queued")
    # queued | running | succeeded | failed | cancelled
    queue = fields.CharField(max_length=20, default="orp:default")
    payload = fields.JSONField(default=dict)
    result = fields.JSONField(null=True)
    error = fields.TextField(null=True)
    progress = fields.FloatField(default=0.0)  # 0.0 - 1.0
    arq_job_id = fields.CharField(max_length=64, null=True)
    created_by = fields.ForeignKeyField(
        "models.Users",
        related_name="jobs",
        null=True,
        on_delete=fields.SET_NULL,
    )
    created_at = fields.DatetimeField(auto_now_add=True)
    started_at = fields.DatetimeField(null=True)
    finished_at = fields.DatetimeField(null=True)

    class Meta:
        table = "jobs"

    def __str__(self):
        return f"job {self.id}: {self.kind} [{self.status}]"


class DownloadRequests(models.Model):
    """
    One row per acquisition attempt-series for the music download engine
    (MOO-78). A user (or a system caller such as MOO-81 song requests) submits
    a provider URL; this row is the domain object tracking that request from
    submission through import. The operational job lives in the jobs table
    (kind="fetch_track", queue orp:heavy); this row links user/provider/song
    and carries the captured source metadata.

    Lifecycle:
      queued -> fetching -> postprocessing -> imported
                                            -> duplicate_skipped
                                            -> failed
      (any active state) -> cancelled
    """

    id = fields.BigIntField(pk=True)
    provider = fields.CharField(max_length=20)  # youtube | soundcloud | spotify
    url = fields.CharField(max_length=2048)  # canonical url from urlcheck
    external_id = fields.CharField(max_length=128, null=True)
    status = fields.CharField(max_length=20, default="queued")
    # queued | fetching | postprocessing | imported | duplicate_skipped
    # | failed | cancelled
    origin = fields.CharField(max_length=20, default="member")
    # member | admin | request | artist_follow
    origin_ref = fields.CharField(max_length=64, null=True)
    priority = fields.CharField(max_length=10, default="normal")  # normal | high
    requested_by = fields.ForeignKeyField(
        "models.Users",
        related_name="download_requests",
        null=True,
        on_delete=fields.SET_NULL,
    )
    job = fields.ForeignKeyField(
        "models.Jobs",
        related_name="download_requests",
        null=True,
        on_delete=fields.SET_NULL,
    )
    song = fields.ForeignKeyField(
        "models.Songs",
        related_name="download_requests",
        null=True,
        on_delete=fields.SET_NULL,
    )
    source_metadata = fields.JSONField(null=True)  # SourceMetadata dict
    progress = fields.FloatField(default=0.0)
    attempts = fields.IntField(default=0)
    error = fields.TextField(null=True)
    error_kind = fields.CharField(max_length=30, null=True)
    # validation | network | tool | too_large | postprocess | duplicate | cancelled
    created_at = fields.DatetimeField(auto_now_add=True)
    started_at = fields.DatetimeField(null=True)
    finished_at = fields.DatetimeField(null=True)

    class Meta:
        table = "download_requests"

    def __str__(self):
        return "download {}: {} [{}]".format(self.id, self.provider, self.status)


class AuthSessions(models.Model):
    """
    Server-side session record backing the cookie-JWT (MOO-89).

    One row per login, keyed by the token's jti. Authentication checks this row
    so sessions are revocable (logout, log-out-everywhere, admin kill) and can
    carry an absolute timeout beyond the short access token's expiry.
    """

    id = fields.IntField(pk=True)
    jti = fields.CharField(max_length=32, unique=True)
    user = fields.ForeignKeyField(
        "models.Users", related_name="sessions", on_delete=fields.CASCADE
    )
    created_at = fields.DatetimeField(auto_now_add=True)
    last_seen_at = fields.DatetimeField(auto_now_add=True)
    expires_at = fields.DatetimeField()
    revoked_at = fields.DatetimeField(null=True)
    ip = fields.CharField(max_length=45, null=True)
    user_agent = fields.CharField(max_length=255, null=True)

    class Meta:
        table = "auth_sessions"


class UserIdentities(models.Model):
    """
    A linked external IDP identity (MOO-88).

    One user owns N identities. An identity is matched strictly by
    (provider, subject) -- never by email, so a provider-side email change
    still resolves to the same account, and an attacker who controls a
    matching email address at some IDP cannot claim an existing account.
    """

    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField(
        "models.Users", related_name="identities", on_delete=fields.CASCADE
    )
    provider = fields.CharField(max_length=40)
    subject = fields.CharField(max_length=255)
    email = fields.CharField(max_length=255, null=True)
    email_verified = fields.BooleanField(default=False)
    display_name = fields.CharField(max_length=255, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    last_login_at = fields.DatetimeField(null=True)

    class Meta:
        table = "user_identities"
        unique_together = (("provider", "subject"),)

    def __str__(self):
        return "identity {}:{}".format(self.provider, self.subject)


class AuditLog(models.Model):
    """
    Append-only security audit log (MOO-89). Authoritative Postgres copy of
    security-relevant events (logins, role/user changes, moderation, settings,
    session kills). No update/delete surface is exposed.
    """

    id = fields.IntField(pk=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    event = fields.CharField(max_length=50)
    actor = fields.ForeignKeyField(
        "models.Users",
        related_name="audit_events",
        null=True,
        on_delete=fields.SET_NULL,
    )
    actor_username = fields.CharField(max_length=20, null=True)
    target_type = fields.CharField(max_length=20, null=True)
    target_id = fields.CharField(max_length=64, null=True)
    ip = fields.CharField(max_length=45, null=True)
    user_agent = fields.CharField(max_length=255, null=True)
    detail = fields.JSONField(null=True)

    class Meta:
        table = "audit_log"


class InstanceSettings(models.Model):
    """
    Persisted instance settings as a flat key/value store (MOO-71).

    Each row is one dotted setting key (e.g. "general.pool_name") whose value
    is JSON-encoded, so strings, numbers, and booleans round-trip. Reads start
    from the coded defaults and overlay the stored rows.
    """

    id = fields.IntField(pk=True)
    key = fields.CharField(max_length=128, unique=True)
    value = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    modified_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "instance_settings"


class SongRequests(models.Model):
    """
    Member song requests (MOO-81): a member asks for a track missing from the
    library; the request is moderated (or auto-approved) then fulfilled via
    the download engine (MOO-78, `download_id` is a soft reference to a
    `download_requests` row -- no DB-level FK, so this table never breaks if
    that table's shape moves under it) and, on the MOO-90 pre-submission
    check, may be short-circuited as a duplicate of an existing song.

    Lifecycle: pending -> approved -> downloading -> fulfilled (happy path);
    terminal exits duplicate | rejected | failed | cancelled.
    """

    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField(
        "models.Users", related_name="song_requests", on_delete=fields.CASCADE
    )
    kind = fields.CharField(max_length=10)  # free_text | url
    artist = fields.CharField(max_length=255, null=True)
    title = fields.CharField(max_length=255, null=True)
    mix_name = fields.CharField(max_length=120, null=True)
    source_url = fields.CharField(max_length=2048, null=True)
    provider = fields.CharField(max_length=20, null=True)  # youtube|soundcloud|spotify
    notes = fields.CharField(max_length=500, null=True)
    # Normalized "artist|title|mix" (free_text) or the source_url (url kind):
    # the open-duplicate guard (an identical still-open request) + admin search.
    normalized_key = fields.CharField(max_length=2048, null=True)
    status = fields.CharField(max_length=20, default="pending")
    # pending|approved|downloading|fulfilled|failed|rejected|duplicate|cancelled
    reason = fields.CharField(max_length=500, null=True)
    duplicate_of = fields.ForeignKeyField(
        "models.Songs",
        related_name="song_requests_duplicate",
        null=True,
        on_delete=fields.SET_NULL,
    )
    possible_duplicate_of = fields.ForeignKeyField(
        "models.Songs",
        related_name="song_requests_possible_duplicate",
        null=True,
        on_delete=fields.SET_NULL,
    )
    fulfilled_song = fields.ForeignKeyField(
        "models.Songs",
        related_name="song_requests_fulfilled",
        null=True,
        on_delete=fields.SET_NULL,
    )
    download_id = fields.IntField(null=True)  # soft ref -> download_requests.id
    decided_by = fields.ForeignKeyField(
        "models.Users",
        related_name="decided_song_requests",
        null=True,
        on_delete=fields.SET_NULL,
    )
    decided_at = fields.DatetimeField(null=True)
    resolved_seen = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)
    modified_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "song_requests"

    def __str__(self):
        return "song_request {}: {} [{}]".format(self.id, self.kind, self.status)


class SongEnrichment(models.Model):
    """
    One row per (song, provider) metadata-enrichment attempt (MOO-85). Beatport
    is the only provider today; the shape is provider-generic so a future
    MusicBrainz/Spotify source can reuse it.

    payload is the normalized fetched fields (see src/enrichment/beatport_client.py
    module docstring for the exact shape -- it is the contract MOO-82's ID3
    editor consumes via GET /admin/enrichment/songs/{song_id}). candidates is
    the top-5 scored search results (see src/enrichment/scoring.py). Applying a
    match writes fields_applied onto the songs row and locks them in
    songs.field_locks; tag_snapshot keeps the pre-apply values so un-apply can
    restore them and clear the locks.
    """

    id = fields.BigIntField(pk=True)
    song = fields.ForeignKeyField(
        "models.Songs", related_name="enrichments", on_delete=fields.CASCADE
    )
    provider = fields.CharField(max_length=20, default="beatport")
    # pending | applied | needs_review | no_match | rejected | error
    status = fields.CharField(max_length=20, default="pending")
    match_method = fields.CharField(max_length=10, null=True)  # auto | manual
    confidence = fields.FloatField(null=True)  # best candidate score, 0-1
    beatport_track_id = fields.BigIntField(null=True)
    beatport_release_id = fields.BigIntField(null=True)
    beatport_artist_ids = fields.JSONField(null=True)  # [int, ...]
    payload = fields.JSONField(null=True)  # normalized fetched fields
    candidates = fields.JSONField(null=True)  # top-5 scored candidates
    fields_applied = fields.JSONField(null=True)  # e.g. ["genre","label","year"]
    tag_snapshot = fields.JSONField(null=True)  # pre-apply songs values
    error = fields.TextField(null=True)
    reviewed_by = fields.ForeignKeyField(
        "models.Users",
        related_name="enrichment_reviews",
        null=True,
        on_delete=fields.SET_NULL,
    )
    matched_at = fields.DatetimeField(null=True)
    applied_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    modified_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "song_enrichment"
        unique_together = (("song", "provider"),)

    def __str__(self):
        return "enrichment {}: song {} [{}/{}]".format(
            self.id, self.song_id, self.provider, self.status
        )


class BeatportCache(models.Model):
    """
    Read-through response cache for the Beatport API v4 client (MOO-85).
    Postgres, not Redis (MOO-77 declared Redis wipeable transport; cached
    responses must survive a redis restart at library scale). cache_key is
    sha1(method + url + sorted-params); expired rows are overwritten in place
    on the next fetch rather than deleted eagerly.
    """

    id = fields.BigIntField(pk=True)
    cache_key = fields.CharField(max_length=40, unique=True)
    url = fields.CharField(max_length=1024)
    response = fields.JSONField()
    fetched_at = fields.DatetimeField(auto_now=True)
    expires_at = fields.DatetimeField()

    class Meta:
        table = "beatport_cache"


class TagRevisions(models.Model):
    """
    One metadata edit of one song (MOO-82): who changed what, when, and from
    which value to which. changes is {field: {"old": ..., "new": ...}} (an
    artwork change records the artwork_path pair), so a revision can be
    inverted and re-applied -- that is what rollback does, as a NEW revision.
    History is append-only and never rewritten.
    """

    id = fields.BigIntField(pk=True)
    song = fields.ForeignKeyField(
        "models.Songs", related_name="tag_revisions", on_delete=fields.CASCADE
    )
    editor = fields.ForeignKeyField(
        "models.Users",
        related_name="tag_revisions",
        null=True,
        on_delete=fields.SET_NULL,
    )
    # Denormalized so history survives the editor's account deletion.
    editor_username = fields.CharField(max_length=20, null=True)
    # user | batch | enrichment | proposal | rollback | artwork
    source = fields.CharField(max_length=20, default="user")
    changes = fields.JSONField()
    batch_id = fields.CharField(max_length=32, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "tag_revisions"

    def __str__(self):
        return "revision {}: song {} [{}]".format(self.id, self.song_id, self.source)


class TagProposals(models.Model):
    """
    A metadata edit PROPOSED by a member who lacks edit_metadata (MOO-82):
    members cannot write tags, they suggest them and a curator approves. An
    approval replays the proposal through the normal edit pipeline, so it
    lands as a TagRevisions row like any other edit.
    """

    id = fields.BigIntField(pk=True)
    song = fields.ForeignKeyField(
        "models.Songs", related_name="tag_proposals", on_delete=fields.CASCADE
    )
    proposer = fields.ForeignKeyField(
        "models.Users",
        related_name="tag_proposals",
        null=True,
        on_delete=fields.SET_NULL,
    )
    changes = fields.JSONField()  # {field: new_value}
    note = fields.CharField(max_length=500, null=True)
    status = fields.CharField(max_length=20, default="pending")
    # pending | approved | rejected
    reviewed_by = fields.ForeignKeyField(
        "models.Users",
        related_name="reviewed_tag_proposals",
        null=True,
        on_delete=fields.SET_NULL,
    )
    reviewed_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "tag_proposals"

    def __str__(self):
        return "proposal {}: song {} [{}]".format(self.id, self.song_id, self.status)


class Artists(models.Model):
    """
    One row per distinct artist name found in the library (MOO-80), kept in
    sync by sync_artists_from_library. name_norm is the dedupe key so
    follows/polling never grow with duplicate spellings/casing of the same
    artist. beatport_artist_id is populated lazily by the release-source
    resolution pass; musicbrainz_id is reserved for a future source and
    unused this stage.
    """

    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=255)
    name_norm = fields.CharField(max_length=255, unique=True)
    track_count = fields.IntField(default=0)
    beatport_artist_id = fields.CharField(max_length=64, null=True, unique=True)
    musicbrainz_id = fields.CharField(max_length=36, null=True)
    image_url = fields.CharField(max_length=1024, null=True)
    last_polled_at = fields.DatetimeField(null=True)
    last_release_seen_at = fields.DatetimeField(null=True)
    resolve_attempted_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    modified_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "artists"

    def __str__(self):
        return "artist {}: {}".format(self.id, self.name)


class ArtistFollows(models.Model):
    """A member follows an artist (MOO-80): per-user, deduped onto the shared
    Artists row. settings carries the per-follow auto_grab/notify flags."""

    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField(
        "models.Users", related_name="artist_follows", on_delete=fields.CASCADE
    )
    artist = fields.ForeignKeyField(
        "models.Artists", related_name="follows", on_delete=fields.CASCADE
    )
    settings = fields.JSONField(default=dict)  # {"auto_grab": bool, "notify": bool}
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "artist_follows"
        unique_together = (("user", "artist"),)

    def __str__(self):
        return "follow user={} artist={}".format(self.user_id, self.artist_id)


class Releases(models.Model):
    """
    One row per (source, external_id) release surfaced by a ReleaseSource for
    a followed artist (MOO-80) -- shared/global, not per-user: one poll, one
    row, one library state for everyone. States: missing | in_library |
    grabbed | ignored (grabbed/ignored are sticky, never overwritten by
    re-matching except grabbed -> in_library on a later full match).
    """

    id = fields.IntField(pk=True)
    artist = fields.ForeignKeyField(
        "models.Artists", related_name="releases", on_delete=fields.CASCADE
    )
    source = fields.CharField(max_length=20, default="beatport")
    external_id = fields.CharField(max_length=64)
    title = fields.CharField(max_length=255)
    release_date = fields.DateField()
    label = fields.CharField(max_length=255, null=True)
    artwork_url = fields.CharField(max_length=1024, null=True)
    source_url = fields.CharField(max_length=1024, null=True)
    track_count = fields.IntField(default=0)
    tracks = fields.JSONField(default=list)
    # [{"title", "mix", "external_id", "duration_seconds"}]
    status = fields.CharField(max_length=20, default="missing")
    # missing | in_library | grabbed | ignored
    matched_song_ids = fields.JSONField(default=list)
    matched_count = fields.IntField(default=0)
    # Soft references (MOO-81 D3.4 convention): request ids created by a
    # grab/auto-grab, not DB FKs, so this table never breaks if song_requests
    # moves under it.
    grab_request_ids = fields.JSONField(default=list)
    ignored_by = fields.ForeignKeyField(
        "models.Users",
        related_name="ignored_releases",
        null=True,
        on_delete=fields.SET_NULL,
    )
    ignored_at = fields.DatetimeField(null=True)
    first_seen_at = fields.DatetimeField(auto_now_add=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    modified_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "releases"
        unique_together = (("source", "external_id"),)

    def __str__(self):
        return "release {}: {} [{}]".format(self.id, self.title, self.status)


class FollowFeedState(models.Model):
    """Per-user 'last seen' marker for the release feed badge (MOO-80)."""

    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField(
        "models.Users", related_name="feed_state", on_delete=fields.CASCADE, unique=True
    )
    seen_at = fields.DatetimeField()

    class Meta:
        table = "follow_feed_state"
