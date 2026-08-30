import pytest

# These files live under tests/ and match pytest's `test_*` discovery glob,
# but they are NOT part of the unit/integration suite:
#
#  * Standalone probe scripts -- module-level `asyncio.run(...)` (executes on
#    import), `print()` instead of `assert`, and live calls to Zoho Catalyst
#    endpoints with real tokens. Meant to be run by hand:
#    `python tests/test_zia.py`.
#  * Playwright e2e -- plain sync scripts that drive a full running stack
#    (backend :8001 + client :5173, login dysp1/demo1234); they have no
#    value without those servers up and are documented to run standalone.
#
# Collecting them made `pytest` do network I/O during collection and abort
# the whole run on import errors (missing CATALYST_API_TOKEN, no playwright,
# absent data files). Skip them here; run them directly when needed.
collect_ignore = [
    "test_catalyst.py",
    "test_llm.py",
    "test_llm_json.py",
    "test_sdk.py",
    "test_signals.py",
    "test_zia.py",
    "test_chaos.py",
    "test_data.py",
    "test_shutdown.py",
    "test_default_shutdown.py",
    "test_ui_playwright.py",
    "test_ui_redesign_playwright.py",
]

# BUG FIX: pytest.mark.anyio auto-parametrizes over every installed anyio
# backend (asyncio, trio). This codebase only ever runs plain asyncio
# (asyncio.run() everywhere, Catalyst Functions and AppSail both use it,
# nothing here uses trio) -- without this fixture, tests fail with
# ModuleNotFoundError on any machine/CI that doesn't happen to have trio
# installed as an unrelated transitive dependency.
@pytest.fixture
def anyio_backend():
    return "asyncio"
