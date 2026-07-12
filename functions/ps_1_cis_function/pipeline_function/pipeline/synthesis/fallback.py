def build_fallback_response(evidence) -> str:
    """Fallback response when LLM synthesis fails or rate limits are exhausted."""
    return (
        f"Analysis engine temporarily unavailable. "
        f"Evidence retrieved for your query: {len(evidence.items)} record(s) found "
        f"(intent: {evidence.intent}). Please retry your query. "
        "All outputs require officer verification before action."
    )
