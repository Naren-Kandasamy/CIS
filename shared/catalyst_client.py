import httpx
import os
import base64

# BUG FIX: env vars must be read lazily (via helper) rather than at module-import
# time, because Catalyst Functions inject env vars *after* module load.
# A module-level HEADERS dict captured os.getenv() before the env was populated,
# producing Authorization: Zoho-oauthtoken None on every call.
def _headers() -> dict:
    token = os.getenv("CATALYST_API_TOKEN")
    if not token:
        raise EnvironmentError("CATALYST_API_TOKEN is not set")
    return {
        "Authorization": f"Zoho-oauthtoken {token}",
        "Content-Type": "application/json",
    }

CATALYST_LLM_URL       = lambda: os.getenv("CATALYST_LLM_ENDPOINT", "")
CATALYST_VLM_URL       = lambda: os.getenv("CATALYST_VLM_ENDPOINT", "")
CATALYST_KB_URL        = lambda: os.getenv("CATALYST_KB_ENDPOINT", "")
CATALYST_ASR_URL       = lambda: os.getenv("CATALYST_ASR_ENDPOINT", "")
CATALYST_TTS_URL       = lambda: os.getenv("CATALYST_TTS_ENDPOINT", "")
CATALYST_DATASTORE_URL = lambda: os.getenv("CATALYST_DATASTORE_URL", "")

async def llm_complete(prompt: str, system: str,
                        temperature: float = 0.1, max_tokens: int = 1000) -> str:
    async with httpx.AsyncClient() as client:
        r = await client.post(CATALYST_LLM_URL(), headers=_headers(), json={
            "model": "qwen-14b-instruct", "system": system,
            "prompt": prompt, "temperature": temperature, "max_tokens": max_tokens
        }, timeout=30.0)
        r.raise_for_status()
        return r.json()["output"]

async def vlm_extract(image_bytes: bytes, prompt: str, system: str) -> str:
    image_b64 = base64.b64encode(image_bytes).decode()
    async with httpx.AsyncClient() as client:
        r = await client.post(CATALYST_VLM_URL(), headers=_headers(), json={
            "model": "qwen-7b-vlm", "system": system, "image": image_b64,
            "prompt": prompt, "temperature": 0.0, "max_tokens": 1000
        }, timeout=45.0)
        r.raise_for_status()
        return r.json()["output"]

async def kb_upload(document_id: str, content: str, metadata: dict):
    async with httpx.AsyncClient() as client:
        r = await client.post(CATALYST_KB_URL() + "/documents", headers=_headers(),
            json={"document_id": document_id, "content": content, "metadata": metadata},
            timeout=15.0)
        r.raise_for_status()

async def kb_search(query: str, top_k: int = 10) -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.post(CATALYST_KB_URL() + "/search", headers=_headers(),
            json={"query": query, "top_k": top_k}, timeout=15.0)
        r.raise_for_status()
        return r.json() or {"results": []}

# BUG FIX: mutable default argument `params=[]` is shared across all calls.
# Using None sentinel and replacing with a fresh list each call.
async def ztsql_query(sql: str, params: list = None) -> list:
    if params is None:
        params = []
    async with httpx.AsyncClient() as client:
        r = await client.post(CATALYST_DATASTORE_URL() + "/query", headers=_headers(),
            json={"query": sql, "params": params}, timeout=15.0)
        r.raise_for_status()
        return r.json()["rows"]

# BUG FIX: same mutable default arg fix as ztsql_query.
async def ztsql_execute(sql: str, params: list = None):
    if params is None:
        params = []
    async with httpx.AsyncClient() as client:
        r = await client.post(CATALYST_DATASTORE_URL() + "/execute", headers=_headers(),
            json={"query": sql, "params": params}, timeout=15.0)
        r.raise_for_status()

async def transcribe_audio(audio_bytes: bytes, language: str = "kn") -> str:
    # BUG FIX: token must be read lazily, same reason as _headers().
    auth_headers = {"Authorization": _headers()["Authorization"]}
    async with httpx.AsyncClient() as client:
        r = await client.post(CATALYST_ASR_URL(),
            headers=auth_headers,
            files={"audio": ("recording.webm", audio_bytes, "audio/webm")},
            data={"language": language}, timeout=20.0)
        r.raise_for_status()
        return r.json()["transcript"]

async def text_to_speech(text: str, language: str = "kn") -> bytes:
    async with httpx.AsyncClient() as client:
        r = await client.post(CATALYST_TTS_URL(), headers=_headers(),
            json={"text": text, "language": language}, timeout=15.0)
        r.raise_for_status()
        return r.content

# --- NoSQL mock for Phase 2 scaffolding ---
_mock_nosql_cache = {}

async def nosql_get(key: str) -> dict | None:
    return _mock_nosql_cache.get(key)

async def nosql_set(key: str, value: str, ttl: int = 3600):
    _mock_nosql_cache[key] = {"value": value}
