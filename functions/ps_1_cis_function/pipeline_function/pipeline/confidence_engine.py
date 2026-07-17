from dataclasses import dataclass
from datetime import date, datetime
from pipeline_function.pipeline.evidence import EvidenceItem, EvidenceObject
from shared.exclusion_engine import get_active_exclusions_bulk, alibi_covers_incident, EXCLUSION_DEMOTION_FACTOR
from shared.feedback_engine import get_trust_weight, get_session_penalized_ids
from typing import Optional

@dataclass
class ConfidenceSignal:
    tier: str; score: float; reasons: list[str]; flags: list[str]

def compute_source_convergence(item: EvidenceItem) -> tuple:
    if "graph" in item.sources and "rag" in item.sources:
        return 1.0, ["Found via both semantic similarity and graph relationship"]
    elif "graph" in item.sources:
        return 0.75, ["Found via direct graph relationship"]
    elif "sql" in item.sources:
        return 0.65, ["Found via structured database match"]
    elif "rag" in item.sources:
        return 0.55, ["Found via semantic MO similarity only"]
    return 0.30, ["Source unknown"]

def compute_evidence_strength(item: EvidenceItem) -> tuple:
    reasons, flags = [], []
    score = 0.50
    if item.evidence_path:
        path = item.evidence_path.lower()
        if "co_accused" in path:
            score = 1.0; reasons.append(f"Direct co-accused: {item.evidence_path}")
        elif "shared_vehicle" in path or "phone_contact" in path:
            score = 0.85; reasons.append(f"Strong associative link: {item.evidence_path}")
        elif "shared_mo" in path:
            score = 0.75; reasons.append(f"Shared MO: {item.evidence_path}")
        elif "shared_tattoo" in path:
            score = 0.65; reasons.append(f"Tattoo match: {item.evidence_path}")
            flags.append("Physical descriptor -- not forensically confirmed")
        elif "temporal_cluster" in path:
            score = 0.55; reasons.append(f"Temporal proximity: {item.evidence_path}")
            flags.append("Temporal proximity alone does not establish connection")
        else:
            score = 0.50; reasons.append(f"Indirect: {item.evidence_path}")
    elif item.similarity_reason:
        score = 0.50; reasons.append(f"MO similarity: {item.similarity_reason[:80]}")
        flags.append("No direct graph relationship -- similarity only")
    else:
        score = 0.30; flags.append("No evidence path -- needs manual verification")
    if item.metadata.get("ocr_extracted"):
        score *= 0.90; flags.append("OCR-extracted fields -- verify against original")
    return score, reasons, flags

def compute_recency(fir_date_str: Optional[str]) -> tuple:
    try:
        days = (date.today() - datetime.strptime(fir_date_str, "%Y-%m-%d").date()).days
        if days <= 90:  return 1.0, ["Recent FIR (within 90 days)"]
        if days <= 365: return 0.8, ["FIR within past year"]
        if days <= 730: return 0.6, ["FIR within past 2 years"]
        return 0.4, [f"Older FIR ({days//365} years ago)"]
    except (ValueError, TypeError):
        return 0.5, ["FIR date unknown"]

def assign_tier(score: float, flags: list) -> str:
    if flags and score < 0.70: return "unverified"
    if score >= 0.80: return "high"
    if score >= 0.60: return "medium"
    if score >= 0.40: return "low"
    return "unverified"

def compute_confidence(item: EvidenceItem) -> ConfidenceSignal:
    c, cr = compute_source_convergence(item)
    s, sr, sf = compute_evidence_strength(item)
    r, rr = compute_recency(item.fir_date)
    final = (c * 0.45) + (s * 0.40) + (r * 0.15)
    return ConfidenceSignal(tier=assign_tier(final, sf), score=round(final, 3),
                             reasons=cr+sr+rr, flags=sf)

async def apply_exclusion_demotion(evidence: EvidenceObject) -> None:
    """
    Heavily demotes (never removes) evidence items whose linked Accused has
    an active EXCLUDED_FROM record for that item's FIR. See
    Docs/PS1_Negative_Evidence_Exclusion_Tracking.md Section 4.4.

    DEVIATION from the design doc: the doc's rank_evidence() takes a single
    active_investigation_fir_id for the whole query, since it assumed
    evidence items carry an accused_id directly. The real EvidenceItem is
    FIR-centric (see evidence.py) and now carries accused_ids per item
    (populated by retrieval/executor.py's ACCUSED_IN lookup), so exclusions
    are checked per item against that item's own fir_id/fir_date instead --
    this also makes the doc's [VERIFY] about Layer 2 supplying a query-wide
    "case in context" id unnecessary.
    """
    fir_ids = {item.fir_id for item in evidence.items if item.accused_ids}
    if not fir_ids:
        return

    exclusions_by_fir = await get_active_exclusions_bulk(fir_ids)
    for item in evidence.items:
        exclusions = exclusions_by_fir.get(item.fir_id)
        if not exclusions:
            continue
        for accused_id in item.accused_ids:
            exclusion = exclusions.get(accused_id)
            if not exclusion or not alibi_covers_incident(exclusion, item.fir_date):
                continue
            item.relevance_score = round(item.relevance_score * EXCLUSION_DEMOTION_FACTOR, 4)
            item.excluded = True
            item.exclusion_reason = exclusion.reason
            item.exclusion_type = exclusion.exclusion_type
            evidence.reasoning_trace.append(
                f"{item.fir_id}: accused {accused_id} excluded -- {exclusion.reason}"
            )
            break  # one active exclusion is enough to demote this evidence item


async def run_confidence_engine(evidence: EvidenceObject) -> EvidenceObject:
    penalized_ids = await get_session_penalized_ids(evidence.session_id)
    
    for item in evidence.items:
        sig = compute_confidence(item)
        item.confidence = sig.tier
        item.relevance_score = sig.score
        item.confidence_reasons = sig.reasons
        item.confidence_flags = sig.flags
        
        # Apply Reasoning Feedback Loop (Trust-Weighting & Session Penalty)
        edge_type = "NARRATIVE_SIMILARITY"
        if item.evidence_path:
            path = item.evidence_path.lower()
            if "co_accused" in path: edge_type = "CO_ACCUSED"
            elif "shared_vehicle" in path: edge_type = "SHARED_VEHICLE"
            elif "phone_contact" in path: edge_type = "PHONE_CONTACT"
            elif "shared_mo" in path: edge_type = "SHARED_MO"
            elif "shared_tattoo" in path: edge_type = "SHARED_TATTOO"
            elif "temporal_cluster" in path: edge_type = "TEMPORAL_CLUSTER"

        crime_type = item.metadata.get("crime_sub_head_id") or item.metadata.get("crime_type")
        trust = await get_trust_weight(edge_type, crime_type)
        
        edge_id = item.metadata.get("edge_id") or item.fir_id
        session_penalty = 0.5 if edge_id in penalized_ids else 1.0
        
        # Apply feedback demotion to both relevance score and confidence tier (implicitly via score)
        item.relevance_score = item.relevance_score * trust * session_penalty
        
        # Optionally re-evaluate confidence tier if score dropped significantly due to feedback
        if item.relevance_score < 0.60 and item.confidence in ["high", "medium"]:
            item.confidence = "low"
            item.confidence_flags.append(f"Demoted due to methodology feedback (trust={trust:.2f}, penalty={session_penalty:.1f})")

        evidence.reasoning_trace.append(
            f"{item.fir_id}: {item.confidence} ({item.relevance_score:.2f}) -- {'; '.join(sig.reasons[:2])}"
        )
    await apply_exclusion_demotion(evidence)
    evidence.rank()
    return evidence
