def build_fallback_response(evidence) -> str:
    """Fallback response when LLM synthesis fails or rate limits are exhausted."""
    return (
        "[Mock Response — LLM unavailable locally] "
        f"Query understood: intent='{evidence.intent}'. "
        f"Evidence retrieved: {len(evidence.items)} item(s). "
        "Connect to Catalyst Qwen API for a real synthesized response."
    )
