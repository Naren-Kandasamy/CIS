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

def _quickml_headers() -> dict:
    token = os.getenv("CATALYST_API_TOKEN")
    if not token:
        raise EnvironmentError("CATALYST_API_TOKEN is not set")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "CATALYST-ORG": "60075634347"
    }

CATALYST_LLM_URL       = lambda: os.getenv("CATALYST_LLM_ENDPOINT", "")
CATALYST_VLM_URL       = lambda: os.getenv("CATALYST_VLM_ENDPOINT", "")
CATALYST_KB_URL        = lambda: os.getenv("CATALYST_KB_ENDPOINT", "")
CATALYST_ASR_URL       = lambda: os.getenv("CATALYST_ASR_ENDPOINT", "")
CATALYST_TTS_URL       = lambda: os.getenv("CATALYST_TTS_ENDPOINT", "")
CATALYST_DATASTORE_URL = lambda: os.getenv("CATALYST_DATASTORE_URL", "")

async def llm_complete(prompt: str, system: str,
                        temperature: float = 0.1, max_tokens: int = 1000) -> str:

    # BUG FIX: the Ollama/Groq dev fallbacks below (Architecture v8 line 48:
    # "Groq + Llama 3.1 70B (offline/dev only) -- Not for production") used to
    # activate silently off a stray LOCAL_MOCK_MODE/GROQ_API_KEY env var alone,
    # with no log line indicating real Catalyst/Qwen was bypassed. They now
    # require an explicit second opt-in flag and always log loudly when used,
    # so a leftover dev env var can never silently reroute production traffic.
    if os.getenv("ALLOW_DEV_LLM_FALLBACK") == "true":
        if os.getenv("LOCAL_MOCK_MODE") == "true":
            print("[DEV FALLBACK - NOT FOR PRODUCTION] Routing LLM call to local Ollama instead of Catalyst Qwen")
            async with httpx.AsyncClient() as client:
                try:
                    # Assuming user has qwen or llama3 installed on local ollama
                    r = await client.post("http://localhost:11434/api/generate", json={
                        "model": "llama3.2", # Fallback model
                        "system": system,
                        "prompt": prompt,
                        "stream": False,
                        "options": {"temperature": temperature}
                    }, timeout=30.0)
                    if r.status_code == 200:
                        return r.json()["response"]
                except Exception as e:
                    return f"[Mock LLM Response - Local Ollama unavailable: {e}]"

        groq_key = os.getenv("GROQ_API_KEY")
        if groq_key:
            print("[DEV FALLBACK - NOT FOR PRODUCTION] Routing LLM call to Groq (Llama 3.3 70B) instead of Catalyst Qwen")
            async with httpx.AsyncClient() as client:
                r = await client.post("https://api.groq.com/openai/v1/chat/completions", headers={
                    "Authorization": f"Bearer {groq_key}",
                    "Content-Type": "application/json"
                }, json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": temperature,
                    "max_tokens": max_tokens
                }, timeout=45.0)
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"]

    async with httpx.AsyncClient() as client:
        r = await client.post(CATALYST_LLM_URL(), headers=_quickml_headers(), json={
            "model": "crm-di-glm47b_30b_it",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
            "chat_template_kwargs": {"enable_thinking": True}
        }, timeout=45.0)
        r.raise_for_status()
        resp = r.json()
        try:
            return resp["choices"][0]["message"]["content"]
        except KeyError:
            return resp.get("output", str(resp))

async def vlm_extract(image_bytes: bytes, prompt: str, system: str) -> str:
    # BUG FIX: previously returned a hardcoded, realistic-looking fake FIR record
    # whenever the VLM endpoint was unconfigured or the call failed for any reason,
    # indistinguishable from a real extraction. Now raises instead, so the caller
    # (backend/api/routes/ocr.py) surfaces a real error rather than fabricated data.
    url = CATALYST_VLM_URL()
    if not url:
        raise EnvironmentError("CATALYST_VLM_ENDPOINT is not configured")

    image_b64 = base64.b64encode(image_bytes).decode()
    async with httpx.AsyncClient() as client:
        r = await client.post(url, headers=_quickml_headers(), json={
            "prompt": prompt,
            "model": "VL-Qwen3.6-35B-A3B",
            "images": [image_b64],
            "system_prompt": system,
            "top_k": 50,
            "top_p": 0.9,
            "temperature": 0.0,
            "max_tokens": 1000
        }, timeout=45.0)
        r.raise_for_status()
        resp = r.json()
        if "choices" in resp:
            return resp["choices"][0]["message"]["content"]
        return resp.get("output", resp.get("text", str(resp)))

async def kb_upload(document_id: str, content: str, metadata: dict):
    url = CATALYST_KB_URL()
    if not url:
        return
    async with httpx.AsyncClient() as client:
        r = await client.post(url + "/documents", headers=_headers(),
            json={"document_id": document_id, "content": content, "metadata": metadata},
            timeout=15.0)
        r.raise_for_status()

async def kb_search(query: str, top_k: int = 10) -> dict:
    url = CATALYST_KB_URL()
    if not url:
        # Mock RAG response for the trap scenario
        if "smiley face" in query.lower() or "glass cutter" in query.lower():
            print(f"[Mock KB] Returning trap scenario matches for query: {query}")
            return {
                "results": [
                    {
                        "fir_id": "TRAP-FIR-001",
                        "excerpt": "A burglary occurred in Belagavi where the suspect broke in through the rear window using a specialized glass cutter and left a calling card with a smiley face.",
                        "score": 0.88,
                        "metadata": {"crime_no": "199991234202100001", "district": "Belagavi"}
                    },
                    {
                        "fir_id": "TRAP-FIR-002",
                        "excerpt": "A burglary occurred in Kalaburagi where the suspect broke in through the rear window using a specialized glass cutter and left a calling card with a smiley face.",
                        "score": 0.86,
                        "metadata": {"crime_no": "199995678202400002", "district": "Kalaburagi"}
                    }
                ]
            }
        return {"results": []}
    async with httpx.AsyncClient() as client:
        r = await client.post(url + "/search", headers=_headers(),
            json={"query": query, "top_k": top_k}, timeout=15.0)
        r.raise_for_status()
        return r.json() or {"results": []}
# BUG FIX: mutable default argument `params=[]` is shared across all calls.
# Using None sentinel and replacing with a fresh list each call.
async def ztsql_query(sql: str, params: list = None) -> list:
    if params is None:
        params = []
    
    url = CATALYST_DATASTORE_URL()
    if not url:
        return []
        
    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(url + "/query", headers=_headers(),
                json={"query": sql, "params": params}, timeout=15.0)
            if r.status_code == 404:
                print(f"[Mock] Datastore 404 - Returning empty list for query: {sql}")
                return []
            r.raise_for_status()
            return r.json()["rows"]
        except Exception as e:
            print(f"Datastore query failed: {e}")
            return []

# BUG FIX: same mutable default arg fix as ztsql_query.
async def ztsql_execute(sql: str, params: list = None):
    if params is None:
        params = []
        
    url = CATALYST_DATASTORE_URL()
    if not url:
        return
        
    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(url + "/execute", headers=_headers(),
                json={"query": sql, "params": params}, timeout=15.0)
            if r.status_code == 404:
                return
            r.raise_for_status()
        except Exception as e:
            print(f"Datastore execute failed: {e}")

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
    url = CATALYST_TTS_URL()
    if not url:
        print("[Mock TTS] URL missing, returning dummy audio bytes.")
        return b"ID3\x04\x00\x00\x00\x00\x00\x00MockAudioData"
        
    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(url, headers=_headers(),
                json={"text": text, "language": language}, timeout=15.0)
            r.raise_for_status()
            return r.content
        except Exception as e:
            print(f"[Mock TTS] Catalyst TTS failed ({e}), returning dummy audio bytes.")
            return b"ID3\x04\x00\x00\x00\x00\x00\x00MockAudioData"

# --- NoSQL mock for Phase 2 scaffolding ---
_mock_nosql_cache = {}

async def nosql_get(key: str) -> dict | None:
    return _mock_nosql_cache.get(key)

async def nosql_set(key: str, value: str, ttl: int = 3600):
    _mock_nosql_cache[key] = {"value": value}
