import json, re
from pipeline_function.pipeline.catalyst_resilient_client import llm_complete_resilient as llm_complete
from pipeline_function.pipeline.cache import get_cached_ner, set_cached_ner, get_ner_cache_lock
from shared.ner_prompt import build_ner_prompt, NER_INTENT_SYSTEM

async def extract_ner_and_intent(normalized_query: str) -> dict:
    # BUG FIX: the cache check-then-LLM-call-then-set sequence used to have
    # no lock -- concurrent identical/near-identical queries (e.g. multiple
    # officers on the same active case) all missed the cache simultaneously
    # and all independently called the LLM instead of one populating it for
    # the rest. Serialized per normalized query below.
    async with get_ner_cache_lock(normalized_query):
        cached = await get_cached_ner(normalized_query)
        if cached:
            return cached

        prompt = build_ner_prompt(normalized_query)

        try:
            raw = await llm_complete(prompt=prompt, system=NER_INTENT_SYSTEM, temperature=0.0, max_tokens=500)
        except Exception as e:
            print(f"[NER Error] LLM call failed: {e}")
            return _fallback_intent()

        try:
            print(f"\\n[DEBUG RAW LLM RESPONSE]: {raw}\\n")
            result = json.loads(raw.strip())
            await set_cached_ner(normalized_query, result)
            return result
        except json.JSONDecodeError:
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                try:
                    result = json.loads(match.group())
                    await set_cached_ner(normalized_query, result)
                    return result
                except json.JSONDecodeError:
                    pass

            return _fallback_intent()

def _fallback_intent() -> dict:
    return {
        "entities": {"persons": [], "locations": [], "fir_ids": [],
                     "dates": [], "ipc_sections": [], "crime_types": []},
        "intent": "lookup", "urgency": "analytical",
        "sub_intents": ["broad_search"], "fallback": True
    }
