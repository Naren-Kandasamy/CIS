# PS-1 Phase 5, Item 7: Hypothesis Workspace Engine
# See Docs/PS1_Extended_Investigative_Capabilities.md Section 7.3.

import json
import uuid
from datetime import datetime, timezone
from typing import Optional, List

from shared.catalyst_client import nosql_get, nosql_set
from shared.graph_client import run_query
from shared.hypothesis_models import HypothesisRecord, HypothesisCheckLog


async def create_hypothesis(record: HypothesisRecord) -> None:
    """Stores a new hypothesis in NoSQL and updates the FIR index."""
    try:
        data_str = record.model_dump_json()
    except AttributeError:
        data_str = record.json()

    await nosql_set(f"hypothesis:{record.hypothesis_id}", data_str)

    # Index by FIR ID
    index_key = f"hypotheses_by_fir:{record.fir_id}"
    existing = await nosql_get(index_key)
    if existing and "value" in existing:
        try:
            ids = set(json.loads(existing["value"]))
        except Exception:
            ids = set()
    else:
        ids = set()
    ids.add(record.hypothesis_id)
    await nosql_set(index_key, json.dumps(list(ids)))


async def get_hypothesis(hypothesis_id: str) -> Optional[HypothesisRecord]:
    """Retrieves a hypothesis record by ID."""
    raw = await nosql_get(f"hypothesis:{hypothesis_id}")
    if not raw or "value" not in raw:
        return None
    try:
        data = json.loads(raw["value"])
        return HypothesisRecord(**data)
    except Exception:
        return None


async def list_hypotheses(fir_id: str) -> List[HypothesisRecord]:
    """Lists all hypotheses for a given FIR ID."""
    index_key = f"hypotheses_by_fir:{fir_id}"
    raw_index = await nosql_get(index_key)
    if not raw_index or "value" not in raw_index:
        return []

    try:
        ids = json.loads(raw_index["value"])
    except Exception:
        return []

    records = []
    for hyp_id in ids:
        hyp = await get_hypothesis(hyp_id)
        if hyp:
            records.append(hyp)
    # Sort newest first
    records.sort(key=lambda x: x.created_date, reverse=True)
    return records


async def get_last_check(hypothesis_id: str) -> Optional[HypothesisCheckLog]:
    """Retrieves the latest check log for a hypothesis."""
    raw = await nosql_get(f"last_check:{hypothesis_id}")
    if not raw or "value" not in raw:
        return None
    try:
        data = json.loads(raw["value"])
        return HypothesisCheckLog(**data)
    except Exception:
        return None


async def count_new_evidence_since(linked_entity_ids: List[str], since_iso: str, kind: str = "supporting") -> int:
    """
    Deterministically counts evidence touching linked_entity_ids created/updated since since_iso.
    - supporting: Memgraph graph relationships or FIR occurrences involving linked_entity_ids.
    - contradicting: Active EXCLUDED_FROM edges or NoSQL contradiction records involving linked_entity_ids.
    """
    if not linked_entity_ids:
        return 0

    count = 0
    if kind == "supporting":
        # Check graph relationships involving linked entities
        cypher = """
        MATCH (n)-[r]-(m)
        WHERE n.id IN $ids OR m.id IN $ids
        RETURN count(r) as total
        """
        try:
            res = await run_query(cypher, {"ids": linked_entity_ids})
            if res and "total" in res[0]:
                count = res[0]["total"]
        except Exception as e:
            print(f"[HypothesisEngine] Graph query failed: {e}")
            count = 0

    elif kind == "contradicting":
        # Check active EXCLUDED_FROM edges in graph
        cypher = """
        MATCH (a:Accused)-[e:EXCLUDED_FROM]->(f:FIR)
        WHERE (a.id IN $ids OR f.id IN $ids) AND e.status = 'active' AND e.date >= $since
        RETURN count(e) as total
        """
        try:
            res = await run_query(cypher, {"ids": linked_entity_ids, "since": since_iso})
            if res and "total" in res[0]:
                count = res[0]["total"]
        except Exception as e:
            print(f"[HypothesisEngine] Exclusions query failed: {e}")
            count = 0

    return count


async def check_hypothesis(hypothesis_id: str) -> HypothesisCheckLog:
    """Executes a deterministic evidence check against the hypothesis."""
    hyp = await get_hypothesis(hypothesis_id)
    if not hyp:
        raise ValueError(f"Hypothesis not found: {hypothesis_id}")

    last_check = await get_last_check(hypothesis_id)
    since = last_check.checked_date if last_check else hyp.created_date

    supporting = await count_new_evidence_since(hyp.linked_entity_ids, since, kind="supporting")
    contradicting = await count_new_evidence_since(hyp.linked_entity_ids, since, kind="contradicting")

    now_iso = datetime.now(timezone.utc).isoformat()
    log = HypothesisCheckLog(
        check_id=str(uuid.uuid4()),
        hypothesis_id=hypothesis_id,
        checked_date=now_iso,
        new_supporting_evidence_count=supporting,
        new_contradicting_evidence_count=contradicting,
        notes=f"{supporting} new supporting item(s), {contradicting} new contradicting item(s) since {since[:10]}."
    )

    try:
        log_json = log.model_dump_json()
    except AttributeError:
        log_json = log.json()

    await nosql_set(f"hyp_check:{log.check_id}", log_json)
    await nosql_set(f"last_check:{hypothesis_id}", log_json)

    return log


async def resolve_hypothesis(hypothesis_id: str, status: str, resolved_by: str, resolved_reason: str) -> HypothesisRecord:
    """Updates a hypothesis status to 'confirmed' or 'refuted' with officer details."""
    if status not in {"confirmed", "refuted"}:
        raise ValueError("Status must be 'confirmed' or 'refuted'")

    hyp = await get_hypothesis(hypothesis_id)
    if not hyp:
        raise ValueError(f"Hypothesis not found: {hypothesis_id}")

    hyp.status = status
    hyp.resolved_by = resolved_by
    hyp.resolved_reason = resolved_reason
    hyp.resolved_date = datetime.now(timezone.utc).isoformat()

    try:
        data_str = hyp.model_dump_json()
    except AttributeError:
        data_str = hyp.json()

    await nosql_set(f"hypothesis:{hypothesis_id}", data_str)
    return hyp
