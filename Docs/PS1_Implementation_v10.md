# PS-1: Implementation Plan v10
## Living Document — KB Clarification Revision

**Supersedes:** `PS1_Implementation_v9.md`
**Folds in:** `PS1_Voice_Language_Layer_v2.md`, `PS1_Evidence_Language_Detection.md`, `PS1_Reasoning_Feedback_Loop.md`, `PS1_Integrity_AntiCorruption_Layer_v1.md`
**Companion document:** `PS1_Architecture_v10.md` — read that first for the *why*; this document is the *how*, file-by-file.

**Verification note on this revision:** v10 makes one surgical change: the KB document upload mechanism. All v9 file-by-file diffs, `[VERIFY]` flags, and confirmed current-state references are preserved verbatim. The only sections that change are those touching `kb_upload`, `kb_search`, `ingestion/pipeline.py`'s `ingest_one`, and the environment variable list.

---

## 0. Changelog — v9 → v10 (Read This First)

One change. Everything else from v9 carries forward unchanged.

| # | Change | v9 | v10 | Why |
|---|---|---|---|---|
| C1 | `kb_upload` in `catalyst_client.py` | `POST /documents` to `CATALYST_KB_ENDPOINT` at ingestion time | **Removed from runtime path.** Replaced by `generate_kb_upload_files()` utility that produces chunked `.txt` files for manual console upload | Catalyst QuickML KB has no programmatic upload API. Upload is UI-only. |
| C2 | `kb_search` in `catalyst_client.py` | `POST` to `CATALYST_KB_ENDPOINT` with `{"query": ..., "top_k": ...}` only | Same, plus `X-QUICKML-ENDPOINT-KEY: {CATALYST_KB_ENDPOINT_KEY}` header | Deployed QuickML RAG pipeline endpoints require an endpoint key |
| C3 | `ingest_one()` in `ingestion/pipeline.py` | Calls `upload_fir_to_kb(fir)` inside `asyncio.gather(...)` | KB call removed; only `write_fir_to_memgraph` and `write_fir_to_ztsql` remain in the gather | KB upload is now a pre-demo manual step, not a runtime operation |
| C4 | `ingestion/kb_writer.py` | `upload_fir_to_kb()` — HTTP POST per FIR | `generate_kb_upload_files()` — writes chunked `.txt` files to `data/kb_chunks/` | Same job (get FIR narratives into the KB), different mechanism |
| C5 | Environment variables | `CATALYST_KB_ENDPOINT` only | `CATALYST_KB_ENDPOINT` + `CATALYST_KB_ENDPOINT_KEY` | Deployed QuickML endpoints require an endpoint key in addition to the URL |

### Additions

| # | Addition | Section |
|---|---|---|
| A13 | `CATALYST_KB_ENDPOINT_KEY` env var | §4 |
| A14 | `ingestion/kb_writer.py` — `generate_kb_upload_files()` implementation | New §16a |

### Deletions

None. All v9 content preserved; the `upload_fir_to_kb` function stub is retained but marked `[DEPRECATED — v10]`.

---

## 0a. Changelog — v8 → v9 (Preserved)

### Additions

| # | Addition | Section(s) | Confirmed against v8 at |
|---|---|---|---|
| A1 | Zia Text Translation (`translate_text`) | §5 (catalyst_client.py) | New function; v8 §5 had no translation capability at all |
| A2 | Ingestion-time language tagging (`tag_and_normalize_language`, `_tag_field`) | §16 (Ingestion Pipeline) | v8 lines 1489–1495 (`ingest_one`) — confirmed exact location, wraps this call |
| A3 | Retrieval-time conditional edge (`should_translate_evidence`, `translate_evidence_node`) | §11 (Retrieval Executor addendum) | New LangGraph node; exact wiring point in `langgraph_router.py` is `[VERIFY]` — see note below |
| A4 | Methodology-scoped trust weighting (`MethodologyTrust`, `CorrectionEvent`, `feedback_engine.py`) | §12 (Confidence Engine), §10 (Evidence Object), new §13a | v8 §12 lines 1104–1194 (`confidence_engine.py`), confirmed formula shape to splice into |
| A5 | Per-citation confirm/correct UI + `/api/feedback/correction` route | §23 (Frontend), §6 (routes) | v8 §23 lines 2317–2378 (component tree) — new leaf components under `AssistantMessage` |
| A6 | `shared/language_utils.py`, `shared/feedback_models.py`, `shared/feedback_engine.py` | §5 | New files under `shared/` |
| A7 | New `EvidenceItem` fields: `edge_type`, `edge_id`, `crime_type`, `language`, `text_original`, `is_translated` | §10 | v8 lines 936–947 (`EvidenceItem` dataclass) — confirmed current field set has none of these |
| A8 | `langdetect` dependency | §5, §16 | No dependency-management section existed in v8 to diff against — noted as new, see §5a |
| A9 | Hash-chained audit entries + read-access logging in `pipeline_function/pipeline/audit.py` | §22 | v8's `audit.py` internals (exact current function/field names) aren't shown anywhere in v8's text, only referenced by name in the file tree — exact splice point is `[VERIFY]`, same honesty rule as the two items below §0's table |
| A10 | `shared/search_log.py` — named-entity search logging | §5, §22 | New file; no v8 equivalent exists |
| A11 | `is_sensitive` downgrade check in `backend/api/middleware/rbac.py` | §22 | v8's `rbac.py` internals also aren't shown in v8's text — same `[VERIFY]` caveat |
| A12 | Append-only evidence versioning | §22 | Extends A2's ingestion-time preserve-original pattern; no new file, a rule applied at every evidence-write call site |

### Changes

| # | Change | v8 (confirmed) | v9 | Why |
|---|---|---|---|---|
| C1 | `shared/catalyst_client.py` `transcribe_audio`/`text_to_speech` | Lines 422–436, generic env-var URLs (`CATALYST_ASR_URL`, `CATALYST_TTS_URL`), untyped payload | Hardcoded Zia endpoint constants, correct multipart shape for ASR, pitch/speed/emotion params for TTS, pinned neutral/moderate default | The v8 stubs called a placeholder URL with a guessed payload shape; the real Zia model cards specify multipart/form-data for ASR and a richer JSON body for TTS |
| C2 | `EvidenceItem` dataclass | Lines 936–947, 11 fields, no citation-structure fields | Same 11 fields + 6 new ones (A7) | Required for A4 (trust weighting needs `edge_type`/`crime_type` to look up) and A5 (per-citation UI needs `edge_id` to route corrections) |
| C3 | `compute_confidence()` in `confidence_engine.py` | Lines 1174–1180, three-signal formula, no external input | Same three signals + `trust_weight` multiplicative dampener, now `async` | Confidence must reflect accumulated reliability, not just retrieval ranking (Architecture v9 §10) |
| C4 | Evidence ranking (currently `EvidenceObject.rank()`, line 987–988) | Sorts purely on `relevance_score` | `rank_evidence()` in the retrieval executor multiplies by `trust_weight` and session penalty before sort | Closes the loop v8 §13/Architecture v8 §13 claimed existed but didn't |
| C5 | `synthesizer.py`'s `items_text` prompt formatting | Lines 1224–1229, formats `FIR:{id} Score:... Sources:... Confidence:... Path:... Reason:...` | Same format, `evidence_path` string is joined by structured `edge_type`/`edge_id` so the frontend can build per-citation controls from the returned evidence list, not by re-parsing prose | The current `evidence_path` is a human-readable string (`"CO_ACCUSED via FIR123"`), parsed by substring match in `compute_evidence_strength` (lines 1132–1147) — that string-matching stays for confidence scoring, but citation UI now reads the new structured fields directly instead of re-parsing the same string a second time |
| C6 | `backend/.env` / `pipeline_function/.env` | `CATALYST_ASR_ENDPOINT`, `CATALYST_TTS_ENDPOINT` | Removed; add `CATALYST_ORG_ID` | Zia URLs are stable platform constants, not per-project deployment URLs |
| C7 | Frontend component tree (§23, lines 2325–2351) | `EvidenceCitations` — whole-answer citation list, no per-item action | Same component, each rendered citation row gets confirm/correct controls wired to `edge_type`/`edge_id`/`crime_type` | Required for A4/A5 — a correction must trace to one specific piece of evidence, not the whole answer |
| C8 | `VoiceButton` (line 2368–2370, 2415) | Records → `/api/transcribe` → Catalyst ASR, no language selection | Adds a language picker (`en`/`hi`/`kn`); non-supported spoken languages are out of scope for ASR (Zia ASR itself only covers these three) — text input in other languages routes through Translation instead (A1) | Zia ASR model card shows no auto-detect; a declared language is required per the real endpoint contract |

### Deletions

None. Strict superset of v8, same principle as Architecture v9 §0.

### Two Things This Revision Deliberately Does *Not* Resolve

Both were flagged `[VERIFY]` in the source addenda, and neither is resolvable from v8's text alone — resolving them here anyway would mean guessing at code that isn't shown, which is worse than leaving the flag standing:

1. **Exact LangGraph node name for retrieval/evidence-assembly**, and the exact runtime shape of whatever object flows between `resolving_entities_node` and the confidence engine. v8 confirms `resolving_entities_node` exists (§7 Entity-to-Lookup Resolution) and confirms the `EvidenceObject`/`EvidenceItem` dataclasses used *after* retrieval (§10), but does not show the LangGraph `StateGraph` wiring itself (node names, edges) anywhere in its ~2,500 lines. The A3/A4 wiring snippets below are written against the `EvidenceObject`/`EvidenceItem` shape that v8 *does* confirm, but the exact `graph.add_conditional_edges(...)` call needs the real node name from the actual `langgraph_router.py` file before it's pasted in.
2. **Whether citation-to-source mapping is exposed all the way to the frontend today.** v8 confirms `evidence_path` exists on `EvidenceItem` and is used internally by the confidence engine's string-matching (lines 1132–1147) and by the synthesis prompt (line 1227) — but nothing in v8's `EvidenceCitations.jsx` description (line 105, 2340) shows what fields actually reach the frontend today. A7's new fields need to be added to whatever serializer currently turns `EvidenceItem` into the JSON the frontend receives — that serializer isn't shown in v8's text, so `[VERIFY]` its location before wiring in the UI changes of §23.

---

## 1. Team & Tooling

*(Unchanged from v8.)*

| Role | Count | Tools |
|---|---|---|
| Full-stack (backend-leaning) | 3 | Claude Code, Antigravity, Copilot |
| Full-stack (frontend-leaning) | 2 | Antigravity, Copilot |

---

## 2. Project Structure `[CHANGED — new files marked]`

```
ps1-cis/
├── shared/
│   ├── __init__.py
│   ├── models.py             # + 6 new language fields on FIRSchema (Sec 5)
│   ├── graph_client.py
│   ├── catalyst_client.py    # CHANGED -- Zia ASR/TTS corrected, translate_text added (Sec 5)
│   ├── language_utils.py     # NEW -- detect_language, is_viable (Sec 5)
│   ├── feedback_models.py    # NEW -- CorrectionEvent, MethodologyTrust (Sec 13a)
│   ├── feedback_engine.py    # NEW -- get_trust_weight, record_feedback_event (Sec 13a)
│   ├── search_log.py         # NEW -- named-entity search logging (Sec 5, Sec 22)
│   ├── ner_examples.py
│   └── ner_prompt.py
│
├── backend/
│   ├── main.py
│   ├── api/
│   │   ├── routes/
│   │   │   ├── query.py
│   │   │   ├── transcribe.py
│   │   │   ├── graph.py
│   │   │   ├── health.py
│   │   │   └── feedback.py   # NEW -- POST /api/feedback/correction (Sec 6)
│   │   └── middleware/
│   │       ├── input_validator.py
│   │       └── rbac.py       # CHANGED -- is_sensitive downgrade gate, vigilance_cell check (Sec 22)
│   ├── job_dispatch.py
│   └── sse_poller.py
│
├── pipeline_function/
│   ├── main.py
│   ├── pipeline/
│   │   ├── graph_definition.py   # + should_translate_evidence conditional edge (Sec 11) [VERIFY wiring]
│   │   ├── session.py
│   │   ├── evidence.py           # CHANGED -- EvidenceItem gets 6 new fields (Sec 10)
│   │   ├── confidence_engine.py  # CHANGED -- trust_weight input (Sec 12)
│   │   ├── cache.py
│   │   ├── catalyst_resilient_client.py
│   │   ├── audit.py              # CHANGED -- hash-chained entries + read logging (Sec 22) [VERIFY current internals]
│   │   ├── preprocessing/
│   │   │   └── normalizer.py     # + translation short-circuit (Layer 1b, Sec 9a)
│   │   ├── query_understanding/
│   │   │   ├── ner_intent.py
│   │   │   └── dag_planner.py
│   │   ├── retrieval/
│   │   │   ├── graph_client.py
│   │   │   ├── rag_client.py
│   │   │   ├── sql_client.py
│   │   │   ├── executor.py       # CHANGED -- trust-weighted ranking (Sec 11)
│   │   │   └── translate_evidence_node.py  # NEW (Sec 11)
│   │   └── synthesis/
│   │       ├── synthesizer.py    # CHANGED -- citation structure (Sec 13)
│   │       └── xai.py
│   └── graph/
│       ├── queries.py
│       └── algorithms.py
│
├── ingestion/
│   ├── pipeline.py            # CHANGED -- tag_and_normalize_language wired into ingest_one (Sec 16)
│   ├── format_detector.py
│   ├── ocr_extractor.py
│   ├── schema_mapper.py
│   ├── validators.py
│   ├── entity_resolution.py
│   ├── kb_writer.py
│   ├── memgraph_writer.py
│   ├── sql_writer.py
│   └── scoring.py
│
├── frontend/
│   └── src/
│       ├── components/
│       │   ├── chat/
│       │   │   ├── ChatWindow.jsx
│       │   │   ├── MessageList.jsx
│       │   │   ├── AssistantMessage.jsx
│       │   │   ├── ConfidenceBadge.jsx
│       │   │   ├── EvidenceCitations.jsx    # CHANGED -- per-citation controls (Sec 23)
│       │   │   ├── CitationFeedback.jsx     # NEW -- confirm/correct + explanation modal (Sec 23)
│       │   │   └── ReasoningTrace.jsx
│       │   ├── dashboard/ ...               # unchanged
│       │   └── input/
│       │       ├── InputBar.jsx
│       │       └── VoiceButton.jsx          # CHANGED -- language picker added (Sec 23)
│       ├── services/
│       │   └── queryService.js
│       └── contexts/ ...                    # unchanged
│
├── data/ ...                                # unchanged
├── infra/ ...                               # unchanged
└── docs/
    ├── PS1_Architecture.md   # -> PS1_Architecture_v9.md
    ├── PS1_Implementation.md # -> PS1_Implementation_v9.md (this file)
    └── demo-preflight.md
```

---

## 3. Team Ownership

*(Unchanged from v8.)*

---

## 4. Environment Variables `[CHANGED — C6]`

Pipeline Function (`pipeline_function/.env`):
```
CATALYST_API_TOKEN=
CATALYST_ORG_ID=                # NEW in v9 -- e.g. 60075634347, used for Zia header auth (Sec 5)
CATALYST_LLM_ENDPOINT=
CATALYST_VLM_ENDPOINT=
CATALYST_KB_ENDPOINT=           # Deployed QuickML RAG pipeline URL (from console after deploy)
CATALYST_KB_ENDPOINT_KEY=       # X-QUICKML-ENDPOINT-KEY value from console [NEW -- v10/A13]
# CATALYST_ASR_ENDPOINT / CATALYST_TTS_ENDPOINT -- REMOVED in v9. Zia ASR/TTS/Translate
#   URLs are stable platform constants hardcoded in catalyst_client.py (Sec 5),
#   not per-project deployment URLs.
CATALYST_DATASTORE_URL=
CATALYST_NOSQL_URL=
CATALYST_PROJECT_ID=
MEMGRAPH_URI=bolt://your-oracle-vm-ip:7687
MEMGRAPH_USERNAME=
MEMGRAPH_PASSWORD=
ENVIRONMENT=development
```

AppSail backend (`backend/.env`) — unchanged from v8; still never holds LLM/VLM/KB/ASR/TTS credentials, per the thin-front-door principle.

**Critical Deployment Fix (`functions/ps_1_cis_function/catalyst-config.json`):**
Ensure the `"env_variables": {}` block is entirely **deleted** from the `catalyst-config.json` file. If left in (even if empty), running `catalyst deploy` will silently wipe out all manually configured environment variables in the Catalyst UI (like `ZC_PROJECT_ID`), triggering the pipeline to silently fall back to a NoSQL mock database and hanging the frontend indefinitely.

---

## 5. shared/ Library `[CHANGED — C1, adds A1/A6/A8]`

### 5a. New Dependency

```
pip install langdetect
```

Add to whichever `requirements.txt` files `backend/` and `pipeline_function/` maintain (v8's project structure implies these may be separate — v8's text does not show a shared top-level `requirements.txt`, so `[VERIFY]` whether one exists before deciding if this is a one-line addition or a two-file one).

### 5.0 `shared/graph_client.py` `[CHANGED — Serverless Asyncio Hardening]`

**Critical Deployment Fix:** In a serverless environment (like Catalyst Functions), the `asyncio` event loop is destroyed between invocations. If the Neo4j `AsyncGraphDatabase.driver` is cached globally across invocations, its internal background tasks (like connection pool keepalives) will become detached and crash the *next* invocation with `RuntimeError: Task attached to a different loop`. 
**Implementation:** Global driver caching (`global _driver`) must be entirely removed. `get_driver()` must instantiate a new driver on every request, and all execution blocks must be wrapped in `try...finally: await driver.close()` to ensure clean teardown before the ephemeral container destroys the loop.

### 5.1 `shared/models.py` `[CHANGED — adds A2's schema fields]`

**Confirmed current state (v8 lines 294–319):**

```python
class FIRSchema(BaseModel):
    id: str
    crime_no: str
    case_no: Optional[str] = None
    date: str
    crime_head_id: Optional[str] = None
    crime_sub_head_id: Optional[str] = None
    crime_type_freetext: Optional[str] = None
    district: str
    unit_id: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    victims: list[VictimSchema] = []
    complainants: list[ComplainantSchema] = []
    accused: list[AccusedSchema] = []
    arrest_surrenders: list[ArrestSurrenderSchema] = []
    act_sections: list[tuple[str, str]] = []
    status: str = "open"
    mo_descriptor: str = ""
    narrative: Optional[str] = None
    ocr_extracted: bool = False

    @validator('district', pre=True)
    def canonicalize_district(cls, v):
        return DISTRICT_CANONICAL.get(str(v).strip().lower(), str(v).strip())
```

**Target — append these fields (additive only, `canonicalize_district` validator untouched):**

```python
    # --- NEW in v9: language tagging (Architecture v9 Sec 15 / A2) ---
    narrative_language: Optional[str] = None        # ISO 639-1, e.g. "ta", "te", "kn"
    narrative_original: Optional[str] = None        # untouched source text, always preserved
    narrative_is_translated: bool = False

    mo_descriptor_language: Optional[str] = None
    mo_descriptor_original: Optional[str] = None
    mo_descriptor_is_translated: bool = False
```

Only `narrative` and `mo_descriptor` get this treatment — the other schemas (`VictimSchema`, `ComplainantSchema`, `AccusedSchema`, `ArrestSurrenderSchema`) are all structured fields with no open-text field to tag.

### 5.2 `shared/catalyst_client.py` `[CHANGED — C1, adds A1]`

**Confirmed current state (v8 lines 357–437) — the two functions being replaced:**

```python
# v8, lines 422-436 -- BEING REPLACED
async def transcribe_audio(audio_bytes: bytes, language: str = "kn") -> str:
    async with httpx.AsyncClient() as client:
        r = await client.post(CATALYST_ASR_URL,
            headers={"Authorization": f"Zoho-oauthtoken {CATALYST_TOKEN}"},
            files={"audio": ("recording.webm", audio_bytes, "audio/webm")},
            data={"language": language}, timeout=20.0)
        r.raise_for_status()
        return r.json()["transcript"]

async def text_to_speech(text: str, language: str = "kn") -> bytes:
    async with httpx.AsyncClient() as client:
        r = await client.post(CATALYST_TTS_URL, headers=HEADERS,
            json={"text": text, "language": language}, timeout=15.0)
        r.raise_for_status()
        return r.content
```

**What was wrong with this, specifically:** `CATALYST_ASR_URL`/`CATALYST_TTS_URL` were read from generic env vars that were never actually pointed at the real Zia endpoints (they didn't exist yet when this was written) — the real Zia model cards, now inspected, show these are **stable platform constants** (`api.catalyst.zoho.in/quickml/api/v1/models/zia/...`), not per-project deployment URLs. The TTS call also has no `pitch`/`speed`/`emotion` fields, which the real model card requires for a well-formed request.

**Target — replaces the two functions above, keeps everything else in the file (`llm_complete`, `vlm_extract`, `kb_upload`, `kb_search`, `ztsql_query`, `ztsql_execute`) exactly as in v8:**

```python
import httpx, os, base64

CATALYST_TOKEN         = os.getenv("CATALYST_API_TOKEN")
CATALYST_ORG_ID        = os.getenv("CATALYST_ORG_ID")          # NEW
CATALYST_LLM_URL       = os.getenv("CATALYST_LLM_ENDPOINT")
CATALYST_VLM_URL       = os.getenv("CATALYST_VLM_ENDPOINT")
CATALYST_KB_URL        = os.getenv("CATALYST_KB_ENDPOINT")
CATALYST_DATASTORE_URL = os.getenv("CATALYST_DATASTORE_URL")
# CATALYST_ASR_URL / CATALYST_TTS_URL -- REMOVED as env vars, see ZIA_* constants below

HEADERS = {
    "Authorization": f"Zoho-oauthtoken {CATALYST_TOKEN}",
    "Content-Type": "application/json"
}

# --- unchanged from v8: llm_complete, vlm_extract, ztsql_query, ztsql_execute all stay exactly as they were ---

# --- kb_search: UPDATED in v10 to include X-QUICKML-ENDPOINT-KEY header ---

CATALYST_KB_URL        = os.getenv("CATALYST_KB_ENDPOINT")
CATALYST_KB_KEY        = os.getenv("CATALYST_KB_ENDPOINT_KEY")   # NEW -- v10

async def kb_upload(document_id: str, content: str, metadata: dict):
    """[DEPRECATED -- v10] KB upload is now a pre-demo manual operation.
    Use generate_kb_upload_files() in ingestion/kb_writer.py instead.
    This stub is preserved so call sites fail loudly rather than silently
    if accidentally called -- it raises NotImplementedError."""
    raise NotImplementedError(
        "kb_upload() is disabled in v10. KB documents are uploaded manually "
        "via the Catalyst QuickML console. See Architecture v10 §20a."
    )

async def kb_search(query: str, top_k: int = 10) -> dict:
    """UPDATED -- v10: adds X-QUICKML-ENDPOINT-KEY header required by deployed
    QuickML RAG pipeline endpoints. All other behaviour unchanged from v9."""
    if not CATALYST_KB_URL:
        print("[WARNING] CATALYST_KB_ENDPOINT not configured — RAG step returning zero results.")
        return {"results": []}
    if not CATALYST_KB_KEY:
        print("[WARNING] CATALYST_KB_ENDPOINT_KEY not configured — RAG step returning zero results.")
        return {"results": []}
    async with httpx.AsyncClient() as client:
        r = await client.post(
            CATALYST_KB_URL,
            headers={
                **HEADERS,
                "X-QUICKML-ENDPOINT-KEY": CATALYST_KB_KEY,   # NEW -- v10
            },
            json={"query": query, "top_k": top_k},
            timeout=15.0,
        )
        r.raise_for_status()
        return r.json() or {"results": []}

# --- NEW/REPLACED: Zia voice/language endpoints -- stable platform constants ---
ZIA_ASR_URL       = "https://api.catalyst.zoho.in/quickml/api/v1/models/zia/audio/transcribe"
ZIA_TTS_URL       = "https://api.catalyst.zoho.in/quickml/api/v1/models/zia/tts/synthesize"
ZIA_TRANSLATE_URL = "https://api.catalyst.zoho.in/quickml/api/v1/models/zia/translate"

ZIA_HEADERS = {
    "CATALYST-ORG": CATALYST_ORG_ID,
    "Authorization": f"Zoho-oauthtoken {CATALYST_TOKEN}",
}
ZIA_HEADERS_JSON = {**ZIA_HEADERS, "Content-Type": "application/json"}
ZIA_VOICE_LANGS = {"en", "hi", "kn"}


async def transcribe_audio(audio_bytes: bytes, language: str = "kn",
                            filename: str = "recording.webm") -> str:
    """REPLACES v8 lines 422-429. Zia Audio-to-Text Transcription --
    multipart/form-data per the verified model card."""
    async with httpx.AsyncClient() as client:
        r = await client.post(
            ZIA_ASR_URL, headers=ZIA_HEADERS,   # no Content-Type -- httpx sets multipart boundary
            files={"audio": (filename, audio_bytes, "audio/webm")},
            data={"language": language}, timeout=20.0,
        )
        r.raise_for_status()
        return r.json()["transcript"]


async def text_to_speech(text: str, language: str = "kn", speaker: str | None = None,
                          pitch: str = "moderate", speed: str = "moderate",
                          emotion: str = "neutral") -> bytes:
    """REPLACES v8 lines 431-436. Pinned to neutral/moderate defaults for
    officer-facing responses -- see Architecture v9 Sec 7."""
    async with httpx.AsyncClient() as client:
        payload = {"text": text, "language": language, "pitch": pitch,
                   "speed": speed, "emotion": emotion}
        if speaker:
            payload["speaker"] = speaker
        r = await client.post(ZIA_TTS_URL, headers=ZIA_HEADERS_JSON, json=payload, timeout=15.0)
        r.raise_for_status()
        return r.content


async def translate_text(text: str, source_lang: str, target_lang: str = "en") -> dict:
    """NEW -- A1. Reused by Layer 1b (query normalization, Sec 9a) and by
    ingestion-time / retrieval-time evidence normalization (A2/A3, Sec 11/16)."""
    async with httpx.AsyncClient() as client:
        r = await client.post(
            ZIA_TRANSLATE_URL, headers=ZIA_HEADERS_JSON,
            json={"source_language": source_lang, "target_language": target_lang, "text": text},
            timeout=15.0,
        )
        r.raise_for_status()
        return r.json()   # {"translated_text": ..., "processing_time": ...}
```

`[VERIFY]` The exact JSON key names (`transcript`, `translated_text`) are inferred from the model cards' plain-English description, not a captured sample response — grab the real "Sample Request and Response" tab before this ships.

### 5.3 `shared/language_utils.py` `[NEW — A2]`

```python
from langdetect import detect, LangDetectException

VIABLE_LANGUAGES = {"en", "hi", "kn"}  # matches ZIA_VOICE_LANGS above; kept as a
                                        # separate constant so this module stays a
                                        # lightweight, no-network-call utility


def detect_language(text: str) -> str | None:
    """Deterministic, local, no-LLM-call. Never raises."""
    if not text or not text.strip():
        return None
    try:
        return detect(text)
    except LangDetectException:
        return None


def is_viable(language_code: str | None) -> bool:
    """None/undetectable is treated as NOT viable -- safer to attempt
    translation (or flag for review) than to silently assume it's fine."""
    return language_code in VIABLE_LANGUAGES
```

### 5.4 `shared/feedback_models.py` / `shared/feedback_engine.py` `[NEW — A4]`

Full implementation given once, in §13a, rather than duplicated here — this section only lists the files as part of the shared library inventory.

### 5.5 `shared/search_log.py` `[NEW — A10]`

```python
# shared/search_log.py
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional
import uuid

TargetType = Literal["person", "vehicle", "property", "none"]
SearchReason = Literal["routine_stop", "informant_tip", "case_followup", "other"]

@dataclass
class SearchLogEntry:
    """One row per named-entity search. Deliberately NOT gated on a case
    existing -- see Architecture v9 Sec 23 / A10. `target_type="none"` covers
    pattern-level browsing (e.g. "recent thefts in this area") and does not
    require target_id; anything else is expected to carry one."""
    officer_id: str
    target_type: TargetType
    target_id: Optional[str] = None
    linked_case_id: Optional[str] = None
    reason: Optional[SearchReason] = None
    search_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)

def log_search(officer_id: str, target_type: TargetType,
               target_id: str | None = None,
               linked_case_id: str | None = None,
               reason: SearchReason | None = None) -> SearchLogEntry:
    """Writes to Catalyst NoSQL under key `search_log:{officer_id}:{search_id}`.
    Fire-and-forget from the caller's perspective -- never blocks or denies
    the search itself; the point is the trail, not a gate. [VERIFY] Catalyst
    NoSQL write helper name/signature -- reuse whatever backend.py's other
    NoSQL writes already call, not shown in v8's text."""
    entry = SearchLogEntry(officer_id, target_type, target_id, linked_case_id, reason)
    # catalyst_client.nosql_write(f"search_log:{officer_id}:{entry.search_id}", entry)
    return entry
```

**Wiring point:** called from wherever a query resolves to a specific named entity —
most naturally inside `pipeline_function/pipeline/query_understanding/ner_intent.py`
once NER has identified a person/vehicle/property target, or in
`backend/api/routes/query.py` right after intent classification, whichever the real
NER-to-query-route data flow makes cleaner. Neither file's current internals are shown
in v8's text, so the exact call site is `[VERIFY]` — the important constraint is that it
fires once per resolved named-entity target, not once per raw query string, so pattern
browsing doesn't generate log noise.

---

## 6. AppSail Front Door + Signals-Triggered Pipeline Function `[CHANGED — adds A5's route]`

*(Sections "Why This Section Changed," "AppSail Platform Constraints," "Signals Dispatch," "SSE Endpoint," "LangGraph Pipeline," "Cold Starts," "Keep-Warm Health Endpoint" are mostly unchanged from v8 — none of the three addenda touch hosting, dispatch, or the SSE contract, with one exception below.)*

### `[CHANGED]` Signals Payload Serialization (Stringified JSON unwrapping)

**Critical Deployment Fix:** When the AppSail backend dispatches a job via Catalyst Signals webhook, Catalyst wraps the payload in an `events -> data` envelope. Importantly, the `data` itself arrives as a **JSON-stringified string**, not a parsed dictionary. The serverless function handler (`pipeline_function/main.py`) must explicitly run `json.loads(raw_event_data)` before attempting to extract the `job_id`. Failing to do so causes an immediate `TypeError: string indices must be integers` crash on every invocation.

### `[NEW — A5]` Feedback Route

```python
# backend/api/routes/feedback.py

from fastapi import APIRouter, HTTPException
from shared.feedback_models import CorrectionEvent
from shared.feedback_engine import record_feedback_event

router = APIRouter()

@router.post("/api/feedback/correction")
async def submit_feedback(event: CorrectionEvent):
    if event.verdict not in {"confirmed", "corrected"}:
        raise HTTPException(400, "verdict must be 'confirmed' or 'corrected'")
    await record_feedback_event(event)
    return {"status": "recorded"}
```

Registered on the same AppSail FastAPI app as `query.py`, `transcribe.py`, `graph.py`, `health.py` (v8 §2 project structure). Consistent with the thin-front-door principle — this route validates and writes; `record_feedback_event`'s arithmetic is cheap enough to run inline without a Signals round-trip to the pipeline Function.

---

## 7. NER + Intent (GLM-4.7-Flash)

*(Unchanged from v8 — no addendum touches NER/intent extraction itself.)*

---

## 8. LLM Resilience — Caching, Retry, Degradation

*(Unchanged from v8 — the three-layer defense, the 10-minute-stall handling, and the `RateLimitExhaustedError` design are untouched. Note: Zia ASR/TTS/Translate calls are outbound HTTP the same shape as the existing LLM/VLM/KB calls this section already covers — no new resilience pattern needed, same client discipline applies.)*

---

## 9. DAG Planner

*(Unchanged.)*

### 9a. `[NEW]` Layer 1b — Translation Short-Circuit in `preprocessing/normalizer.py`

Placement: only fires when the input language tag is outside `{en, hi, kn}` — a cheap check, not a call on every query, so common-case (Kannada/English/Hindi) latency is unaffected.

```python
# pipeline_function/pipeline/preprocessing/normalizer.py (addition)

from shared.catalyst_client import translate_text, ZIA_VOICE_LANGS

async def normalize_input(text: str, declared_language: str) -> str:
    if declared_language not in ZIA_VOICE_LANGS:
        result = await translate_text(text, source_lang=declared_language, target_lang="en")
        text = result["translated_text"]
    # ... existing transliteration + code-switch normalization steps, unchanged ...
    return text
```

`[VERIFY]` This assumes `normalizer.py`'s current entry point takes raw text + a language tag — v8's text names the file (§2 project structure: "transliteration + code-switch normalization") but doesn't reproduce its current function signature, so confirm the real signature before pasting this in.

---

## 10. Evidence Object `[CHANGED — C2, adds A7]`

**Confirmed current state (v8 lines 929–989):**

```python
@dataclass
class EvidenceItem:
    fir_id:             str
    relevance_score:    float
    sources:            list[str]
    convergent:         bool
    evidence_path:      Optional[str]
    similarity_reason:  Optional[str]
    confidence:         str = "medium"
    confidence_reasons: list[str] = field(default_factory=list)
    confidence_flags:   list[str] = field(default_factory=list)
    fir_date:           Optional[str] = None
    metadata:           dict = field(default_factory=dict)
```

**Target — 6 new fields, everything above unchanged:**

```python
@dataclass
class EvidenceItem:
    fir_id:             str
    relevance_score:    float
    sources:            list[str]
    convergent:         bool
    evidence_path:      Optional[str]
    similarity_reason:  Optional[str]
    confidence:         str = "medium"
    confidence_reasons: list[str] = field(default_factory=list)
    confidence_flags:   list[str] = field(default_factory=list)
    fir_date:           Optional[str] = None
    metadata:           dict = field(default_factory=dict)

    # --- NEW in v9 ---
    edge_type:          Optional[str] = None   # e.g. "SHARED_MO", "CO_ACCUSED", or
                                                 # "NARRATIVE_SIMILARITY" for KB-only hits.
                                                 # A4/A5: lookup key for trust weighting
                                                 # and the unit a correction is scoped to.
    edge_id:            Optional[str] = None   # specific graph edge / KB doc instance.
                                                 # A4: same-session penalty target. A5:
                                                 # what a per-citation correction points at.
    crime_type:         Optional[str] = None   # crime_sub_head_id, for narrow-scope
                                                 # trust weighting (A4)
    language:           Optional[str] = None   # A2/A3: ISO 639-1 tag, set at ingestion
                                                 # or by the retrieval-time fallback
    text_original:      Optional[str] = None   # A2/A3: preserved pre-translation text
    is_translated:      bool = False           # A2/A3
```

**Where `edge_type` should be populated:** `add_graph_results()` (v8 lines 970–985) currently sets `evidence_path` from `result.get("path")` — a human-readable string. `edge_type` should be populated alongside it from the same graph query result (Cypher `type(r)` on the traversed relationship), not parsed back out of `evidence_path` — parsing a display string to recover a value the query already had is unnecessary and brittle.

```python
# v8's add_graph_results (line 970), extended:

def add_graph_results(self, graph_results: list):
    for result in graph_results:
        existing = next((e for e in self.items if e.fir_id == result["fir_id"]), None)
        if existing:
            existing.sources.append("graph")
            existing.convergent = True
            existing.evidence_path = result.get("path")
            existing.edge_type = result.get("edge_type")      # NEW -- straight from the Cypher result
            existing.crime_type = result.get("crime_sub_head_id")  # NEW
            existing.confidence = "high"
            existing.relevance_score = min(existing.relevance_score * 1.3, 1.0)
        else:
            self.items.append(EvidenceItem(
                fir_id=result["fir_id"], relevance_score=result.get("score", 0.7),
                sources=["graph"], convergent=False,
                evidence_path=result.get("path"), similarity_reason=None,
                confidence="medium", metadata=result.get("metadata", {}),
                edge_type=result.get("edge_type"),             # NEW
                crime_type=result.get("crime_sub_head_id"),    # NEW
            ))
```

For RAG-only hits (`add_rag_results`, v8 line 961), set `edge_type="NARRATIVE_SIMILARITY"` as the synthetic type the Reasoning Feedback Loop design (Architecture v9 §19a) expects for KB-sourced matches.

`[VERIFY]` Whether the Cypher query results feeding `add_graph_results` already return `edge_type`/`crime_sub_head_id` in their result rows, or whether the Cypher in `graph/queries.py` needs a `RETURN type(r) as edge_type, ...` addition first — v8 doesn't reproduce the actual Cypher strings for the retrieval queries, only the confidence-engine's post-hoc string parsing of `evidence_path`.

---

## 11. Retrieval Executor — Per-Source Timeouts `[CHANGED — adds A3/A4]`

*(Timeout budgets, `execute_with_timeout`, `execute_retrieval`, and the partial-results-notice mechanism are all unchanged from v8 — none of the three addenda touch retrieval timeout/fail-soft behavior.)*

### `[NEW — A3]` Evidence-Language Fallback

**Why a deterministic rule, not an LLM decision:** letting the LLM notice mid-synthesis that it doesn't recognize evidence and call a translation tool itself was considered and rejected — it violates the "LLM plans and synthesizes, systems retrieve" boundary (Architecture v9 §2) and would add a non-deterministic 4th sequential LLM call on top of a pipeline that already has a documented 10-minute rate-limit stall risk (§8).

```python
# pipeline_function/pipeline/retrieval/translate_evidence_node.py

from shared.language_utils import detect_language, is_viable
from shared.catalyst_client import translate_text


def should_translate_evidence(state: dict) -> str:
    """Deterministic rule-based conditional edge -- NOT an LLM call."""
    for evidence_item in state["retrieved_evidence"]:
        tag = evidence_item.get("language")
        if tag is None:
            tag = detect_language(evidence_item.get("text", ""))
            evidence_item["language"] = tag
        if not is_viable(tag):
            return "translate_evidence_node"
    return "confidence_engine_node"


async def translate_evidence_node(state: dict) -> dict:
    for evidence_item in state["retrieved_evidence"]:
        tag = evidence_item.get("language")
        if tag is not None and not is_viable(tag):
            original_text = evidence_item["text"]
            result = await translate_text(original_text, source_lang=tag, target_lang="en")
            evidence_item["text_original"] = original_text
            evidence_item["text"] = result["translated_text"]
            evidence_item["is_translated"] = True
    return state
```

```python
# Wiring into graph_definition.py's StateGraph -- see the §0 note above:
# the exact existing node name this attaches after ("retrieval_node" below
# is a placeholder for whatever the real node is called) is [VERIFY].

graph.add_node("translate_evidence_node", translate_evidence_node)
graph.add_conditional_edges(
    "retrieval_node",   # [VERIFY] exact name in the real graph_definition.py
    should_translate_evidence,
    {"confidence_engine_node": "confidence_engine_node",
     "translate_evidence_node": "translate_evidence_node"}
)
graph.add_edge("translate_evidence_node", "confidence_engine_node")
```

### `[NEW — A4]` Trust-Weighted Ranking

`EvidenceObject.rank()` (v8 lines 987–988: `self.items.sort(key=lambda x: x.relevance_score, reverse=True)`) stays as the final sort — trust weighting happens *before* it, by adjusting `relevance_score` itself, so no change to `rank()` is needed:

```python
# pipeline_function/pipeline/retrieval/executor.py (addition, runs just
# before evidence.rank() is called in execute_retrieval)

from shared.feedback_engine import get_trust_weight

async def apply_trust_weighting(evidence: EvidenceObject, session_id: str):
    penalized = await _get_session_penalized_ids(f"session_penalty:{session_id}")
    for item in evidence.items:
        trust = await get_trust_weight(item.edge_type or "NARRATIVE_SIMILARITY", item.crime_type)
        session_penalty = 0.5 if item.edge_id in penalized else 1.0
        item.relevance_score = item.relevance_score * trust * session_penalty
    # evidence.rank() is still called afterward, unchanged from v8
```

`[VERIFY]` `_get_session_penalized_ids` needs `session_id` threaded through to wherever `execute_retrieval` is called from — confirm the current call signature has this available (v8's DAG planner output includes `step_id`/`type`/`params`/`depends_on`, but session_id's availability at this exact call site isn't shown in v8's text).

---

## 12. Confidence Engine `[CHANGED — C3]`

**Confirmed current state (v8 lines 1104–1194) — full file reproduced above in v8, formula at lines 1174–1180:**

```python
def compute_confidence(item: EvidenceItem) -> ConfidenceSignal:
    c, cr = compute_source_convergence(item)
    s, sr, sf = compute_evidence_strength(item)
    r, rr = compute_recency(item.fir_date)
    final = (c * 0.45) + (s * 0.40) + (r * 0.15)
    return ConfidenceSignal(tier=assign_tier(final, sf), score=round(final, 3),
                             reasons=cr+sr+rr, flags=sf)

def run_confidence_engine(evidence: EvidenceObject) -> EvidenceObject:
    for item in evidence.items:
        sig = compute_confidence(item)
        item.confidence = sig.tier
        item.relevance_score = sig.score
        item.confidence_reasons = sig.reasons
        item.confidence_flags = sig.flags
        evidence.reasoning_trace.append(...)
    evidence.rank()
    return evidence
```

**Target — `compute_confidence` becomes `async` and folds in `trust_weight`; `run_confidence_engine` becomes `async` to await it. Everything else in the file (`compute_source_convergence`, `compute_evidence_strength`, `compute_recency`, `assign_tier`, the `ConfidenceSignal` dataclass) is unchanged:**

```python
from shared.feedback_engine import get_trust_weight

async def compute_confidence(item: EvidenceItem) -> ConfidenceSignal:
    c, cr = compute_source_convergence(item)          # unchanged
    s, sr, sf = compute_evidence_strength(item)        # unchanged
    r, rr = compute_recency(item.fir_date)             # unchanged
    base_final = (c * 0.45) + (s * 0.40) + (r * 0.15)  # unchanged v8 formula

    trust = await get_trust_weight(item.edge_type or "NARRATIVE_SIMILARITY", item.crime_type)  # NEW
    final = base_final * trust                                                                  # NEW

    return ConfidenceSignal(tier=assign_tier(final, sf), score=round(final, 3),
                             reasons=cr + sr + rr, flags=sf)


async def run_confidence_engine(evidence: EvidenceObject) -> EvidenceObject:
    for item in evidence.items:
        sig = await compute_confidence(item)   # now awaited
        item.confidence = sig.tier
        item.relevance_score = sig.score
        item.confidence_reasons = sig.reasons
        item.confidence_flags = sig.flags
        evidence.reasoning_trace.append(
            f"{item.fir_id}: {sig.tier} ({sig.score:.2f}) -- {'; '.join(sig.reasons[:2])}"
        )
    evidence.rank()
    return evidence
```

**Caller impact:** whatever currently calls `run_confidence_engine(evidence)` synchronously (the LangGraph node wrapping this stage — exact name `[VERIFY]`, same caveat as §11) needs an `await` added. This is the one ripple effect of making trust weighting a real input rather than a cosmetic label — worth grepping for all call sites of `run_confidence_engine` and `compute_confidence` before merging, since v8's text doesn't show every caller.

**Why trust weighting multiplies the *final* score rather than being folded into one of the three existing sub-scores:** it's a fourth, independent signal (accumulated reliability of the methodology) — folding it into, say, `evidence_strength` would conflate "how strong is this type of evidence in principle" with "how reliable has this type of evidence been in practice for this officer base," which are different questions with different update mechanisms (one is a fixed lookup table, Section 10's `compute_evidence_strength`; the other is a live, corrections-driven estimate, §13a).

---

## 13. Synthesis (GLM-4.7-Flash) `[CHANGED — C5]`

**Confirmed current state (v8 lines 1198–1250) — `items_text` formatting at lines 1224–1229:**

```python
items_text = "\n".join([
    f"[{i+1}] FIR:{item.fir_id} Score:{item.relevance_score:.2f} "
    f"Sources:{','.join(item.sources)} Confidence:{item.confidence} "
    f"Path:{item.evidence_path or 'N/A'} Reason:{item.similarity_reason or 'N/A'}"
    for i, item in enumerate(evidence.items[:10])
])
```

**This stays exactly as-is** — the LLM-facing prompt format doesn't need the new structured fields, since the LLM never needs to know `edge_id` (that's a UI/backend concern for routing corrections, not something the model should reason about). What changes is the **return value** of `synthesize()`, so the frontend receives enough structure to build per-citation controls:

**Confirmed current return (v8 lines 1245–1249):**

```python
return {
    "text": text,
    "high_confidence": [e.fir_id for e in evidence.items if e.confidence == "high"],
    "reasoning_trace": evidence.reasoning_trace
}
```

**Target — adds a `citations` array carrying the structured fields A5's UI needs:**

```python
return {
    "text": text,
    "high_confidence": [e.fir_id for e in evidence.items if e.confidence == "high"],
    "reasoning_trace": evidence.reasoning_trace,
    "citations": [                                    # NEW
        {
            "fir_id": e.fir_id,
            "edge_type": e.edge_type,
            "edge_id": e.edge_id,
            "crime_type": e.crime_type,
            "confidence": e.confidence,
        }
        for e in evidence.items[:10]                  # same slice as items_text above
    ],
}
```

`[VERIFY]` per the §0 caveat — confirm this `citations` array actually reaches `EvidenceCitations.jsx` unmodified through whatever serializes the job-status document written to Catalyst NoSQL (§6's `write_job_status`) and read back by AppSail's SSE poller. If an intermediate serializer strips unknown keys, it needs updating too — not shown in v8's text.

---

## 13a. Reasoning Feedback Loop `[NEW SECTION — A4]`

This is the concrete implementation behind Architecture v9 §19a. Placed here, directly after Synthesis, since citations (§13) are the entry point a correction attaches to.

### `shared/feedback_models.py`

```python
from pydantic import BaseModel
from typing import Optional

class CorrectionEvent(BaseModel):
    event_id: str
    session_id: str
    officer_id: str
    timestamp: str
    query_text: str
    edge_type: str
    crime_type: Optional[str] = None
    edge_id: Optional[str] = None
    verdict: str                       # "confirmed" | "corrected"
    explanation: Optional[str] = None  # captured verbatim, never auto-parsed

class MethodologyTrust(BaseModel):
    scope_key: str
    confirmations: int = 0
    corrections: int = 0
```

### `shared/feedback_engine.py`

```python
from shared.catalyst_client import nosql_get, nosql_set
from shared.feedback_models import CorrectionEvent, MethodologyTrust
import json

PRIOR_STRENGTH = 10
PRIOR_TRUST = 0.7
TRUST_WEIGHT_FLOOR = 0.3
MIN_SAMPLES_FOR_NARROW_SCOPE = 15


def _smoothed_trust(confirmations: int, corrections: int) -> float:
    total = confirmations + corrections
    smoothed = (confirmations + PRIOR_STRENGTH * PRIOR_TRUST) / (total + PRIOR_STRENGTH)
    return max(smoothed, TRUST_WEIGHT_FLOOR)


async def _load_trust(scope_key: str) -> MethodologyTrust:
    raw = await nosql_get(f"trust:{scope_key}")
    if raw is None:
        return MethodologyTrust(scope_key=scope_key)
    return MethodologyTrust(**json.loads(raw["value"]))


async def _save_trust(trust: MethodologyTrust):
    await nosql_set(f"trust:{trust.scope_key}", trust.json())


async def get_trust_weight(edge_type: str, crime_type: str | None) -> float:
    if crime_type:
        narrow = await _load_trust(f"{edge_type}::{crime_type}")
        if (narrow.confirmations + narrow.corrections) >= MIN_SAMPLES_FOR_NARROW_SCOPE:
            return _smoothed_trust(narrow.confirmations, narrow.corrections)
    broad = await _load_trust(edge_type)
    return _smoothed_trust(broad.confirmations, broad.corrections)


async def record_feedback_event(event: CorrectionEvent):
    await nosql_set(f"correction:{event.event_id}", event.json())

    is_confirm = event.verdict == "confirmed"
    broad = await _load_trust(event.edge_type)
    if is_confirm: broad.confirmations += 1
    else: broad.corrections += 1
    await _save_trust(broad)

    if event.crime_type:
        narrow = await _load_trust(f"{event.edge_type}::{event.crime_type}")
        if is_confirm: narrow.confirmations += 1
        else: narrow.corrections += 1
        await _save_trust(narrow)

    if not is_confirm and event.edge_id:
        await _apply_session_penalty(event.session_id, event.edge_id)


async def _apply_session_penalty(session_id: str, edge_id: str):
    key = f"session_penalty:{session_id}"
    existing = await nosql_get(key)
    penalized_ids = set(json.loads(existing["value"])) if existing else set()
    penalized_ids.add(edge_id)
    await nosql_set(key, json.dumps(list(penalized_ids)), ttl=3600 * 8)
```

**Sanity-check the smoothing:** zero data → exactly `PRIOR_TRUST` (0.7). One correction, zero confirmations → `(0 + 7) / (1 + 10) = 0.636` — a small nudge, not a collapse.

`nosql_get`/`nosql_set` are the same functions already used by `pipeline_function/pipeline/cache.py` (v8 §8, lines 800–805) — no new NoSQL client code, just new key prefixes (`trust:`, `correction:`, `session_penalty:`).

**Explicitly out of scope for this mechanism** (restated from Architecture v9 §19a so it doesn't creep back in during build): entity-extraction corrections, standalone confidence-tier disputes, narrative/synthesis disagreement (captured as audit-log free text only), and any global confidence-formula coefficient retuning.

---

## 14. Memgraph Integration

*(Unchanged from v8 — Oracle Cloud VM setup, constraints/indexes, MAGE algorithm orchestration untouched by any addendum.)*

---

## 15. Catalyst Data Store — ZTSQL Schema `[CHANGED — adds A2's columns]`

*(Table design otherwise unchanged from v8. New columns on the `cases` table:)*

```sql
ALTER TABLE cases ADD COLUMN narrative_language VARCHAR(8);
ALTER TABLE cases ADD COLUMN narrative_original TEXT;
ALTER TABLE cases ADD COLUMN narrative_is_translated BOOLEAN DEFAULT FALSE;
ALTER TABLE cases ADD COLUMN mo_descriptor_language VARCHAR(8);
ALTER TABLE cases ADD COLUMN mo_descriptor_original TEXT;
ALTER TABLE cases ADD COLUMN mo_descriptor_is_translated BOOLEAN DEFAULT FALSE;
```

`[VERIFY]` ZTSQL's actual `ALTER TABLE` support and column-count limits against an already-populated table — v8's Row Count Re-Estimate (§15, line 1478) covers row caps, not schema-migration mechanics; this is genuinely new ground for the project.

---

## 16. Ingestion Pipeline `[CHANGED — adds A2]`

**Confirmed current state (v8 lines 1489–1495):**

```python
async def ingest_one(fir: FIRSchema):
    await asyncio.gather(
        upload_fir_to_kb(fir),
        write_fir_to_memgraph(fir),
        write_fir_to_ztsql(fir)
    )
```

**Target (v10 — KB upload removed from runtime path):**

```python
# ingestion/pipeline.py

from shared.language_utils import detect_language, is_viable
from shared.catalyst_client import translate_text


async def tag_and_normalize_language(fir: FIRSchema) -> FIRSchema:
    """Unchanged from v9."""
    fir = await _tag_field(fir, field="narrative")
    fir = await _tag_field(fir, field="mo_descriptor")
    return fir


async def _tag_field(fir: FIRSchema, field: str) -> FIRSchema:
    """Unchanged from v9."""
    text = getattr(fir, field)
    if not text:
        return fir
    detected = detect_language(text)
    setattr(fir, f"{field}_original", text)
    setattr(fir, f"{field}_language", detected)
    if is_viable(detected):
        return fir
    result = await translate_text(text, source_lang=detected or "auto", target_lang="en")
    setattr(fir, field, result["translated_text"])
    setattr(fir, f"{field}_is_translated", True)
    return fir


async def ingest_one(fir: FIRSchema):
    fir = await tag_and_normalize_language(fir)   # v9 addition, unchanged
    await asyncio.gather(
        # NOTE [v10]: upload_fir_to_kb() REMOVED from this gather.
        # KB documents are generated separately by generate_kb_upload_files()
        # and uploaded to the Catalyst QuickML console manually before the demo.
        # See Architecture v10 §20a and §16a below.
        write_fir_to_memgraph(fir),   # unchanged structural data
        write_fir_to_ztsql(fir)       # stores both original and canonical text
    )
```

*(Derived edge computation, edge pruning, KB document format, activityScore methodology, bias audit, and ingestion run order are all unchanged from v9 — not touched by any addendum.)*

---

## 16a. `ingestion/kb_writer.py` \u2014 KB Upload File Generator `[NEW \u2014 v10/A14]`

**Replaces** the previous `upload_fir_to_kb()` HTTP call pattern with a file-generation utility. Run once after `ingest_all.py` completes, before the demo.

```python
# ingestion/kb_writer.py

import os
from pathlib import Path
from shared.models import FIRSchema

KB_CHUNK_DIR = Path("data/kb_chunks")
KB_CHUNK_MAX_BYTES = 450_000   # safely under Catalyst's 500KB per-upload limit


def _format_fir_document(fir: FIRSchema) -> str:
    """Formats a single FIR as a plain-text KB document.
    Only includes semantic content (narrative + MO) plus structured
    anchor fields (FIR_ID, DISTRICT, CRIME_TYPE) for cross-referencing.
    All other structured fields (IDs, dates, IPC sections, accused) belong
    in ZTSQL -- not the KB.
    """
    lines = [
        f"FIR_ID: {fir.id}",
        f"DISTRICT: {fir.district}",
    ]
    if fir.crime_type_freetext:
        lines.append(f"CRIME_TYPE: {fir.crime_type_freetext}")
    if fir.mo_descriptor:
        lines.append(f"MO: {fir.mo_descriptor}")
    if fir.narrative:
        lines.append(f"NARRATIVE: {fir.narrative}")
    return "\n".join(lines) + "\n\n---\n\n"


def generate_kb_upload_files(firs: list[FIRSchema]) -> list[Path]:
    """Chunks all FIR documents into files < KB_CHUNK_MAX_BYTES each.
    Returns the list of generated file paths.

    Usage (run after ingest_all.py):
        from ingestion.kb_writer import generate_kb_upload_files
        from ingestion.pipeline import load_all_firs
        paths = generate_kb_upload_files(load_all_firs())
        print(f"Generated {len(paths)} files. Upload each to Catalyst QuickML KB console.")
    """
    KB_CHUNK_DIR.mkdir(parents=True, exist_ok=True)

    chunk_index = 1
    current_chunk = []
    current_bytes = 0
    generated_files = []

    for fir in firs:
        doc = _format_fir_document(fir)
        doc_bytes = len(doc.encode("utf-8"))

        if current_bytes + doc_bytes > KB_CHUNK_MAX_BYTES and current_chunk:
            _write_chunk(current_chunk, chunk_index, generated_files)
            chunk_index += 1
            current_chunk = []
            current_bytes = 0

        current_chunk.append(doc)
        current_bytes += doc_bytes

    if current_chunk:
        _write_chunk(current_chunk, chunk_index, generated_files)

    print(f"[KB] Generated {len(generated_files)} upload file(s) in {KB_CHUNK_DIR}/")
    print(f"[KB] Next step: upload each file to Catalyst QuickML console \u2192 Knowledge Base \u2192 Upload Documents")
    return generated_files


def _write_chunk(docs: list[str], index: int, paths: list[Path]) -> None:
    path = KB_CHUNK_DIR / f"kb_upload_chunk_{index:03d}.txt"
    path.write_text("".join(docs), encoding="utf-8")
    size_kb = path.stat().st_size / 1024
    print(f"[KB] Wrote {path.name} ({len(docs)} docs, {size_kb:.1f} KB)")
    paths.append(path)


# [DEPRECATED -- v10] Runtime upload function. Raises NotImplementedError if called.
async def upload_fir_to_kb(fir: FIRSchema):
    raise NotImplementedError(
        "upload_fir_to_kb() is disabled in v10. Use generate_kb_upload_files() "
        "to produce files for manual console upload. See Architecture v10 \u00a720a."
    )
```

### How to Run

```bash
# After ingest_all.py has completed:
python -c "
from ingestion.kb_writer import generate_kb_upload_files
from ingestion.pipeline import load_all_firs   # [VERIFY] real function name
generate_kb_upload_files(load_all_firs())
"
```

Then upload each `data/kb_chunks/kb_upload_chunk_*.txt` file to the Catalyst QuickML console. After deploying the RAG pipeline, add the endpoint URL and key to `.env`.

`[VERIFY]` The exact function name for loading all generated FIRs from disk \u2014 `load_all_firs()` is a placeholder for whatever `ingest_all.py` or `generate_narratives.py` uses to produce the final `list[FIRSchema]`. Confirm before wiring in.

---

## 17. Schema Mapping Layer

*(Unchanged from v8 — the FIELD_NAME_MAP reconciliation against the real KSP ER diagram is untouched by any of the three addenda.)*

---

## 18. NER Few-Shot Library

*(Unchanged.)*

---

## 19. Evaluation — Breaking Circularity, Trap Scenario, Calibration `[CHANGED — new test cases appended, not a separate pass]`

*(Blind evaluation set, trap scenario, and confidence calibration measurement all unchanged from v8. New test cases from the three addenda are appended to the pre-demo test sequence rather than run as a separate suite — see §25's updated checklist.)*

---

## 20. OCR Layer

*(Unchanged.)*

---

## 21. Input Validation Middleware

*(Unchanged — the size/MIME/denylist limits are untouched. Note: the input validation gate runs before Layer 1, so a query in a non-viable language still passes through validation unchanged; the translation short-circuit, §9a, runs after this gate, not instead of it.)*

---

## 22. RBAC + Audit Logging `[CHANGED — adds A9–A12]`

Base RBAC (rank/case visibility checks) is unchanged from v8 and is governed by
`PS1_RBAC_Case_Access_v1.md`, which is not folded into this file-by-file plan since it
introduces case-management routes not yet present in v8's `backend/api/routes/` (no
`cases.py` exists in the current tree). What follows is only the integrity layer that sits
on top of whatever access check already runs.

### `[NEW — A9]` Hash-chained audit entries — `pipeline_function/pipeline/audit.py`

```python
# pipeline_function/pipeline/audit.py (addition)
# [VERIFY] v8's audit.py internals (current function name for writing an
# entry, exact NoSQL key shape) aren't shown anywhere in v8's ~2,500 lines --
# only referenced by filename in the project tree. The sketch below assumes a
# single write_audit_entry()-style function exists; splice against whatever
# the real one is called.

import hashlib
import json

def _chain_hash(entry: dict, previous_hash: str) -> str:
    """Each entry's hash covers its own content PLUS the previous entry's
    hash, so deleting or reordering a past entry breaks every hash computed
    after it. previous_hash for the very first entry in a chain is a fixed
    genesis constant, not empty string, so an empty chain can't be trivially
    forged as "the start"."""
    payload = json.dumps(entry, sort_keys=True) + previous_hash
    return hashlib.sha256(payload.encode()).hexdigest()

def write_audit_entry(entry: dict, previous_hash: str) -> tuple[dict, str]:
    entry_hash = _chain_hash(entry, previous_hash)
    entry["prev_hash"] = previous_hash
    entry["hash"] = entry_hash
    # catalyst_client.nosql_write(f"audit:{entry['timestamp']}:{entry_hash[:8]}", entry)
    return entry, entry_hash

def verify_chain(entries: list[dict]) -> bool:
    """Recomputes the chain across a full ordered fetch; used by vigilance_cell
    review, not on the hot path of every request."""
    prev = GENESIS_HASH
    for e in entries:
        expected = _chain_hash({k: v for k, v in e.items() if k not in ("hash", "prev_hash")}, prev)
        if expected != e["hash"] or e["prev_hash"] != prev:
            return False
        prev = e["hash"]
    return True

GENESIS_HASH = "0" * 64
```

**Read logging, not just writes:** the same `write_audit_entry()` call now fires on case
views, evidence views, Case Board views, and every `is_sensitive` toggle in either
direction — not only on LLM query synthesis, which is likely all v8's version covered
(unconfirmed, since v8's internals aren't shown — flagged above). Each of these call sites
needs `write_audit_entry` wired in individually; there is no single choke point that
already sees all reads.

**Getting `previous_hash` on every write** requires either (a) a single global "last hash"
pointer read-then-written per entry (a serialization point — every write must know the
prior write's hash before computing its own), or (b) per-officer or per-case sub-chains
if global serialization becomes a bottleneck under concurrent writes. Given this project's
throughput ("lakhs of FIRs," not lakhs of *concurrent* writes at any instant), (a) should
be fine at hackathon scale, but confirm Catalyst NoSQL's actual read-then-write consistency
guarantee before relying on it — `[VERIFY]`, noted in §31.

### `[NEW — A10]` Named-entity search logging

`shared/search_log.py` given in full in §5.5. Wiring point is `[VERIFY]` (see that
section) — either `ner_intent.py` once a person/vehicle/property entity is resolved, or
`backend/api/routes/query.py` right after intent classification.

### `[NEW — A11]` `is_sensitive` downgrade gate — `backend/api/middleware/rbac.py`

```python
# backend/api/middleware/rbac.py (addition)
# [VERIFY] same caveat as audit.py -- v8's rbac.py internals aren't shown in
# v8's text; splice against the real current-officer-context lookup, not a
# guessed one.

def can_downgrade_sensitivity(officer: "OfficerProfile") -> bool:
    return officer.role == "vigilance_cell"

def enforce_sensitivity_change(officer, case, new_value: bool):
    if new_value is False and not can_downgrade_sensitivity(officer):
        raise PermissionError("Only vigilance_cell may lower a case's sensitivity flag.")
    # any officer may raise it (new_value=True) -- no check needed on that path
    write_audit_entry({
        "action": "sensitivity_change",
        "case_id": case.case_id,
        "officer_id": officer.officer_id,
        "new_value": new_value,
    }, previous_hash=...)  # [VERIFY] real previous-hash lookup, see A9
    if new_value is False:
        create_review_queue_item(case, reason="sensitivity_downgrade")  # reuses existing
        # ReviewQueueItem primitive -- [VERIFY] exact constructor, referenced
        # but not shown in v8's text either
```

This assumes a `ReviewQueueItem` primitive exists by the time this ships — not yet in v8's
confirmed tree, and `PS1_RBAC_Case_Access_v1.md`'s case-management routes (`cases.py`)
still don't exist here either. `case.is_sensitive` and `case.department` are no longer an
open gap, though — both are now real fields on `FIRSchema` (Architecture v9 §15), so this
gate has something concrete to check once the case routes land.

### `[NEW — A12]` Append-only evidence

No new file — applies as a rule at every write call site that currently mutates a FIR or
`EvidenceItem` field in place. Concretely: any UPDATE-style write to `narrative`,
`mo_descriptor`, or an evidence field's content should become an INSERT of a new version
row with a `superseded_at`/`supersedes_id` pointer back to the prior version, whose content
and hash stay untouched. `ingestion/pipeline.py`'s A2 handling already does this for
translation (`narrative_original` preserved alongside the translated field) — this
generalizes the same pattern to edits generally, not new code so much as a constraint on
future write paths.

### Explicitly out of scope for the hackathon

Anomaly detection on correction-ratio gaming (A11's threat vector in the integrity doc) is
not being built — no detection code, no new endpoint. Everything it would need
(`CorrectionEvent` volume, override frequency, `SearchLogEntry` volume) is already captured
by A4/A9/A10 without additional work, so this is a documented risk, not a missing feature
someone forgot to build.

---

## 23. Frontend `[CHANGED — C7/C8, adds A5]`

### Component Tree (updated, changes marked)

```
App
  Layout
    Sidebar
    MainPanel
      ChatWindow
        StatusIndicator
        MessageList
          UserMessage
          AssistantMessage
            TextResponse
            ConfidenceBadge
            EvidenceCitations         # CHANGED -- each row now renders CitationFeedback
              CitationFeedback        # NEW -- confirm (✓) / correct (✗) per citation
            ReasoningTrace
        DashboardPanel ...            # unchanged
        InputBar
          TextInput
          VoiceButton                 # CHANGED -- language picker added
          SendButton
```

### `[NEW — A5]` `CitationFeedback.jsx`

```javascript
// frontend/src/components/chat/CitationFeedback.jsx

export function CitationFeedback({ citation, sessionId, officerId, queryText }) {
    const [showExplain, setShowExplain] = useState(false)

    async function submit(verdict, explanation = null) {
        await fetch('/api/feedback/correction', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                event_id: crypto.randomUUID(),
                session_id: sessionId,
                officer_id: officerId,
                timestamp: new Date().toISOString(),
                query_text: queryText,
                edge_type: citation.edge_type,
                crime_type: citation.crime_type,
                edge_id: citation.edge_id,
                verdict,
                explanation,
            }),
        })
        setShowExplain(false)
    }

    return (
        <span className="citation-feedback">
            <button onClick={() => submit('confirmed')} title="Confirm this connection">✓</button>
            <button onClick={() => setShowExplain(true)} title="Flag as incorrect">✗</button>
            {showExplain && (
                <ExplanationModal
                    required
                    onSubmit={(text) => submit('corrected', text)}
                    onCancel={() => setShowExplain(false)}
                />
            )}
        </span>
    )
}
```

Confirm needs no explanation (lightweight positive signal). Correct opens a **required** free-text field — this is what populates `CorrectionEvent.explanation`, stored verbatim, never auto-parsed.

### `[CHANGED — C8]` `VoiceButton.jsx`

**Confirmed current state (v8 line 2368–2370):** "MediaRecorder captures audio → sends to `/api/transcribe` → Catalyst Kannada ASR → text returned to InputBar. No local ASR model." No language selection shown.

**Target:** add a language picker (`en`/`hi`/`kn`) before recording starts — Zia ASR requires a declared language up front, per the real model card (no auto-detect option confirmed). Typed text in a non-{en,hi,kn} language is unaffected by this control — that path goes through the backend's Layer 1b translation short-circuit (§9a) instead, with no frontend change needed since it's already plain text input.

### SSE Event Routing

*(Unchanged from v8 — `progress`/`token`/`evidence`/`visualization`/`done` event names carry the new `citations` array (§13) inside the existing `evidence` event payload; no new SSE event type needed.)*

---

## 24. Build Phases `[CHANGED — new checklist items]`

*(Phases 1–4 structure and gates unchanged from v8. New items to fold into the existing phases, not a new phase:)*

**Phase 1 additions:**
- [ ] `[VERIFY]` Capture real Sample Request/Response for all three Zia model cards (ASR, TTS, Translate) before wiring `catalyst_client.py`'s new functions in earnest
- [ ] Confirm exact `langgraph_router.py`/`graph_definition.py` node names for retrieval and confidence-engine stages, needed for §11/§12's wiring

**Phase 2 additions:**
- [ ] Wire `tag_and_normalize_language` into `ingest_one` (§16), confirm it runs before the three-destination write on real test FIRs
- [ ] `POST /api/feedback/correction` route live, `CorrectionEvent`/`MethodologyTrust` writing to Catalyst NoSQL correctly

**Phase 3 additions:**
- [ ] Trust-weighted ranking (§11) and confidence dampening (§12) live end-to-end — verify with the test cases in §25
- [ ] Per-citation confirm/correct UI wired to real citation data from synthesis (§13)

**Phase 4 additions:**
- [ ] Load-test Zia ASR against real KSP Kanglish recordings (same gap class as GLM-4.7-Flash NER, Architecture v9 §30)
- [ ] Consider seeding synthetic (genuinely representative) correction history so the narrow-scope trust fallback has a chance to activate live during judging, not just show the neutral prior

---

## 25. Pre-Demo Checklist `[CHANGED — new items appended]`

*(All v8 items unchanged. Append:)*

```
New, from the three v9 additions:
  [ ] Zia ASR/TTS/Translate -- confirm CATALYST_ORG_ID is set correctly
      for the production Catalyst org, not left at a dev-org value
  [ ] VoiceButton language picker defaults to a sensible value (kn, given
      KSP context) rather than requiring an officer to select every time
  [ ] Trust-weight scoreboard -- confirm it's NOT accidentally reset between
      dev and prod environments if corrections were seeded for demo purposes
      during development (Catalyst NoSQL keys are environment-scoped --
      confirm seeded trust: keys exist in the SAME environment being demoed)
  [ ] Run through one citation confirm + one citation correct live, end to
      end, before judging starts -- confirms the full A4/A5 loop actually
      writes and (for correct) applies the same-session penalty visibly
```

---

## 26. Testing Checklist `[NEW SECTION — consolidates addenda test cases]`

Appended to the existing chaos/eval test scripts (`verify_stories.py`, `eval_ner.py`) rather than run as a separate pass, per v8's own testing philosophy (§19).

**Evidence-language (A2/A3):**
- [ ] Ingest a synthetic FIR with a Tamil-language `narrative` → confirm `narrative_language == "ta"`, original preserved, canonical field holds the translation
- [ ] Ingest a FIR with an English `narrative` → confirm no unnecessary translation call, `narrative_is_translated == False`
- [ ] Ingest a FIR with empty/`None` `narrative` → confirm no crash
- [ ] Simulate an untagged legacy record reaching the retrieval fallback → confirm `should_translate_evidence` tags and routes correctly
- [ ] Simulate an already-tagged `"kn"` evidence item → confirm it skips `translate_evidence_node` entirely

**Reasoning feedback loop (A4):**
- [ ] Zero corrections for an edge type → `get_trust_weight` returns exactly `PRIOR_TRUST` (0.7)
- [ ] One correction, zero confirmations → trust weight ≈ 0.636, not a collapse
- [ ] >50 consistent corrections → trust weight approaches but never drops below `TRUST_WEIGHT_FLOOR` (0.3)
- [ ] Narrow scope below `MIN_SAMPLES_FOR_NARROW_SCOPE` → falls back to broad edge_type-only weight
- [ ] Same-session correction on a specific `edge_id` → re-running in the same session shows it ranked lower; a new session shows normal rank
- [ ] Free-text explanation stored verbatim, never passed to any LLM call automatically

**Voice/Language (A1):**
- [ ] Zia Translate round-trip on all 8 non-en/hi/kn supported languages, at least a smoke test each
- [ ] VoiceButton without a selected language → sensible default or explicit prompt, never a silent failure

**Integrity & Anti-Corruption (A9–A12):**
- [ ] Write 3 audit entries, delete the middle one directly in NoSQL, run `verify_chain()` → confirm it returns `False`
- [ ] Write 3 audit entries normally, run `verify_chain()` with no tampering → confirm `True`
- [ ] Log a search with `target_type="none"` (pattern browsing) → confirm no `target_id` required, no error
- [ ] Log a search with `target_type="person"` and no `linked_case_id` → confirm it's accepted, not blocked
- [ ] Attempt `enforce_sensitivity_change(new_value=False)` as a non-`vigilance_cell` officer → confirm `PermissionError`
- [ ] Same call as an officer with `role == "vigilance_cell"` → confirm it succeeds and a review-queue item is created
- [ ] Attempt `enforce_sensitivity_change(new_value=True)` as any officer → confirm no role check blocks it

---

## To Discuss / Remaining `[CHANGED — new items appended, all v8 items unchanged]`

*(All prior passes 1–5 from v8 carry forward unchanged — Signals verification, rate-limit design response, KSP schema reconciliation, dev-tier confirmation, etc. New items from this revision:)*

**New, requiring hands-on verification before these additions are considered done, not just designed:**
- [ ] `[VERIFY]` Exact current node names in `graph_definition.py`/`langgraph_router.py` for the retrieval and confidence-engine stages — needed to wire §11's conditional edge and confirm §12's `await` ripple-through
- [ ] `[VERIFY]` Whether `EvidenceItem`'s `evidence_path`/citation data already reaches the frontend today, and through which serializer — needed before §13/§23's citation-structure changes can be pasted in confidently
- [ ] `[VERIFY]` Real Sample Request/Response payloads for all three Zia endpoints (ASR, TTS, Translate) — current JSON key assumptions (`transcript`, `translated_text`) are inferred from prose, not captured
- [ ] `[VERIFY]` ZTSQL's `ALTER TABLE` support/limits on an already-populated table — new ground, not previously needed
- [ ] Whether `backend/` and `pipeline_function/` maintain separate `requirements.txt` files (affects where `langdetect` needs adding) — v8's project structure doesn't show a top-level dependency manifest either way
- [ ] Re-tune `MIN_SAMPLES_FOR_NARROW_SCOPE` / `PRIOR_STRENGTH` once real officer correction volume exists post-hackathon — current values are starting guesses
- [ ] `[VERIFY]` Current `pipeline_function/pipeline/audit.py` and `backend/api/middleware/rbac.py` internals (function names, NoSQL key shape, current officer-context lookup) — §22's A9/A11 sketches are written against the file tree's confirmed *existence*, not confirmed internals, same honesty rule as the two items above
- [ ] Confirm Catalyst NoSQL's read-then-write consistency guarantee before relying on a single global `previous_hash` pointer for the audit chain under concurrent writes (§22, A9)
- [ ] `PS1_RBAC_Case_Access_v1.md`'s case-management routes (`cases.py`, `ReviewQueueItem`) don't exist yet in this file tree — `is_sensitive`/`department` are now defined on `FIRSchema` (Architecture v9 §15), so A11's downgrade gate has fields to check; the routes themselves are still the open dependency
- [ ] Begin wiring all three additions into the real codebase now that Architecture v9 and this document exist as a single consolidated reference — the four standalone addenda documents can be retired once this is confirmed to match the actual repo
