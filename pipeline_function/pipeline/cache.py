import hashlib, json
from shared.catalyst_client import nosql_get, nosql_set

CACHE_TTL_SECONDS = 3600  # 1 hour

def cache_key(query: str, cache_type: str) -> str:
    normalized = query.strip().lower()
    hash_digest = hashlib.sha256(normalized.encode()).hexdigest()[:16]
    return f"cache:{cache_type}:{hash_digest}"

async def get_cached_ner(query: str) -> dict | None:
    cached = await nosql_get(cache_key(query, "ner_intent"))
    return json.loads(cached["value"]) if cached else None

async def set_cached_ner(query: str, result: dict):
    await nosql_set(cache_key(query, "ner_intent"), json.dumps(result), ttl=CACHE_TTL_SECONDS)
