import json
import asyncio

from fastapi import APIRouter, Request, HTTPException

from shared.catalyst_client import nosql_get
from shared.graph_client import run_query
from shared.hypothesis_engine import list_hypotheses_by_case

router = APIRouter()

# ── Entity Relation Network ────────────────────────────────────────────────────
#
# Two views over the Memgraph investigation graph, both returned as Cytoscape
# `elements` (same shape the query pipeline emits, so the client's NetworkGraph
# renders them unchanged):
#
#   GET /api/cases/{case_id}/graph  — one case. Nodes/edges reachable from the
#       FIRs this case touches (pinned citations + case hypotheses).
#
#   GET /api/graph                  — the officer's whole desk. Union across
#       every case they collaborate on, with Accused nodes that appear in more
#       than one case flagged (`data.shared`, `data.caseCount`) — the only view
#       where "same accused, multiple cases" is visible.
#
# Graph schema in use: (:Accused)-[:ACCUSED_IN]->(:FIR), (:Victim)-[:VICTIM_IN]->
# (:FIR). FIR.district is treated as a Location node. Accused nodes carry no
# name in this dataset, so the id doubles as the label.

_MAX_SEED_FIRS = 400          # cap the Cypher IN-list
_MAX_ELEMENTS = 1200          # keep the client render sane


async def _case_ids_for_officer(username: str) -> list[str]:
    doc = await nosql_get(f"user_cases:{username}")
    if not doc:
        return []
    try:
        ids = json.loads(doc["value"])
        return ids if isinstance(ids, list) else []
    except (ValueError, KeyError, TypeError):
        return []


async def _seed_firs_for_case(case_id: str) -> set[str]:
    """FIR ids a case touches: pinned citations + hypothesis fir_id /
    linked_entity_ids that look like FIR uuids."""
    firs: set[str] = set()

    board_doc = await nosql_get(f"case_board:{case_id}")
    if board_doc:
        try:
            for pin in json.loads(board_doc["value"]):
                if pin.get("content_type") != "citation":
                    continue
                c = pin.get("content") or {}
                fid = c.get("fir_id") or (c.get("data") or {}).get("fir_id")
                if fid:
                    firs.add(str(fid))
        except (ValueError, KeyError, TypeError):
            pass

    try:
        for h in await list_hypotheses_by_case(case_id):
            if h.fir_id and h.fir_id != case_id:
                firs.add(str(h.fir_id))
            for ent in (h.linked_entity_ids or []):
                # heuristic: FIR ids here are uuids; accused ids are ACC-*
                if "-" in ent and not ent.upper().startswith("ACC"):
                    firs.add(str(ent))
    except Exception:
        pass

    return firs


async def _build_graph(seed_firs: set[str], fir_case_map: dict[str, set[str]] | None = None) -> list[dict]:
    """Given seed FIR ids, pull one hop of Accused + Victim + Location and
    assemble Cytoscape elements. `fir_case_map` (fir_id -> {case_id}) drives the
    per-Accused `shared` / `caseCount` flags on the global view."""
    if not seed_firs:
        return []

    fir_ids = list(seed_firs)[:_MAX_SEED_FIRS]

    accused_rows, victim_rows, fir_rows = await asyncio.gather(
        run_query(
            """
            MATCH (a:Accused)-[:ACCUSED_IN]->(f:FIR)
            WHERE f.id IN $fir_ids
            RETURN a.id AS aid, f.id AS fid
            """,
            {"fir_ids": fir_ids},
        ),
        run_query(
            """
            MATCH (v:Victim)-[:VICTIM_IN]->(f:FIR)
            WHERE f.id IN $fir_ids
            RETURN v.id AS vid, f.id AS fid
            """,
            {"fir_ids": fir_ids},
        ),
        run_query(
            """
            MATCH (f:FIR)
            WHERE f.id IN $fir_ids
            RETURN f.id AS fid, f.crime_no AS crime_no, f.crime_type AS crime_type,
                   f.district AS district, f.date AS date
            """,
            {"fir_ids": fir_ids},
        ),
    )

    elements: list[dict] = []
    fir_meta = {r["fid"]: r for r in fir_rows}
    districts: set[str] = set()

    # FIR nodes (only those that actually exist in the graph)
    for fid, r in fir_meta.items():
        label = r.get("crime_no") or fid[:8]
        elements.append({
            "data": {
                "id": fid,
                "label": f"FIR {label}",
                "type": "fir",
                "details": r.get("crime_type") or "FIR",
                "district": r.get("district"),
                "date": r.get("date"),
            },
            "classes": "fir",
        })
        if r.get("district"):
            districts.add(r["district"])

    # Location nodes from districts + FIR -> Location edges
    for d in districts:
        elements.append({
            "data": {"id": f"loc::{d}", "label": d, "type": "location", "details": "District"},
            "classes": "location",
        })
    for fid, r in fir_meta.items():
        if r.get("district"):
            elements.append({"data": {
                "id": f"{fid}__loc",
                "source": fid,
                "target": f"loc::{r['district']}",
                "label": "Occurred At",
            }})

    # Accused nodes + ACCUSED_IN edges, with cross-case aggregation
    acc_firs: dict[str, set[str]] = {}
    for row in accused_rows:
        if row["fid"] in fir_meta:
            acc_firs.setdefault(row["aid"], set()).add(row["fid"])

    for aid, linked in acc_firs.items():
        cases_hit: set[str] = set()
        if fir_case_map:
            for fid in linked:
                cases_hit |= fir_case_map.get(fid, set())
        node = {
            "id": aid,
            "label": aid,
            "type": "person",
            "details": "Accused",
            "firCount": len(linked),
        }
        if fir_case_map:
            node["caseCount"] = len(cases_hit)
            node["shared"] = len(cases_hit) >= 2
        classes = "person shared" if node.get("shared") else "person"
        elements.append({"data": node, "classes": classes})
        for fid in linked:
            elements.append({"data": {
                "id": f"{aid}__{fid}",
                "source": aid,
                "target": fid,
                "label": "Accused",
            }})

    # Victim nodes + VICTIM_IN edges
    seen_victims: set[str] = set()
    for row in victim_rows:
        if row["fid"] not in fir_meta:
            continue
        vid = row["vid"]
        if vid not in seen_victims:
            elements.append({"data": {
                "id": vid, "label": vid[:10], "type": "victim", "details": "Victim",
            }, "classes": "victim"})
            seen_victims.add(vid)
        elements.append({"data": {
            "id": f"{vid}__{row['fid']}",
            "source": row["fid"],
            "target": vid,
            "label": "Victim",
        }})

    return elements[:_MAX_ELEMENTS]


@router.get("/api/graph")
async def get_global_graph(request: Request):
    """Officer-wide entity relation network — union across every case the
    caller collaborates on. Accused linked to FIRs from >= 2 cases are
    flagged `shared`."""
    username = request.state.username
    case_ids = await _case_ids_for_officer(username)

    fir_case_map: dict[str, set[str]] = {}
    per_case = await asyncio.gather(*[_seed_firs_for_case(cid) for cid in case_ids])
    for cid, firs in zip(case_ids, per_case):
        for fid in firs:
            fir_case_map.setdefault(fid, set()).add(cid)

    seed = set(fir_case_map.keys())
    try:
        elements = await _build_graph(seed, fir_case_map)
    except Exception as exc:  # graph DB unreachable / query error
        return {"elements": [], "degraded": True, "reason": str(exc)[:200]}

    shared = sum(1 for e in elements if e.get("data", {}).get("shared"))
    return {
        "elements": elements,
        "case_count": len(case_ids),
        "seed_fir_count": len(seed),
        "shared_accused_count": shared,
    }


@router.get("/api/cases/{case_id}/graph")
async def get_case_graph(case_id: str, request: Request):
    """Entity relation network for a single case — nodes/edges reachable from
    the FIRs this case touches (pinned citations + case hypotheses)."""
    username = request.state.username

    # reuse the collaborator gate from the cases router
    from backend.api.routes.cases import _require_collaborator
    await _require_collaborator(case_id, username)

    seed = await _seed_firs_for_case(case_id)
    try:
        elements = await _build_graph(seed)
    except Exception as exc:
        return {"elements": [], "degraded": True, "reason": str(exc)[:200]}

    return {"elements": elements, "seed_fir_count": len(seed)}
