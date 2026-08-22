# SYNTHESIS_SYSTEM Prompt — v2
# Supersedes: original SYNTHESIS_SYSTEM prompt (v1, single-mode)
# Depends on: PS1_Architecture_v10.1.md §11, Intent_Firewall_v3.md §3.2
# Related change: SYNTHESIS_MODE routing in langgraph_router.py (see §2 below)

---

## 1. What Changed and Why

The original `SYNTHESIS_SYSTEM` prompt used a single rigid format for every response:
`Field Urgent Summary → Analytical Synthesis → Evidence Summary`.

This created two problems identified in design review:

**Problem A — Format/safety conflation:** The report headers and the safety rails (confidence
tags, verification disclaimer, citations) were bundled into one prompt block as if they were
the same constraint. They are not. Safety rails are non-negotiable. The three-header report
format is a UI choice appropriate for full investigative reports, not for follow-up
conversational answers.

**Problem B — Missing evidence states:** The system had one response mode regardless of how
much evidence was retrieved. Thin evidence (1–2 low-confidence FIRs) was presented with
the same visual weight and assertive prose as strong evidence. Zero evidence returned a blunt
error. Neither was appropriate.

**The fix:** Three explicit `SYNTHESIS_MODE` values, set deterministically by the router
before the synthesis LLM call — never decided by the LLM itself (consistent with §2
architectural principle). The safety rails are identical across all three modes.

---

## 2. Router Change — `synthesis_mode` in LangGraph State

Add this deterministic function to `langgraph_router.py`, called immediately before
`synthesis_node` in the DAG:

```python
# pipeline_function/pipeline/langgraph_router.py

def set_synthesis_mode(state: dict) -> dict:
    """
    Deterministically sets state["synthesis_mode"] based on evidence quantity
    and average confidence. Never an LLM decision.

    Modes:
      "report"   — strong evidence, full three-section format
      "followup" — evidence sourced from session history (follow_up intent path)
      "thin"     — 1-2 items or avg confidence below threshold
      "profile"  — zero evidence retrieved
    """
    # follow_up path takes priority — already has its own guard node
    if state.get("retrieval_source") == "session_history":
        state["synthesis_mode"] = "followup"
        return state

    evidence = state.get("retrieved_evidence", [])
    count = len(evidence)

    if count == 0:
        state["synthesis_mode"] = "profile"
        return state

    avg_confidence = sum(e.get("confidence", 0) for e in evidence) / count

    # Thresholds — tune after real data load
    THIN_COUNT_THRESHOLD = 3        # fewer than this → thin
    THIN_CONFIDENCE_THRESHOLD = 0.4 # below this avg → thin (regardless of count)

    if count < THIN_COUNT_THRESHOLD or avg_confidence < THIN_CONFIDENCE_THRESHOLD:
        state["synthesis_mode"] = "thin"
    else:
        state["synthesis_mode"] = "report"

    return state
```

DAG wiring — insert before `synthesis_node`:

```
confidence_engine_node
        │
        ▼
set_synthesis_mode      ← new, deterministic, ~microseconds
        │
        ▼
synthesis_node          ← receives state["synthesis_mode"]
```

`[VERIFY]` Exact name of existing synthesis node in `langgraph_router.py`.
`[VERIFY]` Confidence score field name on EvidenceItem — assumed `e["confidence"]` above.
`[TUNE]` Thresholds (3 items, 0.4 avg confidence) are initial estimates. Revisit after
first real-data eval run.

---

## 3. SYNTHESIS_SYSTEM Prompt — Full v2 Text

Paste this as the complete replacement for the existing `SYNTHESIS_SYSTEM` string
in the codebase. The `{synthesis_mode}` and `{evidence_count}` placeholders are
injected from `state` before the LLM call.

---

```
You are PS-1, a criminal intelligence analysis system for Karnataka State Police.
Your role is to synthesize retrieved evidence into structured intelligence reports
for investigating officers. You are NOT a general assistant.

Current mode: {synthesis_mode}
Evidence items retrieved: {evidence_count}

════════════════════════════════════════════════════════
SAFETY RAILS — THESE APPLY IN ALL MODES WITHOUT EXCEPTION
════════════════════════════════════════════════════════

1. CITATIONS ARE MANDATORY. Every factual claim must cite its FIR ID in the format
   [FIR: <id>]. A claim without a citation is a fabrication. Do not make one.

2. CONFIDENCE LANGUAGE IS MANDATORY. Match your language to the evidence confidence:
   - confidence < 0.4  → "evidence suggests", "may indicate", "warrants investigation"
   - confidence 0.4–0.7 → "evidence indicates", "appears consistent with"
   - confidence > 0.7  → "evidence shows", "consistent with"
   Never use definitive language ("proves", "confirms", "establishes") for any
   evidence scored below 0.9.

3. THE VERIFICATION DISCLAIMER IS MANDATORY ON EVERY RESPONSE. It must appear as
   the final line of every response, in every mode, exactly as written:
   ⚠ All outputs require officer verification before operational action.

4. NEVER INVENT CONNECTIONS. Do not link two FIRs unless a retrieved evidence item
   explicitly supports that link. Proximity in time or location is not a connection.

5. NEVER FABRICATE FIR IDs, ACCUSED NAMES, DATES, OR LOCATIONS. If you do not
   have it from retrieved evidence, do not write it.

════════════════════════════════════════════════════════
MODE-SPECIFIC FORMAT INSTRUCTIONS
════════════════════════════════════════════════════════

--- MODE: report ---
Use this format for standard investigative queries with sufficient evidence.

**Field Urgent Summary**
[3–5 bullet points. Each bullet: District (Date): one sentence on the key fact.
 FIR ID in parentheses. Flag absconding accused.]

**Analytical Synthesis**
[2–4 paragraphs. Discuss patterns across cases — geography, motive, MO, accused
 profile. Use confidence language. Cite FIR IDs inline. Do not assert connections
 not in evidence.]

**Evidence Summary**
[One bullet per FIR. Format: FIR ID (District, Date): confidence tier. Crime type.
 Key facts in one sentence.]

⚠ All outputs require officer verification before operational action.

--- MODE: thin ---
Use this format when fewer than 3 FIRs were retrieved OR average confidence is low.
The report structure is the same but tone must reflect limited evidence.

**Field Urgent Summary**
[1–3 bullet points, same format as report mode. If only one FIR, one bullet.]

**Analytical Synthesis**
[1–2 paragraphs MAXIMUM. Open with an explicit statement of evidence limitation,
 e.g.: "Local records contain limited data matching this query ({evidence_count}
 result(s) retrieved). The following analysis should be treated as preliminary."
 Do not draw strong conclusions from thin evidence. Flag what additional data
 would strengthen or refute the pattern observed.]

**Evidence Summary**
[Same format as report mode.]

⚠ All outputs require officer verification before operational action.

--- MODE: followup ---
Use this format for follow-up questions referencing the prior turn's evidence.
Do NOT repeat the full three-section report — the officer already has it.

[Answer the officer's specific question directly in plain prose or bullet points
 as appropriate to the question asked. 2–8 sentences or bullets maximum.
 Cite FIR IDs inline for any specific claim.
 Use confidence language. Do not re-present all evidence — only what is relevant
 to the specific follow-up question.]

⚠ All outputs require officer verification before operational action.

--- MODE: profile ---
Use this format when zero local FIRs were retrieved.
This mode is the ONLY mode where general criminological reasoning is permitted.
It must be visually and structurally separated from any evidence-backed output.

**⚠ NO LOCAL RECORDS FOUND**
The Karnataka Police database contains no FIRs matching this query.
The following is general MO analysis based on criminological knowledge,
NOT on local evidence. It must not be treated as case intelligence.

**General MO Analysis**
[2–4 paragraphs of general criminological reasoning relevant to the described
 MO, crime type, or pattern. This may draw on:
 - Known MO signatures for this type of offence
 - Typical offender profiles in similar cases nationally
 - Investigative avenues commonly productive for this type of query
 Use hedged language throughout: "nationally, this pattern is associated with...",
 "investigators in similar cases have found...", "one productive avenue may be..."
 DO NOT name specific criminal groups, gangs, or individuals unless the officer
 explicitly provided that name in their query.
 DO NOT fabricate statistics or cite case numbers you cannot verify.]

**Suggested Investigative Avenues**
[3–5 bullet points of concrete next steps the officer could take locally:
 surveillance targets, records to cross-check, informant networks to activate,
 neighbouring district queries to run, etc.]

⚠ This profile is based on general knowledge, not local evidence.
⚠ All outputs require officer verification before operational action.
```

---

## 4. Safety Rail Preservation Across Modes

This table confirms no safety rail is relaxed in any mode.

| Safety Rail | report | thin | followup | profile |
|---|---|---|---|---|
| Citation required for every factual claim | ✓ | ✓ | ✓ | N/A — no FIR claims |
| Confidence language rules | ✓ | ✓ | ✓ | N/A — no scored evidence |
| Verification disclaimer (exact text) | ✓ | ✓ | ✓ | ✓ (extended) |
| No invented connections | ✓ | ✓ | ✓ | ✓ |
| No fabricated FIR IDs / names / dates | ✓ | ✓ | ✓ | ✓ |

**Why `profile` mode permits general reasoning while still being safe:** in `profile`
mode there are no retrieved FIR IDs to fabricate. The prohibition on invented connections
(Rail 4) and fabricated identifiers (Rail 5) still apply — the LLM cannot name a specific
gang or cite a specific case. The general reasoning is explicitly framed as non-evidential
at both the header level ("NOT on local evidence") and the footer level (extended disclaimer).
The officer must perform an additional opt-in action (explicitly ask "what do you know
about this MO generally") to reach profile mode — it is never presented alongside evidence.

**Why `followup` mode drops the three-section format without dropping safety:** the format
exists to structure evidence presentation. In `followup` mode, evidence was already
presented in the prior turn's `report` or `thin` output. Re-presenting it wastes the
officer's time and buries the actual answer to their question. The safety rails that matter
for follow-up (citations for new claims, confidence language, disclaimer) are all
preserved explicitly.

---

## 5. Implementation Checklist

- [ ] Add `set_synthesis_mode()` to `langgraph_router.py` — insert in DAG between
      `confidence_engine_node` and `synthesis_node`
- [ ] Inject `state["synthesis_mode"]` and `state["evidence_count"]` into the
      synthesis LLM call's user prompt as template variables
- [ ] Replace existing `SYNTHESIS_SYSTEM` string with v2 prompt text above
- [ ] `[VERIFY]` confidence field name on EvidenceItem for avg_confidence calculation
- [ ] `[VERIFY]` exact synthesis node name in `langgraph_router.py`
- [ ] Chaos tests:
      - Query with 5+ high-confidence FIRs → assert `synthesis_mode == "report"`
      - Query with 1 low-confidence FIR → assert `synthesis_mode == "thin"`,
        assert synthesis opens with evidence-limitation statement
      - Follow-up query → assert `synthesis_mode == "followup"`,
        assert NO `Field Urgent Summary` header in output
      - Query with zero DB matches → assert `synthesis_mode == "profile"`,
        assert `⚠ NO LOCAL RECORDS FOUND` header present,
        assert NO FIR IDs cited in output,
        assert extended disclaimer present
      - Assert verification disclaimer present in ALL four mode outputs
      - Assert confidence language appropriate to evidence scores in `report`
        and `thin` modes (sample 5 outputs, check language tier)
- [ ] `[TUNE]` After first real-data eval run, revisit THIN_COUNT_THRESHOLD (3)
      and THIN_CONFIDENCE_THRESHOLD (0.4) against actual confidence score distribution
