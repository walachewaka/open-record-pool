"""
Telemetry: the fire-and-forget event pipeline into Elasticsearch (MOO-83).

Public surface:

    from src import telemetry
    telemetry.emit("play.start", user_id=1, song_id=7)

or, preferably, the typed helpers in src/telemetry/events.py so a call site
cannot misspell a field.

Everything here is best-effort by construction: emit() is a synchronous
O(1) buffer append that never raises and never touches the network, and the
flush loop swallows every Elasticsearch error. A dead ES cluster costs the
user nothing but the telemetry itself.
"""
from src.telemetry.emitter import (  # noqa: F401
    emit,
    enabled,
    level,
    start_emitter,
    stats,
    stop_emitter,
)
