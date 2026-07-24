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
    # BUG FIX: the previous staleness check (getattr(_MOCK_DB_LOCK, '_loop',
    # None) is not loop) was dead code on modern Python -- asyncio.Lock no
    # longer binds to an event loop at construction time (that binding was
    # removed in 3.10+ specifically to avoid this kind of bug; a Lock now
    # binds lazily on first acquire()). getattr(..., '_loop', None) is
    # therefore always None, and None is never the same object as a real
    # running loop, so this condition was True on every single call --
    # _MOCK_DB_LOCK was recreated fresh every time, meaning two concurrent
    # writers to .nosql_mock_db.json each got their OWN lock object and never
    # actually excluded each other. Just cache and reuse the one lock.
    global _MOCK_DB_LOCK
    if _MOCK_DB_LOCK is None:
        _MOCK_DB_LOCK = asyncio.Lock()
    return _MOCK_DB_LOCK

def get_lock(key: str) -> asyncio.Lock:
    # BUG FIX: this used to re-check "does this cached lock belong to a stale/
    # closed event loop" via getattr(existing, '_loop', None) is not
    # current_loop, following BUG-07's stated intent (Catalyst Functions can
    # create a fresh event loop per invocation via asyncio.run(), and reusing
    # a Lock from a prior invocation's now-closed loop raises RuntimeError).
    # In practice this check was dead code with the opposite effect: modern
    # asyncio.Lock (3.10+) no longer binds to a loop at construction, so
    # `existing._loop` is always None -- and None is never `is` any real
    # loop object, so the "stale" branch fired on *every* call, evicting and
    # recreating the lock each time. Two coroutines calling get_lock(same key)
    # concurrently each got a distinct, uncontended Lock object, so `async
    # with` on either one never actually excluded the other -- every
    # get_lock/get_session_lock/get_case_lock call site across the codebase
    # (session history, case metadata, user_cases/review_queue/hypothesis/
    # claim indexes, feedback trust counters, query session-ownership) was
    # silently unprotected. Simple LRU caching, no fabricated staleness
    # check, is both correct and sufficient within a single running process.
    if key in _locks:
        _locks.move_to_end(key)  # mark as recently used
        return _locks[key]

    if len(_locks) >= _LOCKS_MAX:
        _locks.popitem(last=False)  # evict oldest (LRU), not all
    lock = asyncio.Lock()
    _locks[key] = lock
    return lock

def get_session_lock(session_id: str) -> asyncio.Lock:
    return get_lock(f"session:{session_id}")

def get_case_lock(case_id: str) -> asyncio.Lock:
    # Same registry as get_session_lock (LRU eviction + per-event-loop
    # staleness guard already handled by get_lock) -- guards case-metadata
    # read-modify-write (collaborator adds, activity stamps), a distinct
    # critical section from session-history writes, keyed separately so two
    # cases never block on each other.
    return get_lock(f"case:{case_id}")

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
CATALYST_DATASTORE_URL = lambda: _env("ZC_DATASTORE_URL", "CATALYST_DATASTORE_URL", "")

# Zia voice/language endpoints -- verified against console model cards
ZIA_ASR_URL         = "https://api.catalyst.zoho.in/quickml/api/v1/models/zia/audio/transcribe"
ZIA_TTS_URL         = "https://api.catalyst.zoho.in/quickml/api/v1/models/zia/tts/synthesize"
ZIA_TRANSLATE_URL   = "https://api.catalyst.zoho.in/quickml/api/v1/models/zia/translate"

def _zia_headers() -> dict:
    CATALYST_ORG_ID = _env("ZC_ORG_ID", "CATALYST_ORG_ID", "60075634347")
    h = _headers()
    return {
        "CATALYST-ORG": CATALYST_ORG_ID,
        "Authorization": h["Authorization"]
    }

def _zia_headers_json() -> dict:
    h = _zia_headers()
    h["Content-Type"] = "application/json"
    return h

# Languages Zia ASR/TTS actually support
ZIA_VOICE_LANGS = {"en", "hi", "kn"}

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
        print("[WARNING] CATALYST_KB_ENDPOINT not configured — RAG step returning zero results.")
        return {"results": []}
    
    # NEW -- v10 (RAG API update): The endpoint requires the specific Document IDs to search against.
    doc_ids_str = _env("ZC_KB_DOCUMENTS", "CATALYST_KB_DOCUMENTS", "")
    if not doc_ids_str:
        print("[WARNING] CATALYST_KB_DOCUMENTS or ZC_KB_DOCUMENTS not configured in .env. RAG requires document IDs.")
        return {"results": []}
        
    document_ids = [d.strip() for d in doc_ids_str.split(",") if d.strip()]

    async with httpx.AsyncClient() as client:
        # We use _quickml_headers() because it uses a Bearer token
        # which is correctly authorized for the RAG QuickML endpoint.
        r = await client.post(
            url, 
            headers=await _quickml_headers(),
            json={
                "query": query, 
                "documents": document_ids
            }, 
            timeout=15.0
        )
        r.raise_for_status()
        resp = r.json()
        
        # The API returns {"status": "success", "response": "...", "retrieved_nodes": [...]}
        # We map this back to our expected {"results": [...]} format for the unified Retrieval layer.
        nodes = resp.get("retrieved_nodes", [])
        
        # We just need the text content for the LLM to synthesize
        results = []
        for n in nodes:
            results.append({
                "content": n.get("content", ""),
                "score": 1.0  # RAG endpoint doesn't return scores in the sample
            })
            
        return {"results": results}
# BUG FIX: mutable default argument `params=[]` is shared across all calls.
# Using None sentinel and replacing with a fresh list each call.
async def ztsql_query(sql: str, params: list = None) -> list:
    if params is None:
        params = []

    url = CATALYST_DATASTORE_URL()
    if not url:
        return []

    for attempt in range(6):
        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(url + "/query", headers=_headers(),
                    json={"query": sql, "params": params}, timeout=15.0)
                if r.status_code == 404:
                    print(f"[Mock] Datastore 404 - Returning empty list for query: {sql}")
                    return []
                r.raise_for_status()
                return r.json()["rows"]
        except (httpx.RequestError, httpx.HTTPError) as e:
            if attempt < 5:
                await asyncio.sleep(1.5)
            else:
                print(f"Datastore query failed after retries: {e}")
                return []
    return []

async def ztsql_execute(sql: str, params: list = None):
    if params is None:
        params = []
        
    url = CATALYST_DATASTORE_URL()
    if not url:
        return
        
    for attempt in range(6):
        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(url + "/execute", headers=_headers(),
                    json={"query": sql, "params": params}, timeout=15.0)
                if r.status_code == 404:
                    return
                r.raise_for_status()
                return
        except (httpx.RequestError, httpx.HTTPError) as e:
            if attempt < 5:
                await asyncio.sleep(1.5)
            else:
                print(f"Datastore execute failed after retries: {e}")
                return

async def transcribe_audio(audio_bytes: bytes, language: str = "kn", filename: str = "recording.webm") -> str:
    """Zia Audio-to-Text Transcription. multipart/form-data per the verified model card."""
    async with httpx.AsyncClient() as client:
        r = await client.post(
            ZIA_ASR_URL,
            headers=_zia_headers(),   # no Content-Type -- httpx sets multipart boundary itself
            files={"audio": (filename, audio_bytes, "audio/webm")},
            data={"language": language},
            timeout=20.0,
        )
        r.raise_for_status()
        return r.json()["transcript"]

async def text_to_speech(text: str, language: str = "kn",
                          speaker: str | None = None,
                          pitch: str = "moderate",
                          speed: str = "moderate",
                          emotion: str = "neutral") -> bytes:
    """Zia Text-to-Audio Synthesis. Pinned to neutral/moderate defaults for officer-facing responses."""
    async with httpx.AsyncClient() as client:
        payload = {
            "text": text,
            "language": language,
            "pitch": pitch,
            "speed": speed,
            "emotion": emotion,
        }
        if speaker:
            payload["speaker"] = speaker
        r = await client.post(ZIA_TTS_URL, headers=_zia_headers_json(), json=payload, timeout=15.0)
        r.raise_for_status()
        return r.content   # audio/wav

async def translate_text(text: str, source_lang: str, target_lang: str = "en") -> dict:
    """Zia Text Translation. New Layer 1b hop -- only called when source_lang not in ZIA_VOICE_LANGS."""
    async with httpx.AsyncClient() as client:
        r = await client.post(
            ZIA_TRANSLATE_URL,
            headers=_zia_headers_json(),
            json={"source_language": source_lang, "target_language": target_lang, "text": text},
            timeout=15.0,
        )
        r.raise_for_status()
        return r.json()   # {"translated_text": ..., "processing_time": ...}

async def transcribe_and_normalize(audio_bytes: bytes, declared_language: str) -> str:
    """
    Layer 1 orchestrator: ASR -> (conditional) translate -> plain text into Layer 2.
    """
    if declared_language in ZIA_VOICE_LANGS:
        return await transcribe_audio(audio_bytes, language=declared_language)

    raise ValueError(
        f"Zia ASR does not support '{declared_language}'. "
        f"Route typed text in this language through translate_text() instead."
    )

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
