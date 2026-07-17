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
            # BUG-03 FIX: normalize entities for deterministic city detection
            result = _normalize_entities(result)
            await set_cached_ner(normalized_query, result)
            return result
        except json.JSONDecodeError:
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                try:
                    result = json.loads(match.group())
                    result = _normalize_entities(result)
                    await set_cached_ner(normalized_query, result)
                    return result
                except json.JSONDecodeError:
                    pass

            return _fallback_intent()


# BUG-03 FIX: Known KSP districts (Karnataka). The LLM is non-deterministic
# about whether it places a district in 'city' or in 'locations'. This set
# is used to promote any location that matches a known district into 'city'
# so that Cypher district-level filtering always fires reliably.
_KSP_DISTRICTS = {
    "bengaluru", "mysuru", "mangaluru", "hubballi", "belagavi",
    "dharwad", "davangere", "ballari", "shivamogga", "tumakuru",
    "kalaburagi", "bidar", "raichur", "koppal", "gadag",
    "uttara kannada", "haveri", "bagalkot", "vijayapura",
    "chitradurga", "chikkamagaluru", "hassan", "mandya", "chamarajanagar",
    "kodagu", "udupi", "dakshina kannada", "yadgir", "ramanagara",
    "chikkaballapura", "kolar", "bengaluru rural",
    # Common alternate spellings / anglicised forms
    "bangalore", "mysore", "mangalore", "hubli", "hubli-dharwad",
    "belgaum", "bijapur", "gulbarga", "bellary",
}

def _normalize_entities(result: dict) -> dict:
    """
    Post-parse normalization pass over NER output:
    1. Promote any 'location' that matches a known KSP district into 'city'
       when 'city' is absent or empty, so Cypher district filtering is reliable.
    2. Ensure all required entity fields always exist to prevent KeyError downstream.
    """
    entities = result.get("entities", {})

    # Ensure required list keys always exist
    for key in ("persons", "locations", "fir_ids", "dates", "ipc_sections", "crime_types"):
        if key not in entities:
            entities[key] = []
    entities.setdefault("city", "")
    entities.setdefault("weapon", "")

    # Promote district from locations -> city if city not already set
    if not entities.get("city"):
        for loc in entities.get("locations", []):
            if loc.strip().lower() in _KSP_DISTRICTS:
                entities["city"] = loc
                print(f"[NER Normalize] Promoted '{loc}' from locations -> city")
                break

    result["entities"] = entities
    return result


def _fallback_intent() -> dict:
    return {
        "entities": {
            "persons": [], "locations": [], "city": "", "weapon": "",
            "fir_ids": [], "dates": [], "ipc_sections": [], "crime_types": []
        },
        "intent": "lookup", "urgency": "analytical",
        "sub_intents": ["broad_search"], "fallback": True
    }
