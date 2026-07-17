import json
from typing import Optional
from shared.catalyst_client import nosql_get, nosql_set
from shared.feedback_models import CorrectionEvent, MethodologyTrust

PRIOR_STRENGTH = 10
PRIOR_TRUST = 0.7
TRUST_WEIGHT_FLOOR = 0.3
MIN_SAMPLES_FOR_NARROW_SCOPE = 15

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
        narrow_key = f"{edge_type}::{crime_type}"
        narrow = await _load_trust(narrow_key)
        if (narrow.confirmations + narrow.corrections) >= MIN_SAMPLES_FOR_NARROW_SCOPE:
            return _smoothed_trust(narrow.confirmations, narrow.corrections)
    
    broad = await _load_trust(edge_type)
    return _smoothed_trust(broad.confirmations, broad.corrections)

async def record_feedback_event(event: CorrectionEvent):
    await nosql_set(f"correction:{event.event_id}", event.model_dump_json())
    
    is_confirm = event.verdict == "confirmed"
    broad = await _load_trust(event.edge_type)
    if is_confirm:
        broad.confirmations += 1
    else:
        broad.corrections += 1
    await _save_trust(broad)
    
    if event.crime_type:
        narrow_key = f"{event.edge_type}::{event.crime_type}"
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
    existing = await nosql_get(key)
    penalized_ids = set(json.loads(existing["value"])) if existing else set()
    penalized_ids.add(edge_id)
    await nosql_set(key, json.dumps(list(penalized_ids)), ttl=3600 * 8)

async def get_session_penalized_ids(session_id: str) -> set[str]:
    key = f"session_penalty:{session_id}"
    existing = await nosql_get(key)
    return set(json.loads(existing["value"])) if existing else set()
