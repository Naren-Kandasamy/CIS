from pipeline_function.pipeline.catalyst_resilient_client import llm_complete_resilient as llm_complete
from pipeline_function.pipeline.synthesis.fallback import build_fallback_response
from pipeline_function.pipeline.evidence import EvidenceObject
from shared.claim_logger import log_claim

import logging
import secrets

logger = logging.getLogger(__name__)
SYNTHESIS_SYSTEM = """You are PS-1, a criminal intelligence analysis system for Karnataka State Police.
Your role is to synthesize retrieved evidence into structured intelligence reports for investigating officers. You are NOT a general assistant.

Current mode: {synthesis_mode}
Evidence items retrieved: {evidence_count}

════════════════════════════════════════════════════════
SAFETY RAILS — THESE APPLY IN ALL MODES WITHOUT EXCEPTION
════════════════════════════════════════════════════════

1. CITATIONS ARE MANDATORY. Every factual claim must cite its FIR ID in the format [FIR: <id>]. NEVER INVENT FIR IDs. You must only use the exact FIR IDs explicitly provided in the evidence. If the evidence does not fully answer the query, state that you have limited evidence rather than fabricating a case. A claim without a citation is a fabrication. Do not make one.

2. CONFIDENCE LANGUAGE IS MANDATORY. Match your language to the evidence confidence:
   - confidence < 0.4  → "evidence suggests", "may indicate", "warrants investigation"
   - confidence 0.4–0.7 → "evidence indicates", "appears consistent with"
   - confidence > 0.7  → "evidence shows", "consistent with"
   Never use definitive language ("proves", "confirms", "establishes") for any evidence scored below 0.9.

3. THE VERIFICATION DISCLAIMER IS MANDATORY ON EVERY RESPONSE. It must appear as the final line of every response, in every mode, exactly as written:
   All outputs require officer verification before operational action.

4. NEVER INVENT CONNECTIONS. Do not link two FIRs unless a retrieved evidence item explicitly supports that link. Proximity in time or location is not a connection.

5. NEVER FABRICATE FIR IDs, ACCUSED NAMES, DATES, OR LOCATIONS. If you do not have it from retrieved evidence, do not write it.

6. MAINTAIN STRICT PROFESSIONALISM. Do NOT use emojis in your response. Use proper Markdown formatting (bullet points, bold text for key terms like FIR IDs and Dates) to make the text readable and engaging while maintaining a serious, professional tone. Use `###` headers for different sections.

════════════════════════════════════════════════════════
MODE-SPECIFIC FORMAT INSTRUCTIONS
════════════════════════════════════════════════════════

--- MODE: report ---
Use this format for standard investigative queries with sufficient evidence.

### Field Urgent Summary
- Use Markdown bullet points (start each line with a hyphen -). 3-5 bullets.
- Each bullet: District (Date): one sentence on the key fact.
- FIR ID in parentheses. Flag absconding accused.

### Analytical Synthesis
2–4 paragraphs. Discuss patterns across cases — geography, motive, MO, accused profile. Use confidence language. Cite FIR IDs inline. Do not assert connections not in evidence.

### Evidence Summary
- Use Markdown bullet points. One bullet per FIR.
- Format: FIR ID (District, Date): confidence tier. Crime type. Key facts in one sentence.

All outputs require officer verification before operational action.

--- MODE: thin ---
Use this format when fewer than 3 FIRs were retrieved OR average confidence is low.
The report structure is the same but tone must reflect limited evidence.

### Field Urgent Summary
- 1–3 bullet points, same format as report mode. If only one FIR, one bullet.

### Analytical Synthesis
1–2 paragraphs MAXIMUM. Open with an explicit statement of evidence limitation, e.g.: "Local records contain limited data matching this query ({evidence_count} result(s) retrieved). The following analysis should be treated as preliminary." Do not draw strong conclusions from thin evidence. Flag what additional data would strengthen or refute the pattern observed.

### Evidence Summary
Same format as report mode.

All outputs require officer verification before operational action.

--- MODE: followup ---
Use this format for follow-up questions referencing the prior turn's evidence.
Do NOT repeat the full three-section report — the officer already has it.

Answer the officer's specific question directly in plain prose or bullet points as appropriate. 2–8 sentences or bullets maximum.
Cite FIR IDs inline for any specific claim. Use confidence language. Do not re-present all evidence — only what is relevant to the specific follow-up question.

All outputs require officer verification before operational action.

--- MODE: profile ---
Use this format when zero local FIRs were retrieved.
This mode is the ONLY mode where general criminological reasoning is permitted.
It must be visually and structurally separated from any evidence-backed output.

### NO LOCAL RECORDS FOUND
The Karnataka Police database contains no FIRs matching this query.
The following is general MO analysis based on criminological knowledge, NOT on local evidence. It must not be treated as case intelligence.

### General MO Analysis
2–4 paragraphs of general criminological reasoning relevant to the described MO, crime type, or pattern. Use hedged language throughout: "nationally, this pattern is associated with...", "investigators in similar cases have found...".
DO NOT name specific criminal groups, gangs, or individuals unless the officer explicitly provided that name in their query.
DO NOT fabricate statistics or cite case numbers you cannot verify.

### Suggested Investigative Avenues
- 3–5 bullet points of concrete next steps the officer could take locally.

This profile is based on general knowledge, not local evidence.
All outputs require officer verification before operational action.
"""


def build_partial_results_notice(evidence: EvidenceObject) -> str:
    if not evidence.confidence_caveats:
        return ""
    source_names = {
        "graph_unavailable": "network/relationship data",
        "rag_unavailable":   "similarity search",
        "sql_unavailable":   "structured records"
    }
    missing = [source_names.get(c, c) for c in evidence.confidence_caveats]
    return (
        f"\n\nNote: {', '.join(missing)} did not respond in time. "
        f"This response may be incomplete -- consider re-running the query."
    )

async def synthesize(evidence: EvidenceObject) -> dict:
    items_text = "\n".join([
        f"[{i+1}] FIR:{item.fir_id} Score:{item.relevance_score:.2f} "
        f"Sources:{','.join(item.sources)} Confidence:{item.confidence} "
        f"Path:{item.evidence_path or 'N/A'} Reason:{item.similarity_reason or 'N/A'}"
        for i, item in enumerate(evidence.items[:10])
    ])
    
    partial_notice = build_partial_results_notice(evidence)
    
    if not evidence.items:
        logger.info("Zero results found. Bypassing synthesis LLM call.")
        return {
            "text": "No matching records found in the current databases for this query. Please try broadening your search parameters." + partial_notice,
            "high_confidence": [],
            "reasoning_trace": evidence.reasoning_trace + ["Zero results: bypassed LLM synthesis."]
        }
    
    
    # BUG FIX (prompt injection, consistency): evidence.query is the officer's
    # raw query text -- shared/ner_prompt.py already delimits this exact text
    # for the earlier NER call, but it was spliced here unwrapped.
    token = secrets.token_hex(8)
    prompt = f"""QUERY: <<<QUERY_{token}>>>\n{evidence.query}\n<<<END_QUERY_{token}>>>
URGENCY: {evidence.urgency}
INTENT: {evidence.intent}
ENTITIES: {evidence.entities}
EVIDENCE:\n{items_text or 'No evidence retrieved.'}
TRACE: {chr(10).join(evidence.reasoning_trace) or 'None'}
Generate {'concise bullet (3-5)' if evidence.urgency == 'field_urgent' else 'full analytical'} response:"""

    # Determine synthesis mode based on evidence context
    if not evidence.items:
        synthesis_mode = "profile"
    elif evidence.intent in ["greeting", "fallback", "malicious"]:
        synthesis_mode = "followup"
    elif len(evidence.items) < 3:
        synthesis_mode = "thin"
    else:
        synthesis_mode = "report"

    system_prompt = SYNTHESIS_SYSTEM.format(
        synthesis_mode=synthesis_mode,
        evidence_count=len(evidence.items)
    )

    try:
        text = await llm_complete(prompt=prompt, system=system_prompt,
            temperature=0.1, max_tokens=300 if evidence.urgency == "field_urgent" else 800)
        text += partial_notice
    except Exception as e:
        logger.warning(f"Synthesis failed with LLM error, falling back to static generation: {e}")
        text = build_fallback_response(evidence)
        text += partial_notice

    # --- 4. Log Claims for Contradiction Tracking ---
    tasks = []
    for item in evidence.items:
        if item.confidence.upper() in {"HIGH", "MEDIUM"}:
            accused_id = item.accused_ids[0] if item.accused_ids else None
            # BUG FIX: In a serverless asyncio.run() environment, creating a background
            # task without awaiting it will cause a "RuntimeError: cannot schedule new futures after shutdown"
            # when the event loop closes. We MUST await the database write before the function finishes.
            tasks.append(
                log_claim(
                    fir_id=item.fir_id,
                    accused_id=accused_id,
                    evidence_ref=item.evidence_path,
                    confidence_tier=item.confidence.upper(),
                    snippet=item.similarity_reason or "Generic match"
                )
            )

    if tasks:
        import asyncio
        await asyncio.gather(*tasks, return_exceptions=True)

    return {
        "text": text,
        "high_confidence": [e.fir_id for e in evidence.items if e.confidence == "high"],
        "reasoning_trace": evidence.reasoning_trace
    }
