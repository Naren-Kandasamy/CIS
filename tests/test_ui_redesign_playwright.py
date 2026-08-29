"""End-to-end coverage for the Phase 1-6 UI redesign.

Same shape as tests/test_ui_playwright.py: a plain Playwright sync script
(no pytest fixtures) so it can run standalone against the live dev
servers -- backend :8001, client :5173/app/, login dysp1 / demo1234.

    python tests/test_ui_redesign_playwright.py

Covers:
  * login lands on the /cases folder grid, NOT the chat
  * create a case through the dialog -> its folder tile appears
  * open a folder -> the per-case workspace renders
  * start a session -> URL becomes /cases/<c_>/sessions/<s_>
  * submit a query -> status pill shows then hides -> evidence renders
  * pin a citation -> reload -> still pinned
  * evidence board: add a card, drag it, reload -> position persisted
  * SSE cut-off: a /api/query stream with no terminal event still
    resolves via the /api/query/status/<job> poll
"""
import re
import time

from playwright.sync_api import sync_playwright, expect

BASE = "http://localhost:5173/app"
LOGIN_USER = "dysp1"
LOGIN_PASS = "demo1234"


def _login(page):
    page.goto(f"{BASE}/login")
    page.wait_for_selector("#login-username", timeout=10000)
    page.locator("#login-username").fill(LOGIN_USER)
    page.locator("#login-password").fill(LOGIN_PASS)
    page.locator("button[type='submit']").click()
    page.wait_for_url(re.compile(r"/app/cases$"), timeout=15000)


def test_login_lands_on_folder_grid(page):
    print("\n[1] login -> /cases folder grid ...")
    _login(page)
    # the folder room, not the chat
    page.wait_for_selector("text=Case files", timeout=10000)
    assert page.locator(".chat-messages").count() == 0, "landed on chat, expected folder grid"
    assert page.locator(".case-folder, .cases-grid").count() > 0
    print("    ok")


def test_create_case_via_dialog(page):
    print("\n[2] create case via dialog ...")
    _login(page)
    title = f"PW Redesign Case {int(time.time())}"

    # open the New case dialog (sidebar action or the dashed folder tile)
    opener = page.locator("text=New case").first
    if opener.count() == 0:
        opener = page.locator("text=Open a case file").first
    opener.click()

    dialog = page.locator(".modal-card")
    dialog.wait_for(state="visible", timeout=5000)
    dialog.locator(".dialog-field input").first.fill(title)
    dialog.locator(".modal-actions .btn-primary").click()

    # the new folder tile shows up in the grid
    page.wait_for_selector(f"text={title}", timeout=10000)
    print("    ok:", title)
    return title


def test_open_folder_into_workspace(page):
    print("\n[3] open folder -> workspace ...")
    _login(page)
    folder = page.locator(".case-folder").first
    folder.wait_for(state="visible", timeout=10000)
    folder.click()
    page.wait_for_url(re.compile(r"/app/cases/c_[0-9a-f]+$"), timeout=10000)
    # workspace chrome: either the dossier panels or the "start first session" empty state
    page.wait_for_selector(".dossier-panel, .empty-state, .workspace-head", timeout=10000)
    print("    ok:", page.url)


def test_start_session_url_shape(page):
    print("\n[4] start session -> /sessions/s_ ...")
    _login(page)
    page.locator(".case-folder").first.click()
    page.wait_for_url(re.compile(r"/app/cases/c_[0-9a-f]+$"), timeout=10000)

    starter = page.locator(
        ".drawer-sessions-head button, text=Start first session, text=New session"
    ).first
    starter.wait_for(state="visible", timeout=10000)
    starter.click()
    page.wait_for_url(re.compile(r"/app/cases/c_[0-9a-f]+/sessions/s_[0-9a-f]+"), timeout=15000)
    print("    ok:", page.url)


def test_query_progress_then_evidence(page):
    print("\n[5] query -> status pill -> evidence ...")
    _login(page)
    page.locator(".case-folder").first.click()
    page.wait_for_url(re.compile(r"/app/cases/c_[0-9a-f]+$"), timeout=10000)
    page.locator(
        ".drawer-sessions-head button, text=Start first session, text=New session"
    ).first.click()
    page.wait_for_url(re.compile(r"/sessions/s_[0-9a-f]+"), timeout=15000)

    box = page.locator("textarea, .input-box input").first
    box.wait_for(state="visible", timeout=10000)
    box.fill("list recent theft cases in Belagavi")
    page.locator("button[type='submit'], button.action-btn.primary").first.click()

    page.wait_for_selector(".status-pill", timeout=8000)
    page.wait_for_selector(".status-pill", state="hidden", timeout=60000)

    last = page.locator(".message").last
    expect(last).to_be_visible()
    # evidence panel or at least a rendered field report
    assert last.locator(".evidence-card, .message-content").count() > 0
    print("    ok")


def test_pin_citation_persists_across_reload(page):
    print("\n[6] pin citation -> reload -> still pinned ...")
    _login(page)
    page.locator(".case-folder").first.click()
    page.wait_for_url(re.compile(r"/app/cases/c_[0-9a-f]+$"), timeout=10000)
    case_url = page.url

    page.locator(
        ".drawer-sessions-head button, text=Start first session, text=New session"
    ).first.click()
    page.wait_for_url(re.compile(r"/sessions/s_[0-9a-f]+"), timeout=15000)
    box = page.locator("textarea, .input-box input").first
    box.fill("list recent theft cases in Belagavi")
    page.locator("button[type='submit'], button.action-btn.primary").first.click()
    page.wait_for_selector(".status-pill", state="hidden", timeout=60000)

    # expand evidence if collapsed, then pin the first citation
    details = page.locator("details.evidence-card").first
    if details.count() and not details.evaluate("d => d.open"):
        details.locator("summary").click()
    pin = page.locator("button[aria-label='Pin to case board']").first
    pin.wait_for(state="visible", timeout=10000)
    pin.click()
    expect(page.locator("button[aria-label='Pinned to case board']").first).to_be_visible(timeout=10000)

    # workspace shows the pinned citation, and it survives a reload
    page.goto(case_url)
    page.wait_for_selector("text=Pinned Citations, text=Pinned citation", timeout=10000)
    rows_before = page.locator(".dossier-row, .citations-row, tbody tr").count()
    page.reload()
    page.wait_for_selector("text=Pinned Citations, text=Pinned citation", timeout=10000)
    assert page.locator(".dossier-row, .citations-row, tbody tr").count() == rows_before
    print("    ok")


def test_board_card_position_persists(page):
    print("\n[7] board: add card -> drag -> reload -> position kept ...")
    _login(page)
    page.locator(".case-folder").first.click()
    page.wait_for_url(re.compile(r"/app/cases/c_[0-9a-f]+$"), timeout=10000)
    case_id = re.search(r"/cases/(c_[0-9a-f]+)", page.url).group(1)

    page.goto(f"{BASE}/cases/{case_id}/board")
    page.wait_for_selector(".corkboard, .board-stage", timeout=10000)

    # add a blank note
    page.locator(".board-toolbar >> text=Note").click()
    card = page.locator(".board-card").last
    card.wait_for(state="visible", timeout=5000)

    start = card.bounding_box()
    page.mouse.move(start["x"] + start["width"] / 2, start["y"] + 20)
    page.mouse.down()
    page.mouse.move(start["x"] + 180, start["y"] + 120, steps=10)
    page.mouse.up()
    time.sleep(1.5)  # let the ~800ms debounced PUT flush
    moved = card.bounding_box()
    assert abs(moved["x"] - start["x"]) > 60, "card did not move"

    page.reload()
    page.wait_for_selector(".board-card", timeout=10000)
    after = page.locator(".board-card").last.bounding_box()
    # within a few px of where it was dropped (allow for zoom rounding)
    assert abs(after["x"] - moved["x"]) < 12 and abs(after["y"] - moved["y"]) < 12, (
        f"position not persisted: dropped at {moved}, reloaded at {after}"
    )
    print("    ok")


def test_sse_cutoff_recovers_via_poll(page):
    print("\n[8] SSE stream with no terminal event -> poll recovery ...")
    _login(page)
    page.locator(".case-folder").first.click()
    page.wait_for_url(re.compile(r"/app/cases/c_[0-9a-f]+$"), timeout=10000)
    page.locator(
        ".drawer-sessions-head button, text=Start first session, text=New session"
    ).first.click()
    page.wait_for_url(re.compile(r"/sessions/s_[0-9a-f]+"), timeout=15000)

    job_id = "job_pwtest_cutoff"

    def handle_query(route):
        # a job id, a couple of progress frames, then the connection ends
        # WITHOUT a `done` event -- the client must fall back to polling.
        body = (
            f'data: {{"type":"job","job_id":"{job_id}"}}\n\n'
            'data: {"type":"progress","step":"retrieval","status":"running"}\n\n'
            'data: {"type":"progress","step":"synthesis","status":"running"}\n\n'
        )
        route.fulfill(status=200, headers={"Content-Type": "text/event-stream"}, body=body)

    def handle_status(route):
        # pollForCompletedJob resolves on status "done"|"failed" and reads a
        # flat {answer, evidence, visualization} shape.
        route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body='{"status":"done","answer":"Recovered via poll.","evidence":[]}',
        )

    page.route("**/api/query", handle_query)
    page.route(re.compile(r".*/api/query/status/.*"), handle_status)

    box = page.locator("textarea, .input-box input").first
    box.fill("trigger a cut-off stream")
    page.locator("button[type='submit'], button.action-btn.primary").first.click()

    expect(page.locator("text=Recovered via poll.")).to_be_visible(timeout=30000)
    print("    ok")


ALL = [
    test_login_lands_on_folder_grid,
    test_create_case_via_dialog,
    test_open_folder_into_workspace,
    test_start_session_url_shape,
    test_query_progress_then_evidence,
    test_pin_citation_persists_across_reload,
    test_board_card_position_persists,
    test_sse_cutoff_recovers_via_poll,
]


def main():
    print("=" * 60)
    print("UI redesign E2E (Phase 1-6)")
    print("=" * 60)
    failures = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for fn in ALL:
            ctx = browser.new_context()
            page = ctx.new_page()
            try:
                fn(page)
            except Exception as exc:  # noqa: BLE001 - report and continue
                failures.append((fn.__name__, exc))
                print(f"    FAIL: {exc}")
            finally:
                ctx.close()
        browser.close()

    if failures:
        print(f"\n{len(failures)} failure(s):")
        for name, exc in failures:
            print(f"  - {name}: {exc}")
        raise SystemExit(1)
    print("\nAll UI redesign E2E checks passed.")


if __name__ == "__main__":
    main()
