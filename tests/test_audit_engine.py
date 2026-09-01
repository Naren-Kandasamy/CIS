# BUG FIX (2026-09 audit) regression coverage: shared/audit_engine.py's
# write_hash_chained_entry was previously a print()-only stub. These tests
# exercise the real NoSQL-backed, hash-chained implementation against an
# in-memory fake store (no real Catalyst NoSQL needed) to prove: entries
# persist, sequence numbers increment, each entry's hash covers the previous
# entry's hash (so the chain is genuinely linked, not just a flat log), and
# verify_audit_chain() detects tampering.
import json
from unittest.mock import patch, AsyncMock

import pytest

from shared.audit_engine import write_hash_chained_entry, verify_audit_chain, _GENESIS_HASH


class FakeNoSQL:
    """Minimal in-memory stand-in for the real Catalyst NoSQL get/set calls."""

    def __init__(self):
        self.store: dict[str, str] = {}

    async def get(self, key):
        if key not in self.store:
            return None
        return {"value": self.store[key]}

    async def set(self, key, value, ttl=None):
        self.store[key] = value
        return {"key": key, "value": value}


@pytest.fixture
def fake_nosql():
    fake = FakeNoSQL()
    with patch("shared.audit_engine.nosql_get", side_effect=fake.get), \
         patch("shared.audit_engine.nosql_set", side_effect=fake.set):
        yield fake


@pytest.mark.asyncio
async def test_first_entry_chains_to_genesis(fake_nosql):
    entry = await write_hash_chained_entry("test_event", {"who": "officer_1"})
    assert entry["seq"] == 1
    assert entry["prev_hash"] == _GENESIS_HASH
    assert entry["entry_hash"]  # non-empty


@pytest.mark.asyncio
async def test_sequence_increments_and_links_to_prior_hash(fake_nosql):
    first = await write_hash_chained_entry("event_a", {"n": 1})
    second = await write_hash_chained_entry("event_b", {"n": 2})

    assert second["seq"] == first["seq"] + 1
    assert second["prev_hash"] == first["entry_hash"]
    assert second["entry_hash"] != first["entry_hash"]


@pytest.mark.asyncio
async def test_verify_audit_chain_passes_on_untouched_chain(fake_nosql):
    for i in range(5):
        await write_hash_chained_entry("event", {"n": i})

    result = await verify_audit_chain()
    assert result == {"ok": True, "checked": 5, "broken_at": None}


@pytest.mark.asyncio
async def test_verify_audit_chain_detects_payload_tampering(fake_nosql):
    for i in range(5):
        await write_hash_chained_entry("event", {"n": i})

    # Tamper with entry 3's payload directly in the fake store, as someone
    # with raw NoSQL write access (bypassing write_hash_chained_entry, and
    # therefore the hash it computes) could.
    tampered = json.loads(fake_nosql.store["audit:entry:000000000003"])
    tampered["payload"] = {"n": 999}
    fake_nosql.store["audit:entry:000000000003"] = json.dumps(tampered)

    result = await verify_audit_chain()
    assert result["ok"] is False
    assert result["broken_at"] == 3


@pytest.mark.asyncio
async def test_write_hash_chained_entry_never_raises_on_storage_failure():
    with patch("shared.audit_engine.nosql_get", side_effect=RuntimeError("NoSQL down")):
        # Must not propagate -- an audit-logging failure must never take down
        # the request path that's trying to record an event.
        result = await write_hash_chained_entry("event", {"n": 1})
        assert result is None
