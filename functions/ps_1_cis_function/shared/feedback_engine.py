import json
from typing import Optional
from shared.catalyst_client import nosql_get, nosql_set, get_lock, get_session_lock
from shared.feedback_models import CorrectionEvent, MethodologyTrust

PRIOR_STRENGTH = 10
PRIOR_TRUST = 0.7
TRUST_WEIGHT_FLOOR = 0.3
MIN_SAMPLES_FOR_NARROW_SCOPE = 15

# BUG FIX: edge_type/crime_type are client-controlled (backend/api/routes/feedback.py
# passes payload values straight through with no format/allowlist check) and were
# being joined into scope keys with a raw, unescaped "::" delimiter. A caller could
# set edge_type="SHARED_MO::burglary" (crime_type=None) and its broad-scope key
# ("trust:SHARED_MO::burglary") would collide with the narrow-scope key a genuine
# edge_type="SHARED_MO", crime_type="burglary" submission uses, letting an attacker
# poison another scope's trust record. Percent-encoding "%" then ":" in each part
# before joining guarantees the joined "::" can only ever be the real delimiter, so
# no input can forge a key belonging to a different scope.
def _sanitize_scope_part(value: str) -> str:
    return value.replace("%", "%25").replace(":", "%3A")

def _narrow_scope_key(edge_type: str, crime_type: str) -> str:
    return f"{_sanitize_scope_part(edge_type)}::{_sanitize_scope_part(crime_type)}"

def _smoothed_trust(confirmations: int, corrections: int) -> float:
    total = confirmations + corrections
    smoothed = (
        (confirmations + PRIOR_STRENGTH * PRIOR_TRUST)
        / (total + PRIOR_STRENGTH)
    )
    return max(smoothed, TRUST_WEIGHT_FLOOR)

async def _load_trust(scope_key: str) -> MethodologyTrust:
    raw = await nosql_get(f"trust:{scope_key}")
    if raw is None:
        return MethodologyTrust(scope_key=scope_key)
    return MethodologyTrust(**json.loads(raw["value"]))

async def _save_trust(trust: MethodologyTrust):
    await nosql_set(f"trust:{trust.scope_key}", trust.model_dump_json())

async def get_trust_weight(edge_type: str, crime_type: Optional[str]) -> float:
    if crime_type:
        narrow_key = _narrow_scope_key(edge_type, crime_type)
        narrow = await _load_trust(narrow_key)
        if (narrow.confirmations + narrow.corrections) >= MIN_SAMPLES_FOR_NARROW_SCOPE:
            return _smoothed_trust(narrow.confirmations, narrow.corrections)

    broad = await _load_trust(_sanitize_scope_part(edge_type))
    return _smoothed_trust(broad.confirmations, broad.corrections)

async def record_feedback_event(event: CorrectionEvent):
    await nosql_set(f"correction:{event.event_id}", event.model_dump_json())

    is_confirm = event.verdict == "confirmed"
    broad_key = _sanitize_scope_part(event.edge_type)
    # BUG FIX: _load_trust/_save_trust is a read-modify-write; two concurrent
    # feedback events for the same scope_key could both read the same counts
    # before either write landed, so the second write silently clobbered the
    # first instead of both increments applying. Serialize per scope_key with
    # the existing lock registry (shared/catalyst_client.py), same pattern as
    # get_session_lock's usage in backend/job_dispatch.py.
    async with get_lock(f"trust:{broad_key}"):
        broad = await _load_trust(broad_key)
        if is_confirm:
            broad.confirmations += 1
        else:
            broad.corrections += 1
        await _save_trust(broad)

    if event.crime_type:
        narrow_key = _narrow_scope_key(event.edge_type, event.crime_type)
        async with get_lock(f"trust:{narrow_key}"):
            narrow = await _load_trust(narrow_key)
            if is_confirm:
                narrow.confirmations += 1
            else:
                narrow.corrections += 1
            await _save_trust(narrow)

    if not is_confirm and event.edge_id:
        await _apply_session_penalty(event.session_id, event.edge_id)

async def _apply_session_penalty(session_id: str, edge_id: str):
    key = f"session_penalty:{session_id}"
    # BUG FIX: unlocked read-modify-write let two concurrent negative-verdict
    # submissions for the same session race -- both read the same snapshot,
    # then the later write silently dropped the earlier one's edge_id, so a
    # lead the officer explicitly rejected could keep reappearing in ranked
    # results. Reuse get_session_lock, already used for this exact
    # read-modify-write race in backend/job_dispatch.py.
    async with get_session_lock(session_id):
        existing = await nosql_get(key)
        penalized_ids = set(json.loads(existing["value"])) if existing else set()
        penalized_ids.add(edge_id)
        await nosql_set(key, json.dumps(list(penalized_ids)), ttl=3600 * 8)

async def get_session_penalized_ids(session_id: str) -> set[str]:
    key = f"session_penalty:{session_id}"
    existing = await nosql_get(key)
    return set(json.loads(existing["value"])) if existing else set()
