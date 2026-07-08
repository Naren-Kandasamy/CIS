# PS-1: Reasoning Feedback Loop
## Methodology-Scoped Trust Weighting — Learning From Corrected Deductions, Not Just Corrected Facts

**Status:** New addendum to Architecture v8 / Implementation v8, extending Layer 4 (Confidence Engine), Layer 3 (Retrieval), and Layer 7 (Session Memory + Feedback)
**Scope:** This is the "feedback loop" gap identified in Architecture v8 Section 13, which currently states only "Officer feedback logged and used to improve results over time" with no actual mechanism behind it. This doc is that mechanism.
**Written for:** direct hand-off to Antigravity — every section states current state, target state, and exact files to touch.

---

## 1. Context — Why This Design Looks the Way It Does

This section exists because the reasoning behind this feature matters as much as the feature itself — several tempting-but-wrong designs were considered and rejected along the way, and Antigravity should understand why, so it doesn't "helpfully" reintroduce them during implementation.

**Fine-tuning / LoRA was ruled out first.** GLM-4.7-Flash and Qwen VLM are Catalyst-*hosted* inference endpoints, called via API the same way you'd call any external LLM provider (`catalyst_client.py`). The `QuickML.deployment.READ` OAuth scope used for Zia ASR/TTS/Translation is about *invoking* a deployed model, not training one. There is no verified path to accessing or adjusting model parameters for these hosted models, so LoRA-style parameter-efficient fine-tuning is not feasible here — there's nothing to attach an adapter to. This ruled out "real learning" and pointed toward system-level adaptation instead: adjusting how the *pipeline* uses evidence and reasoning, not how the model itself computes.

**The scope question then went through several rounds of narrowing.** Four levels of "what can officer feedback correct" were considered:

- **Level A — Entity extraction** (wrong name/location/IPC section). Rejected as the primary focus — correctly identified as closer to a *memory* problem ("forgetting a name or case number") than a *reasoning* problem, and one that's already substantially mitigated if RAG and session state (which already exist, Layer 7) work properly. Not built as a dedicated new loop; the existing session memory already covers most of this.
- **Level B — Retrieved evidence relevance** ("this connection isn't actually relevant"). Kept, but reframed.
- **Level C — Confidence tier disputes** ("this should be MEDIUM, not HIGH"). Originally scoped as "log only, don't auto-adjust" out of concern that a single correction could swing a formula that scores every future case. This concern was valid but too broad — the actual fix that emerged was scoping trust adjustments *narrowly* rather than not adjusting at all.
- **Level D — Disputing the LLM's synthesized narrative/explanation.** Rejected entirely as an automated loop. A correction here is free text with no unambiguous resolution, and building an automated response would require the LLM to *interpret* the correction and decide what to change — the exact "LLM decides" anti-pattern already ruled out once for evidence-language detection (`PS1_Evidence_Language_Detection.md`, Section 1). Free-text disagreement with the narrative is still captured, just as an honest audit-log entry, not a loop that pretends to close.

**The key reframe that unified B and C:** a correction against a specific retrieved connection isn't really about that one edge — it's about the *reasoning pattern* that produced it. Your graph already labels these patterns as distinct edge types: `SHARED_MO`, `TEMPORAL_CLUSTER`, `CO_ACCUSED`, `SHARED_TATTOO`, `SHARED_VEHICLE` (Implementation v8's Cypher constraints, Section 14/17). So instead of tracking "was this one edge right," the system tracks "how reliable has *this type* of reasoning been" — and only lets that reliability score shift retrieval ranking and confidence scoring, never entity extraction, never the narrative itself.

**Two concerns were raised against this and both are addressed in the design, not dismissed:**

1. *A mistake once or twice doesn't mean it's wrong this time.* Addressed by making trust adjustment a **slow-moving statistical estimate**, not a switch — a small number of corrections barely moves the needle; only a sustained pattern does. Evidence is also never fully suppressed, only deprioritized (a floor on the trust weight, detailed in Section 4).
2. *Skewing away from general pattern-solving toward narrow specialization* — e.g., punishing MO-matching globally when it's actually only unreliable for one crime type, unfairly dragging down cases where it works well. Addressed by scoping the trust weight to **(edge type × crime type)** where enough data exists, falling back to edge-type-only when a specific combination doesn't have enough corrections yet to be statistically meaningful.

That's the full reasoning trail. Everything below is the concrete design built from it.

---

## 2. Current State vs. Target State

| Aspect | Current (Architecture v8 Section 13) | Target (this doc) |
|---|---|---|
| Feedback loop | One unbacked bullet point: "Officer feedback logged and used to improve results over time" — no schema, no storage design, no mechanism for corrections to affect anything | A concrete, scoped, two-speed loop: instant same-session re-ranking + slow-moving cross-session trust weighting |
| What can be corrected | Undefined | Specifically: a cited piece of evidence/reasoning in a synthesized answer, tagged by which edge type and crime type it belongs to. Free-text explanation captured but never auto-parsed or auto-acted-on |
| Storage | Audit logs exist (Layer 7) but nothing reads them back into the pipeline | New `CorrectionEvent` records + a `MethodologyTrust` scoreboard, both read by retrieval and the Confidence Engine |
| Effect on future queries | None | Two effects: (a) same-session, same-edge-instance penalty, applied immediately; (b) cross-session, methodology-scoped trust weight, applied slowly, based on accumulated confirm/correct ratio |
| Risk of overcorrection | N/A (nothing exists to overcorrect) | Explicitly mitigated: Bayesian-style smoothing (a few corrections can't swing the score much), a trust-weight floor (evidence never disappears, only deprioritized), and a fallback from narrow to broad scoping when data is sparse |
| Entity-extraction corrections (Level A) | Not handled | Explicitly out of scope for this loop — treated as a session-memory problem, already covered by existing Layer 7 mechanics |
| Narrative/explanation disputes (Level D) | Not handled | Explicitly out of scope for automation — captured as free-text audit log only, never acted on automatically |

---

## 3. Architecture

### 3.1 Two Distinct Signals, Two Different Speeds

This is the single most important architectural decision in this doc, so it's stated up front before any code: there are **two separate mechanisms**, not one.

```
Officer flags a cited piece of evidence in a synthesized answer
                    │
                    ▼
        Correction (or Confirmation) Event
                    │
        ┌───────────┴────────────┐
        ▼                        ▼
 SAME-SESSION,              CROSS-SESSION,
 SAME-EDGE-INSTANCE         METHODOLOGY-SCOPED
 penalty                    trust weight
        │                        │
 Applied immediately,     Applied slowly, via
 to THIS session's        Bayesian-style smoothed
 re-ranking only           ratio, floor-clamped,
 (Catalyst NoSQL           narrow-then-broad
 session memory --         fallback scoping
 already exists,           (new MethodologyTrust
 Layer 7)                  store)
        │                        │
        ▼                        ▼
 Demoable live: flag it,   Persists across all
 ask again in same         future sessions/officers
 session, see it drop      -- moves gradually,
                           never all at once
```

Why two mechanisms and not one: the demo requirement ("must be completely functional, we're deploying this, corrections should visibly work live") needs an *instant* effect. But an instant, permanent, global effect from a single correction is exactly the overcorrection risk flagged in Section 1. The same-session penalty gives you the live demo moment (safe, because it's scoped to one session and reset on next login); the cross-session trust weight gives you the real, defensible, slow-moving improvement (safe, because it's statistically damped and never zeroes anything out).

### 3.2 What Gets Tagged, and How

Every piece of evidence cited in a synthesized answer already has to trace back to something concrete for your XAI/explainability requirement (Architecture v8's "evidence-backed explanations" framing, Section 1) — a specific Memgraph edge, or a specific Catalyst KB document. This doc assumes that citation-to-source mapping already exists in your synthesis output (if it doesn't yet, it's a prerequisite for this feature, not something this doc builds — flag as `[VERIFY]` against your actual current synthesis/XAI code).

Given that mapping exists, each citable piece of evidence carries:
- `edge_type` (for graph-sourced evidence: `SHARED_MO`, `TEMPORAL_CLUSTER`, `CO_ACCUSED`, `SHARED_TATTOO`, `SHARED_VEHICLE`; for KB-sourced narrative matches: a synthetic type like `NARRATIVE_SIMILARITY`)
- `crime_type` — taken from the relevant FIR's `crime_sub_head_id` (Implementation v8's real-schema field)
- `edge_id` or `kb_doc_id` — the specific instance, for the same-session penalty

### 3.3 Data Model — New Records

Two new record types, stored in Catalyst NoSQL (same store already used for session memory and audit logs, Layer 7 — no new infrastructure):

**`CorrectionEvent`** — one per officer action (correction or confirmation), append-only, forms the "library of past mistakes/confirmations" from Point 3 of the discussion:

```python
class CorrectionEvent(BaseModel):
    event_id: str
    session_id: str
    officer_id: str
    timestamp: str
    query_text: str                    # the query that produced the flagged evidence
    edge_type: str                     # e.g. "SHARED_MO"
    crime_type: Optional[str] = None   # crime_sub_head_id, if applicable
    edge_id: Optional[str] = None      # specific graph edge or KB doc, for same-session penalty
    verdict: str                       # "confirmed" | "corrected"
    explanation: Optional[str] = None  # free text -- stored verbatim, NEVER auto-parsed/auto-acted-on
```

**`MethodologyTrust`** — one per (edge_type) and one per (edge_type, crime_type) combination, updated (not appended) as corrections/confirmations accumulate. This is the "scoreboard" from Point 4:

```python
class MethodologyTrust(BaseModel):
    scope_key: str              # "SHARED_MO" or "SHARED_MO::burglary"
    confirmations: int = 0
    corrections: int = 0
    # trust_weight is NOT stored directly -- it's computed on read from
    # confirmations/corrections via the smoothed estimator in Section 4.2,
    # so the smoothing formula can be tuned later without a data migration.
```

### 3.4 Pipeline Integration Points

```
Layer 3 -- Retrieval
    Cypher/KB ranking queries now multiply relevance score by the
    current trust_weight for that evidence's (edge_type, crime_type)
    -- narrow-then-broad fallback (Section 4.3)

Layer 4 -- Confidence Engine
    Same trust_weight feeds into the confidence formula as one input
    among existing signals (graph proximity, corroboration count, etc.)
    -- weakens (never zeroes) the contribution of historically
    unreliable methodology/crime-type combinations

Layer 6 -- Output
    Synthesized answer's citations must expose enough structure
    (edge_type, edge_id, crime_type) for the officer-facing UI to let
    an officer flag a SPECIFIC cited piece of evidence, not just the
    whole answer

Layer 7 -- Session Memory + Feedback  [this is where "Feedback" in the
    existing Layer 7 name finally gets a real mechanism]
    - New API endpoint receives correction/confirmation events
    - Writes CorrectionEvent (audit trail + library)
    - Updates MethodologyTrust scoreboard (persistent, slow-moving)
    - Writes an ephemeral same-session penalty into existing session
      memory (already a Catalyst NoSQL per-session_id store)
```

---

## 4. Implementation

### 4.1 New API Endpoint — `backend/api/routes/feedback.py`

This is a thin AppSail route (consistent with AppSail's existing "thin front door only" principle, Implementation v8 Section 6) — it validates and writes, it doesn't compute the trust weight itself synchronously if that's expensive; the actual smoothing/update logic lives in the shared feedback module below and can run inline (it's cheap arithmetic, no LLM call, so no need to route it through the pipeline Function).

```python
# backend/api/routes/feedback.py

from fastapi import APIRouter, HTTPException
from shared.feedback_models import CorrectionEvent
from shared.feedback_engine import record_feedback_event

router = APIRouter()

@router.post("/api/feedback/correction")
async def submit_feedback(event: CorrectionEvent):
    if event.verdict not in {"confirmed", "corrected"}:
        raise HTTPException(400, "verdict must be 'confirmed' or 'corrected'")
    await record_feedback_event(event)
    return {"status": "recorded"}
```

### 4.2 `shared/feedback_models.py`

```python
# shared/feedback_models.py

from pydantic import BaseModel
from typing import Optional

class CorrectionEvent(BaseModel):
    event_id: str
    session_id: str
    officer_id: str
    timestamp: str
    query_text: str
    edge_type: str
    crime_type: Optional[str] = None
    edge_id: Optional[str] = None
    verdict: str                       # "confirmed" | "corrected"
    explanation: Optional[str] = None  # captured verbatim, never auto-parsed

class MethodologyTrust(BaseModel):
    scope_key: str
    confirmations: int = 0
    corrections: int = 0
```

### 4.3 `shared/feedback_engine.py` — The Core Logic

This is where the discussion's two safeguards (slow-moving smoothing, and narrow-then-broad scoping) actually get implemented.

```python
# shared/feedback_engine.py

from shared.catalyst_client import nosql_get, nosql_set
from shared.feedback_models import CorrectionEvent, MethodologyTrust
import json

# --- Tunable constants -- these encode both safeguards from Section 1 ---

# Bayesian-style smoothing (Beta-distribution prior). PRIOR_STRENGTH acts
# like a virtual sample size of "neutral" evidence already baked in --
# the higher this is, the more real corrections/confirmations it takes
# to move the trust weight meaningfully. This directly implements
# "a mistake once or twice shouldn't swing it."
PRIOR_STRENGTH = 10          # equivalent to 10 neutral prior observations
PRIOR_TRUST = 0.7            # neutral starting trust -- most methodologies
                             # start "reasonably trusted," not distrusted

# Floor -- trust weight can never drop below this. Evidence is deprioritized,
# never hidden. Directly implements "don't fully suppress a signal."
TRUST_WEIGHT_FLOOR = 0.3

# Minimum sample size before a NARROW (edge_type, crime_type) scope is
# trusted on its own -- below this, fall back to the broader edge_type-only
# scope. Directly implements the "don't skew narrowly on sparse data" fix.
MIN_SAMPLES_FOR_NARROW_SCOPE = 15


def _smoothed_trust(confirmations: int, corrections: int) -> float:
    """
    Beta-Bernoulli-style shrinkage estimator. With zero observations,
    returns PRIOR_TRUST exactly. As real observations accumulate, the
    estimate moves toward the true confirm/correct ratio -- but slowly,
    proportional to PRIOR_STRENGTH.
    """
    total = confirmations + corrections
    raw_ratio = confirmations / total if total > 0 else PRIOR_TRUST
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
    await nosql_set(f"trust:{trust.scope_key}", trust.json())


async def get_trust_weight(edge_type: str, crime_type: str | None) -> float:
    """
    The narrow-then-broad fallback. Called from retrieval ranking and the
    Confidence Engine -- NOT from the correction-recording path.
    """
    if crime_type:
        narrow_key = f"{edge_type}::{crime_type}"
        narrow = await _load_trust(narrow_key)
        if (narrow.confirmations + narrow.corrections) >= MIN_SAMPLES_FOR_NARROW_SCOPE:
            return _smoothed_trust(narrow.confirmations, narrow.corrections)
        # not enough narrow-scope data yet -- fall back to broad scope below

    broad = await _load_trust(edge_type)
    return _smoothed_trust(broad.confirmations, broad.corrections)


async def record_feedback_event(event: CorrectionEvent):
    """
    Writes the correction/confirmation to the permanent library (audit
    trail + few-shot-style example bank), updates BOTH the narrow and
    broad MethodologyTrust scopes, and writes the ephemeral same-session
    penalty. Three separate writes, each serving one of the two speeds
    described in Section 3.1.
    """
    # 1. Permanent library entry (Point 3 -- "did I make this mistake before?")
    await nosql_set(f"correction:{event.event_id}", event.json())

    # 2. Persistent, slow-moving trust scoreboard (Point 4) -- both scopes
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

    # 3. Ephemeral same-session penalty (instant demo effect) -- only for
    # corrections, only for this specific edge instance, only this session.
    if not is_confirm and event.edge_id:
        await _apply_session_penalty(event.session_id, event.edge_id)


async def _apply_session_penalty(session_id: str, edge_id: str):
    """
    Session-scoped, ephemeral. Read alongside existing session state
    (Layer 7 already stores resolved entities/prior results per
    session_id) -- this just adds one more key to that same session
    record. Cleared naturally when the session ends; never persists
    beyond it, and never affects any other officer's session.
    """
    key = f"session_penalty:{session_id}"
    existing = await nosql_get(key)
    penalized_ids = set(json.loads(existing["value"])) if existing else set()
    penalized_ids.add(edge_id)
    await nosql_set(key, json.dumps(list(penalized_ids)), ttl=3600 * 8)  # session-length TTL
```

**Notes for Antigravity:**

- `nosql_get` / `nosql_set` are the existing functions already used elsewhere (`shared/catalyst_client.py`, referenced in Implementation v8 Section 8's caching code) — no new client code needed, just new keys.
- The smoothing formula is a standard Beta-Bernoulli shrinkage estimator — if you want to sanity check it: with zero data it returns exactly `PRIOR_TRUST` (0.7); after 1 correction and 0 confirmations, it only drops to `(0 + 7) / (1 + 10) = 0.636` — a small nudge, not a collapse. It takes sustained, repeated correction (well past `PRIOR_STRENGTH`) before it approaches the real observed ratio.
- `MIN_SAMPLES_FOR_NARROW_SCOPE = 15` is a starting guess, not a verified constant — tune based on how much officer interaction volume you realistically expect during the demo/judging window. With very few officers testing over a few days, the narrow scope may rarely activate at all during the hackathon itself — that's fine; the fallback to broad scope means the mechanism still functions, it just won't show off narrow-scoping specifically unless you seed some synthetic correction data for the demo.

### 4.4 Wiring Into Retrieval — `pipeline_function/pipeline/retrieval_node.py` (or wherever ranking happens)

```python
from shared.feedback_engine import get_trust_weight

async def rank_evidence(evidence_items: list[dict], session_id: str) -> list[dict]:
    """
    Applies both trust signals: the persistent methodology weight
    (Section 4.3) and the ephemeral same-session penalty (Section 3.1).
    """
    session_key = f"session_penalty:{session_id}"
    penalized = await _get_session_penalized_ids(session_key)  # existing session read pattern

    for item in evidence_items:
        base_score = item["relevance_score"]  # existing scoring, unchanged
        trust = await get_trust_weight(item.get("edge_type", "NARRATIVE_SIMILARITY"),
                                        item.get("crime_type"))
        session_penalty = 0.5 if item.get("edge_id") in penalized else 1.0
        item["relevance_score"] = base_score * trust * session_penalty

    return sorted(evidence_items, key=lambda x: x["relevance_score"], reverse=True)
```

`[VERIFY]` The exact existing ranking function name and evidence-item shape in your current retrieval code — this snippet assumes a list-of-dicts shape consistent with the `translate_evidence_node` design in `PS1_Evidence_Language_Detection.md` Section 6.2, but should be checked against whatever the real current retrieval/ranking code looks like before wiring in.

### 4.5 Wiring Into the Confidence Engine

The Confidence Engine (Layer 4) already combines multiple signals into a formula. Add `trust_weight` as one more input — a multiplicative dampener, not a replacement for existing signals:

```python
# Conceptual addition to the existing confidence formula --
# exact integration point depends on your current formula's shape.

async def compute_confidence(evidence_item: dict, existing_signals: dict) -> float:
    trust = await get_trust_weight(evidence_item.get("edge_type", "NARRATIVE_SIMILARITY"),
                                    evidence_item.get("crime_type"))
    base_confidence = existing_confidence_formula(existing_signals)  # unchanged
    return base_confidence * trust
```

`[VERIFY]` The real current confidence formula's shape and where it lives — this is a conceptual splice point, not a drop-in replacement, since the actual formula wasn't reproduced in full in Implementation v8's text.

### 4.6 UI Requirement — What Antigravity Needs to Build on the Frontend

Per the "both feedback types" decision (upvote/downvote alone doesn't carry enough context):

- Each cited piece of evidence in a synthesized answer needs a **per-citation control**, not a single whole-answer control — a confirm (✓) and a correct (✗) action, each attached to that citation's `edge_type` / `edge_id` / `crime_type`.
- Selecting "correct" (✗) opens a **free-text explanation field** — required, not optional, since the explanation is what populates the correction library (Section 3.3, `CorrectionEvent.explanation`). This is the "explain your point from this standpoint" requirement — captured verbatim, never parsed automatically.
- Selecting "confirmed" (✓) needs no explanation — it's a lightweight positive signal, still valuable for the confirm/correct ratio in Section 4.2.
- Both actions POST to `/api/feedback/correction` (Section 4.1).

---

## 5. Explicitly Out of Scope (And Why)

Restating this from Section 1 in one place, since it's easy for scope to creep back in during implementation:

- **Entity-extraction corrections (names, IPC sections, dates)** — not built as part of this loop. This is a session-memory concern; if it needs its own improvement mechanism later, it's a separate, smaller feature (closer to the "dynamic few-shot bank" idea raised earlier), not part of methodology trust weighting.
- **Confidence-tier disputes as a standalone complaint** ("this whole answer shouldn't be HIGH") — not a separate mechanism. It's implicitly handled because confidence is now partly a function of the trust weights on the evidence that fed into it; there's no separate "dispute the tier directly" button.
- **Narrative/synthesis disagreement** — captured as free text in the audit log only (reuse the existing audit log mechanism, Architecture v8 Section 13). No automated response, no parsing, no loop. If asked, the honest answer is: "captured for manual review, not auto-acted-on, by design."
- **Any global, single-number confidence-formula retuning** — not built. The formula's *inputs* now include a trust weight; the formula's *coefficients* are untouched by this feature.

---

## 6. Testing / Verification Checklist

- [ ] Zero corrections/confirmations for an edge type → `get_trust_weight` returns exactly `PRIOR_TRUST` (0.7)
- [ ] One correction, zero confirmations → trust weight drops modestly (≈0.636 per the worked example in Section 4.3), not sharply
- [ ] Many consistent corrections (>50, all "corrected") for one edge type → trust weight approaches but never goes below `TRUST_WEIGHT_FLOOR` (0.3)
- [ ] Narrow scope (edge_type + crime_type) with fewer than `MIN_SAMPLES_FOR_NARROW_SCOPE` observations → falls back to broad edge_type-only weight, confirmed via logging/inspection
- [ ] Narrow scope with enough samples, and a *different* trust trajectory than the broad scope → confirms narrow scoping actually isolates crime-type-specific reliability rather than just mirroring the broad score
- [ ] Same-session correction on a specific `edge_id` → immediately re-running a query in the same session shows that specific evidence ranked lower; a **new** session shows it back at its normal (methodology-weighted, not session-penalized) rank
- [ ] Confirmation events accumulate correctly alongside corrections in the same scoreboard (not just corrections being tracked)
- [ ] Free-text explanation is stored verbatim in `CorrectionEvent.explanation` and is never passed to any LLM call automatically anywhere in this feature's code path

---

## 7. Migration Checklist for Antigravity — Exact File Touch List

1. Create `shared/feedback_models.py` (Section 4.2)
2. Create `shared/feedback_engine.py` (Section 4.3) — this is the core logic, implement and unit-test the smoothing function in isolation before wiring it into retrieval/confidence
3. Create `backend/api/routes/feedback.py` (Section 4.1), register the route on the AppSail FastAPI app
4. Update whatever module currently ranks retrieved evidence (Layer 3) to call `get_trust_weight` and apply the session penalty (Section 4.4) — `[VERIFY]` exact current function/file name first
5. Update the Confidence Engine (Layer 4) to fold `trust_weight` into its existing formula as a multiplicative input (Section 4.5) — `[VERIFY]` exact current formula location first
6. Frontend: add per-citation confirm/correct controls to the synthesized-answer UI component, with a required free-text field on "correct" (Section 4.6)
7. Add the test cases from Section 6 to the existing chaos/eval suite
8. Optional, for demo strength: seed a small amount of synthetic correction/confirmation history before judging day so the narrow-scope fallback has a chance to activate live, rather than only ever showing the neutral prior — genuinely representative synthetic data, not fabricated to look impressive, since the point is to demonstrate the mechanism honestly

---

## 8. Summary for `agents.md` / Antigravity Context

> New capability: officer feedback on synthesized answers now closes a real loop, scoped to *reasoning methodology* (graph edge type: SHARED_MO, CO_ACCUSED, etc.), not individual facts or the narrative text itself. Two speeds: an instant same-session penalty on a specific flagged edge instance (demoable live, resets each session), and a slow-moving cross-session trust weight per (edge_type, crime_type) — falling back to edge_type-only when narrow data is sparse — computed via Beta-Bernoulli-style smoothing so a few corrections can't swing it and a floor ensures no evidence type is ever fully suppressed, only deprioritized. Entity-extraction corrections and narrative disagreements are explicitly out of scope for this mechanism — the former is a session-memory concern, the latter is captured as an honest audit-log entry only, never auto-acted-on. No LLM is ever asked to decide whether or how to apply a correction — every step is deterministic arithmetic, consistent with the "LLM plans and synthesizes, systems retrieve" boundary already established in Architecture v8 Section 2 and reused in the Evidence-Language Detection design.
