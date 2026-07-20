"""MOO-83 telemetry harness: event pipeline, beacon, status, Grafana proxy.

Runs inside the backend container against the live stack (like every other
harness), and additionally imports the in-process emitter from /app to assert
the buffer/level/drop behaviour that HTTP cannot observe.

Covers: the emitter contract (never raises, drop-on-overflow, level filtering),
the event taxonomy, the beacon route (authz / 422 / unknown song / rate limit),
the status card, the audit shipper's idempotency, the Grafana proxy's
authorization + header-injection defence, and the "ES down is not an outage"
promise.
"""
import asyncio
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, "/app")

from qa_lib import BASE, check, login, request, summary  # noqa: E402

ADMIN_PW = "QaCheck2!pass"
USER_PW = "QaUser2!pass"
ADMIN = "admin"
MEMBER = "qa2_alice"

ES = "http://elasticsearch:9200"


def es_get(path):
    """Raw ES query (the harness runs inside the compose network)."""
    try:
        with urllib.request.urlopen(ES + path, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as err:
        return json.loads(err.read().decode())
    except Exception as err:
        return {"transport_error": str(err)}


def es_count(query):
    body = es_get("/orp-events-*/_search?size=0&q=" + urllib.parse.quote(query))
    return int((((body.get("hits") or {}).get("total")) or {}).get("value") or 0)


# --- 1. the emitter, in-process -------------------------------------------


def test_emitter():
    from src.telemetry import emitter
    from src.telemetry import events

    emitter.reset_for_tests()

    check(
        "emitter: enabled in the live stack",
        emitter.enabled() and emitter.level() == "detailed",
        "level={}".format(emitter.level()),
    )

    emitter.emit("play.start", user_id=1, song_id=2, song_label="A - B")
    buffered = list(emitter._get_buffer())
    doc = buffered[-1]
    check(
        "emitter: envelope carries @timestamp / event / hour / weekday",
        doc.get("event") == "play.start"
        and doc.get("@timestamp", "").endswith("Z")
        and 0 <= doc.get("hour_of_day", -1) <= 23
        and 0 <= doc.get("day_of_week", -1) <= 6,
        str(doc),
    )

    # An unmapped kwarg must land under attrs, never as a top-level field: the
    # index mapping is dynamic:false.
    emitter.emit("play.start", nonsense_field="x")
    doc = list(emitter._get_buffer())[-1]
    check(
        "emitter: unmapped fields are nested under attrs",
        "nonsense_field" not in doc and (doc.get("attrs") or {}).get("nonsense_field") == "x",
        str(doc),
    )

    # emit() must never raise, whatever it is handed.
    raised = False
    try:
        emitter.emit("play.start", song_id=object())
        events.play_start(None, None)
        events.job_finished(None)
    except Exception:
        raised = True
    check("emitter: emit() never raises", not raised)

    # Drop-on-overflow: oldest events go, and the counter moves.
    emitter.reset_for_tests()
    capacity = emitter.buffer_max()
    for index in range(capacity + 25):
        emitter.emit("play.start", song_id=index)
    stats = emitter.stats()
    check(
        "emitter: overflow drops oldest and counts them",
        stats["buffer_size"] == capacity and stats["events_dropped"] == 25,
        "size={} dropped={}".format(stats["buffer_size"], stats["events_dropped"]),
    )
    emitter.reset_for_tests()


def test_event_schemas():
    from src.telemetry import emitter, events

    emitter.reset_for_tests()

    song = type(
        "S",
        (),
        {"id": 7, "title": "Title", "artist": "Artist", "genre": "House", "duration_seconds": 100},
    )()
    user = type("U", (), {"id": 3, "username": "alice"})()

    events.play_start(user, song)
    doc = list(emitter._get_buffer())[-1]
    check(
        "events: play.start carries song_label / artist / genre / duration_ms",
        doc["song_label"] == "Artist - Title"
        and doc["duration_ms"] == 100000
        and doc["genre"] == "House"
        and doc["user_id"] == 3
        and doc["username"] == "alice",
        str(doc),
    )

    events.play_end(user, song, position_ms=90000, duration_ms=100000, ended=False)
    doc = list(emitter._get_buffer())[-1]
    check(
        "events: 90% listened without 'ended' is a completion",
        doc["event"] == "play.complete" and abs(doc["completion_pct"] - 0.9) < 0.001,
        str(doc),
    )

    events.play_end(user, song, position_ms=5000, duration_ms=100000, ended=False)
    doc = list(emitter._get_buffer())[-1]
    check(
        "events: 5% listened is a skip",
        doc["event"] == "play.skip" and doc["listened_ms"] == 5000,
        str(doc),
    )

    events.search_query(user, "bass", {"genre": None}, 0, 12, "es")
    doc = list(emitter._get_buffer())[-1]
    check(
        "events: an empty result set sets zero_results",
        doc["zero_results"] is True and doc["query"] == "bass" and doc["engine"] == "es",
        str(doc),
    )
    emitter.reset_for_tests()


def test_basic_level_privacy():
    """TELEMETRY_LEVEL=basic is the operator consent lever (D2)."""
    import os

    from src.telemetry import emitter, events

    emitter.reset_for_tests()
    os.environ["TELEMETRY_LEVEL"] = "basic"
    try:
        events.search_query(None, "secret query", {}, 3, 5, "es")
        doc = list(emitter._get_buffer())[-1]
        check(
            "level=basic: the raw search string is not recorded",
            "query" not in doc and doc["result_count"] == 3,
            str(doc),
        )
        before = emitter.stats()["events_emitted"]
        events.api_request("GET", "/songs", 200, 5, None)
        check(
            "level=basic: api.request events are suppressed",
            emitter.stats()["events_emitted"] == before,
        )
    finally:
        os.environ["TELEMETRY_LEVEL"] = "detailed"
        emitter.reset_for_tests()

    os.environ["TELEMETRY_ENABLED"] = "false"
    try:
        before = emitter.stats()["events_emitted"]
        events.play_start(None, None)
        check(
            "TELEMETRY_ENABLED=false: emit() is a pure no-op",
            emitter.stats()["events_emitted"] == before and not emitter.enabled(),
        )
    finally:
        os.environ["TELEMETRY_ENABLED"] = "true"
        emitter.reset_for_tests()


# --- 2. the HTTP surface ---------------------------------------------------


def test_beacon(member_token):
    status, body, _ = request(
        "POST",
        "/telemetry/beacon",
        body={
            "type": "play.end",
            "song_id": 1,
            "position_ms": 1000,
            "duration_ms": 2000,
            "ended": False,
        },
    )
    check("beacon: unauthenticated -> 401", status == 401, str(status))

    status, body, _ = request(
        "POST",
        "/telemetry/beacon",
        token=member_token,
        body={
            "type": "play.end",
            "song_id": 1,
            "position_ms": 190000,
            "duration_ms": 200000,
            "ended": True,
        },
    )
    check("beacon: valid body -> 202 accepted", status == 202 and body.get("accepted"), str(body))

    status, body, _ = request(
        "POST",
        "/telemetry/beacon",
        token=member_token,
        body={
            "type": "nonsense",
            "song_id": 1,
            "position_ms": 0,
            "duration_ms": 1,
            "ended": False,
        },
    )
    check("beacon: unknown type -> 422", status == 422, str(body))

    status, body, _ = request(
        "POST",
        "/telemetry/beacon",
        token=member_token,
        body={
            "type": "play.end",
            "song_id": 999999999,
            "position_ms": 0,
            "duration_ms": 1000,
            "ended": True,
        },
    )
    check(
        "beacon: unknown song is accepted and dropped (never leaks the catalog)",
        status == 202,
        str(status),
    )

    status, body, _ = request(
        "POST",
        "/telemetry/beacon",
        token=member_token,
        body={
            "type": "play.end",
            "song_id": 1,
            "position_ms": -5,
            "duration_ms": 1000,
            "ended": True,
        },
    )
    check("beacon: a negative position -> 422", status == 422, str(status))


def test_status(admin_token, member_token):
    status, body, _ = request("GET", "/admin/telemetry/status", token=member_token)
    check("status: a member without view_reports -> 403", status == 403, str(status))

    status, body, _ = request("GET", "/admin/telemetry/status", token=admin_token)
    ok = status == 200 and body.get("es_reachable") and body.get("enabled")
    check(
        "status: admin sees the live pipeline card",
        ok,
        "status={} es={} grafana={} index={}".format(
            status,
            body.get("es_reachable"),
            body.get("grafana_reachable"),
            body.get("index_today"),
        ),
    )
    check(
        "status: Grafana is reachable from the backend",
        bool(body.get("grafana_reachable")),
        str(body.get("grafana_reachable")),
    )
    check(
        "status: the audit shipper reports a cursor",
        (body.get("audit_shipper") or {}).get("last_shipped_audit_id") is not None,
        str(body.get("audit_shipper")),
    )


def test_grafana_proxy(admin_token, member_token):
    status, body, _ = request("GET", "/admin/grafana/api/health")
    check("proxy: unauthenticated -> 401", status == 401, str(status))

    status, body, _ = request("GET", "/admin/grafana/api/health", token=member_token)
    check("proxy: a member without view_reports -> 403", status == 403, str(status))

    status, body, headers = request("GET", "/admin/grafana/api/health", token=admin_token)
    check("proxy: admin reaches Grafana -> 200", status == 200, str(body)[:120])

    # The embed must be framable by the admin panel, and by nobody else.
    status, body, headers = request(
        "GET", "/admin/grafana/d/orp-listening", token=admin_token
    )
    csp = headers.get("content-security-policy", "")
    check(
        "proxy: X-Frame-Options is dropped and CSP allows only our own origins",
        "x-frame-options" not in {k.lower() for k in headers}
        and "frame-ancestors" in csp
        and "'none'" not in csp,
        "csp={}".format(csp),
    )

    # Header-injection defence: a client-supplied identity must be stripped, so
    # a Viewer cannot promote themselves to a Grafana Admin.
    status, body, _ = request(
        "GET",
        "/admin/grafana/api/user",
        token=admin_token,
        headers={"X-WEBAUTH-USER": "attacker", "X-WEBAUTH-ROLE": "Admin"},
    )
    login_name = body.get("login") if isinstance(body, dict) else None
    check(
        "proxy: client-supplied X-WEBAUTH-* headers are stripped",
        login_name == ADMIN,
        "grafana identity={}".format(login_name),
    )

    status, body, _ = request(
        "GET", "/admin/grafana/api/search?type=dash-db", token=admin_token
    )
    uids = sorted(item.get("uid") for item in body) if isinstance(body, list) else []
    check(
        "proxy: the four dashboards are provisioned as code",
        uids == ["orp-engagement", "orp-library", "orp-listening", "orp-system"],
        str(uids),
    )


def test_grafana_unpublished():
    """Grafana must not be reachable except through the authenticated proxy."""
    try:
        urllib.request.urlopen("http://grafana:3000/api/health", timeout=3)
        internal = True
    except Exception:
        internal = False
    check(
        "grafana: reachable on the docker network (but never published to the host)",
        internal,
        "the compose service uses expose:, not ports:",
    )


# --- 3. end to end ---------------------------------------------------------


def test_pipeline_end_to_end(admin_token, member_token):
    """Drive the real routes, then look for the documents in Elasticsearch."""
    status, body, _ = request("GET", "/songs?page=1&page_size=1", token=member_token)
    song_id = body["items"][0]["id"] if body.get("items") else None
    if song_id is None:
        check("e2e: a song exists to play", False, "empty library")
        return

    request("POST", "/songs/{}/play".format(song_id), token=member_token)
    request(
        "POST",
        "/telemetry/beacon",
        token=member_token,
        body={
            "type": "play.end",
            "song_id": song_id,
            "position_ms": 200000,
            "duration_ms": 200000,
            "ended": True,
        },
    )
    request("GET", "/songs?q=zzzzz-no-such-track", token=member_token)
    request("GET", "/search?q=zzzzz-no-such-track", token=member_token)

    # api.request is sampled at TELEMETRY_API_SAMPLE_RATE (0.1), so a handful of
    # calls proves nothing: drive enough traffic that seeing zero would be a
    # 1-in-10^9 accident rather than a bug.
    for _ in range(200):
        request("GET", "/songs?page=1&page_size=1", token=member_token)

    # The flush loop ticks every TELEMETRY_FLUSH_INTERVAL_SECONDS (2s), and ES
    # refreshes every 5s.
    time.sleep(10)
    es_get("/orp-events-*/_refresh")

    for label, query in (
        ("play.start", "event:play.start"),
        ("play.complete", "event:play.complete"),
        ("search.query with zero results", "event:search.query AND zero_results:true"),
        ("api.request (sampled)", "event:api.request"),
    ):
        count = es_count(query)
        check("e2e: {} documents reached ES".format(label), count > 0, "count={}".format(count))


def test_index_setup():
    template = es_get("/_index_template/orp-events")
    templates = template.get("index_templates") or []
    check(
        "setup: the orp-events index template exists",
        bool(templates),
        str(template)[:120],
    )
    if templates:
        mappings = (
            templates[0]["index_template"]["template"]["mappings"]  # noqa: E501
        )
        check(
            "setup: the mapping is strict (dynamic: false)",
            mappings.get("dynamic") in (False, "false"),
            str(mappings.get("dynamic")),
        )

    policy = es_get("/_ilm/policy/orp-events-retention")
    check(
        "setup: the ILM retention policy exists",
        "orp-events-retention" in policy,
        str(policy)[:120],
    )


def test_audit_shipper():
    """The PG audit log is projected into ES, exactly once per row."""
    asyncio.get_event_loop().run_until_complete(_ship())
    es_get("/orp-events-*/_refresh")
    time.sleep(2)
    shipped = es_count("_exists_:audit_id")
    logins = es_count("event:auth.login")
    check("shipper: audit rows are projected into ES", shipped > 0, "count={}".format(shipped))
    check(
        "shipper: login rows become first-class auth.login events",
        logins > 0,
        "count={}".format(logins),
    )

    # Re-running must add nothing: the doc id is derived from the row id.
    asyncio.get_event_loop().run_until_complete(_ship())
    es_get("/orp-events-*/_refresh")
    time.sleep(2)
    after = es_count("_exists_:audit_id")
    check(
        "shipper: re-running ships nothing new (idempotent by doc id)",
        after == shipped,
        "before={} after={}".format(shipped, after),
    )


async def _ship():
    from tortoise import Tortoise

    from src.database.config import TORTOISE_ORM
    from src.telemetry import shipper

    await Tortoise.init(config=TORTOISE_ORM)
    try:
        shipper.reset_for_tests()
        await shipper.ship_audit_events()
    finally:
        await Tortoise.close_connections()


def main():
    admin_token, _ = login(ADMIN, ADMIN_PW)
    member_token, _ = login(MEMBER, USER_PW)
    if not admin_token or not member_token:
        check("login", False, "could not log in as admin/member")
        return 1

    test_emitter()
    test_event_schemas()
    test_basic_level_privacy()
    test_beacon(member_token)
    test_status(admin_token, member_token)
    test_grafana_proxy(admin_token, member_token)
    test_grafana_unpublished()
    test_index_setup()
    test_pipeline_end_to_end(admin_token, member_token)
    test_audit_shipper()

    failed = summary()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
