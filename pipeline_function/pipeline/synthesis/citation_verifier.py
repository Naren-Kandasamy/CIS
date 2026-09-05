import re

# BUG FIX (2026-09 audit): SYNTHESIS_SYSTEM (synthesizer.py) already instructs
# the LLM, quite firmly, to cite every claim as "[FIR: <id>]" and to never
# invent an FIR ID -- but that instruction is enforced by prompt wording
# alone. Nothing downstream ever checked whether the model actually complied.
# That matters for two distinct failure modes, not just "the LLM hallucinates
# sometimes":
#   1. Ordinary hallucination -- the model cites a real-looking but wrong ID.
#   2. Prompt injection -- FIR narrative text or history is officer/case-
#      entered free text that reaches the prompt as "untrusted data" (see the
#      delimiting already done in langgraph_router.py's synthesizing_response_
#      node). A crafted narrative could still try to get the model to cite a
#      fabricated or an excluded/ruled-out FIR as if it were live evidence.
# A regex denylist on the *input* (backend/api/middleware/input_validator.py)
# can't catch either case -- it only ever sees the officer's query, never the
# model's output. This module is the output-side check: parse every
# "[FIR: <id>]" citation out of the synthesized text and confirm it names an
# ID that was actually in the evidence set handed to the LLM. It does not
# use an LLM itself, so it can't be prompt-injected, and it's fully
# deterministic/unit-testable.

CITATION_PATTERN = re.compile(r"\[FIR:\s*([^\]]+?)\s*\]", re.IGNORECASE)


def extract_cited_fir_ids(response_text: str) -> list[str]:
    """Every FIR ID cited in the response, in order of first appearance, deduplicated."""
    seen = []
    for match in CITATION_PATTERN.findall(response_text or ""):
        fir_id = match.strip()
        if fir_id and fir_id not in seen:
            seen.append(fir_id)
    return seen


def verify_citations(response_text: str, evidence_dicts: list[dict]) -> dict:
    """
    Compare every "[FIR: <id>]" citation in response_text against the FIR IDs
    actually present in evidence_dicts (the exact list handed to the LLM as
    EVIDENCE_START/EVIDENCE_END in langgraph_router.py).

    Returns:
        {
            "cited": [...],       # every FIR ID the model cited
            "verified": [...],    # cited IDs that were genuinely in evidence
            "unverified": [...],  # cited IDs NOT found in evidence -- either
                                   # hallucinated, fabricated, or (rarer)
                                   # injected via crafted narrative text
        }

    An evidence item's "excluded" flag does NOT make its citation unverified
    here -- the model is allowed to cite an excluded item (e.g. "X was
    considered but ruled out [FIR: 123]"); that's a legitimate, sourced
    claim. "unverified" means the ID doesn't correspond to any retrieved
    evidence item at all.
    """
    cited = extract_cited_fir_ids(response_text)
    known_fir_ids = {str(item.get("fir_id")) for item in evidence_dicts if item.get("fir_id") is not None}

    verified = [fid for fid in cited if fid in known_fir_ids]
    unverified = [fid for fid in cited if fid not in known_fir_ids]

    return {"cited": cited, "verified": verified, "unverified": unverified}
