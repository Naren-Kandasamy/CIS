from dataclasses import dataclass
from datetime import date, datetime
from pipeline_function.pipeline.evidence import EvidenceItem, EvidenceObject
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

def run_confidence_engine(evidence: EvidenceObject) -> EvidenceObject:
    for item in evidence.items:
        sig = compute_confidence(item)
        item.confidence = sig.tier
        item.relevance_score = sig.score
        item.confidence_reasons = sig.reasons
        item.confidence_flags = sig.flags
        evidence.reasoning_trace.append(
            f"{item.fir_id}: {sig.tier} ({sig.score:.2f}) -- {'; '.join(sig.reasons[:2])}"
        )
    evidence.rank()
    return evidence
