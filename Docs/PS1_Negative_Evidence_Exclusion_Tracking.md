# PS-1: Negative Evidence & Exclusion Tracking
## Teaching the Graph What's Been Ruled Out — Not Just What's Connected

**Status:** New addendum to Architecture v8 / Implementation v8, extending Layer 2 (Query Understanding), Layer 3 (Retrieval), and the Memgraph schema
**Roadmap position:** Item 1 of the 8-item senior-investigator review roadmap — built first because it's the smallest surface area (pure graph schema addition, no new external data source) and because items later in the roadmap (CDR integration, proactive cold-case matching) will surface *more* candidate connections that this mechanism needs to be able to suppress.
**Written for:** direct hand-off to Antigravity — every section states current state, target state, and exact files to touch.

---

## 1. Context — Why This Exists

This came out of a deliberate "senior investigator" review pass over the whole architecture, done specifically to find where the system would fail to hold up against how real investigations actually work, not just where it would fail a demo.

**The finding:** every piece of graph reasoning in PS-1 — `SHARED_MO`, `CO_ACCUSED`, `TEMPORAL_CLUSTER`, `SHARED_TATTOO`, `SHARED_VEHICLE` — is built to find connections. Nothing in the current design records or reasons about *exclusions*: alibis, contradicted statements, suspects who have been actively ruled out. Concretely, if an accused has a confirmed alibi for one case, nothing today stops the graph from continuing to surface them as a strong MO match the next time an officer queries a similar case. The system has no memory of "we already checked this and it isn't them."

**Why this is a real gap and not a nice-to-have:** an investigator needs "who's ruled out" as much as "who's connected." A crime intelligence system that only ever adds candidates and never removes them will, over time, keep re-surfacing the same false leads to different officers across different sessions — wasting investigative effort on a question that's already been answered, and worse, potentially diluting confidence in genuinely strong leads by cluttering results with previously-dismissed ones.

**Where this sits relative to the rest of the roadmap:**
- It must land **before** CDR integration and proactive cold-case matching (later roadmap items), since those will generate more candidate suspect/connection suggestions, and this is the mechanism that keeps already-ruled-out people from cluttering those results too.
- It sets up, but does **not** build, the Confidence Engine's planned "contradicted" state (a separate, later roadmap item) — that item handles the case where a *previously high-confidence claim* gets contradicted by new evidence mid-investigation. This doc handles the simpler, more foundational case: an officer explicitly recording that a specific accused is excluded from a specific case, or that a specific piece of evidence has been contradicted. The two are related (an exclusion record is exactly the kind of hard signal the Confidence Engine's contradicted-state work will consume later) but this doc stops at building the exclusion/negative-evidence layer itself.
- It's conceptually adjacent to, but **distinct from**, the Reasoning Feedback Loop (`PS1_Reasoning_Feedback_Loop.md`). That system asks "how reliable has this *type* of reasoning been, in general, over time" — a slow-moving, statistical, methodology-scoped signal. This system asks "has *this specific accused* been ruled out of *this specific case*" — an instant, case-specific, hard fact recorded by an officer. Both follow the same underlying philosophy (demote or flag, never silently delete evidence), and both compose together in the same final ranking formula (Section 4.5), but they answer different questions and neither replaces the other.

**A design principle carried over from the Reasoning Feedback Loop doc, and load-bearing here too:** exclusions **demote and flag, they never silently delete.** An excluded accused should still be visible to an officer, clearly marked as ruled out with the reason shown, sorted to the bottom rather than hidden. Silently removing information would work against the legal-defensibility/transparency differentiator the whole system is built around — an investigator (or an auditor, or a court) should be able to see exactly what was excluded and why, not just receive a shorter list with no explanation.

**A second principle, new to this doc:** exclusions must be **reversible**. Real investigations aren't static — an alibi witness can later be found to have lied, a ruled-out suspect can resurface as credible given new evidence. If exclusions were permanent and immutable, a single wrong or outdated exclusion could permanently blind the system to a real lead. Every exclusion record carries a status and can be explicitly reversed by an officer, with the reversal itself logged.

---

## 2. Current State vs. Target State

| Aspect | Current (Architecture v8 / Implementation v8) | Target (this doc) |
|---|---|---|
| Exclusion/negative evidence | Doesn't exist. All graph edge types (`SHARED_MO`, `CO_ACCUSED`, `TEMPORAL_CLUSTER`, `SHARED_TATTOO`, `SHARED_VEHICLE`) are additive only | New `EXCLUDED_FROM` relationship type between `Accused` and `FIR`, recording that a specific accused has been ruled out (generally, or via confirmed alibi) for a specific case |
| Contradicted evidence/statements | Doesn't exist | New `ContradictionRecord`, marking a specific piece of evidence (KB document, witness statement) as contradicted by other evidence, without deleting it |
| Effect on retrieval | An accused with a known alibi for Case A still surfaces as a strong candidate the next time a similar case is queried | Retrieval ranking checks active exclusions for the case under investigation and heavily demotes (never deletes) matching candidates, with the reason visibly attached |
| Reversibility | N/A | Every exclusion has a `status` (`active` / `reversed`) and a full reversal audit trail — nothing is a one-way door |
| Alibi time-window logic | N/A | Deterministic overlap check: an alibi only excludes an accused from a case if the alibi's confirmed time window actually overlaps the incident's timestamp — no blanket "this person has an alibi for something, so exclude them from everything" |
| Who decides an exclusion applies | N/A | Always an officer, explicitly, via a dedicated action — never inferred or auto-applied by the LLM |
| UI | N/A | New officer-facing action: "Rule out this suspect for this case" / "Mark this evidence as contradicted," each requiring a reason |

---

## 3. Architecture

### 3.1 Data Model — New Relationship: `EXCLUDED_FROM`

A single relationship type between `Accused` and `FIR`, with a property (`exclusion_type`) distinguishing the two flavors discussed — rather than two separate Cypher relationship types. This is a deliberate simplification: querying "is this accused excluded from this FIR" becomes one relationship pattern regardless of *why*, and the `exclusion_type` property still carries full semantic meaning for anything that needs to distinguish them (UI display, audit reporting).

```cypher
(:Accused)-[:EXCLUDED_FROM {
    exclusion_id: string,
    exclusion_type: string,       // "ruled_out" | "alibi_confirmed"
    reason: string,
    time_window_start: string,    // only set when exclusion_type = "alibi_confirmed"
    time_window_end: string,
    verification_method: string,  // e.g. "CCTV", "witness_corroboration", "phone_tower_data"
    officer_id: string,
    date: string,
    status: string,               // "active" | "reversed"
    reversed_by: string,
    reversed_reason: string,
    reversed_date: string
}]->(:FIR)
```

**Why scoped to a specific (Accused, FIR) pair, not global:** ruling someone out of Case A says nothing about Case B. An accused could legitimately still be connected to other cases through entirely separate evidence. Exclusion is deliberately narrow — it answers "is this person a viable suspect for *this* case," not "should this person be removed from the graph."

### 3.2 Data Model — New Record: Evidence/Statement Contradiction

Separate from accused exclusion, because the thing being marked isn't a person, it's a piece of evidence (a KB-indexed narrative, a witness statement, an OCR-extracted document field):

```python
class ContradictionRecord(BaseModel):
    contradiction_id: str
    evidence_ref: str                        # kb_doc_id, or a structured field reference
    fir_id: str
    reason: str
    contradicting_evidence_ref: Optional[str] = None   # what contradicts it, if known
    officer_id: str
    date: str
    status: str = "active"                   # "active" | "reversed"
    reversed_by: Optional[str] = None
    reversed_reason: Optional[str] = None
    reversed_date: Optional[str] = None
```

This follows the exact same demote-don't-delete, reversible-status pattern as `EXCLUDED_FROM` — deliberately kept structurally parallel so both are easy to reason about and query the same way.

### 3.3 Pipeline Integration Points

```
Layer 2 -- Query Understanding
    Intent detection needs to recognize when a query is scoped to a
    SPECIFIC case under active investigation (e.g. "who else could be
    connected to FIR-2024-00417") vs. a general research query with no
    single case context. Exclusion filtering only applies in the former.
    -- [VERIFY] tie-in point against existing intent/NER logic, Section 5.1

Layer 3 -- Retrieval
    rank_evidence() (already modified once for the Reasoning Feedback
    Loop, PS1_Reasoning_Feedback_Loop.md Section 4.4) gets a further
    extension here: check active EXCLUDED_FROM records and active
    ContradictionRecords for the case in context, demote matching
    candidates, attach the reason for display -- never delete.

Officer-facing UI / new API routes
    Two new actions: "rule out this suspect for this case" and "mark
    this evidence as contradicted," each requiring a reason. Plus a
    reversal action for both. These are explicit officer actions --
    never inferred automatically by the LLM or any pipeline step.
```

**Why exclusion is never LLM-inferred, stated explicitly:** this is the same principle enforced throughout the last two addendum docs. An exclusion is a legal/investigative fact ("we verified this alibi") — it must be asserted by a person with actual knowledge of the verification, not guessed at by a language model pattern-matching on text. The LLM plans and synthesizes over whatever evidence retrieval gives it; it never decides that evidence should be excluded.

---

## 4. Implementation

### 4.1 `shared/exclusion_models.py`

```python
# shared/exclusion_models.py

from pydantic import BaseModel
from typing import Optional

class ExclusionRecord(BaseModel):
    exclusion_id: str
    fir_id: str
    accused_id: str
    exclusion_type: str                      # "ruled_out" | "alibi_confirmed"
    reason: str
    time_window_start: Optional[str] = None  # ISO datetime, alibi_confirmed only
    time_window_end: Optional[str] = None
    verification_method: Optional[str] = None
    officer_id: str
    date: str
    status: str = "active"                   # "active" | "reversed"
    reversed_by: Optional[str] = None
    reversed_reason: Optional[str] = None
    reversed_date: Optional[str] = None


class ContradictionRecord(BaseModel):
    contradiction_id: str
    evidence_ref: str
    fir_id: str
    reason: str
    contradicting_evidence_ref: Optional[str] = None
    officer_id: str
    date: str
    status: str = "active"
    reversed_by: Optional[str] = None
    reversed_reason: Optional[str] = None
    reversed_date: Optional[str] = None
```

### 4.2 `shared/exclusion_engine.py` — Core Logic

```python
# shared/exclusion_engine.py

from datetime import datetime
from shared.catalyst_client import memgraph_write, memgraph_read
from shared.exclusion_models import ExclusionRecord, ContradictionRecord

EXCLUSION_DEMOTION_FACTOR = 0.05   # heavy demotion, never zero -- stays visible, sinks to bottom


async def create_exclusion(record: ExclusionRecord):
    """
    Writes a new EXCLUDED_FROM edge. Always officer-initiated -- called
    only from the API route in Section 4.3, never from any pipeline
    or LLM-driven code path.
    """
    await memgraph_write("""
        MATCH (a:Accused {id: $accused_id}), (f:FIR {id: $fir_id})
        MERGE (a)-[e:EXCLUDED_FROM {exclusion_id: $exclusion_id}]->(f)
        SET e.exclusion_type = $exclusion_type,
            e.reason = $reason,
            e.time_window_start = $time_window_start,
            e.time_window_end = $time_window_end,
            e.verification_method = $verification_method,
            e.officer_id = $officer_id,
            e.date = $date,
            e.status = 'active'
    """, record.dict())


async def reverse_exclusion(exclusion_id: str, reversed_by: str, reversed_reason: str):
    """
    Reversal is explicit and logged -- never a silent delete. The edge
    stays in the graph permanently, with status flipped to 'reversed',
    preserving a full audit trail of "we thought this person was ruled
    out, here's why we changed our mind, and who made that call."
    """
    await memgraph_write("""
        MATCH ()-[e:EXCLUDED_FROM {exclusion_id: $exclusion_id}]->()
        SET e.status = 'reversed',
            e.reversed_by = $reversed_by,
            e.reversed_reason = $reversed_reason,
            e.reversed_date = $reversed_date
    """, {
        "exclusion_id": exclusion_id,
        "reversed_by": reversed_by,
        "reversed_reason": reversed_reason,
        "reversed_date": datetime.utcnow().isoformat(),
    })


async def get_active_exclusions(fir_id: str) -> dict[str, ExclusionRecord]:
    """
    Returns active exclusions for a case, keyed by accused_id, for use
    in retrieval ranking (Section 4.4). Only 'active' status records --
    reversed exclusions are excluded from this lookup entirely, so a
    reversed exclusion has zero effect on future ranking.
    """
    rows = await memgraph_read("""
        MATCH (a:Accused)-[e:EXCLUDED_FROM {status: 'active'}]->(f:FIR {id: $fir_id})
        RETURN a.id AS accused_id, e AS exclusion
    """, {"fir_id": fir_id})
    return {row["accused_id"]: ExclusionRecord(**row["exclusion"]) for row in rows}


def alibi_covers_incident(exclusion: ExclusionRecord, incident_datetime: str) -> bool:
    """
    Deterministic overlap check -- an alibi_confirmed exclusion only
    actually applies if its confirmed time window covers the specific
    incident it's meant to exclude the accused from. Prevents a blanket
    "this person has an alibi for something" from over-applying to a
    case whose actual timestamp falls outside the verified window.
    Not relevant for exclusion_type = "ruled_out", which has no time
    window and always applies once active.
    """
    if exclusion.exclusion_type != "alibi_confirmed":
        return True  # ruled_out exclusions have no time-window condition

    if not exclusion.time_window_start or not exclusion.time_window_end:
        return False  # malformed alibi record -- fail safe, don't exclude on bad data

    return exclusion.time_window_start <= incident_datetime <= exclusion.time_window_end
```

### 4.3 New API Routes — `backend/api/routes/exclusions.py`

```python
# backend/api/routes/exclusions.py

from fastapi import APIRouter, HTTPException
from datetime import datetime
import uuid

from shared.exclusion_models import ExclusionRecord, ContradictionRecord
from shared.exclusion_engine import create_exclusion, reverse_exclusion
from shared.catalyst_client import nosql_set  # reused for ContradictionRecord storage

router = APIRouter()

@router.post("/api/investigation/exclude")
async def submit_exclusion(payload: dict):
    if payload.get("exclusion_type") not in {"ruled_out", "alibi_confirmed"}:
        raise HTTPException(400, "exclusion_type must be 'ruled_out' or 'alibi_confirmed'")
    if payload["exclusion_type"] == "alibi_confirmed" and (
        not payload.get("time_window_start") or not payload.get("time_window_end")
    ):
        raise HTTPException(400, "alibi_confirmed exclusions require a time window")

    record = ExclusionRecord(
        exclusion_id=str(uuid.uuid4()),
        date=datetime.utcnow().isoformat(),
        status="active",
        **payload,
    )
    await create_exclusion(record)
    return {"status": "recorded", "exclusion_id": record.exclusion_id}


@router.post("/api/investigation/exclude/{exclusion_id}/reverse")
async def submit_exclusion_reversal(exclusion_id: str, payload: dict):
    if not payload.get("reversed_reason"):
        raise HTTPException(400, "reversed_reason is required")
    await reverse_exclusion(exclusion_id, payload["reversed_by"], payload["reversed_reason"])
    return {"status": "reversed"}


@router.post("/api/investigation/contradiction")
async def submit_contradiction(payload: dict):
    record = ContradictionRecord(
        contradiction_id=str(uuid.uuid4()),
        date=datetime.utcnow().isoformat(),
        status="active",
        **payload,
    )
    await nosql_set(f"contradiction:{record.contradiction_id}", record.json())
    return {"status": "recorded", "contradiction_id": record.contradiction_id}
```

`[VERIFY]` `memgraph_write` / `memgraph_read` are named here consistently with the pattern used for other Memgraph operations elsewhere in the project (e.g. `create_shared_mo_edge`), but confirm the actual current function names/signatures in `shared/catalyst_client.py` before wiring these in.

### 4.4 Wiring Into Retrieval Ranking — Extending `rank_evidence()`

This extends the same function already modified once in the Reasoning Feedback Loop doc (`PS1_Reasoning_Feedback_Loop.md`, Section 4.4). Rather than adding a wholly separate LangGraph node, the exclusion check is folded into the same ranking pass as one more multiplicative factor — keeping a single, unified scoring formula rather than scattering ranking logic across multiple places.

```python
# pipeline_function/pipeline/retrieval_node.py  (further extension)

from shared.feedback_engine import get_trust_weight
from shared.exclusion_engine import get_active_exclusions, alibi_covers_incident

async def rank_evidence(evidence_items: list[dict], session_id: str,
                         active_investigation_fir_id: str | None,
                         incident_datetime: str | None) -> list[dict]:
    """
    Combines three independent demotion signals into one final score:
      1. methodology trust weight   (Reasoning Feedback Loop -- general,
                                      slow-moving, per edge_type/crime_type)
      2. same-session penalty       (Reasoning Feedback Loop -- instant,
                                      per specific edge_id, this session only)
      3. case-specific exclusion    (this doc -- instant, per specific
                                      accused/FIR pair, hard officer fact)
    These are conceptually different signals (general reliability vs.
    a hard case-specific ruling) and are deliberately kept as separate
    multiplicative factors rather than merged into one number, so each
    can be reasoned about, tested, and tuned independently.
    """
    session_key = f"session_penalty:{session_id}"
    penalized = await _get_session_penalized_ids(session_key)

    exclusions = {}
    if active_investigation_fir_id:
        exclusions = await get_active_exclusions(active_investigation_fir_id)

    for item in evidence_items:
        base_score = item["relevance_score"]
        trust = await get_trust_weight(item.get("edge_type", "NARRATIVE_SIMILARITY"),
                                        item.get("crime_type"))
        session_penalty = 0.5 if item.get("edge_id") in penalized else 1.0

        exclusion_penalty = 1.0
        accused_id = item.get("accused_id")
        if accused_id and accused_id in exclusions:
            exclusion = exclusions[accused_id]
            applies = alibi_covers_incident(exclusion, incident_datetime) if incident_datetime else True
            if applies:
                exclusion_penalty = EXCLUSION_DEMOTION_FACTOR
                item["excluded"] = True
                item["exclusion_reason"] = exclusion.reason
                item["exclusion_type"] = exclusion.exclusion_type

        item["relevance_score"] = base_score * trust * session_penalty * exclusion_penalty

    # Excluded items sink to the bottom but remain in the list -- never dropped.
    return sorted(evidence_items,
                  key=lambda x: (x.get("excluded", False), -x["relevance_score"]))
```

**Why `active_investigation_fir_id` can be `None`:** many queries are general research, not scoped to one specific case ("show me all burglaries in Hubballi this year"). Exclusion filtering only makes sense when there's a specific case in context to check exclusions against — this is the Layer 2 dependency flagged in Section 3.3. `[VERIFY]` how the current intent/query-understanding layer represents "this query is about case X specifically" — the parameter name and source here are illustrative pending that check.

### 4.5 UI Requirements

- On any accused shown as a candidate connection for a specific case, an officer-facing action: **"Rule out for this case"** — opens a form requiring `exclusion_type` (ruled out generally, or confirmed alibi), a reason, and (for alibi) a time window and verification method.
- On any cited piece of evidence in a synthesized answer, an action: **"Mark as contradicted"** — requires a reason, optionally a reference to the contradicting evidence.
- Excluded/contradicted items remain visible in results, visually distinguished (e.g. greyed out, badge reading "Ruled out — [reason]" or "Contradicted — [reason]"), sorted below non-excluded results — never hidden.
- A reversal action ("Reinstate this suspect") must be available wherever an exclusion is displayed, requiring its own reason.

---

## 5. Explicitly Out of Scope (And Why)

- **The Confidence Engine's "contradicted" state** (surfacing "this was previously HIGH confidence, now contradicted" as a distinct signal) — this is a separate, later roadmap item. This doc builds the exclusion records that item will eventually consume; it doesn't build that surfacing logic itself.
- **Automated contradiction detection** — nothing in this doc has the system automatically decide two pieces of evidence contradict each other via NLP or LLM inference. Contradiction is always an explicit officer assertion, for the same reason exclusions are: it's a factual/legal judgment, not a pattern-matching task.
- **Global suspect removal** — an exclusion never removes an accused from the graph or from consideration for any other case. It is always scoped to one specific (accused, FIR) pair.
- **Automatic alibi verification** — the system doesn't verify whether an alibi is actually true (e.g. by cross-checking CCTV or CDR data automatically). It records that an officer has verified it, via whatever process they used, and stores their stated verification method as metadata. Automating the verification itself is out of scope entirely.

---

## 6. Testing / Verification Checklist

- [ ] Create a `ruled_out` exclusion for an accused/FIR pair → confirm that accused is demoted (not removed) in subsequent retrieval for that FIR, with the reason visible
- [ ] Create an `alibi_confirmed` exclusion with a time window that does **not** cover the FIR's actual incident timestamp → confirm the exclusion does **not** apply (via `alibi_covers_incident`), and the accused ranks normally
- [ ] Create an `alibi_confirmed` exclusion with a time window that **does** cover the incident timestamp → confirm the accused is demoted
- [ ] Reverse an exclusion → confirm the accused immediately returns to normal ranking on the next retrieval, and the reversal (who, why, when) is queryable from the edge itself
- [ ] Query the same case from a different officer's session → confirm the exclusion applies identically (this is a persistent, cross-session, case-specific fact, unlike the Reasoning Feedback Loop's same-session penalty)
- [ ] Query a *different* case involving the same accused, with no exclusion recorded for that case → confirm the accused is **not** demoted there — exclusion scope is per-FIR, not global
- [ ] Mark a piece of evidence as contradicted → confirm it's flagged and demoted in future retrieval, not deleted, and remains inspectable
- [ ] A query with no specific case in context (`active_investigation_fir_id = None`) → confirm exclusion filtering is skipped entirely, no error

---

## 7. Migration Checklist for Antigravity — Exact File Touch List

1. Create `shared/exclusion_models.py` (Section 4.1)
2. Create `shared/exclusion_engine.py` (Section 4.2) — unit test `alibi_covers_incident` in isolation first, it's the one piece of actual logic here
3. Create `backend/api/routes/exclusions.py` (Section 4.3), register routes on the AppSail FastAPI app
4. Extend `rank_evidence()` in the retrieval module (Section 4.4) to add the exclusion check alongside the existing trust-weight and session-penalty factors — `[VERIFY]` this is the same function already touched by the Reasoning Feedback Loop doc; make sure both changes land together consistently, not as conflicting edits
5. Confirm Layer 2 query understanding can supply an `active_investigation_fir_id` (or equivalent) when a query is scoped to a specific case — `[VERIFY]` exact current mechanism
6. Add Memgraph schema constraint/index for the new `EXCLUDED_FROM` relationship type if your Memgraph setup uses explicit relationship indexes (consistent with however `SHARED_MO` etc. are currently indexed)
7. Frontend: add "Rule out for this case" and "Mark as contradicted" actions, plus their reversal counterparts, with the required-reason forms (Section 4.5)
8. Add the test cases from Section 6 to the existing chaos/eval suite

---

## 8. Summary for `agents.md` / Antigravity Context

> New capability: officers can now explicitly rule out an accused for a specific case (general exclusion or confirmed alibi with a time window) and mark specific evidence as contradicted — both stored as reversible, auditable records (`EXCLUDED_FROM` graph edges, `ContradictionRecord`s), never as silent deletions. Retrieval ranking demotes matching candidates heavily but never removes them, with the reason always visible to the officer. Alibi exclusions only apply when their verified time window actually overlaps the incident being investigated, checked deterministically. Exclusion is always an explicit officer action — never inferred by the LLM or any automated pipeline step — and is scoped strictly to one (accused, case) pair, never applied globally. This is a different mechanism from the Reasoning Feedback Loop's methodology trust weighting (general, slow-moving, statistical) — this one is instant, case-specific, and asserted as hard fact by a person with actual knowledge of the exclusion's basis.
