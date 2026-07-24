from dataclasses import dataclass, field
from typing import Optional

@dataclass
class EvidenceItem:
    fir_id:             str
    relevance_score:    float
    sources:            list[str]
    convergent:         bool
    evidence_path:      Optional[str]
    similarity_reason:  Optional[str]
    confidence:         str = "medium"
    confidence_reasons: list[str] = field(default_factory=list)
    confidence_flags:   list[str] = field(default_factory=list)
    fir_date:           Optional[str] = None
    metadata:           dict = field(default_factory=dict)
    accused_ids:        list[str] = field(default_factory=list)
    excluded:           bool = False
    exclusion_reason:   Optional[str] = None
    exclusion_type:     Optional[str] = None

@dataclass
class EvidenceObject:
    query:               str
    session_id:          str
    urgency:             str
    intent:              str
    entities:             dict
    items:               list[EvidenceItem] = field(default_factory=list)
    visualizations:      list[dict] = field(default_factory=list)
    reasoning_trace:     list[str] = field(default_factory=list)
    confidence_caveats:  list[str] = field(default_factory=list)

    def add_rag_results(self, rag_response: dict):
        # BUG-07 FIX: use .get() with fallbacks so a real Catalyst KB response
        # that uses slightly different key names (e.g. "document_id" instead of
        # "fir_id", "relevance" instead of "score") doesn't cause a hard KeyError.
        for hit in rag_response.get("results", []):
            self.items.append(EvidenceItem(
                fir_id=hit.get("fir_id") or hit.get("document_id") or hit.get("id", "unknown"),
                relevance_score=hit.get("score") or hit.get("relevance") or hit.get("similarity", 0.5),
                sources=["rag"], convergent=False,
                evidence_path=None, similarity_reason=hit.get("excerpt") or hit.get("text"),
                confidence="medium", metadata=hit.get("metadata", {})
            ))

    def add_graph_results(self, graph_results: list):
        for result in graph_results:
            accused_ids = result.get("metadata", {}).get("accused_ids", [])
            existing = next((e for e in self.items if e.fir_id == result["fir_id"]), None)
            if existing:
                existing.sources.append("graph")
                existing.convergent = True
                existing.evidence_path = result.get("path")
                existing.confidence = "high"
                existing.relevance_score = min(existing.relevance_score * 1.3, 1.0)
                if accused_ids:
                    existing.accused_ids = accused_ids
            else:
                self.items.append(EvidenceItem(
                    fir_id=result["fir_id"], relevance_score=result.get("score", 0.7),
                    sources=["graph"], convergent=False,
                    evidence_path=result.get("path"), similarity_reason=None,
                    confidence="medium", metadata=result.get("metadata", {}),
                    accused_ids=accused_ids
                ))
    
    async def add_sql_results(self, sql_results: list):
        """Map structured SQL rows to EvidenceItems."""
        # BUG FIX: SQL rows only carry crime_sub_head_id (not a display name)
        # and "date" (not "crime_type"/"Date") -- the visualization code
        # (building_visualization_node) reads metadata["crime_type"]/["Date"],
        # so without this, SQL-sourced evidence was silently bucketed as
        # "Unknown" in the dashboard exactly like the KB-metadata mismatch fixed
        # earlier. Resolves the friendly name via the same cache
        # entity_lookup_resolver.py already loads.
        from pipeline_function.pipeline.query_understanding.entity_lookup_resolver import get_crime_sub_head_name
        for row in sql_results:
            fir_id = row.get("id") or row.get("fir_internal_id")
            if not fir_id:
                continue
            csh_id = row.get("crime_sub_head_id")
            crime_type_name = await get_crime_sub_head_name(csh_id) if csh_id else None
            self.items.append(EvidenceItem(
                fir_id=fir_id,
                relevance_score=row.get("score", 0.65),
                sources=["sql"],
                convergent=False,
                evidence_path=None,
                similarity_reason=f"Structured match: {row.get('crime_no', 'unknown')}",
                confidence="medium",
                fir_date=row.get("date"),
                metadata={
                    **row,
                    "crime_type": crime_type_name or "Unknown",
                    "Date": row.get("date", ""),
                }
            ))

    def rank(self):
        self.items.sort(key=lambda x: x.relevance_score, reverse=True)
