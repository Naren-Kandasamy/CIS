import httpx
import os
import base64
import time
import asyncio
from collections import OrderedDict

# BUG FIX: general-purpose keyed lock registry, used both to guard the
# session-history read-modify-write race (two concurrent queries in the same
# session both read the same history snapshot, then the one that finishes
# last silently overwrites the other's contribution) and the NER cache
# stampede (concurrent identical queries all miss cache and all hit the LLM).
# Only serializes requests landing in the same process/warm container (a full
# cross-process guarantee would need a database-level conditional write on
# the NoSQL item, which the Catalyst REST API's condition syntax for this SDK
# version did not accept in testing). Bounded so a long-running warm container
# with many distinct sessions/queries doesn't grow this unboundedly.
# BUG-06 FIX: switched from plain dict + bulk clear() to OrderedDict with LRU
# eviction. The old bulk clear() had a narrow race: if a coroutine held a lock
# from _locks and the dict hit _LOCKS_MAX, a concurrent call would clear ALL
# entries (including the held lock), allowing another coroutine to create a
# fresh uncontested lock for the same key and enter the critical section
# simultaneously. LRU eviction only removes the OLDEST unused entry.
_locks: OrderedDict = OrderedDict()
_LOCKS_MAX = 2000
# BUG-04 FIX: file-level lock for local mock NoSQL to prevent concurrent
# asyncio tasks from doing read-modify-write races on .nosql_mock_db.json
_MOCK_DB_LOCK: asyncio.Lock | None = None

def _get_mock_db_lock() -> asyncio.Lock:
    global _MOCK_DB_LOCK
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        return asyncio.Lock()
    if _MOCK_DB_LOCK is None or getattr(_MOCK_DB_LOCK, '_loop', None) is not loop:
        _MOCK_DB_LOCK = asyncio.Lock()
    return _MOCK_DB_LOCK

def get_lock(key: str) -> asyncio.Lock:
    # BUG-07 FIX: Catalyst Functions create a new event loop per invocation via
    # asyncio.run(). A Lock cached here from a prior invocation belongs to the
    # old (closed) event loop. Using it raises:
    #   RuntimeError: This lock is created for a different event loop
    # which silently crashes the pipeline. Mirror the same guard already used
    # by _get_mock_db_lock().
    try:
        current_loop = asyncio.get_event_loop()
    except RuntimeError:
        current_loop = None

    if key in _locks:
        existing = _locks[key]
        if current_loop and getattr(existing, '_loop', None) is not current_loop:
            # Stale lock from a dead event loop — evict and recreate.
            del _locks[key]
        else:
            _locks.move_to_end(key)  # mark as recently used
            return existing

    if len(_locks) >= _LOCKS_MAX:
        _locks.popitem(last=False)  # evict oldest (LRU), not all
    lock = asyncio.Lock()
    _locks[key] = lock
    return lock

def get_session_lock(session_id: str) -> asyncio.Lock:
    return get_lock(f"session:{session_id}")

# BUG FIX: env vars must be read lazily (via helper) rather than at module-import
# time, because Catalyst Functions inject env vars *after* module load.
# A module-level HEADERS dict captured os.getenv() before the env was populated,
# producing Authorization: Zoho-oauthtoken None on every call.
# BUG FIX: Catalyst's AppSail rejects any deployed env var whose key contains
# the substring "CATALYST" ("environment_variables must not contain reserved
# keywords"), so deployed env vars are set under a ZC_ prefix instead. Local
# .env keeps the original CATALYST_ names for readability; _env() checks both.
def _env(zc_name: str, catalyst_name: str, default: str = None) -> str:
    return os.getenv(zc_name) or os.getenv(catalyst_name, default)

def _headers() -> dict:
    token = _env("ZC_API_TOKEN", "CATALYST_API_TOKEN")
    if not token:
        raise EnvironmentError("CATALYST_API_TOKEN is not set")
    return {
        "Authorization": f"Zoho-oauthtoken {token}",
        "Content-Type": "application/json",
    }

async def _quickml_headers() -> dict:
    token = await _get_nosql_access_token()
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "CATALYST-ORG": "60075634347"
    }

CATALYST_LLM_URL       = lambda: _env("ZC_LLM_ENDPOINT", "CATALYST_LLM_ENDPOINT", "")
CATALYST_VLM_URL       = lambda: _env("ZC_VLM_ENDPOINT", "CATALYST_VLM_ENDPOINT", "")
CATALYST_KB_URL        = lambda: _env("ZC_KB_ENDPOINT", "CATALYST_KB_ENDPOINT", "")
CATALYST_ASR_URL       = lambda: _env("ZC_ASR_ENDPOINT", "CATALYST_ASR_ENDPOINT", "")
CATALYST_TTS_URL       = lambda: _env("ZC_TTS_ENDPOINT", "CATALYST_TTS_ENDPOINT", "")
CATALYST_DATASTORE_URL = lambda: _env("ZC_DATASTORE_URL", "CATALYST_DATASTORE_URL", "")

async def llm_complete(prompt: str, system: str,
                        temperature: float = 0.1, max_tokens: int = 1000) -> str:



    async with httpx.AsyncClient() as client:
        r = await client.post(CATALYST_LLM_URL(), headers=await _quickml_headers(), json={
            "model": "crm-di-glm47b_30b_it",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
            "chat_template_kwargs": {"enable_thinking": False}
        }, timeout=45.0)
        r.raise_for_status()
        resp = r.json()
        if "choices" in resp:
            return resp["choices"][0]["message"]["content"]
        elif "response" in resp:
            return resp["response"]
        else:
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
        r = await client.post(url, headers=await _quickml_headers(), json={
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
        print("[WARNING] ZC_KB_ENDPOINT not configured — RAG step returning zero results. "
              "Set ZC_KB_ENDPOINT in your AppSail/Function environment.")
        return {"results": []}
    async with httpx.AsyncClient() as client:
        r = await client.post(url + "/search", headers=_headers(),
            json={"query": query, "top_k": top_k}, timeout=15.0)
        r.raise_for_status()
        return r.json() or {"results": []}
# BUG FIX: mutable default argument `params=[]` is shared across all calls.
# Using None sentinel and replacing with a fresh list each call.
async def ztsql_query(sql: str, params: list = None) -> list:
    # BUG FIX: this used to catch every exception (network errors, auth
    # failures, malformed SQL) and silently return [] -- indistinguishable
    # from "the query legitimately found nothing." That meant a genuinely
    # broken SQL retrieval step could never be told apart from "no matches"
    # anywhere downstream (confidence_caveats, reasoning_trace, or callers
    # like entity_lookup_resolver.py's cache loader). Only the "datastore not
    # configured" case degrades silently now; real request failures raise, so
    # execute_with_timeout's except-Exception handler (executor.py) can
    # correctly mark the source as unavailable instead of "empty."
    if params is None:
        params = []

    url = CATALYST_DATASTORE_URL()
    if not url:
        return []

    async with httpx.AsyncClient() as client:
        r = await client.post(url + "/query", headers=_headers(),
            json={"query": sql, "params": params}, timeout=15.0)
        if r.status_code == 404:
            print(f"[Mock] Datastore 404 - Returning empty list for query: {sql}")
            return []
        r.raise_for_status()
        return r.json()["rows"]

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

# --- Real Catalyst NoSQL persistence ---
# BUG FIX: this used to be a plain in-memory dict (_mock_nosql_cache), never
# wired to any real Catalyst NoSQL table -- job status and session history
# writes from a separate deployed process (pipeline Function) could never be
# seen by the backend AppSail process reading them, since each holds its own
# empty dict. Now talks to a real "AppKeyValueStore" NoSQL table (partition
# key: item_key, TTL attribute: expires_at) via the Catalyst BaaS REST API.
CATALYST_NOSQL_TABLE = "AppKeyValueStore"
_nosql_token_cache = {"access_token": None, "expires_at": 0.0}

def _nosql_base_url() -> str:
    project_id = _env("ZC_PROJECT_ID", "CATALYST_PROJECT_ID")
    if not project_id:
        raise EnvironmentError("CATALYST_PROJECT_ID is not set")
    return f"https://api.catalyst.zoho.in/baas/v1/project/{project_id}/nosqltable/{CATALYST_NOSQL_TABLE}"

async def _get_nosql_access_token() -> str:
    """
    Returns a cached, valid OAuth access token for NoSQL calls, refreshing via
    CATALYST_REFRESH_TOKEN (+ CATALYST_CLIENT_ID/CATALYST_CLIENT_SECRET) a
    minute before expiry -- Catalyst access tokens are only valid ~1 hour.
    Falls back to a static CATALYST_ACCESS_TOKEN/CATALYST_API_TOKEN if no
    refresh credentials are configured (that static token will itself expire
    hourly with no way to renew it).
    """
    now = time.time()
    if _nosql_token_cache["access_token"] and now < _nosql_token_cache["expires_at"]:
        return _nosql_token_cache["access_token"]

    refresh_token = _env("ZC_REFRESH_TOKEN", "CATALYST_REFRESH_TOKEN")
    client_id = _env("ZC_CLIENT_ID", "CATALYST_CLIENT_ID")
    client_secret = _env("ZC_CLIENT_SECRET", "CATALYST_CLIENT_SECRET")
    if refresh_token and client_id and client_secret:
        async with httpx.AsyncClient() as client:
            r = await client.post("https://accounts.zoho.in/oauth/v2/token", params={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
            }, timeout=15.0)
            r.raise_for_status()
            data = r.json()
            _nosql_token_cache["access_token"] = data["access_token"]
            _nosql_token_cache["expires_at"] = now + data.get("expires_in", 3600) - 60
            return _nosql_token_cache["access_token"]

    token = _env("ZC_ACCESS_TOKEN", "CATALYST_ACCESS_TOKEN") or _env("ZC_API_TOKEN", "CATALYST_API_TOKEN")
    if not token:
        raise EnvironmentError(
            "No Catalyst NoSQL credentials configured -- set CATALYST_REFRESH_TOKEN, "
            "CATALYST_CLIENT_ID and CATALYST_CLIENT_SECRET (preferred, auto-refreshes), "
            "or at minimum CATALYST_ACCESS_TOKEN"
        )
    return token

async def _nosql_headers() -> dict:
    token = await _get_nosql_access_token()
    return {"Authorization": f"Zoho-oauthtoken {token}", "Content-Type": "application/json"}

async def _nosql_request(method: str, path: str, json_body) -> dict:
    # BUG FIX: 4 attempts / 1s apart proved too thin against real observed
    # connection flakiness to this host during testing -- bumped for
    # resilience, still well inside the 120s SSE poll budget in the worst case.
    import asyncio
    headers = await _nosql_headers()
    url = _nosql_base_url() + path
    last_error = None
    max_attempts = 6
    for attempt in range(max_attempts):
        try:
            async with httpx.AsyncClient() as client:
                r = await client.request(method, url, headers=headers, json=json_body, timeout=15.0)
                r.raise_for_status()
                return r.json()
        except httpx.RequestError as e:
            last_error = e
            if attempt < max_attempts - 1:
                await asyncio.sleep(1.5)
                continue
    raise last_error

async def nosql_get(key: str) -> dict | None:
    """Fetch a value from the real Catalyst NoSQL AppKeyValueStore table with local fallback."""
    project_id = _env("ZC_PROJECT_ID", "CATALYST_PROJECT_ID")
    token = _env("ZC_ACCESS_TOKEN", "CATALYST_ACCESS_TOKEN") or _env("ZC_API_TOKEN", "CATALYST_API_TOKEN")
    refresh_token = _env("ZC_REFRESH_TOKEN", "CATALYST_REFRESH_TOKEN")
    
    if _env("MOCK_NOSQL_ONLY", "") == "true" or not project_id or not (token or refresh_token):
        import json
        import os
        db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.nosql_mock_db.json"))
        if not os.path.exists(db_path):
            return None
        try:
            async with _get_mock_db_lock():
                with open(db_path, "r") as f:
                    data = json.load(f)
            val = data.get(key)
            return {"value": val} if val is not None else None
        except Exception:
            return None

    resp = await _nosql_request("POST", "/item/fetch", {"keys": [{"item_key": {"S": key}}]})
    items = resp.get("data", {}).get("get") or []
    if not items:
        return None
    return {"value": items[0]["item"]["item_value"]["S"]}

async def nosql_set(key: str, value: str, ttl: int = None):
    """
    Upsert a value into the real Catalyst NoSQL AppKeyValueStore table with local fallback.
    """
    project_id = _env("ZC_PROJECT_ID", "CATALYST_PROJECT_ID")
    token = _env("ZC_ACCESS_TOKEN", "CATALYST_ACCESS_TOKEN") or _env("ZC_API_TOKEN", "CATALYST_API_TOKEN")
    refresh_token = _env("ZC_REFRESH_TOKEN", "CATALYST_REFRESH_TOKEN")
    
    if _env("MOCK_NOSQL_ONLY", "") == "true" or not project_id or not (token or refresh_token):
        import json
        import os
        db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.nosql_mock_db.json"))
        async with _get_mock_db_lock():
            data = {}
            if os.path.exists(db_path):
                try:
                    with open(db_path, "r") as f:
                        data = json.load(f)
                except Exception:
                    pass
            data[key] = value
            try:
                with open(db_path, "w") as f:
                    json.dump(data, f, indent=2)
            except Exception as e:
                print(f"Failed to write to local mock NoSQL DB: {e}")
        return

    item = {"item_key": {"S": key}, "item_value": {"S": value}}
    if ttl:
        item["expires_at"] = {"N": str(int(time.time()) + ttl)}
    await _nosql_request("POST", "/item", [{"item": item, "return": "NULL"}])
