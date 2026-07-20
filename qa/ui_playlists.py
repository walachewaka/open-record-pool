"""MOO-84 playlist UI smoke via Playwright (QA2, MOO-92).

The repo ships no e2e tooling (the Playwright suite was lost in MOO-95), so this
drives the real browser against the built frontend: log in, see your crates,
open one, and confirm another user's PRIVATE crate is not reachable from the UI
while a PUBLIC one is.
"""
import sys

from playwright.sync_api import sync_playwright

FRONTEND = "http://localhost:8088"
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print("[{}] {}{}".format("PASS" if ok else "FAIL", name, " -- " + detail if detail else ""), flush=True)


def login(page, username, password):
    page.goto(FRONTEND + "/login", wait_until="networkidle")
    page.fill("input[type=text], input[name=username], #username", username)
    page.fill("input[type=password]", password)
    page.click("button[type=submit], button:has-text('Login'), button:has-text('Log in')")
    page.wait_for_timeout(2500)
    return "/login" not in page.url


def main():
    priv_id, pub_id = sys.argv[1], sys.argv[2]
    with sync_playwright() as pw:
        browser = pw.chromium.launch()

        # --- Alice: owns the crates ---
        ctx = browser.new_context()
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        ok = login(page, "qa2_alice", "QaUser2!pass")
        check("UI: member can log in through the web UI", ok, "url={}".format(page.url))

        page.goto(FRONTEND + "/crate/" + priv_id, wait_until="networkidle")
        page.wait_for_timeout(1500)
        body = page.inner_text("body")
        check(
            "UI/MOO-84: owner can open their own private crate",
            "QA2 UI Private" in body,
            "page shows crate name",
        )
        check(
            "UI/MOO-84: the crate's tracks render",
            "Anita" in body or "track" in body.lower(),
            body[:70].replace("\n", " "),
        )
        page.screenshot(path="/tmp/qa_ui_owner_crate.png")

        # --- Bob: must NOT see Alice's private crate ---
        ctx2 = browser.new_context()
        page2 = ctx2.new_page()
        login(page2, "qa2_bob", "QaUser2!pass")

        page2.goto(FRONTEND + "/crate/" + priv_id, wait_until="networkidle")
        page2.wait_for_timeout(1500)
        body2 = page2.inner_text("body")
        check(
            "UI/MOO-84 IDOR: another user's PRIVATE crate does not render its "
            "contents in the UI",
            "QA2 UI Private" not in body2 and "Anita" not in body2,
            "body={}".format(body2[:80].replace("\n", " ")),
        )
        page2.screenshot(path="/tmp/qa_ui_private_denied.png")

        page2.goto(FRONTEND + "/crate/" + pub_id, wait_until="networkidle")
        page2.wait_for_timeout(1500)
        body3 = page2.inner_text("body")
        check(
            "UI/MOO-84: a PUBLIC crate is consultable by another user",
            "QA2 UI Public" in body3,
            "body={}".format(body3[:80].replace("\n", " ")),
        )
        page2.screenshot(path="/tmp/qa_ui_public_ok.png")

        check("UI: no uncaught JS errors on the crate pages", not errors, str(errors[:2]))
        browser.close()

    passed = sum(1 for _, ok in RESULTS if ok)
    print("\n==== UI SUMMARY: {}/{} passed ====".format(passed, len(RESULTS)))
    for name, ok in RESULTS:
        if not ok:
            print("FAILED:", name)


if __name__ == "__main__":
    main()
