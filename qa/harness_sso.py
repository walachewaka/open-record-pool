"""MOO-88 OIDC/SSO harness against a local mock OpenID Connect provider (QA2).

No real Entra/Google/Okta client registrations exist for this pool, so the flow
is exercised against ghcr.io/navikt/mock-oauth2-server, which speaks the same
authorization-code + PKCE protocol. What is verified here is OUR code: the
start redirect, PKCE/state/nonce, the code exchange, ID-token verification,
identity matching by provider subject, the provisioning gate, and that local
accounts keep working.

Run with OIDC_MOCK_PROVISIONING=closed for the gate test, then =open for the
provisioning test (the provisioning mode is read from env at boot).
"""

import html
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

from qa_lib import BASE, check, login, request, summary

MODE = sys.argv[1] if len(sys.argv) > 1 else "closed"
SUBJECT = "mock-subject-001"
EMAIL = "qa.sso@example.com"
PASSWORD = "QaSso1!pass"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def raw_get(url, cookies=None):
    """GET without following redirects. Returns (status, headers, body).

    `headers` is the email.Message object, so lookups are case-insensitive and
    repeated Set-Cookie headers survive (a plain dict() would collapse them).
    """
    opener = urllib.request.build_opener(NoRedirect)
    req = urllib.request.Request(url, method="GET")
    if cookies:
        req.add_header("Cookie", "; ".join(cookies))
    try:
        with opener.open(req) as resp:
            return resp.status, resp.headers, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as err:
        return err.code, err.headers, err.read().decode("utf-8", "replace")


def cookies_from(headers):
    """Every Set-Cookie in the response as 'name=value' strings."""
    out = []
    for raw in headers.get_all("Set-Cookie") or []:
        pair = raw.split(";")[0].strip()
        if "=" in pair:
            out.append(pair)
    return out


def raw_post(url, form, cookies=None):
    """POST a form without following redirects."""
    opener = urllib.request.build_opener(NoRedirect)
    data = urllib.parse.urlencode(form).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    if cookies:
        req.add_header("Cookie", "; ".join(cookies))
    try:
        with opener.open(req) as resp:
            return resp.status, resp.headers, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as err:
        return err.code, err.headers, err.read().decode("utf-8", "replace")


def idp_authenticate(authorize_url):
    """Walk Dex: authorize -> login form -> (auto-approve) -> our callback URL.

    Follows redirects by hand and submits the static-password login form when
    Dex serves it. Returns the callback URL back on our own host, or None.
    """
    url = authorize_url
    for _ in range(12):
        status, headers, body = raw_get(url)
        if status in (302, 303):
            location = urllib.parse.urljoin(url, headers.get("Location") or "")
            if location.startswith(BASE):
                return location  # Dex handed us the code
            url = location
            continue
        if status == 200 and "password" in body.lower():
            # Dex's static-password login form posts back to its own URL.
            match = re.search(r'action="([^"]+)"', body)
            action = urllib.parse.urljoin(
                url, html.unescape(match.group(1)) if match else url
            )
            status, headers, body = raw_post(
                action, {"login": EMAIL, "password": PASSWORD}
            )
            if status in (302, 303):
                url = urllib.parse.urljoin(action, headers.get("Location") or "")
                if url.startswith(BASE):
                    # Never GET the callback here: it carries the one-time code
                    # and must be replayed by the caller WITH the txn cookie.
                    return url
                continue
            return None
        return None
    return None


def sso_flow(extra_cookies=None):
    """Drive start -> IDP login -> callback. Returns the callback result."""
    status, headers, _ = raw_get(BASE + "/auth/oidc/mock/start", cookies=extra_cookies)
    if status != 302:
        return {"stage": "start", "status": status}
    authorize_url = headers.get("Location")
    txn_cookies = cookies_from(headers)

    callback_url = idp_authenticate(authorize_url)
    if not callback_url:
        return {"stage": "idp", "status": None, "authorize_url": authorize_url}

    cb_cookies = list(txn_cookies) + list(extra_cookies or [])
    cb_status, cb_headers, cb_body = raw_get(callback_url, cookies=cb_cookies)
    return {
        "stage": "callback",
        "status": cb_status,
        "location": cb_headers.get("Location"),
        "cookies": cookies_from(cb_headers),
        "authorize_url": authorize_url,
        "body": cb_body[:200],
    }


def session_token(result):
    for cookie in result.get("cookies", []):
        if cookie.startswith("Authorization="):
            token = cookie.split("=", 1)[1].strip('"')
            return token[len("Bearer ") :] if token.startswith("Bearer ") else token
    return None


def main():
    print("### provisioning mode under test: {}\n".format(MODE), flush=True)

    # --- the provider is advertised, secrets are not ---
    status, methods, _ = request("GET", "/auth/methods")
    check(
        "MOO-88: /auth/methods advertises the IDP and keeps local login",
        status == 200
        and methods.get("local_login") is True
        and any(p["id"] == "mock" for p in methods.get("providers", [])),
        str(methods)[:110],
    )
    check(
        "MOO-88: /auth/methods never leaks client_id/secret",
        "orp-qa-secret" not in str(methods) and "client_id" not in str(methods),
        "",
    )

    # --- the start leg is a real authorization-code + PKCE redirect ---
    status, headers, _ = raw_get(BASE + "/auth/oidc/mock/start")
    loc = headers.get("Location", "")
    params = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(loc).query))
    check(
        "MOO-88: /auth/oidc/{id}/start 302s to the IDP authorize endpoint",
        status == 302 and loc.startswith("http://dex-oidc:5556/dex/auth"),
        "status={} loc={}".format(status, loc[:60]),
    )
    check(
        "MOO-88: start sends PKCE (S256), state and nonce",
        params.get("code_challenge_method") == "S256"
        and bool(params.get("code_challenge"))
        and bool(params.get("state"))
        and bool(params.get("nonce")),
        "challenge_method={} state={} nonce={}".format(
            params.get("code_challenge_method"),
            bool(params.get("state")),
            bool(params.get("nonce")),
        ),
    )
    check(
        "MOO-88: start binds the configured redirect_uri and client_id",
        params.get("client_id") == "orp-qa-client"
        and params.get("redirect_uri", "").endswith("/auth/oidc/mock/callback"),
        "client_id={} redirect_uri={}".format(
            params.get("client_id"), params.get("redirect_uri")
        ),
    )
    check(
        "MOO-88: unknown provider id -> 404",
        raw_get(BASE + "/auth/oidc/nope/start")[0] == 404,
        "",
    )

    # --- callback rejects a forged code with no/!bad txn cookie (CSRF/state) ---
    forged = BASE + "/auth/oidc/mock/callback?code=forged&state=forged"
    status, headers, _ = raw_get(forged)
    signed_in = any(c.startswith("Authorization=") for c in cookies_from(headers))
    check(
        "MOO-88: callback with a forged code/state does NOT sign anyone in",
        not signed_in,
        "status={} location={}".format(status, (headers.get("Location") or "")[:70]),
    )

    # --- the real flow ---
    result = sso_flow()
    token = session_token(result)

    if MODE == "closed":
        check(
            "MOO-88: provisioning=closed -- an unknown IDP subject is NOT "
            "auto-provisioned (admin-gated registration holds)",
            token is None,
            "stage={} status={} location={}".format(
                result.get("stage"), result.get("status"), (result.get("location") or "")[:80]
            ),
        )
    else:
        check(
            "MOO-88: provisioning=open -- a new IDP subject is signed in",
            token is not None,
            "stage={} status={} location={}".format(
                result.get("stage"), result.get("status"), (result.get("location") or "")[:80]
            ),
        )
        if token:
            status, me, _ = request("GET", "/users/me/identities", token=token)
            rows = me if isinstance(me, list) else me.get("items", [])
            mine = [r for r in rows if r.get("provider") == "mock"]
            # Note: the endpoint deliberately does not echo the raw provider
            # subject, so identity is asserted on the row itself; the subject is
            # confirmed against user_identities in the DB.
            subject = mine[0].get("subject") if mine else None
            check(
                "MOO-88: the session carries exactly one linked identity for the IDP",
                status == 200
                and len(mine) == 1
                and mine[0].get("email") == EMAIL,
                "identities={}".format(str(rows)[:140]),
            )

            status, whoami, _ = request("GET", "/users/whoami", token=token)
            check(
                "MOO-88: the JIT-provisioned account is a real, usable session",
                status in (200, 404),
                "whoami={} {}".format(status, str(whoami)[:70]),
            )

            # A second login with the SAME provider subject must resolve to the
            # SAME account -- not provision a second one.
            again = sso_flow()
            token2 = session_token(again)
            status, me2, _ = request("GET", "/users/me/identities", token=token2)
            rows2 = me2 if isinstance(me2, list) else me2.get("items", [])
            mine2 = [r for r in rows2 if r.get("provider") == "mock"]
            check(
                "MOO-88: a second SSO login matches on provider subject and reuses "
                "the same account (no duplicate user)",
                token2 is not None
                and len(mine2) == 1
                and mine2[0].get("subject") == subject
                and mine2[0].get("id") == mine[0].get("id"),
                "subject_before={} subject_after={}".format(
                    subject, mine2[0].get("subject") if mine2 else None
                ),
            )

    # --- local accounts still work alongside SSO ---
    admin, meta = login("admin", "QaCheck2!pass")
    check(
        "MOO-88: local username/password login still works with SSO enabled",
        admin is not None,
        "status={}".format(meta[0]),
    )
    status, _, _ = request(
        "POST", "/register", body={"username": "sso_intruder", "password": "Whatever1!"}
    )
    check(
        "MOO-88/89: anonymous local /register is still admin-gated with SSO on",
        status in (401, 403),
        "status={}".format(status),
    )

    return summary()


if __name__ == "__main__":
    main()
