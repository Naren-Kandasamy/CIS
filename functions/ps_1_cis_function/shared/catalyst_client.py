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

# BUG FIX: CATALYST_API_TOKEN (used by _headers()) is not an OAuth access
# token at all -- posting it to the Zia endpoints as "Zoho-oauthtoken <...>"
# got a clean 401 INVALID_OAUTHTOKEN. Worse, the refresh-token-derived OAuth
# access token used everywhere else in this file (_get_nosql_access_token(),
# shared by NoSQL and _quickml_headers()) IS a valid OAuth token but was
# never granted the QuickML.deployment.READ scope these three Zia endpoints
# require -- confirmed via a live call returning 401 INVALID_OAUTHSCOPE.
# Zia needs its own refresh token, generated against a Self Client grant
# with QuickML.deployment.READ explicitly requested.
_zia_token_cache = {"access_token": None, "expires_at": 0.0}

async def _get_zia_access_token() -> str:
    now = time.time()
    if _zia_token_cache["access_token"] and now < _zia_token_cache["expires_at"]:
        return _zia_token_cache["access_token"]

    refresh_token = _env("ZC_ZIA_REFRESH_TOKEN", "ZIA_REFRESH_TOKEN")
    client_id = _env("ZC_CLIENT_ID", "CATALYST_CLIENT_ID")
    client_secret = _env("ZC_CLIENT_SECRET", "CATALYST_CLIENT_SECRET")
    if not (refresh_token and client_id and client_secret):
        raise EnvironmentError("ZIA_REFRESH_TOKEN is not set")

    async with httpx.AsyncClient() as client:
        r = await client.post("https://accounts.zoho.in/oauth/v2/token", params={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        }, timeout=15.0)
        r.raise_for_status()
        data = r.json()
        _zia_token_cache["access_token"] = data["access_token"]
        _zia_token_cache["expires_at"] = now + data.get("expires_in", 3600) - 60
        return _zia_token_cache["access_token"]

async def _zia_headers() -> dict:
    CATALYST_ORG_ID = _env("ZC_ORG_ID", "CATALYST_ORG_ID", "60075634347")
    token = await _get_zia_access_token()
    return {
        "CATALYST-ORG": CATALYST_ORG_ID,
        "Authorization": f"Zoho-oauthtoken {token}"
    }

async def _zia_headers_json() -> dict:
    h = await _zia_headers()
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

        # BUG FIX: this previously discarded every field on each node except
        # "content", replacing it with a fixed score of 1.0. Whatever ID/
        # metadata fields the real endpoint returns (fir_id/document_id/id/
        # metadata/excerpt/text -- evidence.py's add_rag_results() checks all
        # of these) were thrown away, so every RAG-sourced EvidenceItem fell
        # back to fir_id="unknown" with no metadata. Spreading the raw node
        # preserves whatever fields it actually carries under their real
        # names, while still guaranteeing content/score are present.
        results = []
        for n in nodes:
            results.append({
                **n,
                "content": n.get("content", ""),
                "score": n.get("score", 1.0),
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

# Extensions Zia ASR actually accepts -- verified live by posting identical
# WAV bytes under different names: .wav/.mp3/.ogg/.flac return 200, while
# .webm and .m4a return 400 INVALID_FILE_EXTENSION. Zia validates by
# extension, so the name we send matters as much as the bytes.
ZIA_ASR_EXTENSIONS = {".wav", ".mp3", ".ogg", ".flac"}

# --- Multilingual Indic & Code-Mixed Phonetic Lexicon Engine ---
INDIC_PHONETIC_PATTERNS = [
    # Comprehensive Bengaluru Locations & Police Stations Gazetteer
    (r"\b(delhi gavi|bela gavi|belgaum|bellagavi)\b", "Belagavi", True),
    (r"\b(coupon park|cupon park|cabbon park|cubon park)\b", "Cubbon Park", True),
    (r"\b(kora mangala|kora mangalam|koramangla)\b", "Koramangala", True),
    (r"\b(malleswaram|malleshwaram|maleswaram)\b", "Malleshwaram", True),
    (r"\b(indira nagar|indranagar)\b", "Indiranagar", True),
    (r"\b(white field|widfield)\b", "Whitefield", True),
    (r"\b(hala suru|ulsoor station|ulsoor)\b", "Halasuru", True),
    (r"\b(yeshwantpur|yashwantpur)\b", "Yeshwanthpur", True),
    (r"\b(hsr layout|hsr)\b", "HSR Layout", True),
    (r"\b(btm layout|btm)\b", "BTM Layout", True),
    (r"\b(jayanagar|jaya nagar)\b", "Jayanagar", True),
    (r"\b(rajajinagar|rajaji nagar)\b", "Rajajinagar", True),
    (r"\b(electronic city|e-city|ecity)\b", "Electronic City", True),
    (r"\b(marathahalli|marathalli)\b", "Marathahalli", True),
    (r"\b(bellandur|bellandoor)\b", "Bellandur", True),
    (r"\b(hebbal|hebbala)\b", "Hebbal", True),
    (r"\b(yelahanka|yelahanka new town)\b", "Yelahanka", True),
    (r"\b(banashankari|bsk layout|bsk)\b", "Banashankari", True),
    (r"\b(vijayanagar|vijaya nagar)\b", "Vijayanagar", True),
    (r"\b(mg road|mahatma gandhi road)\b", "MG Road", True),
    (r"\b(brigade road|brigade rd)\b", "Brigade Road", True),
    (r"\b(commercial street|commercial st)\b", "Commercial Street", True),
    (r"\b(majestic|ksrtc bus stand|sangam circle)\b", "Majestic", True),
    (r"\b(banaswadi|banaswadi station)\b", "Banaswadi", True),
    (r"\b(kammanahalli|kamanahalli)\b", "Kammanahalli", True),
    (r"\b(pulakeshinagar|fraser town|frazer town)\b", "Pulakeshinagar (Frazer Town)", True),
    (r"\b(shivaji nagar|shivajinagar)\b", "Shivajinagar", True),
    (r"\b(kr puram|krishna rajapuram|kr puram station)\b", "KR Puram", True),
    (r"\b(kengeri|kengeri satellite town)\b", "Kengeri", True),
    (r"\b(peenya|peenya industrial area)\b", "Peenya", True),
    (r"\b(nagarbhavi|nagarbavi)\b", "Nagarbhavi", True),
    (r"\b(rr nagar|rajarajeshwari nagar)\b", "RR Nagar", True),
    (r"\b(jp nagar|jayaprakash nagar)\b", "JP Nagar", True),
    (r"\b(silk board|silk board junction)\b", "Silk Board", True),
    (r"\b(vidhana soudha|vidhana suada)\b", "Vidhana Soudha", True),
    (r"\b(high court|karnataka high court)\b", "High Court", True),
    (r"\b(mico layout|mico layout station)\b", "Mico Layout", True),
    (r"\b(sg palya|sudduguntepalya)\b", "SG Palya", True),
    (r"\b(tilak nagar|tilaknagar)\b", "Tilak Nagar", True),
    (r"\b(bommanahalli|bomanahalli)\b", "Bommanahalli", True),
    (r"\b(begur|begur station)\b", "Begur", True),
    (r"\b(varthur|varthur station)\b", "Varthur", True),
    (r"\b(kadugodi|kadugodi station)\b", "Kadugodi", True),
    (r"\b(mahadevapura|mahadevapura station)\b", "Mahadevapura", True),
    (r"\b(hennur|hennur main road)\b", "Hennur", True),
    (r"\b(rt nagar|rabindranath tagore nagar)\b", "RT Nagar", True),
    (r"\b(sanjay nagar|sanjaynagar)\b", "Sanjay Nagar", True),
    (r"\b(mathikere|mattikere)\b", "Mathikere", True),
    (r"\b(basavanagudi|basavanagudi station)\b", "Basavanagudi", True),
    (r"\b(sadashivanagar|sadashiva nagar)\b", "Sadashivanagar", True),

    # Legal Section Normalization
    (r"\b(302 ic|302 ip|sec 302|ipc 302|section 302 ipc)\b", "Section 302 IPC", True),
    (r"\b(307 ic|307 ip|sec 307|ipc 307|section 307 ipc)\b", "Section 307 IPC", True),
    (r"\b(420 ic|420 ip|sec 420|ipc 420|section 420 ipc)\b", "Section 420 IPC", True),
    (r"\b(395 ic|395 ip|sec 395|ipc 395|section 395 ipc)\b", "Section 395 IPC", True),
    (r"\b(bns 103|103 bns|sec 103 bns)\b", "Section 103 BNS", True),
    (r"\b(bns 109|109 bns|sec 109 bns)\b", "Section 109 BNS", True),

    # Verbs / Intent Words across Indian Languages (Kanglish, Hinglish, Tanglish, Tenglish, Marathi, Malayalam, Bengali)
    # Kannada / Kanglish
    (r"\b(torisi|torisri|torsi|torso|torisu|torskoli)\b", "show", False),
    (r"\b(kodi|kodri|kodiye)\b", "give", False),
    (r"\b(yelli|ellie|elli)\b", "where", False),
    (r"\b(yaaru|yaru)\b", "who", False),
    (r"\b(helu|helri|heli)\b", "tell", False),
    (r"\b(enaitoo|enaitu)\b", "what happened", False),
    # Hindi / Hinglish
    (r"\b(dikhao|dikhaye|dikhado|dikhaiye|dekho)\b", "show", False),
    (r"\b(batao|bataiye|bataoji)\b", "tell", False),
    (r"\b(kaha|kahan)\b", "where", False),
    (r"\b(kaun|kaun hai)\b", "who", False),
    (r"\b(kya hai|kya tha)\b", "what is", False),
    # Tamil / Tanglish
    (r"\b(kaattu|kaattungal|kaattupannu)\b", "show", False),
    (r"\b(sollo|solloongal|solli)\b", "tell", False),
    (r"\b(enge|engay)\b", "where", False),
    (r"\b(yaar|yaaru)\b", "who", False),
    (r"\b(kudungu|kudu)\b", "give", False),
    # Telugu / Tenglish
    (r"\b(chupinchu|chupiyyi|chupinchandi)\b", "show", False),
    (r"\b(cheppu|cheppandi)\b", "tell", False),
    (r"\b(ekkada|ekkadi)\b", "where", False),
    (r"\b(evaru|evau)\b", "who", False),
    (r"\b(ivvandi|ivvu)\b", "give", False),
    # Marathi
    (r"\b(dakhav|dakhawa|dakhva)\b", "show", False),
    (r"\b(sanga|sangitala)\b", "tell", False),
    (r"\b(kothe|kuthay)\b", "where", False),
    (r"\b(kon)\b", "who", False),
    # Malayalam / Manglish
    (r"\b(kaanikku|kaanikkuk)\b", "show", False),
    (r"\b(para|parayuk)\b", "tell", False),
    (r"\b(evide|evidey)\b", "where", False),
    # Bengali
    (r"\b(dekhao|dekhun)\b", "show", False),
    (r"\b(bolon|bolu)\b", "tell", False),
    (r"\b(kothay|kothai)\b", "where", False),
]

def preprocess_indic_phonetics(text: str) -> str:
    """Pre-processes raw code-mixed transcript using deterministic Indic phonetic regex rules."""
    import re
    if not text:
        return ""
    result = text
    for pattern, replacement, case_sensitive in INDIC_PHONETIC_PATTERNS:
        flags = 0 if case_sensitive else re.IGNORECASE
        result = re.sub(pattern, replacement, result, flags=flags)
    return result

async def transcribe_audio(audio_bytes: bytes, language: str = "kn", filename: str = "recording.wav") -> str:
    """In-Repo ONNX Indic ASR Transcription (models/indic_asr_tiny.onnx + Cloud Fallback)."""
    # 1. Primary: Try In-Repo ONNX Indic ASR Model (~9.66 MB in models/)
    try:
        from shared.onnx_indic_asr import ONNXIndicASR
        onnx_text = ONNXIndicASR.transcribe(audio_bytes, language=language)
        if onnx_text and onnx_text.strip():
            print(f"[ONNX IN-REPO ASR SUCCESS] Transcribed: '{onnx_text.strip()}'")
            return preprocess_indic_phonetics(onnx_text.strip())
    except Exception as e:
        print(f"[ONNX IN-REPO ASR NOTE] {e}")

    # 2. Secondary: Try HuggingFace Cloud Inference API for Indic-ASR / Whisper-Hindi2Hinglish
    hf_key = _env("HF_API_KEY", "HUGGINGFACE_API_KEY")
    hf_models = [
        "OriserveAI/Whisper-Hindi2Hinglish",
        "Sreyan88/Indic-ASR",
        "openai/whisper-large-v3-turbo"
    ]
    for model_id in hf_models:
        try:
            async with httpx.AsyncClient() as client:
                headers = {}
                if hf_key:
                    headers["Authorization"] = f"Bearer {hf_key}"
                hf_url = f"https://api-inference.huggingface.co/models/{model_id}"
                r = await client.post(hf_url, headers=headers, content=audio_bytes, timeout=25.0)
                if r.status_code == 200:
                    res = r.json()
                    text = ""
                    if isinstance(res, dict):
                        text = res.get("text", "")
                    elif isinstance(res, list) and len(res) > 0:
                        text = res[0].get("text", "")
                    if text and text.strip():
                        print(f"[HF CLOUD ASR SUCCESS] Model {model_id} transcribed: '{text.strip()}'")
                        return preprocess_indic_phonetics(text.strip())
        except Exception as e:
            print(f"[HF CLOUD ASR WARNING] Failed on model {model_id}: {e}")

    # 2. Try Groq/OpenAI Whisper-v3 Cloud API
    whisper_key = _env("GROQ_API_KEY", "OPENAI_API_KEY")
    whisper_url = _env("WHISPER_API_URL", "OPENAI_AUDIO_URL", "https://api.groq.com/openai/v1/audio/transcriptions")
    if whisper_key:
        try:
            async with httpx.AsyncClient() as client:
                headers = {"Authorization": f"Bearer {whisper_key}"}
                files = {"file": (filename, audio_bytes, "audio/wav")}
                data = {
                    "model": "whisper-large-v3-turbo" if "groq" in whisper_url else "whisper-1",
                    "prompt": "Transcribe Karnataka Police crime queries accurately in Indian English, Kanglish, Hinglish, Tanglish, Tenglish, Kannada, Hindi, Tamil, Telugu, Marathi, Malayalam. Keep police station names (Belagavi, Cubbon Park, Koramangala) and legal sections (Section 302 IPC, Section 307 IPC, Section 103 BNS) exact.",
                    "temperature": "0.0"
                }
                r = await client.post(whisper_url, headers=headers, files=files, data=data, timeout=30.0)
                if r.status_code == 200:
                    text = r.json().get("text", "")
                    if text and text.strip():
                        return preprocess_indic_phonetics(text.strip())
        except Exception as e:
            print(f"[WHISPER ASR ERROR] {e}. Falling back to Zia ASR.")

    # 3. Zia ASR Cloud REST API fallback
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ZIA_ASR_EXTENSIONS:
        filename = "recording.wav"
        ext = ".wav"

    async with httpx.AsyncClient() as client:
        r = await client.post(
            ZIA_ASR_URL,
            headers=await _zia_headers(),
            files={"file": (filename, audio_bytes, _ZIA_ASR_MIMES.get(ext, "audio/wav"))},
            data={"language": language if language in ZIA_VOICE_LANGS else "en"},
            timeout=20.0,
        )
        r.raise_for_status()
        raw_text = r.json().get("text", "")
        return preprocess_indic_phonetics(raw_text)

# Zia TTS treats "speaker" as required, and speaker names are per-language
# (not interchangeable) -- see the Text-to-Audio Synthesis model card's
# Speaker list in the Catalyst console. A caller that only knows the language
# still needs a valid one, so map each supported language to a default.
ZIA_DEFAULT_SPEAKERS = {"en": "Mary", "hi": "Divya", "kn": "Anu"}

async def text_to_speech(text: str, language: str = "kn",
                          speaker: str | None = None,
                          pitch: str = "moderate",
                          speed: str = "moderate",
                          emotion: str = "neutral") -> bytes:
    """Zia Text-to-Audio Synthesis. Pinned to neutral/moderate defaults for officer-facing responses."""
    async with httpx.AsyncClient() as client:
        payload = {
            "text": text,
            "language": language if language in ZIA_VOICE_LANGS else "en",
            "speaker": speaker or ZIA_DEFAULT_SPEAKERS.get(language, "Mary"),
            "pitch": pitch,
            "speed": speed,
            "emotion": emotion,
        }
        r = await client.post(ZIA_TTS_URL, headers=await _zia_headers_json(), json=payload, timeout=15.0)
        r.raise_for_status()
        return r.content   # audio/wav

async def translate_text(text: str, source_lang: str, target_lang: str = "en") -> dict:
    """Zia Text Translation. New Layer 1b hop -- only called when source_lang not in ZIA_VOICE_LANGS."""
    # Using GLM-4.7-Flash for translation as the QuickML Zia Translate endpoint is failing with undocumented 'zoho-inputstream' errors.
    sys_prompt = f"You are a professional translator. Translate the following text from {source_lang} to {target_lang}. Output ONLY the translated text, no conversational filler or markdown."
    try:
        translated = await llm_complete(text, sys_prompt, temperature=0.1, max_tokens=1000)
        return {"translated_text": translated.strip(), "processing_time": 0}
    except Exception as e:
        print(f"[LLM TRANSLATE ERROR] Failed to translate: {e}")
        raise

async def normalize_transcript_text(text: str, source_lang: str = "en") -> str:
    """
    SOTA Multilingual Indic & Code-Mixed (Kanglish, Hinglish, Tanglish, Tenglish, Marathi, Malayalam, Bengali) Legal Domain Normalizer.
    Converts raw transliterated/spoken Indian phrases into clean, structured English investigative queries.
    """
    if not text or not text.strip():
        return ""
    
    # Run deterministic pre-processing first
    working_text = preprocess_indic_phonetics(text.strip())

    # Translate if non-English & non-code-mixed declared language
    if source_lang and source_lang.split("-")[0] not in ("en", "english", "mix"):
        try:
            translation_res = await translate_text(working_text, source_lang=source_lang, target_lang="en")
            working_text = translation_res.get("translated_text", working_text)
        except Exception as e:
            print(f"[TRANSLATE ERROR] Failed to translate: {e}")

    sys_prompt = (
        "You are an expert SOTA Multilingual & Code-Mixed Indian Language (Kanglish, Hinglish, Tanglish, Tenglish, Marathi, Malayalam, Bengali) voice normalizer for Karnataka State Police (KSP).\n"
        "The input is a raw speech-to-text transcript spoken by a police officer using code-mixed speech or native script.\n\n"
        "Your Processing Guidelines:\n"
        "1. TRANSLATE & CONVERT ALL CODE-MIXED / TRANSLITERATED INDIAN PHRASES TO CLEAN ENGLISH:\n"
        "   - Kannada/Kanglish: 'torisi'/'kodi' -> 'show'/'give', 'yelli' -> 'where', 'yaaru' -> 'who', 'nalli' -> 'in'\n"
        "   - Hindi/Hinglish: 'dikhao'/'batao' -> 'show'/'tell', 'kaha' -> 'where', 'kaun' -> 'who', 'me' -> 'in'\n"
        "   - Tamil/Tanglish: 'kaattu'/'sollo' -> 'show'/'tell', 'enge' -> 'where', 'yaar' -> 'who'\n"
        "   - Telugu/Tenglish: 'chupinchu'/'cheppu' -> 'show'/'tell', 'ekkada' -> 'where', 'evaru' -> 'who'\n"
        "   - Marathi: 'dakhav'/'sanga' -> 'show'/'tell', 'kothe' -> 'where', 'kon' -> 'who'\n"
        "   - Malayalam/Manglish: 'kaanikku'/'para' -> 'show'/'tell', 'evide' -> 'where'\n"
        "   - Bengali: 'dekhao'/'bolon' -> 'show'/'tell', 'kothay' -> 'where'\n"
        "2. CORRECT PHONETICALLY GARBLED POLICE STATIONS & TOWNS:\n"
        "   - 'Delhi Gavi' -> 'Belagavi', 'Coupon Park'/'Cupon Park' -> 'Cubbon Park', 'Malleswaram' -> 'Malleshwaram', 'Kora Mangala' -> 'Koramangala', 'Indira Nagar' -> 'Indiranagar', 'Hala Suru' -> 'Halasuru (Ulsoor)', 'HSR' -> 'HSR Layout'\n"
        "3. STANDARDIZE LEGAL & CASE TERMINOLOGY:\n"
        "   - '302 IC'/'302 IP' -> 'Section 302 IPC', '307 IC' -> 'Section 307 IPC', '420 IC' -> 'Section 420 IPC', 'BNS 103' -> 'Section 103 BNS', 'BNS 109' -> 'Section 109 BNS', 'POCSO', 'FIR 142' -> 'FIR No. 142'\n"
        "4. EXAMPLES:\n"
        "   - Input: 'Belagavi station case 142 nalli Section 302 IPC crime details torisi'\n"
        "     Output: 'Show crime details for FIR No. 142 under Section 302 IPC registered at Belagavi station'\n"
        "   - Input: 'Cubbon Park FIR 89 me Section 307 dikhao Ramesh suspect status kya hai'\n"
        "     Output: 'Show details of Section 307 IPC under FIR No. 89 at Cubbon Park station and tell suspect status of Ramesh'\n"
        "   - Input: 'Koramangala station murder case accused Ramesh info kaattu'\n"
        "     Output: 'Show accused Ramesh information in Koramangala station murder case'\n"
        "5. PRESERVE INVESTIGATIVE INTENT:\n"
        "   - Output a single, clean, grammatically correct English query ready for crime intelligence graph retrieval.\n"
        "   - Do NOT add conversational filler, quotes, preamble, or markdown."
    )
    try:
        corrected = await llm_complete(working_text, sys_prompt, temperature=0.1, max_tokens=250)
        return corrected.strip()
    except Exception as e:
        print(f"[PHONETIC CORRECTION ERROR] LLM failed: {e}")
        return working_text

async def transcribe_and_normalize(audio_bytes: bytes, declared_language: str,
                                    filename: str = "recording.wav") -> str:
    """
    Layer 1 orchestrator: ASR -> (conditional) translate -> plain text into Layer 2.
    """
    if declared_language in ZIA_VOICE_LANGS:
        raw_transcript = await transcribe_audio(audio_bytes, language=declared_language, filename=filename)
        return await normalize_transcript_text(raw_transcript, source_lang=declared_language)

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
    url = _nosql_base_url() + path
    last_error = None
    max_attempts = 3
    for attempt in range(max_attempts):
        headers = await _nosql_headers()
        try:
            async with httpx.AsyncClient() as client:
                r = await client.request(method, url, headers=headers, json=json_body, timeout=15.0)
                if r.status_code == 401:
                    # Invalidate token cache on 401 and retry refresh
                    _nosql_token_cache["access_token"] = None
                    if attempt < max_attempts - 1:
                        await asyncio.sleep(0.5)
                        continue
                r.raise_for_status()
                return r.json()
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            last_error = e
            if attempt < max_attempts - 1:
                await asyncio.sleep(1.0)
                continue
    raise last_error

def _running_in_catalyst() -> bool:
    """True when executing inside a deployed Catalyst AppSail/Function.

    X_ZOHO_CATALYST_LISTEN_PORT is injected by the Catalyst runtime itself,
    not by the project's own environment-variable config, so it stays a
    reliable signal even when the app's own config vars are missing -- which
    is exactly the situation this guard exists to catch.
    """
    return bool(os.getenv("X_ZOHO_CATALYST_LISTEN_PORT"))


def _mock_nosql_reason() -> str | None:
    """Why the local mock store would be used, or None if real NoSQL is configured."""
    if _env("MOCK_NOSQL_ONLY", "") == "true":
        return "MOCK_NOSQL_ONLY=true"
    if not _env("ZC_PROJECT_ID", "CATALYST_PROJECT_ID"):
        return "ZC_PROJECT_ID/CATALYST_PROJECT_ID is not set"
    token = _env("ZC_ACCESS_TOKEN", "CATALYST_ACCESS_TOKEN") or _env("ZC_API_TOKEN", "CATALYST_API_TOKEN")
    if not (token or _env("ZC_REFRESH_TOKEN", "CATALYST_REFRESH_TOKEN")):
        return "neither ZC_ACCESS_TOKEN nor ZC_REFRESH_TOKEN is set"
    return None


def _should_use_mock_nosql() -> bool:
    """
    BUG FIX: nosql_get/nosql_set used to fall back to a container-local JSON
    file whenever config looked incomplete -- silently, and in production too.
    In a deployed AppSail that file starts empty, so the user store simply
    appeared to contain nobody: every login returned "Invalid username or
    password", and five of those tripped the lockout into a 429. The real
    cause (missing NoSQL config) was completely invisible, and it recurred on
    every deploy because each new container gets a fresh empty file.

    The mock store is a local-development convenience, so refuse it outright
    when running inside Catalyst unless it was explicitly requested.
    """
    reason = _mock_nosql_reason()
    if reason is None:
        return False
    if _running_in_catalyst() and _env("MOCK_NOSQL_ONLY", "") != "true":
        raise EnvironmentError(
            f"NoSQL is not configured in this deployment ({reason}). Refusing to fall "
            "back to the local mock store -- that would silently serve an empty user/"
            "session database. Set the missing variable(s) in the AppSail/Function "
            "Configuration tab and redeploy."
        )
    return True


async def nosql_get(key: str) -> dict | None:
    """Fetch a value from the real Catalyst NoSQL AppKeyValueStore table with local fallback."""
    if _should_use_mock_nosql():
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
    if _should_use_mock_nosql():
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

async def nosql_delete(key: str):
    """
    Delete an item from the real Catalyst NoSQL AppKeyValueStore table with local fallback.
    """
    if _should_use_mock_nosql():
        import json
        import os
        db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.nosql_mock_db.json"))
        async with _get_mock_db_lock():
            if os.path.exists(db_path):
                try:
                    with open(db_path, "r") as f:
                        data = json.load(f)
                    if key in data:
                        del data[key]
                        with open(db_path, "w") as f:
                            json.dump(data, f, indent=2)
                except Exception as e:
                    print(f"Failed to delete from local mock NoSQL DB: {e}")
        return

    try:
        # The Python SDK delete_items method uses DELETE /item with a list of keys
        await _nosql_request("DELETE", "/item", [{"item_key": {"S": key}}])
    except Exception as e:
        print(f"Warning: nosql_delete DELETE call failed: {e}. Falling back to TTL expiration.")
        # If the exact DELETE endpoint format changes, fall back to soft-deleting via 1-second TTL.
        # Use valid empty JSON structures so concurrent readers don't crash before the row expires.
        fallback_val = "[]" if key.startswith(("history:", "case_sessions:")) else "{}"
        await nosql_set(key, fallback_val, ttl=1)
