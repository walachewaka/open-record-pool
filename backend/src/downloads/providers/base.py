"""
Provider adapter contract + the shared subprocess wrapper (MOO-78 D1/D2).

The three tools (yt-dlp, scdl, spotDL) run as pinned CLI subprocesses in their
own venvs -- never imported into the app. Invocation rules (SECURITY.md 9):
  - argv arrays only, absolute binary paths, NEVER a shell string
  - a scrubbed environment (only PATH/HOME plus the specific creds the adapter
    passes), cwd confined to a private per-request workdir
  - a hard timeout after which the whole process group is killed

No create_subprocess_shell anywhere in this package -- asserted by the harness.
"""
import asyncio
import os
import signal

DOWNLOAD_TIMEOUT_SECONDS = int(os.environ.get("DOWNLOAD_TIMEOUT_SECONDS", "900"))
DOWNLOAD_MAX_FILE_MB = int(os.environ.get("DOWNLOAD_MAX_FILE_MB", "200"))

# stderr fragments that mark a transient (retryable) failure vs a permanent one.
_TRANSIENT_MARKERS = (
    "timed out",
    "timeout",
    "temporary failure",
    "connection reset",
    "connection refused",
    "network is unreachable",
    "http error 5",
    "http error 429",
    "too many requests",
    "read operation timed out",
    "unable to download",
    "getaddrinfo",
    "name or service not known",
)


class ToolError(Exception):
    """A provider tool subprocess failed. `transient` gates retry classification."""

    def __init__(self, message, transient=False, kind="tool"):
        super().__init__(message)
        self.transient = transient
        self.kind = kind


def source_metadata(
    title=None,
    artist=None,
    album=None,
    artwork_url=None,
    upload_date=None,
    duration_seconds=None,
    uploader=None,
    source_url=None,
    raw=None,
):
    """Build a SourceMetadata dict (plain dict, 3.7-friendly) with stable keys."""
    return {
        "title": title,
        "artist": artist,
        "album": album,
        "artwork_url": artwork_url,
        "upload_date": upload_date,
        "duration_seconds": duration_seconds,
        "uploader": uploader,
        "source_url": source_url,
        "raw": raw,
    }


def _scrubbed_env(extra=None):
    """A minimal environment for the tool subprocess (SECURITY.md 9)."""
    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": "/tmp",
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "LC_ALL": os.environ.get("LC_ALL", "C.UTF-8"),
    }
    if extra:
        env.update({k: v for k, v in extra.items() if v is not None})
    return env


def redact_argv(argv, redact=()):
    """A log-safe copy of argv with the value AFTER each redacted flag masked."""
    if not redact:
        return list(argv)
    safe = list(argv)
    for i, token in enumerate(safe):
        if token in redact and i + 1 < len(safe):
            safe[i + 1] = "***"
    return safe


def _classify_stderr(stderr):
    low = (stderr or "").lower()
    return any(marker in low for marker in _TRANSIENT_MARKERS)


async def run_tool(
    argv, cwd, timeout=None, progress_cb=None, redact=(), env_extra=None
):
    """
    Run a tool subprocess with argv arrays only and a scrubbed env, streaming
    stdout so a progress callback can parse it. Kills the whole process group
    on timeout. Returns (rc, stdout, stderr); raises ToolError on timeout.

    progress_cb, when given, is called with each decoded stdout line.
    """
    timeout = timeout or DOWNLOAD_TIMEOUT_SECONDS
    # start_new_session=True puts the child in its own process group so a
    # timeout can kill the whole tree (yt-dlp spawns ffmpeg children).
    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=cwd,
        env=_scrubbed_env(env_extra),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )

    stdout_lines = []

    async def _pump():
        assert proc.stdout is not None
        while True:
            raw = await proc.stdout.readline()
            if not raw:
                break
            line = raw.decode("utf-8", "replace").rstrip("\n")
            stdout_lines.append(line)
            if progress_cb is not None:
                try:
                    await progress_cb(line)
                except Exception:
                    pass

    try:
        await asyncio.wait_for(asyncio.gather(_pump(), proc.wait()), timeout=timeout)
    except asyncio.TimeoutError:
        _kill_group(proc)
        raise ToolError(
            "Tool timed out after {}s".format(timeout), transient=True, kind="network"
        )

    stderr_bytes = await proc.stderr.read() if proc.stderr else b""
    stderr = stderr_bytes.decode("utf-8", "replace")
    return proc.returncode, "\n".join(stdout_lines), stderr


def _kill_group(proc):
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except ProcessLookupError:
            pass


def raise_for_tool(rc, stderr, context):
    """Raise a classified ToolError when a tool exited non-zero."""
    if rc == 0:
        return
    transient = _classify_stderr(stderr)
    tail = (stderr or "").strip().splitlines()
    detail = tail[-1] if tail else "exit code {}".format(rc)
    raise ToolError(
        "{}: {}".format(context, detail),
        transient=transient,
        kind="network" if transient else "tool",
    )


class ProviderAdapter(object):
    """
    Base class for the three provider adapters. Subclasses implement probe()
    (metadata only, never audio) and fetch() (download + convert to mp3 into
    workdir, returning the single resulting file's absolute path).
    """

    name = None

    async def probe(self, url, external_id, workdir):
        raise NotImplementedError

    async def fetch(self, url, external_id, workdir, progress_cb=None):
        raise NotImplementedError


def single_audio_file(workdir):
    """
    The one audio file a tool wrote into workdir, realpath-confined. Raises
    ToolError when zero or more than one candidate exists (a fatal tool error).
    """
    audio_exts = (".mp3", ".m4a", ".opus", ".ogg", ".flac", ".wav", ".aac")
    root = os.path.realpath(workdir)
    found = []
    for entry in os.listdir(root):
        full = os.path.realpath(os.path.join(root, entry))
        if not full.startswith(root + os.sep):
            continue
        if os.path.isfile(full) and full.lower().endswith(audio_exts):
            found.append(full)
    if len(found) != 1:
        raise ToolError(
            "expected exactly one audio file in workdir, found {}".format(len(found)),
            transient=False,
            kind="tool",
        )
    return found[0]
