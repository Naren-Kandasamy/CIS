# PS-1 Phase 5, item 1: Negative Evidence & Exclusion Tracking.
# See Docs/PS1_Negative_Evidence_Exclusion_Tracking.md Section 4.2.
#
# DEVIATIONS from the design doc, reconciled against the real codebase:
# - memgraph_write/memgraph_read (doc's assumed names) don't exist; the real
#   helpers are shared/graph_client.py's run_write/run_query.
# - The doc's create_exclusion Cypher never SETs e.accused_id/e.fir_id on the
#   edge itself (only uses them to MATCH the endpoint nodes), which means
#   ExclusionRecord(**row["exclusion"]) in get_active_exclusions couldn't
#   reconstruct a full record -- both required fields would be missing. Fixed
#   by SETting them as edge properties too, so the edge is self-describing.
# - Added an existence pre-check for the Accused/FIR nodes: the doc's MATCH
#   silently matches zero rows (and MERGE/SET silently do nothing) if either
#   id is wrong, which would report "recorded" for an exclusion that was
#   never actually written.
# - Added get_active_exclusions_bulk for ranking (confidence_engine.py),
#   which needs exclusions for many FIRs in one round trip rather than one
#   Memgraph query per evidence item.

from datetime import datetime, timezone
from typing import Iterable, Optional

from shared.catalyst_client import get_session_lock, get_case_lock
from shared.claim_logger import check_and_flag_contradicted_claims
from shared.graph_client import run_query, run_write
from shared.exclusion_models import ExclusionRecord

EXCLUSION_DEMOTION_FACTOR = 0.05  # heavy demotion, never zero -- stays visible, sinks to bottom


async def create_exclusion(record: ExclusionRecord) -> None:
    """
    Writes a new EXCLUDED_FROM edge. Always officer-initiated -- called only
    from the API route in backend/api/routes/exclusions.py, never from any
    pipeline or LLM-driven code path.
    """
    if not await run_query("MATCH (a:Accused {id: $id}) RETURN a.id AS id LIMIT 1", {"id": record.accused_id}):
        raise ValueError(f"No Accused node with id={record.accused_id!r}")
    if not await run_query("MATCH (f:FIR {id: $id}) RETURN f.id AS id LIMIT 1", {"id": record.fir_id}):
        raise ValueError(f"No FIR node with id={record.fir_id!r}")

    # BUG FIX: get_active_exclusions/get_active_exclusions_bulk key their
    # result dict by accused_id alone -- nothing prevented a second active
    # exclusion being created for the same (accused_id, fir_id) pair (MERGE
    # above matches on exclusion_id, not this pair), which would silently
    # drop one of the two from every future ranking lookup with no error to
    # anyone and no deterministic which-one-wins. Reject a second active
    # exclusion for the same pair instead -- an officer who wants to change
    # the reasoning should reverse the existing one first, preserving the
    # audit trail the whole feature exists to provide.
    existing = await get_active_exclusions(record.fir_id)
    if record.accused_id in existing:
        raise ValueError(
            f"An active exclusion already exists for accused={record.accused_id!r} "
            f"fir={record.fir_id!r} (exclusion_id={existing[record.accused_id].exclusion_id!r}) "
            f"-- reverse it first if you need to change it"
        )

    await run_write("""
        MATCH (a:Accused {id: $accused_id}), (f:FIR {id: $fir_id})
        MERGE (a)-[e:EXCLUDED_FROM {exclusion_id: $exclusion_id}]->(f)
        SET e.accused_id = $accused_id,
            e.fir_id = $fir_id,
            e.exclusion_type = $exclusion_type,
            e.reason = $reason,
            e.time_window_start = $time_window_start,
            e.time_window_end = $time_window_end,
            e.verification_method = $verification_method,
            e.officer_id = $officer_id,
            e.date = $date,
            e.status = 'active'
    """, record.model_dump())

    # Wire up the contradiction-detection integration: check_and_flag_contradicted_claims
    # was imported here but never actually called -- a new exclusion ("this
    # person is ruled out") is exactly the event that should be checked
    # against past HIGH/MEDIUM-confidence LLM claims about this accused/FIR,
    # flagging any that are now contradicted for review.
    try:
        await check_and_flag_contradicted_claims(record.fir_id, record.accused_id, record.reason)
    except Exception as e:
        # Best-effort: a failure here must never roll back or block the
        # exclusion write itself, which is the actual audit-trail record.
        print(f"[ExclusionEngine] Contradiction check failed for {record.exclusion_id!r}: {e}")


async def reverse_exclusion(exclusion_id: str, reversed_by: str, reversed_reason: str) -> None:
    """
    Reversal is explicit and logged -- never a silent delete. The edge stays
    in the graph permanently, with status flipped to 'reversed', preserving a
    full audit trail of "we thought this person was ruled out, here's why we
    changed our mind, and who made that call."
    """
    rows = await run_query(
        "MATCH ()-[e:EXCLUDED_FROM {exclusion_id: $id}]->() RETURN e.status AS status LIMIT 1",
        {"id": exclusion_id},
    )
    if not rows:
        raise ValueError(f"No exclusion with id={exclusion_id!r}")
    # BUG FIX: the status was fetched but never checked -- calling reverse a
    # second time on an already-reversed exclusion silently overwrote the
    # ORIGINAL reversal's reversed_by/reversed_reason/reversed_date with the
    # second call's values, destroying the first reversal's audit trail (the
    # exact thing this feature exists to preserve, per the docstring above).
    if rows[0]["status"] != "active":
        raise ValueError(f"Exclusion {exclusion_id!r} is not active (status={rows[0]['status']!r}) -- cannot reverse it again")

    await run_write("""
        MATCH ()-[e:EXCLUDED_FROM {exclusion_id: $exclusion_id}]->()
        SET e.status = 'reversed',
            e.reversed_by = $reversed_by,
            e.reversed_reason = $reversed_reason,
            e.reversed_date = $reversed_date
    """, {
        "exclusion_id": exclusion_id,
        "reversed_by": reversed_by,
        "reversed_reason": reversed_reason,
        "reversed_date": datetime.now(timezone.utc).isoformat(),
    })


async def get_active_exclusions(fir_id: str) -> dict[str, ExclusionRecord]:
    """
    Active exclusions for one case, keyed by accused_id. Only 'active' status
    records -- a reversed exclusion has zero effect on future ranking.
    """
    # NOTE: `RETURN e AS exclusion` looks like it would hand back the edge's
    # properties, but the neo4j driver's Record.data() serializes a
    # Relationship as a (start_props, type, end_props) tuple -- its own
    # properties aren't in there at all. properties(e) projects them as a
    # plain map instead, which the driver then decodes as a normal dict.
    rows = await run_query("""
        MATCH (a:Accused)-[e:EXCLUDED_FROM {status: 'active'}]->(f:FIR {id: $fir_id})
        RETURN a.id AS accused_id, properties(e) AS exclusion
    """, {"fir_id": fir_id})
    return {row["accused_id"]: ExclusionRecord(**row["exclusion"]) for row in rows}


async def get_active_exclusions_bulk(fir_ids: Iterable[str]) -> dict[str, dict[str, ExclusionRecord]]:
    """
    Same as get_active_exclusions but for many FIRs in one round trip --
    {fir_id: {accused_id: ExclusionRecord}}. Used at ranking time, where
    checking each evidence item's FIR one-by-one would mean one Memgraph
    query per evidence item.
    """
    fir_ids = list(dict.fromkeys(fir_ids))
    if not fir_ids:
        return {}
    rows = await run_query("""
        MATCH (a:Accused)-[e:EXCLUDED_FROM {status: 'active'}]->(f:FIR)
        WHERE f.id IN $fir_ids
        RETURN f.id AS fir_id, a.id AS accused_id, properties(e) AS exclusion
    """, {"fir_ids": fir_ids})
    result: dict[str, dict[str, ExclusionRecord]] = {}
    for row in rows:
        result.setdefault(row["fir_id"], {})[row["accused_id"]] = ExclusionRecord(**row["exclusion"])
    return result


def alibi_covers_incident(exclusion: ExclusionRecord, incident_datetime: Optional[str]) -> bool:
    """
    Deterministic overlap check -- an alibi_confirmed exclusion only actually
    applies if its confirmed time window covers the specific incident it's
    meant to exclude the accused from. Prevents a blanket "this person has an
    alibi for something" from over-applying to a case whose actual timestamp
    falls outside the verified window. Not relevant for exclusion_type =
    "ruled_out", which has no time window and always applies once active.
    """
    if exclusion.exclusion_type != "alibi_confirmed":
        return True  # ruled_out exclusions have no time-window condition

    if not incident_datetime or not exclusion.time_window_start or not exclusion.time_window_end:
        return False  # unknown/malformed data -- fail safe, don't exclude

    return exclusion.time_window_start <= incident_datetime <= exclusion.time_window_end
