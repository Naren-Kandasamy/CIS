import pytest

# BUG FIX: pytest.mark.anyio auto-parametrizes over every installed anyio
# backend (asyncio, trio). This codebase only ever runs plain asyncio
# (asyncio.run() everywhere, Catalyst Functions and AppSail both use it,
# nothing here uses trio) -- without this fixture, tests fail with
# ModuleNotFoundError on any machine/CI that doesn't happen to have trio
# installed as an unrelated transitive dependency.
@pytest.fixture
def anyio_backend():
    return "asyncio"
