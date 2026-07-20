"""Shared HTTP helpers for the QA checkpoint-2 harnesses (MOO-92).

Stdlib only -- runs inside the backend container against the live stack.
"""
import json
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://localhost:5000"

RESULTS = []


def request(method, path, token=None, body=None, form=None, headers=None):
    """Return (status, parsed_body_or_text, response_headers)."""
    url = BASE + path
    data = None
    hdrs = dict(headers or {})
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        hdrs["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
        data = json.dumps(body).encode()
        hdrs["Content-Type"] = "application/json"
    if token:
        hdrs["Cookie"] = "Authorization=Bearer " + token
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return resp.status, _parse(raw), dict(resp.headers)
    except urllib.error.HTTPError as err:
        raw = err.read().decode("utf-8", "replace")
        return err.code, _parse(raw), dict(err.headers)
    except Exception as err:  # noqa: BLE001 - surface transport errors as -1
        return -1, {"transport_error": str(err)}, {}


def _parse(raw):
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def login(username, password):
    """Log in and return the bare JWT from the Authorization cookie."""
    status, body, headers = request(
        "POST", "/login", form={"username": username, "password": password}
    )
    if status != 200:
        return None, (status, body)
    cookie = headers.get("set-cookie", "")
    token = None
    for part in cookie.split(";"):
        part = part.strip()
        if part.startswith("Authorization="):
            token = part.split("=", 1)[1].strip('"')
            if token.startswith("Bearer "):
                token = token[len("Bearer ") :]
    return token, (status, body)


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    mark = "PASS" if ok else "FAIL"
    line = "[{}] {}".format(mark, name)
    if detail:
        line += " -- {}".format(detail)
    print(line, flush=True)
    return bool(ok)


def summary():
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    failed = [n for n, ok, _ in RESULTS if not ok]
    print("\n==== SUMMARY: {}/{} passed ====".format(passed, len(RESULTS)), flush=True)
    for name in failed:
        print("FAILED: {}".format(name), flush=True)
    return failed
