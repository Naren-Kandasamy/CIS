import datetime
import hashlib
import json

from shared.catalyst_client import nosql_get, nosql_set, get_lock

# BUG FIX (2026-09 audit): write_hash_chained_entry was a print()-only stub --
# "Mock implementation... will be fully implemented when the A9 audit engine
# is built" -- despite already being called on every firewall block, canned
# response and follow-up-synthesis event (langgraph_router.py). Anything
# printed only reaches Catalyst's platform log aggregation: not queryable as
# a record, not tamper-evident, and gone once log retention rolls over. For a
# police intelligence system this is the entire point of an audit trail
# (Docs/audit/Final_Checklist_Review.md Phase 6 Step 3, "Integrity &
# Anti-Corruption Layer" -- audit-logging for sensitive/cross-jurisdiction
# access), so it needed a real, persistent, tamper-evident implementation
# rather than staying a stub indefinitely.
#
# Design: entries are stored in the same Catalyst NoSQL store as everything
# else, under "audit:entry:{seq:012d}", with a monotonic "audit:seq" counter
# guarded by the existing get_lock() registry (same pattern already used for
# session history and case metadata elsewhere in shared/catalyst_client.py).
# Each entry's hash covers its own payload AND the previous entry's hash, so
# altering or deleting any past entry breaks the chain from that point
# forward -- detectable by re-walking the chain and recomputing hashes
# (verify_audit_chain, below), without needing a separate WORM store.
#
# This does NOT claim cryptographic non-repudiation (there's no external
# anchor -- someone with direct NoSQL write access could rewrite the whole
# chain consistently). It raises the bar from "silent, unlogged tampering"
# to "tampering is detectable by anyone who re-verifies the chain," which is
# what a stdout print gave zero of.

_GENESIS_HASH = "0" * 64


def _entry_hash(seq: int, event_type: str, payload: dict, timestamp: str, prev_hash: str) -> str:
    # Canonical (sorted-key, no-whitespace) JSON so the same logical entry
    # always hashes identically regardless of dict insertion order.
    canonical = json.dumps(
        {"seq": seq, "event_type": event_type, "payload": payload, "timestamp": timestamp, "prev_hash": prev_hash},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


async def write_hash_chained_entry(event_type: str, payload: dict) -> dict:
    """
    Append a tamper-evident audit entry. Returns the stored entry (including
    its seq and hash) so callers that need to correlate/display it can.
    Never raises -- an audit-logging failure must not take down the request
    it's trying to record; on failure this logs to stdout as a fallback
    (strictly worse than a real entry, but no worse than the old stub) and
    returns None.
    """
    try:
        async with get_lock("audit:seq"):
            seq_doc = await nosql_get("audit:seq")
            seq = int(seq_doc["value"]) + 1 if seq_doc else 1

            prev_hash = _GENESIS_HASH
            if seq > 1:
                prev_doc = await nosql_get(f"audit:entry:{seq - 1:012d}")
                if prev_doc:
                    prev_hash = json.loads(prev_doc["value"])["entry_hash"]

            timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
            entry_hash = _entry_hash(seq, event_type, payload, timestamp, prev_hash)
            entry = {
                "seq": seq,
                "event_type": event_type,
                "payload": payload,
                "timestamp": timestamp,
                "prev_hash": prev_hash,
                "entry_hash": entry_hash,
            }

            await nosql_set(f"audit:entry:{seq:012d}", json.dumps(entry))
            await nosql_set("audit:seq", str(seq))
            return entry
    except Exception as e:
        print(f"[AUDIT] FAILED to write hash-chained entry ({event_type}): {e}. "
              f"Falling back to stdout only: {json.dumps(payload, default=str)}")
        return None


async def verify_audit_chain(start_seq: int = 1, end_seq: int | None = None) -> dict:
    """
    Re-walk the chain from start_seq to end_seq (inclusive; defaults to the
    current tail) and recompute every entry's hash. Returns
    {"ok": bool, "checked": int, "broken_at": int | None}. Intended for an
    admin/ops check, not the request hot path -- O(n) NoSQL reads.
    """
    if end_seq is None:
        seq_doc = await nosql_get("audit:seq")
        end_seq = int(seq_doc["value"]) if seq_doc else 0

    prev_hash = _GENESIS_HASH
    if start_seq > 1:
        prior_doc = await nosql_get(f"audit:entry:{start_seq - 1:012d}")
        if prior_doc:
            prev_hash = json.loads(prior_doc["value"])["entry_hash"]

    checked = 0
    for seq in range(start_seq, end_seq + 1):
        doc = await nosql_get(f"audit:entry:{seq:012d}")
        if not doc:
            return {"ok": False, "checked": checked, "broken_at": seq}
        entry = json.loads(doc["value"])
        recomputed = _entry_hash(seq, entry["event_type"], entry["payload"], entry["timestamp"], prev_hash)
        if entry.get("prev_hash") != prev_hash or entry.get("entry_hash") != recomputed:
            return {"ok": False, "checked": checked, "broken_at": seq}
        prev_hash = entry["entry_hash"]
        checked += 1

    return {"ok": True, "checked": checked, "broken_at": None}


async def _write_firewall_audit_log(state: dict, event_type: str):
    entry = {
        "event_type": f"intent_firewall:{event_type}",
        "session_id": state.get("session_id"),
        "intent": state.get("intent_obj", {}).get("intent"),
        "raw_input": state.get("query"),
    }
    await write_hash_chained_entry(entry["event_type"], entry)
