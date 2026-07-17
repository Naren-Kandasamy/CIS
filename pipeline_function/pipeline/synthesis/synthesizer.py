from pipeline_function.pipeline.catalyst_resilient_client import llm_complete_resilient as llm_complete
from pipeline_function.pipeline.catalyst_resilient_client import RateLimitExhaustedError
from pipeline_function.pipeline.synthesis.fallback import build_fallback_response
from pipeline_function.pipeline.evidence import EvidenceObject

import logging

logger = logging.getLogger(__name__)

SYNTHESIS_SYSTEM = """You are a criminal intelligence assistant for KSP field investigators.
Synthesize retrieved evidence into clear, actionable summaries.

RULES:
- Cite every factual claim with its source (FIR ID / graph path / algorithm)
- Use "appears as accused in FIR" -- NEVER "committed"
- Flag low-confidence results explicitly -- never present as certain
- HIGH confidence: state as fact. MEDIUM: use qualifier. LOW/UNVERIFIED: flag for verification
- field_urgent: 3-5 bullet points maximum
- analytical: full paragraph synthesis with evidence section
- If evidence object is empty: state no records found, suggest alternative queries
- Never fabricate connections not in evidence
- If an evidence item has excluded=true, do not present it as a lead -- state
  that it has been ruled out and give its exclusion_reason; never omit it
- Always end with: "All outputs require officer verification before action."
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
    
    
    prompt = f"""QUERY: {evidence.query}
URGENCY: {evidence.urgency}
INTENT: {evidence.intent}
ENTITIES: {evidence.entities}
EVIDENCE:\n{items_text or 'No evidence retrieved.'}
TRACE: {chr(10).join(evidence.reasoning_trace) or 'None'}
Generate {'concise bullet (3-5)' if evidence.urgency == 'field_urgent' else 'full analytical'} response:"""

    try:
        text = await llm_complete(prompt=prompt, system=SYNTHESIS_SYSTEM,
            temperature=0.1, max_tokens=300 if evidence.urgency == "field_urgent" else 800)
        text += partial_notice
    except Exception as e:
        logger.warning(f"Synthesis failed with LLM error, falling back to static generation: {e}")
        text = build_fallback_response(evidence)
        text += partial_notice

    return {
        "text": text,
        "high_confidence": [e.fir_id for e in evidence.items if e.confidence == "high"],
        "reasoning_trace": evidence.reasoning_trace
    }
