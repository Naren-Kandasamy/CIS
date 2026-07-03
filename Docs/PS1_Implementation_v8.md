# PS-1: Implementation Plan
## Living Document — Clean Revision

---

## 1. Team & Tooling

| Role | Count | Tools |
|---|---|---|
| Full-stack (backend-leaning) | 3 | Claude Code, Antigravity, Copilot |
| Full-stack (frontend-leaning) | 2 | Antigravity, Copilot |

AI-assisted development. Team handles architecture decisions, debugging, integration. Timeline: 25-28 days.

---

## 2. Project Structure

```
ps1-cis/
├── shared/
│   ├── __init__.py
│   ├── models.py             # Pydantic schemas -- FIR, Accused, Location
│   ├── graph_client.py       # Memgraph async driver (run_query, run_write, close)
│   ├── catalyst_client.py    # All Catalyst API calls (LLM, VLM, KB, ASR, TTS, ZTSQL)
│   ├── ner_examples.py       # 30+ few-shot NER examples -- single source of truth
│   └── ner_prompt.py         # builds full prompt from examples + schema + query
│
├── backend/                  # AppSail service -- THIN FRONT DOOR ONLY (Architecture Section 16)
│   ├── main.py               # FastAPI app + lifespan startup
│   ├── api/
│   │   ├── routes/
│   │   │   ├── query.py      # Validates, checks cache, fires Signals Custom Publisher event,
│   │   │   │                 #   holds SSE connection polling job state in NoSQL
│   │   │   ├── transcribe.py # Catalyst ASR proxy
│   │   │   ├── graph.py      # Memgraph graph data endpoint (JSON, not credentials)
│   │   │   └── health.py     # Keep-warm ping target, no expensive calls
│   │   └── middleware/
│   │       ├── input_validator.py  # Size limits, injection denylist, MIME checks
│   │       └── rbac.py             # Role-based access control (gatekeeping, pre-dispatch)
│   │       # NOTE: result audit logging (intent, confidence_breakdown) lives in
│   │       #   pipeline_function/pipeline/audit.py instead -- that data only
│   │       #   exists after the pipeline runs (Section 22)
│   ├── job_dispatch.py        # Fires job to the Signals Custom Publisher REST API URL
│   │                           #   (httpx POST, plain JSON body); does NOT run the pipeline
│   └── sse_poller.py          # Polls Catalyst NoSQL job document on a short
│                               #   interval, forwards transitions as SSE events
│
├── pipeline_function/         # Catalyst Function -- THE ACTUAL PIPELINE
│   │                           #   (15-min budget, triggered as a Signals Function
│   │                           #   target via Custom Publisher -> Rule -> Function;
│   │                           #   NOT a Circuit -- see Architecture Section 16)
│   ├── main.py                # Event function entrypoint -- runs all stages below
│   │                           #   sequentially in one invocation, writing job
│   │                           #   status to NoSQL after each stage
│   ├── pipeline/
│   │   ├── graph_definition.py   # LangGraph state machine
│   │   ├── session.py            # ConversationState + checkpointing
│   │   ├── evidence.py           # EvidenceObject + EvidenceItem dataclasses
│   │   ├── confidence_engine.py  # Three-score confidence computation
│   │   ├── cache.py               # NER+intent response caching (Catalyst NoSQL)
│   │   ├── catalyst_resilient_client.py  # retry/backoff wrapper for all LLM calls
│   │   ├── audit.py               # Tamper-evident result audit logging (Section 22) --
│   │   │                           #   runs here, not AppSail, since intent/confidence
│   │   │                           #   data only exists post-pipeline
│   │   ├── preprocessing/
│   │   │   └── normalizer.py     # transliteration + code-switch normalization
│   │   ├── query_understanding/
│   │   │   ├── ner_intent.py     # Qwen 14B NER + intent (single call)
│   │   │   └── dag_planner.py    # Full LangGraph DAG planner
│   │   ├── retrieval/
│   │   │   ├── graph_client.py   # Memgraph traversal queries
│   │   │   ├── rag_client.py     # Catalyst KB RAG API
│   │   │   ├── sql_client.py     # Catalyst Data Store ZTSQL
│   │   │   └── executor.py       # Parallel asyncio.gather execution + evidence assembly
│   │   └── synthesis/
│   │       ├── synthesizer.py    # Qwen 14B synthesis
│   │       └── xai.py            # confidence signals + reasoning trace
│   └── graph/
│       ├── queries.py            # all Cypher/MAGE query strings
│       └── algorithms.py         # MAGE algorithm orchestration
│
├── ingestion/                 # Offline batch process -- runs via data/scripts/, NOT
│   │                           #   part of the live query path, no AppSail/Event
│   │                           #   Function split needed (see Section 16 below)
│   ├── pipeline.py            # ingestion orchestrator
│   ├── format_detector.py     # JSON / PDF / image routing
│   ├── ocr_extractor.py       # Qwen 7B VLM extraction
│   ├── schema_mapper.py       # CCTNS field names -> canonical
│   ├── validators.py          # Pydantic validation + value normalization
│   ├── entity_resolution.py   # rapidfuzz dedup
│   ├── kb_writer.py           # Catalyst KB upload
│   ├── memgraph_writer.py     # Memgraph structural ingestion
│   ├── sql_writer.py          # ZTSQL inserts
│   └── scoring.py             # activityScore computation
│
├── frontend/
│   └── src/
│       ├── components/
│       │   ├── chat/
│       │   │   ├── ChatWindow.jsx        # SSE consumer + streaming render
│       │   │   ├── MessageList.jsx
│       │   │   ├── AssistantMessage.jsx
│       │   │   ├── ConfidenceBadge.jsx
│       │   │   ├── EvidenceCitations.jsx
│       │   │   └── ReasoningTrace.jsx    # collapsible
│       │   ├── dashboard/
│       │   │   ├── DashboardPanel.jsx    # visualization router
│       │   │   ├── NetworkGraph.jsx      # Cytoscape.js (JSON-fed, no DB connection)
│       │   │   ├── CrimeMap.jsx          # Leaflet.js + OpenStreetMap
│       │   │   ├── TrendChart.jsx        # Recharts
│       │   │   └── DonutChart.jsx        # Recharts
│       │   └── input/
│       │       ├── InputBar.jsx
│       │       └── VoiceButton.jsx       # MediaRecorder -> /api/transcribe
│       ├── services/
│       │   └── queryService.js           # SSE consumer utility -- unaware pipeline
│       │                                 #   moved off AppSail, same event contract
│       └── contexts/
│           ├── SessionContext.jsx        # session_id + message history
│           └── UIContext.jsx             # urgency mode, sidebar state
│
├── data/
│   ├── raw/                              # public data dumps (NCRB, OpenCity)
│   ├── scripts/
│   │   ├── extract_distributions.py     # Phase 1: real distributions
│   │   ├── generate_base_firs.py        # Phase 2: 3,500 base FIRs
│   │   ├── plant_stories.py             # Phase 3: 4 expanded stories
│   │   ├── generate_narratives.py       # Phase 4: Qwen 14B narratives
│   │   ├── ingest_all.py                # Full ingestion orchestrator
│   │   ├── compute_derived_edges.py     # SHARED_MO, SHARED_TATTOO, TEMPORAL_CLUSTER (incremental)
│   │   ├── prune_stale_edges.py         # monthly: archive 2yr+ unreinforced edges
│   │   ├── run_mage_algorithms.py       # MAGE: Louvain, Betweenness, PageRank, WCC
│   │   ├── compute_scores.py            # activityScore per accused
│   │   ├── audit_activity_score_bias.py # bias check across district + age
│   │   ├── verify_stories.py            # assertion suite -- all 4 stories must pass
│   │   ├── eval_ner.py                  # NER evaluation -- 90%+ target
│   │   ├── blind_evaluation_set.py      # generates packet for independent labeling
│   │   ├── plant_trap_scenario.py       # deliberate false-positive test pair
│   │   ├── verify_trap_scenario.py      # MUST PASS -- launch blocker
│   │   ├── measure_confidence_calibration.py  # HIGH tier >=85% check vs blind labels
│   │   └── audit_schema_coverage.py     # surface unknown CCTNS fields
│   └── seed/
│       ├── firs.json                    # generated, no narratives
│       └── firs_with_narratives.json    # final seed file (4,000 FIRs)
│
├── infra/
│   └── catalyst/
│       └── app-config.json
└── docs/
    ├── PS1_Architecture.md
    ├── PS1_Implementation.md
    └── demo-preflight.md
```

**Why the split:** `backend/` deploys to AppSail and only validates, caches, fires the job, and holds the SSE connection -- it never runs NER, planning, retrieval, or synthesis directly. `pipeline_function/` deploys as a Catalyst Function (15-minute budget), triggered as a **Signals Function target** -- a Custom Publisher in Signals receives the job from AppSail and a Rule routes it to this Function. This is **not** a Circuit (Circuits are unavailable in the IN data center this project runs in, and even where available only execute 30s-capped Basic I/O functions) and **not** a Custom Event Listener (Catalyst Event Listeners, including Custom Event Listeners, are a deprecated component that reached End-Of-Life on 30 April, 2026 -- new Catalyst projects cannot access them). See Architecture Section 16 for the full verified rationale, including both corrections this design went through. The pipeline logic itself (LangGraph state machine, confidence engine, retrieval clients) is unchanged from the original design -- only its deployment target and trigger mechanism moved.

---

## 3. Team Ownership

| Person | Primary Module | Secondary |
|---|---|---|
| Naren | Pipeline orchestration (LangGraph), DAG planner, integration | API layer |
| Backend 2 | Memgraph schema, Cypher queries, MAGE algorithms | Derived edge computation |
| Backend 3 | Ingestion pipeline, schema mapper, data generation | ZTSQL layer |
| Frontend 1 | Chat UI + SSE integration | Voice input |
| Frontend 2 | Dashboard panels (Cytoscape, Leaflet, Recharts) | PDF export |

### Integration Contracts (freeze Week 1)

- Graph node/edge schema -- Backend 2 <-> Backend 3
- API response shapes (Evidence Object JSON) -- Naren <-> Frontend 1
- Dashboard data payloads -- Naren <-> Frontend 2

---

## 4. Environment Variables

AppSail backend (`backend/.env`) -- thin front door only, no LLM/VLM/KB/SQL endpoints needed since it never calls them directly:
```
CATALYST_API_TOKEN=
CATALYST_SIGNALS_PUBLISHER_URL=  # Signals Custom Publisher REST API URL -- fires the job.
                                   #   IMPORTANT: dev and prod environments have DIFFERENT
                                   #   URLs for the same publisher (confirmed via official
                                   #   docs) -- must be swapped, not just re-pointed at a
                                   #   different host, when promoting to production
CATALYST_NOSQL_URL=              # for cache check + job-state polling
CATALYST_PROJECT_ID=
SESSION_SECRET=
ENVIRONMENT=development
```

Pipeline Function (`pipeline_function/.env`) -- the actual pipeline, needs every Catalyst API client:
```
CATALYST_API_TOKEN=
CATALYST_LLM_ENDPOINT=
CATALYST_VLM_ENDPOINT=
CATALYST_KB_ENDPOINT=
CATALYST_ASR_ENDPOINT=
CATALYST_TTS_ENDPOINT=
CATALYST_DATASTORE_URL=
CATALYST_NOSQL_URL=
CATALYST_PROJECT_ID=
MEMGRAPH_URI=bolt://your-oracle-vm-ip:7687
MEMGRAPH_USERNAME=
MEMGRAPH_PASSWORD=
ENVIRONMENT=development
```

Frontend (.env):
```
VITE_API_BASE_URL=https://your-appsail.catalyst.zoho.com
```

No DB credentials in frontend. Frontend talks to AppSail only -- never directly to Signals, the pipeline Function, or NoSQL. See Architecture Section 16 for the full hosting rationale: AppSail is a thin front door that validates, checks cache, and fires a Signals Custom Publisher event; the actual pipeline runs as a Signals Function target with its own environment and full set of Catalyst client credentials.

---


## 5. shared/ Library

### shared/models.py

Single source of truth for all data schemas. **Updated against the official KSP ER diagram** -- the original single `accused` list with a `role` field has been split into three genuinely distinct entities (`Victim`, `Complainant`, `Accused`), matching the real schema's separate tables. See Implementation Section 17 for the full reconciliation and the open decisions this raises (demographic fields, district attribution, node modeling in Memgraph).

```python
from pydantic import BaseModel, validator
from typing import Optional

DISTRICT_CANONICAL = {
    "mysore": "Mysuru", "mysuru": "Mysuru",
    "mandya": "Mandya",
    "bangalore": "Bengaluru", "bengaluru": "Bengaluru",
    "shimoga": "Shivamogga", "shivamogga": "Shivamogga",
    "hubli": "Hubballi", "hubballi": "Hubballi"
}

# NOTE: CRIME_TYPE_CANONICAL (free-text crime type normalization) is no
# longer the primary classification path -- the real schema uses
# CrimeHeadID -> CrimeSubHeadID lookups instead of a flat crime_type string
# (Implementation Section 17, Structural Difference #2). Kept here only as
# a fallback for free-text narrative parsing where no CrimeSubHeadID is
# available yet (e.g. raw OCR'd FIR text before classification).
CRIME_TYPE_CANONICAL = {
    "chain snatching": "chain_snatching",
    "chain-snatching": "chain_snatching",
    "burglary": "burglary", "house breaking": "burglary",
    "vehicle theft": "vehicle_theft", "auto theft": "vehicle_theft",
    "assault": "assault", "robbery": "robbery",
    "fraud": "fraud", "cheating": "fraud"
}

class VictimSchema(BaseModel):
    victim_id: str
    name: str
    age_years: Optional[int] = None
    gender_id: Optional[str] = None
    is_police: bool = False

class ComplainantSchema(BaseModel):
    complainant_id: str
    name: str
    age_years: Optional[int] = None
    occupation_id: Optional[str] = None
    # religion_id, caste_id deliberately omitted here -- see Implementation
    # Section 17 Open Decision 1. Add explicitly, with a documented reason,
    # if the team decides PS-1 should ingest these rather than dropping them
    # at the ingestion boundary.
    gender_id: Optional[str] = None

class AccusedSchema(BaseModel):
    accused_id: str
    name: str
    sort_label: Optional[str] = None  # "A1", "A2" -- display order from source data
    aliases: list[str] = []
    age_years: Optional[int] = None
    gender_id: Optional[str] = None
    tattoos: list[str] = []
    prior_fir_count: int = 0
    is_primary_accused: bool = True
    complainant_is_also_accused: bool = False

class ArrestSurrenderSchema(BaseModel):
    arrest_surrender_id: str
    accused_id: str
    arrest_or_surrender_type_id: Optional[str] = None
    arrest_surrender_date: Optional[str] = None
    arrest_district_id: Optional[str] = None  # can differ from the case's filing
                                                 # district -- Implementation Section 17
                                                 # Open Decision 3
    investigating_officer_id: Optional[str] = None

class FIRSchema(BaseModel):
    id: str                       # our surrogate key (fir_internal_id)
    crime_no: str                 # real KSP composite key -- see parse_crime_no()
    case_no: Optional[str] = None
    date: str                     # registered_date
    crime_head_id: Optional[str] = None      # major classification (was flat crime_type)
    crime_sub_head_id: Optional[str] = None  # minor classification (was flat crime_type)
    crime_type_freetext: Optional[str] = None  # fallback only, see CRIME_TYPE_CANONICAL note above
    district: str                 # derived via unit_id -> Unit -> DistrictID, not a source field directly
    unit_id: str                  # police station -- was "station" (flat string) before
    lat: Optional[float] = None
    lon: Optional[float] = None
    victims: list[VictimSchema] = []
    complainants: list[ComplainantSchema] = []
    accused: list[AccusedSchema] = []
    arrest_surrenders: list[ArrestSurrenderSchema] = []
    act_sections: list[tuple[str, str]] = []  # (act_code, section_code) pairs -- was flat ipc_sections string
    status: str = "open"
    mo_descriptor: str = ""
    narrative: Optional[str] = None
    ocr_extracted: bool = False

    @validator('district', pre=True)
    def canonicalize_district(cls, v):
        return DISTRICT_CANONICAL.get(str(v).strip().lower(), str(v).strip())
```

### shared/graph_client.py

```python
from neo4j import AsyncGraphDatabase  # neo4j driver works with Memgraph bolt
import os

_driver = None

async def get_driver():
    global _driver
    if _driver is None:
        _driver = AsyncGraphDatabase.driver(
            os.getenv("MEMGRAPH_URI"),
            auth=(os.getenv("MEMGRAPH_USERNAME", ""),
                  os.getenv("MEMGRAPH_PASSWORD", ""))
        )
    return _driver

async def run_query(cypher: str, params: dict = {}) -> list:
    driver = await get_driver()
    async with driver.session() as session:
        result = await session.run(cypher, params)
        return [record.data() async for record in result]

async def run_write(cypher: str, params: dict = {}):
    driver = await get_driver()
    async with driver.session() as session:
        await session.execute_write(lambda tx: tx.run(cypher, params))

async def close():
    global _driver
    if _driver:
        await _driver.close()
        _driver = None
```

### shared/catalyst_client.py

```python
import httpx, os, base64

CATALYST_TOKEN         = os.getenv("CATALYST_API_TOKEN")
CATALYST_LLM_URL       = os.getenv("CATALYST_LLM_ENDPOINT")
CATALYST_VLM_URL       = os.getenv("CATALYST_VLM_ENDPOINT")
CATALYST_KB_URL        = os.getenv("CATALYST_KB_ENDPOINT")
CATALYST_ASR_URL       = os.getenv("CATALYST_ASR_ENDPOINT")
CATALYST_TTS_URL       = os.getenv("CATALYST_TTS_ENDPOINT")
CATALYST_DATASTORE_URL = os.getenv("CATALYST_DATASTORE_URL")

HEADERS = {
    "Authorization": f"Zoho-oauthtoken {CATALYST_TOKEN}",
    "Content-Type": "application/json"
}

async def llm_complete(prompt: str, system: str,
                        temperature: float = 0.1, max_tokens: int = 1000) -> str:
    async with httpx.AsyncClient() as client:
        r = await client.post(CATALYST_LLM_URL, headers=HEADERS, json={
            "model": "qwen-14b-instruct", "system": system,
            "prompt": prompt, "temperature": temperature, "max_tokens": max_tokens
        }, timeout=30.0)
        r.raise_for_status()
        return r.json()["output"]

async def vlm_extract(image_bytes: bytes, prompt: str, system: str) -> str:
    image_b64 = base64.b64encode(image_bytes).decode()
    async with httpx.AsyncClient() as client:
        r = await client.post(CATALYST_VLM_URL, headers=HEADERS, json={
            "model": "qwen-7b-vlm", "system": system, "image": image_b64,
            "prompt": prompt, "temperature": 0.0, "max_tokens": 1000
        }, timeout=45.0)
        r.raise_for_status()
        return r.json()["output"]

async def kb_upload(document_id: str, content: str, metadata: dict):
    async with httpx.AsyncClient() as client:
        r = await client.post(CATALYST_KB_URL + "/documents", headers=HEADERS,
            json={"document_id": document_id, "content": content, "metadata": metadata},
            timeout=15.0)
        r.raise_for_status()

async def kb_search(query: str, top_k: int = 10) -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.post(CATALYST_KB_URL + "/search", headers=HEADERS,
            json={"query": query, "top_k": top_k}, timeout=15.0)
        r.raise_for_status()
        return r.json()

async def ztsql_query(sql: str, params: list = []) -> list:
    async with httpx.AsyncClient() as client:
        r = await client.post(CATALYST_DATASTORE_URL + "/query", headers=HEADERS,
            json={"query": sql, "params": params}, timeout=15.0)
        r.raise_for_status()
        return r.json()["rows"]

async def ztsql_execute(sql: str, params: list = []):
    async with httpx.AsyncClient() as client:
        r = await client.post(CATALYST_DATASTORE_URL + "/execute", headers=HEADERS,
            json={"query": sql, "params": params}, timeout=15.0)
        r.raise_for_status()

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

---

## 6. AppSail Front Door + Signals-Triggered Pipeline Function

### Why This Section Changed (Twice)

The original design ran LangGraph end-to-end inside one AppSail request, streaming intermediate steps over SSE as the graph executed. That design assumed the entire pipeline -- NER, planning, retrieval, confidence, synthesis -- could fit in AppSail's 30-second hard timeout. Three sequential Qwen 14B calls plus retries made that a real risk on analytical queries, not just an edge case.

**First fix:** AppSail stopped running the pipeline; a Custom Event Listener fired a job to a plain Catalyst Event Function with a 15-minute budget instead of 30 seconds.

**Second fix (this revision):** further verification found Catalyst Event Listeners -- including Custom Event Listeners -- are a deprecated component that reached End-Of-Life on 30 April, 2026. New Catalyst projects cannot access them at all. The trigger mechanism below has been corrected to use **Catalyst Signals** instead: a Custom Publisher receives the job from AppSail, a Rule routes it to a Function target, and that Function target carries the same confirmed 15-minute budget the design has relied on throughout. See Architecture Section 16 for the full verified rationale behind both corrections.

**What's unchanged across both fixes:** AppSail validates, checks cache, fires the job, and holds the SSE connection -- it never runs NER, planning, retrieval, or synthesis itself. The actual LangGraph execution runs inside a single Function invocation with a 15-minute budget. This is **not** wrapped in a Circuit -- Circuits only execute 30s-capped Basic I/O functions and are unavailable in the IN data center this project runs in.

### AppSail Platform Constraints (Verified)

AppSail and Serverless Functions both have a 30-second hard request timeout -- not a difference between them. AppSail is chosen for the front door specifically because it supports persistent-process patterns (FastAPI, connection pooling, a warm SSE loop holding many open officer connections) rather than per-invocation function semantics. It no longer needs LangGraph compiled in-process, since LangGraph now runs inside the pipeline Function, not on AppSail.

Confirmed platform behavior:
- Cold start on first request to an inactive app -- standard serverless on-demand spawning
- Instance stays active **5 minutes** once spawned, serves any requests in that window
- App must bind its listening port within **10 seconds** of spawn or the instance is killed
- Every request -- cold or warm -- still subject to the 30-second hard timeout
- Functions triggered as a Signals Function target (the pipeline's new home) get a **15-minute** dispatch budget instead -- confirmed via official Catalyst docs (Signals' own target-timeout table), this is the structural fix that makes the redesign work

**This makes the field_urgent <10s and analytical <30s targets still meaningful UX goals, but no longer platform-enforced AppSail constraints** -- the pipeline itself now has 15 minutes of headroom inside the Function. Per-source retrieval timeouts (Section 11) still matter for keeping total pipeline latency low, just not because of a 30s AppSail wall anymore.

### Signals Dispatch (AppSail side)

AppSail checks for an identical recent query before dispatching a new job -- this is a distinct, coarser cache from the NER+intent cache inside the pipeline (Section 8 Layer 1): it short-circuits the *entire* pipeline for a repeated question, not just the NER call, which matters most during demo open-floor segments where judges often ask similar things in sequence.

```python
# backend/job_dispatch.py

import httpx
import uuid
import hashlib

SIGNALS_PUBLISHER_URL = settings.CATALYST_SIGNALS_PUBLISHER_URL
# Confirmed limits (Signals Custom Publisher, official docs):
#   500 requests/minute (locks 60s if exceeded -- far above demo query volume)
#   64KB max payload per event -- comfortably above query+session_id JSON
QUERY_CACHE_TTL_SECONDS = 300  # short window -- this is a "just asked this" cache,
                                 # not the longer-lived NER cache inside the pipeline

def query_cache_key(query: str) -> str:
    normalized = query.strip().lower()
    digest = hashlib.sha256(normalized.encode()).hexdigest()[:16]
    return f"cache:full_query:{digest}"

async def dispatch_query_job(session_id: str, query: str) -> str:
    """
    Checks for a recent identical query first (full-pipeline short-circuit).
    If not cached, posts the job as an event to the Signals Custom Publisher
    and returns immediately -- does NOT wait for the pipeline, which runs
    separately as the Signals Function target.
    """
    cached = await nosql_get(query_cache_key(query))
    if cached:
        job_id = str(uuid.uuid4())
        cached_result = json.loads(cached["value"])
        await write_job_status(job_id, session_id, query, status="done", result=cached_result)
        return job_id

    job_id = str(uuid.uuid4())
    await write_job_status(job_id, session_id, query, status="queued")

    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.post(
            SIGNALS_PUBLISHER_URL,
            json={
                "job_id": job_id,
                "session_id": session_id,
                "query": query,
            },
        )
        response.raise_for_status()  # confirms Signals accepted the event (200),
                                       # not that the pipeline has finished. The
                                       # Rule configured in the Signals console
                                       # routes this event to the Function target --
                                       # no rule_identifier needed in the body, unlike
                                       # the old Custom Event Listener contract; routing
                                       # is configured in the console, not the payload.

    return job_id
```

**Where the cache gets populated:** the pipeline Function writes to `cache:full_query:{digest}` as part of its final `status="done"` write (see the handler just below), so the *next* AppSail dispatch for the same query text hits this short-circuit. This is a small addition to that handler -- not a separate write path.

### SSE Endpoint -- Polls Job State, Doesn't Run the Pipeline

```python
# backend/api/routes/query.py

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse
import asyncio
import json

router = APIRouter()

@router.post("/api/query")
async def query(request: QueryRequest):
    job_id = await dispatch_query_job(request.session_id, request.query)
    return EventSourceResponse(stream_job_status(job_id))

async def stream_job_status(job_id: str):
    """
    Polls the Catalyst NoSQL job document on a short interval and forwards
    meaningful status transitions as SSE events. The pipeline Function (not
    this endpoint) is what actually advances `status` through the pipeline stages.
    """
    last_status = None
    while True:
        job = await read_job_status(job_id)

        if job["status"] != last_status:
            last_status = job["status"]
            yield {"event": "progress", "data": json.dumps({"status": job["status"]})}

        if job["status"] == "done":
            yield {"event": "evidence", "data": json.dumps(job["result"]["evidence"])}
            if job["result"].get("visualization"):
                yield {"event": "visualization", "data": json.dumps(job["result"]["visualization"])}
            yield {"event": "token", "data": json.dumps({"token": job["result"]["answer"]})}
            yield {"event": "done", "data": "{}"}
            break

        if job["status"] == "failed":
            yield {"event": "error", "data": json.dumps({"error": job["error"]})}
            break

        await asyncio.sleep(0.5)  # poll interval -- widen if NoSQL read latency
                                    # turns out higher than assumed (Architecture Section 16)
```

This endpoint never imports or calls LangGraph, Qwen, Memgraph, or the KB directly -- it only talks to Catalyst NoSQL and the Signals Custom Publisher URL. The SSE event names (`progress`, `evidence`, `visualization`, `token`, `done`) are chosen to be a close match to the original token-streaming design so `frontend/src/services/queryService.js` needs minimal changes (see Section 23).

### LangGraph Pipeline -- Now Inside a Signals-Triggered Function

```python
# pipeline_function/main.py -- Catalyst Function entrypoint, configured in the
# Signals console as the Function target for the "cis_query_rule" Rule
#
# CONSOLE-VERIFIED 28 June 2026: the function signature and payload shape below
# are confirmed against a real deployed Function (ps_1_cis_function), not assumed
# from docs. event.get_raw_data() returns Catalyst's full Signals envelope, NOT
# just the JSON body that was POSTed to the publisher -- the actual job fields
# are nested under raw_data['events'][0]['data']. An earlier draft of this
# handler assumed event_data["job_id"] worked directly at the top level; it
# does not, and has been corrected below based on a real captured payload:
#
#   {'version': 1, 'account': {...}, 'events': [{'id': '...', 'time_in_ms': '...',
#    'event_config': {'id': '...', 'api_name': 'query_job'},
#    'source': 'publisher_id:.../service:custom',
#    'data': {'job_id': 'test-1', 'query': 'test query', 'session_id': 'test-session'}}],
#    'rule_id': '...', 'target_id': '...', 'attempt': 1}

import logging
logger = logging.getLogger()

def handler(event, context):
    """
    Triggered as a Signals Function target -- invoked when the Rule routes an
    event from the Custom Publisher here. Runs the full LangGraph pipeline
    inside this single invocation. Console-confirmed: a 60-second test
    invocation completed with 0 timeouts and 0 errors (platform dashboard:
    Total Invocations 1, Avg. Invocation Time 60.02s) -- ruling out a 30-second-
    style cap on this Function type. A follow-up test called
    context.get_max_execution_time_ms() directly from inside a running
    invocation: it returned 900000ms -- exactly 15 minutes, confirmed
    from the platform's own SDK, not inferred. A ~400-second sleep in the
    same run completed cleanly with no timeout, consistent with this figure.
    """
    raw_data = event.get_raw_data()
    job_data = raw_data['events'][0]['data']

    job_id = job_data["job_id"]
    session_id = job_data["session_id"]
    query = job_data["query"]
    logger.info(f"Received job {job_id} for session {session_id}")

    import asyncio
    asyncio.run(_run_pipeline(job_id, session_id, query))
    context.close_with_success()

async def _run_pipeline(job_id: str, session_id: str, query: str):
    try:
        config = {"configurable": {"thread_id": session_id}}
        input_state = {"query": query}

        async for step_name, step_output in run_pipeline_stages(input_state, config):
            await write_job_status(job_id, status=f"{step_name}_complete", partial=step_output)

        final = await get_final_state(input_state, config)
        await write_job_status(job_id, status="done", result=final)
        await nosql_set(query_cache_key(query), json.dumps(final), ttl=QUERY_CACHE_TTL_SECONDS)
        # ^ populates the short-window full-query cache that AppSail's
        #   job_dispatch.py checks before firing the next job (Section 6 above)

    except Exception as e:
        await write_job_status(job_id, status="failed", error=str(e))
```

LangGraph is compiled once per Event Function cold start (same `build_pipeline_graph()` as before, just relocated from `backend/main.py` to `pipeline_function/main.py`), and session isolation via `thread_id = session_id` is unchanged:

```python
config = {"configurable": {"thread_id": session_id}}
async for event in pipeline.astream_events(input_state, config=config, version="v2"):
    ...
```

### LangGraph Pipeline Structure (Unchanged)

```
normalize -> ner_intent -> dag_planner -> retrieval -> confidence -> synthesis
                                                                        |
                                    (analytical) -> viz_builder -> END
                                    (field_urgent)               -> END
```

The graph topology, node logic, and resilience wrapper (Section 8) are unchanged from the original design -- only the deployment boundary moved.

### Cold Starts -- Now Split Across Two Services

Cold-start mitigation now applies separately to each service:

**AppSail (front door):** narrower scope than before -- it no longer needs to warm Memgraph or do a full Catalyst LLM round-trip before serving traffic, since it doesn't call those directly anymore. It only needs the NoSQL client and the Signals Custom Publisher URL ready, which makes the 10-second port-binding window easier to respect.

```python
# backend/main.py

from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Lightweight -- just confirm NoSQL client + Signals publisher URL are configured.
    # No Memgraph handshake, no LLM ping -- those now live in pipeline_function/.
    await init_nosql_client()
    yield
    await close_nosql_client()

app = FastAPI(lifespan=lifespan)
```

**Pipeline Event Function:** this is where the original heavy warm-up logic (Memgraph handshake, Catalyst LLM/KB ping) now belongs, since it's where those connections are actually used:

```python
# pipeline_function/main.py -- run once per cold start, before handling events

async def warm_connections():
    try:
        await init_memgraph()
        from shared.graph_client import run_query
        await run_query("RETURN 1 as warmup")

        from shared.catalyst_client import llm_complete, kb_search
        await llm_complete(prompt="ping", system="Respond with OK.", max_tokens=5)
        await kb_search(query="warmup", top_k=1)
    except Exception as e:
        print(f"Warm-up failed (non-fatal, will retry on first real invocation): {e}")
```

Event Functions don't have the same 10-second port-bind constraint as AppSail (they're not serving HTTP directly), so there's more slack here than there was under the old single-AppSail design -- but a cold pipeline function is still slower on its first invocation after idling, so a keep-warm strategy is still worth having. **Partially resolved:** cold starts on Catalyst Functions are confirmed real by independent developer reports ("you will notice a delay if a function hasn't been used for a while"), but no official spec was found stating the exact idle threshold before a Function goes cold, unlike AppSail's documented 5-minute instance lifetime. **Still open:** without a documented idle threshold, there's no way to set a keep-warm ping interval with confidence the way AppSail's was set to exactly 5 minutes. Treat this as something to observe empirically once the Function is deployed (note the gap between idle queries and when a delay reappears) rather than something derivable from docs alone.

### Keep-Warm Health Endpoint (AppSail)

```python
# backend/api/routes/health.py

from fastapi import APIRouter

router = APIRouter()

@router.get("/health")
async def health_check():
    """
    Cheap endpoint for keep-warm pings -- no Memgraph or Catalyst calls,
    no NoSQL reads beyond a trivial connectivity check.
    Pinged externally every 5 minutes (the exact AppSail instance
    lifetime) to prevent cold starts during operation/judging.
    """
    return {"status": "ok"}
```

```yaml
# .github/workflows/keep-warm.yml
name: Keep AppSail Warm
on:
  schedule:
    - cron: '*/5 * * * *'   # every 5 minutes -- matches AppSail instance lifetime exactly
jobs:
  ping:
    runs-on: ubuntu-latest
    steps:
      - name: Ping health endpoint
        run: curl -f https://your-appsail.catalyst.zoho.com/health
```

Must be active well before judging -- not switched on minutes before the demo, since the first ping cycle still pays one cold start. The pipeline Function's own cold-start behavior should be observed empirically during Phase 1-2 build (no documented idle threshold exists to plan a ping interval against, see Section 6) -- if delays are noticeable, add a second lightweight ping target once a reasonable interval has been observed rather than guessed.

---

## 7. NER + Intent (Qwen 14B)

Single call, temperature 0.0, combined NER + intent output. Uses the resilient LLM client (Section 8) so rate limits don't crash the request.

```python
from pipeline.catalyst_resilient_client import llm_complete_resilient as llm_complete
from shared.ner_prompt import build_ner_prompt, NER_INTENT_SYSTEM
import json, re

async def extract_ner_and_intent(normalized_query: str) -> dict:
    prompt = build_ner_prompt(normalized_query)
    raw = await llm_complete(prompt=prompt, system=NER_INTENT_SYSTEM,
                              temperature=0.0, max_tokens=500)
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            return json.loads(match.group())
        # Graceful fallback -- do not crash
        return {
            "entities": {"persons": [], "locations": [], "fir_ids": [],
                         "dates": [], "ipc_sections": [], "crime_types": []},
            "intent": "lookup", "urgency": "analytical",
            "sub_intents": ["broad_search"], "fallback": True
        }
```

### New Gap Surfaced by the KSP Schema Correction -- Entity-to-Lookup Resolution

**This did not exist as a problem before the schema correction.** Under the original guessed schema, NER extracted `crime_types: ["murder"]` / `ipc_sections: ["302"]` as free text, and the (also-guessed) `firs` table stored `crime_type`/`ipc_sections` as flat strings -- free text matched free text directly, no resolution step needed. The real schema replaces both with lookup-driven IDs (`CrimeSubHeadID` via `CrimeHead`/`CrimeSubHead`, and `(ActCode, SectionCode)` pairs via `Act`/`Section`) -- so an officer saying "murder cases" or "section 302" now produces NER text that has no direct column to match against. **Nothing in the current design resolves this gap.** `entity_resolution.py` (Section 16/22) only handles accused-name fuzzy-dedup during *ingestion*; there is no equivalent for resolving NER-extracted crime-type/section text into real lookup IDs at *query time*.

**What's needed, to be built during Phase 2 alongside the DAG planner (not yet written):**

```python
# pipeline_function/pipeline/query_understanding/entity_lookup_resolver.py
# NEW MODULE -- does not exist yet, needs to be built

async def resolve_crime_sub_head(crime_type_text: str) -> str | None:
    """
    "murder" -> CrimeSubHeadID, via fuzzy match against crime_sub_heads.crime_sub_head_name.
    Returns None if no confident match -- caller decides whether to fall back
    to free-text narrative search (RAG) instead of a structured filter.
    """
    ...

async def resolve_act_section(ipc_section_text: str) -> tuple[str, str] | None:
    """
    "302" -> ("IPC", "302"), via lookup against sections.section_code,
    defaulting to act_code="IPC" when the officer doesn't name the act
    explicitly (the overwhelming majority of spoken/typed references --
    confirm this assumption holds once real query samples exist, since
    NDPS/other-act section numbers can collide with IPC numbering).
    """
    ...
```

**Where this plugs in:** between NER+Intent (this section) and the DAG planner (Section 9) -- the DAG planner currently receives the raw `intent_object` straight from NER and passes `crime_types`/`ipc_sections` text directly into step `params` with no resolution in between. This resolver should run first, attaching resolved `crime_sub_head_id`/`act_section` IDs alongside the original free text, so SQL/graph retrieval steps can filter on real IDs while RAG retrieval can still fall back to the original free text for narrative similarity search when no confident lookup match exists.

**Open question, not yet decided:** what happens when resolution fails or is ambiguous (e.g. "theft" could plausibly map to several `CrimeSubHead` rows, or an officer's phrasing doesn't closely match any lookup value)? Options: (a) fall back to RAG-only retrieval for that entity, accepting lower precision, (b) ask the DAG planner to treat it as unresolved and skip structured filtering on that entity, (c) surface a clarifying question to the officer. This wasn't a design question before the schema correction since free text never needed resolving -- worth deciding deliberately rather than discovering the failure mode mid-build.

---

## 8. LLM Resilience -- Caching, Retry, Degradation

Every query makes three separate Qwen 14B calls (NER+intent, DAG planning, synthesis). A rate limit hit on any one breaks the response unless handled. Three layers of defense, applied across all three call sites.

### Layer 1 -- Response Caching (NER+Intent)

```python
# pipeline_function/pipeline/cache.py

import hashlib, json
from shared.catalyst_client import nosql_get, nosql_set

CACHE_TTL_SECONDS = 3600  # 1 hour -- entity/intent extraction is stable per query text

def cache_key(query: str, cache_type: str) -> str:
    normalized = query.strip().lower()
    hash_digest = hashlib.sha256(normalized.encode()).hexdigest()[:16]
    return f"cache:{cache_type}:{hash_digest}"

async def get_cached_ner(query: str) -> dict | None:
    cached = await nosql_get(cache_key(query, "ner_intent"))
    return json.loads(cached["value"]) if cached else None

async def set_cached_ner(query: str, result: dict):
    await nosql_set(cache_key(query, "ner_intent"), json.dumps(result), ttl=CACHE_TTL_SECONDS)
```

Wired into `extract_ner_and_intent` (Section 7) -- check cache before calling Qwen 14B, populate cache after. Removes a meaningful fraction of LLM load, especially during demo open-floor segments where similar questions recur across officers/judges.

### Layer 2 -- Retry with Exponential Backoff

**Updated following hackathon workshop Q&A:** organizers confirmed that hitting Catalyst's Qwen/Zia rate limit causes an approximately **10-minute stall before it resets** -- not a transient few-second throttle. This changes what the retry loop below is actually for. Retrying into a 10-minute stall would either block the pipeline Function for most of its 15-minute budget (if retries wait long enough to plausibly clear the stall) or fail fast without ever waiting long enough to matter (if they don't) -- there's no useful middle ground with a stall this long. The retry loop below is deliberately kept fast and fails over to Layer 3 (graceful degradation) quickly, rather than trying to wait out the actual stall -- waiting out a confirmed 10-minute stall inside a 15-minute budget is not a viable retry strategy, it's just a different way of timing out.

```python
# pipeline_function/pipeline/catalyst_resilient_client.py

import asyncio, random
from shared.catalyst_client import llm_complete as _raw_llm_complete

MAX_RETRIES = 3
BASE_DELAY = 1.0
# NOTE: this backoff (max ~4s across 3 attempts) is intentionally short.
# It exists to absorb brief transient errors, NOT to wait out the confirmed
# 10-minute rate-limit stall (see note above) -- if the real rate limit is
# hit, these retries fail fast and hand off to Layer 3 (degraded response)
# rather than blocking the Function for minutes.

class RateLimitError(Exception): pass
class RateLimitExhaustedError(Exception): pass

async def llm_complete_resilient(prompt: str, system: str, **kwargs) -> str:
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            return await _raw_llm_complete(prompt, system, **kwargs)
        except RateLimitError as e:
            last_error = e
            if attempt < MAX_RETRIES - 1:
                # Exponential backoff + jitter -- absorbs brief transient
                # errors only, not the confirmed 10-min stall (see above)
                delay = BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.5)
                await asyncio.sleep(delay)
                continue
        except Exception:
            raise  # non-rate-limit errors fail fast, no retry

    raise RateLimitExhaustedError(
        f"Qwen 14B rate limited after {MAX_RETRIES} attempts"
    ) from last_error
```

**New consideration surfaced by the 10-minute stall:** if the *first* of three sequential LLM calls (NER+intent) hits the stall and fails over to degradation, that's recoverable -- the officer gets a slightly worse response immediately rather than waiting. But if the rate limit is hit mid-pipeline on a *shared* limit (i.e., the stall affects all subsequent calls in the same window, not just the one that triggered it), then DAG planning or synthesis calls made moments later could hit the same stalled window and also fail fast into degradation -- meaning a single rate-limit event could degrade an entire query's response, not just one stage of it. **Open question, not yet answered by the workshop:** is the 10-minute stall scoped per-call-type, per-project, or per-account? This determines whether degradation happens once per affected query or compounds across the three calls. Worth a follow-up question if there's another chance to ask.

All three LLM call sites import from this module instead of the raw client:
```python
# ner_intent.py, dag_planner.py, synthesizer.py all use:
from pipeline.catalyst_resilient_client import llm_complete_resilient as llm_complete
```

### Layer 3 -- Graceful Degradation (Synthesis Fallback)

NER and DAG planning already have safe fallbacks (broad_search intent, default plan -- see Sections 7 and 9). Synthesis needed a new fallback: if retries are exhausted, build a response directly from the Evidence Object instead of failing the request.

```python
def build_fallback_response(evidence) -> str:
    """
    Template-built response from raw Evidence Object when Qwen 14B
    is unavailable. Less natural, but officer gets real data, not an error.
    """
    if not evidence.items:
        return ("No matching records found. The synthesis service is "
                "currently busy -- the search itself completed normally.")

    lines = ["Synthesis temporarily unavailable -- showing raw evidence:\n"]
    for item in evidence.items[:5]:
        marker = {"high": "[HIGH]", "medium": "[MEDIUM]",
                  "low": "[LOW]", "unverified": "[UNVERIFIED]"}.get(item.confidence, "")
        lines.append(f"{marker} {item.fir_id}")
        if item.evidence_path:
            lines.append(f"   Path: {item.evidence_path}")
        if item.similarity_reason:
            lines.append(f"   Reason: {item.similarity_reason[:100]}")
    lines.append("\nPlease retry in a moment for a full synthesized response.")
    return "\n".join(lines)
```

Used in synthesis (Section 12) -- if `llm_complete_resilient` raises `RateLimitExhaustedError`, fall back to this instead of propagating the error to the officer.

### Known Limitation

**Partially resolved via workshop Q&A:** organizers confirmed the rate limit's consequence (≈10-minute stall, then resets) and that hackathon credits should cover normal usage -- but the exact requests/minute or concurrent-request threshold remains undisclosed. The design above now explicitly treats the 10-minute stall as something to fail away from quickly (Layer 2/3), not wait out. Still open: whether the stall is scoped per-call-type, per-project, or per-account (affects whether one rate-limit event degrades one LLM call or an entire query) -- see note above. Real-world load testing during Phase 1-2 build, especially simulating concurrent officer/judge queries, would help confirm this before judging day rather than discovering it live.

---

## 9. DAG Planner

Full LangGraph DAG planner for production. Template router used as scaffold in Phase 2, replaced by DAG planner in Phase 3 without changing any other pipeline components.

```python
# pipeline_function/pipeline/query_understanding/dag_planner.py

DAG_PLANNER_SYSTEM = """You are a query planner for a criminal intelligence system.
Given a structured intent object, generate an execution plan as a JSON array of steps.
Each step: step_id, type, operation, params, depends_on (list of step_ids).
Steps with no unmet dependencies run in parallel.
Output ONLY valid JSON array. No preamble."""

async def build_dag(intent_object: dict) -> list:
    prompt = DAG_PLANNER_PROMPT.format(intent_object=json.dumps(intent_object))
    raw = await llm_complete(prompt=prompt, system=DAG_PLANNER_SYSTEM,
                              temperature=0.0, max_tokens=800)
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        return _default_plan(intent_object)

def _default_plan(intent: dict) -> list:
    return [
        {"step_id": 1, "type": "rag", "operation": "mo_search", "params": {}, "depends_on": []},
        {"step_id": 2, "type": "evidence_assembly", "operation": "merge_and_rank", "params": {}, "depends_on": [1]},
        {"step_id": 3, "type": "synthesis", "operation": "generate_response", "params": {}, "depends_on": [2]}
    ]
```

---

## 10. Evidence Object

```python
# pipeline_function/pipeline/evidence.py

from dataclasses import dataclass, field
from typing import Optional

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

@dataclass
class EvidenceObject:
    query:               str
    session_id:          str
    urgency:             str
    intent:              str
    entities:             dict
    items:               list[EvidenceItem] = field(default_factory=list)
    visualizations:      list[dict] = field(default_factory=list)
    reasoning_trace:     list[str] = field(default_factory=list)
    confidence_caveats:  list[str] = field(default_factory=list)  # sources that timed out/failed

    def add_rag_results(self, rag_response: dict):
        for hit in rag_response.get("results", []):
            self.items.append(EvidenceItem(
                fir_id=hit["fir_id"], relevance_score=hit["score"],
                sources=["rag"], convergent=False,
                evidence_path=None, similarity_reason=hit.get("excerpt"),
                confidence="medium", metadata=hit.get("metadata", {})
            ))

    def add_graph_results(self, graph_results: list):
        for result in graph_results:
            existing = next((e for e in self.items if e.fir_id == result["fir_id"]), None)
            if existing:
                existing.sources.append("graph")
                existing.convergent = True
                existing.evidence_path = result.get("path")
                existing.confidence = "high"
                existing.relevance_score = min(existing.relevance_score * 1.3, 1.0)
            else:
                self.items.append(EvidenceItem(
                    fir_id=result["fir_id"], relevance_score=result.get("score", 0.7),
                    sources=["graph"], convergent=False,
                    evidence_path=result.get("path"), similarity_reason=None,
                    confidence="medium", metadata=result.get("metadata", {})
                ))

    def rank(self):
        self.items.sort(key=lambda x: x.relevance_score, reverse=True)
```

---

## 11. Retrieval Executor -- Per-Source Timeouts

Each retrieval source runs under its own timeout budget. If a source exceeds its budget, the pipeline proceeds without it instead of blocking every concurrent officer's query on one slow component. This is the fail-soft pattern for retrieval reliability.

### Timeout Budgets

```python
TIMEOUT_BUDGETS = {
    "graph": 5.0,   # multi-hop traversal -- most expensive, most headroom
    "rag":   3.0,   # managed service -- should be consistently fast
    "sql":   4.0    # aggregations -- can be slow on large date ranges
}
```

Sources run in parallel via `asyncio.gather`, so actual wait is `max()` not `sum()` -- worst case ~5s, leaving headroom inside the field_urgent 10s target.

### Executor

```python
# pipeline_function/pipeline/retrieval/executor.py

import asyncio
from pipeline.evidence import EvidenceObject

TIMEOUT_BUDGETS = {"graph": 5.0, "rag": 3.0, "sql": 4.0}

async def execute_with_timeout(coro, source_type: str, evidence: EvidenceObject):
    timeout = TIMEOUT_BUDGETS.get(source_type, 5.0)
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        evidence.reasoning_trace.append(
            f"WARNING: {source_type} retrieval exceeded {timeout}s budget -- "
            f"proceeding without this source"
        )
        evidence.confidence_caveats.append(f"{source_type}_unavailable")
        return None
    except Exception as e:
        evidence.reasoning_trace.append(f"WARNING: {source_type} retrieval failed: {str(e)}")
        evidence.confidence_caveats.append(f"{source_type}_unavailable")
        return None

async def execute_retrieval(steps: list, evidence: EvidenceObject, state: dict):
    parallel_steps = [s for s in steps if s["type"] in ("graph", "rag", "sql")]

    tasks = []
    for step in parallel_steps:
        if step["type"] == "graph":
            coro = run_graph_step(step, state)
        elif step["type"] == "rag":
            coro = run_rag_step(step, evidence.query)
        elif step["type"] == "sql":
            coro = run_sql_step(step, evidence.entities)
        tasks.append(execute_with_timeout(coro, step["type"], evidence))

    results = await asyncio.gather(*tasks)

    for step, result in zip(parallel_steps, results):
        if result is None:
            continue   # timed out or failed, already logged
        if step["type"] == "rag":
            evidence.add_rag_results(result)
        elif step["type"] == "graph":
            evidence.add_graph_results(result)
        elif step["type"] == "sql":
            evidence.add_sql_results(result)

    evidence.rank()
    return evidence
```

### Partial Results Notice (Synthesis Integration)

```python
# pipeline_function/pipeline/synthesis/synthesizer.py (addition)

def build_partial_results_notice(evidence: EvidenceObject) -> str:
    if not evidence.confidence_caveats:
        return ""
    source_names = {
        "graph_unavailable": "network/relationship data",
        "rag_unavailable":   "similarity search",
        "sql_unavailable":   "structured records"
    }
    missing = [source_names.get(c, c) for c in evidence.confidence_caveats]
    return (
        f"\n\nNote: {', '.join(missing)} did not respond in time. "
        f"This response may be incomplete -- consider re-running the query."
    )
```

Appended to the synthesis prompt context so Qwen 14B caveats its answer when sources are missing.

### Frontend Notice

```javascript
// frontend/src/components/chat/PartialResultsNotice.jsx

export function PartialResultsNotice({ caveats }) {
    if (!caveats || caveats.length === 0) return null
    return (
        <div className="bg-orange-dim border border-orange text-orange text-xs p-2 rounded mb-2">
            Partial results -- some data sources did not respond in time.
            Consider re-running this query.
        </div>
    )
}
```

---

## 12. Confidence Engine

```python
# pipeline_function/pipeline/confidence_engine.py

from dataclasses import dataclass
from datetime import date, datetime
from pipeline.evidence import EvidenceItem, EvidenceObject
from typing import Optional

@dataclass
class ConfidenceSignal:
    tier: str; score: float; reasons: list[str]; flags: list[str]

def compute_source_convergence(item: EvidenceItem) -> tuple:
    if "graph" in item.sources and "rag" in item.sources:
        return 1.0, ["Found via both semantic similarity and graph relationship"]
    elif "graph" in item.sources:
        return 0.75, ["Found via direct graph relationship"]
    elif "sql" in item.sources:
        return 0.65, ["Found via structured database match"]
    elif "rag" in item.sources:
        return 0.55, ["Found via semantic MO similarity only"]
    return 0.30, ["Source unknown"]

def compute_evidence_strength(item: EvidenceItem) -> tuple:
    reasons, flags = [], []
    score = 0.50
    if item.evidence_path:
        path = item.evidence_path.lower()
        if "co_accused" in path:
            score = 1.0; reasons.append(f"Direct co-accused: {item.evidence_path}")
        elif "shared_vehicle" in path or "phone_contact" in path:
            score = 0.85; reasons.append(f"Strong associative link: {item.evidence_path}")
        elif "shared_mo" in path:
            score = 0.75; reasons.append(f"Shared MO: {item.evidence_path}")
        elif "shared_tattoo" in path:
            score = 0.65; reasons.append(f"Tattoo match: {item.evidence_path}")
            flags.append("Physical descriptor -- not forensically confirmed")
        elif "temporal_cluster" in path:
            score = 0.55; reasons.append(f"Temporal proximity: {item.evidence_path}")
            flags.append("Temporal proximity alone does not establish connection")
        else:
            score = 0.50; reasons.append(f"Indirect: {item.evidence_path}")
    elif item.similarity_reason:
        score = 0.50; reasons.append(f"MO similarity: {item.similarity_reason[:80]}")
        flags.append("No direct graph relationship -- similarity only")
    else:
        score = 0.30; flags.append("No evidence path -- needs manual verification")
    if item.metadata.get("ocr_extracted"):
        score *= 0.90; flags.append("OCR-extracted fields -- verify against original")
    return score, reasons, flags

def compute_recency(fir_date_str: Optional[str]) -> tuple:
    try:
        days = (date.today() - datetime.strptime(fir_date_str, "%Y-%m-%d").date()).days
        if days <= 90:  return 1.0, ["Recent FIR (within 90 days)"]
        if days <= 365: return 0.8, ["FIR within past year"]
        if days <= 730: return 0.6, ["FIR within past 2 years"]
        return 0.4, [f"Older FIR ({days//365} years ago)"]
    except (ValueError, TypeError):
        return 0.5, ["FIR date unknown"]

def assign_tier(score: float, flags: list) -> str:
    if flags and score < 0.70: return "unverified"
    if score >= 0.80: return "high"
    if score >= 0.60: return "medium"
    if score >= 0.40: return "low"
    return "unverified"

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
        evidence.reasoning_trace.append(
            f"{item.fir_id}: {sig.tier} ({sig.score:.2f}) -- {'; '.join(sig.reasons[:2])}"
        )
    evidence.rank()
    return evidence
```

---

## 13. Synthesis (Qwen 14B)

```python
# pipeline_function/pipeline/synthesis/synthesizer.py

from pipeline.catalyst_resilient_client import llm_complete_resilient as llm_complete
from pipeline.catalyst_resilient_client import RateLimitExhaustedError
from pipeline.synthesis.fallback import build_fallback_response
from pipeline.evidence import EvidenceObject

SYNTHESIS_SYSTEM = """You are a criminal intelligence assistant for KSP field investigators.
Synthesize retrieved evidence into clear, actionable summaries.

RULES:
- Cite every factual claim with its source (FIR ID / graph path / algorithm)
- Use "appears as accused in FIR" -- NEVER "committed"
- Flag low-confidence results explicitly -- never present as certain
- HIGH confidence: state as fact. MEDIUM: use qualifier. LOW/UNVERIFIED: flag for verification
- field_urgent: 3-5 bullet points maximum
- analytical: full paragraph synthesis with evidence section
- If evidence object is empty: state no records found, suggest alternative queries
- Never fabricate connections not in evidence
- Always end with: "All outputs require officer verification before action."
"""

async def synthesize(evidence: EvidenceObject) -> dict:
    items_text = "\n".join([
        f"[{i+1}] FIR:{item.fir_id} Score:{item.relevance_score:.2f} "
        f"Sources:{','.join(item.sources)} Confidence:{item.confidence} "
        f"Path:{item.evidence_path or 'N/A'} Reason:{item.similarity_reason or 'N/A'}"
        for i, item in enumerate(evidence.items[:10])
    ])
    prompt = f"""QUERY: {evidence.query}
URGENCY: {evidence.urgency}
INTENT: {evidence.intent}
ENTITIES: {evidence.entities}
EVIDENCE:\n{items_text or 'No evidence retrieved.'}
TRACE: {chr(10).join(evidence.reasoning_trace) or 'None'}
Generate {'concise bullet (3-5)' if evidence.urgency == 'field_urgent' else 'full analytical'} response:"""

    try:
        text = await llm_complete(prompt=prompt, system=SYNTHESIS_SYSTEM,
            temperature=0.1, max_tokens=300 if evidence.urgency == "field_urgent" else 800)
    except RateLimitExhaustedError:
        # Graceful degradation -- officer sees real evidence, not an error
        text = build_fallback_response(evidence)

    return {
        "text": text,
        "high_confidence": [e.fir_id for e in evidence.items if e.confidence == "high"],
        "reasoning_trace": evidence.reasoning_trace
    }
```

---

## 14. Memgraph Integration

### Oracle Cloud VM Setup (One-Time)

```bash
# Ubuntu 22.04 ARM VM on Oracle Cloud Free Tier
curl -fsSL https://get.docker.com | sh
docker run -d --name memgraph -p 7687:7687 \
  --restart unless-stopped \
  -v mg_lib:/var/lib/memgraph \
  memgraph/memgraph-mage:latest

# Verify MAGE available
docker exec -it memgraph mgconsole
# CALL mg.procedures() YIELD name WHERE name STARTS WITH 'community' RETURN name;
```

### Constraints + Indexes (run once before any data)

**Synced with Architecture Section 15:** the architecture doc's graph schema already specified `Victim` as a node type distinct from `Accused`; this implementation section had drifted and only defined `:Accused`. Corrected below to include `:Victim` and the new `:Complainant` node type (see Implementation Section 17, Open Decision 1, before populating any complainant demographic fields).

```cypher
CREATE CONSTRAINT ON (a:Accused)      ASSERT a.id IS UNIQUE;
CREATE CONSTRAINT ON (f:FIR)          ASSERT f.id IS UNIQUE;
CREATE CONSTRAINT ON (vc:Victim)      ASSERT vc.id IS UNIQUE;
CREATE CONSTRAINT ON (cp:Complainant) ASSERT cp.id IS UNIQUE;
CREATE CONSTRAINT ON (v:Vehicle)      ASSERT v.regNo IS UNIQUE;
CREATE CONSTRAINT ON (p:Phone)        ASSERT p.number IS UNIQUE;
CREATE CONSTRAINT ON (l:Location)     ASSERT l.id IS UNIQUE;
CREATE INDEX ON :FIR(district);
CREATE INDEX ON :FIR(date);
CREATE INDEX ON :FIR(crimeType);
CREATE INDEX ON :Accused(communityId);
```

### MAGE Algorithms (pipeline_function/graph/algorithms.py)

```python
from shared.graph_client import run_query, run_write

async def run_mage_algorithms():
    # Louvain
    results = await run_query("""
        CALL community_detection.get(
            subgraphQuery := "MATCH (n:Accused)-[r:CO_ACCUSED|SHARED_MO]-(m:Accused) RETURN n,r,m"
        ) YIELD node, community_id
        RETURN node.id as id, community_id
    """)
    for r in results:
        await run_write("MATCH (a:Accused {id:$id}) SET a.communityId=$cid",
                        {"id": r["id"], "cid": r["community_id"]})

    # Betweenness Centrality
    results = await run_query("""
        CALL betweenness_centrality.get(directed:=False, normalized:=True)
        YIELD node, betweenness_centrality WHERE node:Accused
        RETURN node.id as id, betweenness_centrality
    """)
    for r in results:
        await run_write("MATCH (a:Accused {id:$id}) SET a.centralityScore=$score",
                        {"id": r["id"], "score": r["betweenness_centrality"]})

    # PageRank
    results = await run_query("""
        CALL pagerank.get() YIELD node, rank WHERE node:Accused
        RETURN node.id as id, rank
    """)
    for r in results:
        await run_write("MATCH (a:Accused {id:$id}) SET a.pageRankScore=$score",
                        {"id": r["id"], "score": r["rank"]})

    # WCC
    results = await run_query("""
        CALL weakly_connected_components.get()
        YIELD node, component_id WHERE node:Accused
        RETURN node.id as id, component_id
    """)
    for r in results:
        await run_write("MATCH (a:Accused {id:$id}) SET a.componentId=$cid",
                        {"id": r["id"], "cid": r["component_id"]})
```

---

## 15. Catalyst Data Store -- ZTSQL Schema

**Updated against the official KSP Police FIR System ER diagram.** The original guessed schema (flat `firs`/`accused`/`fir_accused` tables) is replaced below with a structure derived from the real `CaseMaster`/`Accused`/`Victim`/`ComplainantDetails` design, simplified for PS-1's scope -- we don't need every lookup table the full KSP system has (e.g. `Designation`, `BloodGroupID`, `PhysicallyChallenged` on `Employee` aren't relevant to PS-1's query patterns), but the core case/person/classification structure now matches the real system rather than a guess.

```sql
-- Core case record, derived from CaseMaster
CREATE TABLE cases (
    fir_internal_id   TEXT PRIMARY KEY,      -- our own surrogate key, not CrimeNo itself
    crime_no          TEXT NOT NULL UNIQUE,  -- real KSP composite key, see parse_crime_no()
    case_no           TEXT,                  -- last 9 digits of crime_no (YYYY+serial)
    registered_date   TEXT NOT NULL,
    unit_id           TEXT NOT NULL,         -- FK -> units.unit_id (police station)
    case_category_id  TEXT,                  -- FK -> case_categories.id (FIR/UDR/Zero FIR/PAR)
    gravity_offence_id TEXT,
    crime_head_id     TEXT,                  -- FK -> crime_heads.id (major classification)
    crime_sub_head_id TEXT,                  -- FK -> crime_sub_heads.id (e.g. Murder, Robbery)
    case_status_id    TEXT DEFAULT 'open',
    court_id          TEXT,
    incident_from     TEXT,
    incident_to       TEXT,
    info_received_at_station TEXT,
    lat               TEXT,
    lon               TEXT,
    narrative         TEXT,
    mo_descriptor     TEXT,                  -- PS-1-derived, not a KSP source field
    ocr_extracted     INTEGER DEFAULT 0,      -- PS-1-derived, not a KSP source field
    created_at        TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Distinct from accused and complainant -- real schema keeps these three separate
CREATE TABLE victims (
    victim_id      TEXT PRIMARY KEY,
    fir_internal_id TEXT NOT NULL,           -- FK -> cases.fir_internal_id
    victim_name    TEXT,
    age_years      INTEGER,
    gender_id      TEXT,
    victim_is_police INTEGER DEFAULT 0
);

CREATE TABLE complainants (
    complainant_id  TEXT PRIMARY KEY,
    fir_internal_id TEXT NOT NULL,           -- FK -> cases.fir_internal_id
    complainant_name TEXT,
    age_years       INTEGER,
    occupation_id   TEXT,
    religion_id     TEXT,                    -- see Section 17 Open Decision 1 before populating
    caste_id        TEXT,                    -- see Section 17 Open Decision 1 before populating
    gender_id       TEXT
);

CREATE TABLE accused (
    accused_id        TEXT PRIMARY KEY,
    fir_internal_id    TEXT NOT NULL,        -- FK -> cases.fir_internal_id
    accused_name       TEXT NOT NULL,
    age_years          INTEGER,
    gender_id          TEXT,
    accused_sort_label TEXT,                 -- "A1", "A2" -- display order, not a real ID
    aliases            TEXT,                 -- PS-1-derived, not a KSP source field
    tattoos            TEXT,                 -- PS-1-derived, not a KSP source field
    prior_fir_count    INTEGER DEFAULT 0,    -- PS-1-derived
    activity_score     REAL DEFAULT 0.0,     -- PS-1-derived (Architecture Section 24)
    community_id       INTEGER,              -- PS-1-derived (MAGE Louvain output)
    centrality_score   REAL DEFAULT 0.0,     -- PS-1-derived (MAGE Betweenness output)
    page_rank_score    REAL DEFAULT 0.0      -- PS-1-derived (MAGE PageRank output)
);

-- New table -- did not exist in the original guessed schema
CREATE TABLE arrest_surrenders (
    arrest_surrender_id     TEXT PRIMARY KEY,
    fir_internal_id          TEXT NOT NULL,   -- FK -> cases.fir_internal_id
    accused_id               TEXT NOT NULL,   -- FK -> accused.accused_id
    arrest_or_surrender_type_id TEXT,
    arrest_surrender_date    TEXT,
    arrest_state_id          TEXT,
    arrest_district_id       TEXT,            -- NOTE: can differ from the FIR's filing district --
                                                --   see Section 17 Open Decision 3
    unit_id                  TEXT,            -- police station handling the arrest
    investigating_officer_id TEXT,
    court_id                 TEXT,
    is_primary_accused       INTEGER DEFAULT 1,
    complainant_is_also_accused INTEGER DEFAULT 0
);

-- Act/Section now genuinely many-to-many, replacing the flat ipc_sections string
CREATE TABLE case_act_sections (
    fir_internal_id TEXT NOT NULL,           -- FK -> cases.fir_internal_id
    act_code        TEXT NOT NULL,
    section_code    TEXT NOT NULL,
    act_order       INTEGER,
    section_order   INTEGER,
    PRIMARY KEY (fir_internal_id, act_code, section_code)
);

-- Lookup tables -- simplified subset of the real schema's lookups,
-- only the ones PS-1's query patterns actually need
CREATE TABLE acts (
    act_code   TEXT PRIMARY KEY,
    act_description TEXT,
    short_name TEXT
);

CREATE TABLE sections (
    act_code        TEXT NOT NULL,
    section_code    TEXT NOT NULL,
    section_description TEXT,
    PRIMARY KEY (act_code, section_code)
);

CREATE TABLE crime_heads (
    crime_head_id   TEXT PRIMARY KEY,
    crime_head_name TEXT  -- e.g. "Crimes Against Body"
);

CREATE TABLE crime_sub_heads (
    crime_sub_head_id   TEXT PRIMARY KEY,
    crime_head_id       TEXT NOT NULL,  -- FK -> crime_heads.crime_head_id
    crime_sub_head_name TEXT  -- e.g. "Murder", "Robbery"
);

CREATE TABLE case_categories (
    case_category_id TEXT PRIMARY KEY,
    category_name     TEXT  -- FIR, UDR, Zero FIR, PAR
);

CREATE TABLE units (
    unit_id      TEXT PRIMARY KEY,
    unit_name    TEXT,
    district_id  TEXT,
    state_id     TEXT
);

CREATE TABLE districts (
    district_id   TEXT PRIMARY KEY,
    district_name TEXT,
    state_id      TEXT
);
```

No geospatial types -- lat/lon stored as TEXT, distance computed in Python via geopy. Same approach as the original design, unaffected by the schema correction.

### Row Count Re-Estimate Against Data Store Dev Caps

The real schema has more tables than the original 3-table guess, which changes the row-count math against the confirmed 5,000/table, 25,000/project dev caps (still open pending the dev-vs-prod answer, see To Discuss). `cases` sits at 4,000 with 1,000 rows of headroom. The new `victims`, `complainants`, `arrest_surrenders`, and `case_act_sections` tables each add their own row counts on top of the previous `accused` (~1,500) estimate -- worth a fresh total once real data composition (how many victims/complainants per case, how many act-sections per case) is known, rather than assuming the original ~12,250-14,000 total estimate still holds with more tables in the mix.

---

## 16. Ingestion Pipeline

### Three-Destination Write (Per FIR, Parallel)

```python
async def ingest_one(fir: FIRSchema):
    await asyncio.gather(
        upload_fir_to_kb(fir),        # Catalyst KB plain text document
        write_fir_to_memgraph(fir),   # Memgraph nodes + explicit edges
        write_fir_to_ztsql(fir)       # ZTSQL structured row
    )
```

### Derived Edge Computation -- Incremental, Not Brute-Force

Brute-force all-pairs comparison is O(n^2) -- fine at 4,000 FIRs, never finishes at lakh scale. Corrected design: each new FIR is compared against the existing population via Catalyst KB semantic search (sub-linear), not pairwise comparison. Cost per new FIR is independent of total population size.

```python
# ingestion/derived_edges.py

from shared.catalyst_client import kb_search
from shared.graph_client import run_query, run_write
from datetime import date

SIMILARITY_THRESHOLD = 0.82
MAX_CANDIDATES_PER_QUERY = 20

async def compute_shared_mo_edges_incremental(new_fir_ids: list[str]):
    """
    Run only on the newly ingested batch. Each new FIR is compared against
    the FULL existing population via Catalyst KB search -- not pairwise
    brute force. O(M log N) for M new FIRs against N total, not O(N^2).
    """
    for fir_id in new_fir_ids:
        mo_descriptor = await get_mo_descriptor(fir_id)
        similar = await kb_search(query=mo_descriptor, top_k=MAX_CANDIDATES_PER_QUERY)

        for hit in similar["results"]:
            if hit["fir_id"] == fir_id or hit["score"] < SIMILARITY_THRESHOLD:
                continue
            await create_shared_mo_edge(fir_id, hit["fir_id"], hit["score"])

    print(f"Incremental SHARED_MO: {len(new_fir_ids)} new FIRs vs full population")

async def create_shared_mo_edge(fir_a: str, fir_b: str, score: float):
    """MERGE with reinforcement -- reuses existing edge instead of duplicating."""
    accused_a = await get_accused_for_fir(fir_a)
    accused_b = await get_accused_for_fir(fir_b)

    for a1 in accused_a:
        for a2 in accused_b:
            await run_write("""
                MATCH (a1:Accused {id: $a1}), (a2:Accused {id: $a2})
                MERGE (a1)-[r:SHARED_MO]-(a2)
                ON CREATE SET r.similarityScore = $score,
                              r.createdAt = $today,
                              r.lastReinforced = $today,
                              r.reinforcementCount = 1
                ON MATCH SET  r.lastReinforced = $today,
                              r.reinforcementCount = r.reinforcementCount + 1,
                              r.similarityScore = CASE
                                  WHEN $score > r.similarityScore THEN $score
                                  ELSE r.similarityScore END
            """, {"a1": a1, "a2": a2, "score": score, "today": date.today().isoformat()})
```

### Edge Pruning -- Bounding Graph Growth

Monthly background job. Archives (not deletes) SHARED_MO / TEMPORAL_CLUSTER edges 2+ years old with no reinforcement. CO_ACCUSED, SHARED_TATTOO, SHARED_VEHICLE are never pruned -- durable facts, not decaying inference.

```python
# ingestion/edge_pruning.py

from shared.graph_client import run_query, run_write
from datetime import date, timedelta

PRUNE_AGE_YEARS = 2

async def prune_stale_edges():
    cutoff = (date.today() - timedelta(days=365 * PRUNE_AGE_YEARS)).isoformat()

    candidates = await run_query("""
        MATCH (a:Accused)-[r:SHARED_MO|TEMPORAL_CLUSTER]-(b:Accused)
        WHERE r.lastReinforced < $cutoff OR r.lastReinforced IS NULL
        RETURN id(r) as edge_id, type(r) as edge_type,
               a.id as accused_a, b.id as accused_b, r.createdAt as created_at
    """, {"cutoff": cutoff})

    archived = 0
    for edge in candidates:
        # Archive metadata before removing -- audit trail, not silent deletion
        await run_write("""
            CREATE (arc:ArchivedEdge {
                edgeType: $edge_type, accusedA: $accused_a, accusedB: $accused_b,
                createdAt: $created_at, archivedAt: $archived_at,
                reason: 'stale_no_reinforcement'
            })
        """, {
            "edge_type": edge["edge_type"], "accused_a": edge["accused_a"],
            "accused_b": edge["accused_b"], "created_at": edge["created_at"],
            "archived_at": date.today().isoformat()
        })
        await run_write("MATCH ()-[r]-() WHERE id(r) = $edge_id DELETE r",
                        {"edge_id": edge["edge_id"]})
        archived += 1

    print(f"Pruned {archived} stale edges (archived, not deleted)")
    return archived
```

Run monthly via cron or scheduled job, separate from the ingestion run.

### KB Document Format

```
FIR_ID: FIR/123/2024/MYS
DATE: 2024-03-15
DISTRICT: Mysuru
STATION: Mysuru Central PS
CRIME_TYPE: Chain Snatching
IPC_SECTIONS: 379, 382
ACCUSED: Suresh Babu (ACC-001) [tattoos: cobra:right_forearm]
VICTIM_PROFILE: Female, approximately 55 years, pedestrian

MO_DESCRIPTOR: Accused rode past victim on motorcycle near bus stand,
grabbed gold chain from neck of elderly woman, fled towards ring road.

NARRATIVE: [full FIR narrative text]
```

### activityScore -- Documented Methodology (Heuristic, Not ML)

A heuristic indicator surfacing accused profiles for human investigative review. Not a predictive risk model, not a recidivism predictor, not a basis for any action without human verification. Answers "who might be worth a closer look" -- nothing more.

```python
# ingestion/scoring.py

"""
activityScore Methodology
==========================

WHY THESE FOUR FACTORS:

prior_fir_count (weight 0.4, highest):
  Direct, factual, court-documented history -- the only factor based
  on the accused's own actions rather than network position or
  demographics. Highest weight because least likely to encode bias.
  Capped at /10 to prevent one extreme outlier dominating unboundedly.

centrality_score (weight 0.3):
  Betweenness centrality from MAGE -- structural bridge position in
  a known network. One step removed from the person's own actions
  (about who they're connected to), so weighted lower than priors.

community_size > 5 (weight 0.2, binary not continuous):
  Binary deliberately -- a graded weight would let small network-size
  differences swing the score more than the signal strength justifies.
  Binary keeps influence bounded and explicit.

has_recent_fir (weight 0.1, lowest, binary):
  Recency alone says little. Included mainly to slightly deprioritize
  cold profiles vs currently relevant ones, not as a risk signal.

EXPLICITLY EXCLUDED:
  - Age: correlates with district-level crime stats reflecting
    historical policing patterns, not individual behavior.
  - District/location as a direct factor: would systematically
    elevate scores for anyone in over-policed areas. Appears only
    indirectly via community_size (network structure), never as a
    standalone multiplier.
  - Gender, religion, caste: never included under any circumstance.

VERSION: v1.0. Any weight change requires updating this rationale,
not just the number.
"""

ACTIVITY_SCORE_ACTION_THRESHOLD = 0.70

def compute_activity_score(prior_fir_count: int, centrality_score: float,
                            community_size: int, has_recent_fir: bool) -> float:
    return (
        min(prior_fir_count / 10, 1.0) * 0.4 +
        centrality_score * 0.3 +
        (0.2 if community_size > 5 else 0.0) +
        (0.1 if has_recent_fir else 0.0)
    )
```

### Bias Audit -- District and Age

Run against the actual generated dataset to check whether score distribution correlates suspiciously with district or age -- either would indicate the formula functions as a demographic proxy rather than an investigative signal.

```python
# data/scripts/audit_activity_score_bias.py

import asyncio, statistics
from shared.graph_client import run_query

async def audit_by_district():
    results = await run_query("""
        MATCH (a:Accused) WHERE a.activityScore IS NOT NULL
        RETURN a.district as district, a.activityScore as score
    """)
    by_district = {}
    for r in results:
        by_district.setdefault(r["district"], []).append(r["score"])

    means = []
    for district, scores in sorted(by_district.items()):
        mean = statistics.mean(scores)
        means.append(mean)
        print(f"{district:<20} mean={mean:.3f} n={len(scores)}")

    spread = max(means) - min(means)
    print(f"District spread: {spread:.3f}")
    if spread > 0.15:
        print("WARNING: large district spread -- investigate demographic skew")

async def audit_by_age():
    results = await run_query("""
        MATCH (a:Accused) WHERE a.activityScore IS NOT NULL AND a.dob IS NOT NULL
        RETURN a.dob as dob, a.activityScore as score
    """)
    from datetime import date
    buckets = {"18-25": [], "26-35": [], "36-45": [], "46+": []}
    for r in results:
        try:
            age = date.today().year - int(r["dob"][:4])
            bucket = ("18-25" if age <= 25 else "26-35" if age <= 35
                     else "36-45" if age <= 45 else "46+")
            buckets[bucket].append(r["score"])
        except (ValueError, TypeError):
            continue

    means = [statistics.mean(s) for s in buckets.values() if s]
    for bucket, scores in buckets.items():
        if scores:
            print(f"{bucket:<12} mean={statistics.mean(scores):.3f} n={len(scores)}")
    if means:
        spread = max(means) - min(means)
        print(f"Age spread: {spread:.3f}")
        if spread > 0.15:
            print("WARNING: score correlates with age despite exclusion -- "
                  "check indirect correlation via prior_fir_count or network position")

async def main():
    print("=== activityScore Bias Audit ===")
    await audit_by_district()
    await audit_by_age()

if __name__ == "__main__":
    asyncio.run(main())
```

Run against the full 4,000-FIR dataset once generated -- only meaningful with real score distributions.

### Human Sign-Off Requirement

Documentation alone is easy to ignore under operational pressure -- the requirement is structural, not just policy.

```python
# backend/api/middleware/rbac.py (addition)

def requires_supervisor_signoff(activity_score: float) -> bool:
    """
    Any workflow letting an officer act (not just view) based partly
    on activityScore requires supervising officer sign-off above
    this threshold. Viewing the score never requires sign-off.
    """
    return activity_score >= ACTIVITY_SCORE_ACTION_THRESHOLD
```

Reinforced in the synthesis system prompt: any evidence item with `activityScore >= 0.70` triggers an appended disclaimer -- "activityScore is a heuristic indicator for investigative prioritization only. Any action beyond review requires supervising officer sign-off and independent verification."

**Hackathon scope:** threshold constant and synthesis-level disclaimer implemented. Full workflow gating (actual sign-off UI flow) is documented as production scope, out for 25-28 days -- same scoping pattern as RBAC (Section 21).

### Ingestion Run Order

```bash
python data/scripts/extract_distributions.py          # Phase 1
python data/scripts/generate_base_firs.py             # Phase 2: 3,500 FIRs
python data/scripts/plant_stories.py                  # Phase 3: 500 FIRs
python data/scripts/generate_narratives.py            # Phase 4: overnight ~8-10hrs
python data/scripts/ingest_all.py firs_with_narratives.json  # KB + Memgraph + ZTSQL
python data/scripts/compute_derived_edges.py          # incremental SHARED_MO/TATTOO/TEMPORAL
python data/scripts/run_mage_algorithms.py            # Louvain, Betweenness, PageRank, WCC
python data/scripts/compute_scores.py                 # activityScore per accused
python data/scripts/verify_stories.py                 # All 4 stories must pass
```

**Production-only, scheduled separately (monthly):**
```bash
python data/scripts/prune_stale_edges.py               # archive 2yr+ unreinforced edges
```

---

## 17. Schema Mapping Layer

**Updated against the official KSP Police FIR System ER diagram (received from organizers).** The original `FIELD_NAME_MAP` was built on guessed/common CCTNS-style field name variants, since no real schema existed yet. The real schema is structurally richer than assumed -- it's a normalized relational design with lookup tables (`CaseCategory`, `CrimeHead`/`CrimeSubHead`, `Act`/`Section`, `District`/`State`, etc.) rather than flat text fields, and includes entities the original guess didn't have at all (`Victim` as a distinct table from `Accused`/`ComplainantDetails`, `ArrestSurrender` tracking, `ChargesheetDetails`, full `Employee`/`Unit`/`Rank` hierarchy for officers). The mapping below is corrected accordingly -- this is a structural update, not just a renaming exercise.

### Key Structural Differences From the Original Guess

1. **`CrimeNo` is a structured composite key, not an opaque ID.** Format: `1-digit Case Category Code + 4-digit District ID + 4-digit Police Station (Unit) ID + 4-digit Year + 5-digit running serial`. E.g. `104430006202600001` decodes to Category `1` (FIR), District `4430`, Unit `0062`, Year `0260` -- wait, the actual breakdown per the doc is Category(1) + District(4) + Unit(4) + Year(4) + Serial(5) = 18 digits total. This means **the crime number itself is parseable** -- category, district, station, and year can all be extracted from `CrimeNo` alone via fixed-width slicing, which the original flat `id` field never supported. Worth writing a `parse_crime_no()` helper rather than treating it as an opaque string.
2. **Crime classification is two-level and lookup-driven, not a flat string.** `CrimeMajorHeadID` -> `CrimeHead` (e.g. "Crimes Against Body") and `CrimeMinorHeadID` -> `CrimeSubHead` (e.g. "Murder", "Robbery") replace the guessed flat `crime_type` field. This is actually better for the NER/intent layer -- "find murder cases" can resolve to a specific `CrimeSubHeadID` via a lookup join instead of fuzzy-matching a free-text string against `CRIME_TYPE_CANONICAL`.
3. **Acts and Sections are normalized and many-to-many via `ActSectionAssociation`**, not a single comma-separated `ipc_sections` string. A case can invoke multiple Act+Section pairs, each with its own display order. The `normalize_ipc_sections()` regex-based extraction is no longer needed for ingestion *if* source data already comes in this structured form -- but may still be needed if source FIR text is unstructured free text that needs section numbers extracted before being matched against the real `Section.SectionCode` lookup.
4. **Victims, Complainants, and Accused are three separate tables**, not folded into one `accused` list with a `role` field as originally guessed. A `Victim` is not assumed to be a complainant, and a complainant is not assumed to not be the accused (`ComplainantDetails` and the `IsComplainantAccused` flag on `ArrestSurrender` both exist specifically because these can diverge -- e.g. a complainant who is later found to also be an accused).
5. **No single victim/accused `district` field** -- district context comes from the case's `PoliceStationID` -> `Unit` -> `DistrictID` chain, or from `ArrestSurrenderDistrictId` specifically for where an arrest occurred (which can differ from the case's filing district). The original guessed schema's flat `district` field on `accused` doesn't have a clean equivalent -- needs a decision (see Open Decisions below).
6. **Demographic fields on `ComplainantDetails`** (occupation, religion, caste, age, gender) exist in the real schema and were not part of the original guess at all. These raise a genuine design question for PS-1 -- see Open Decisions below, since the architecture's bias-auditing principle (Architecture Section 24, activityScore bias check) was written without these fields in mind.

### Corrected FIELD_NAME_MAP

```python
# ingestion/schema_mapper.py

# Maps real KSP source field names (and common case/spacing variants) to
# PS-1's internal canonical field names. Real KSP field names from the
# official ER diagram are the primary keys here; lowercase/underscore
# variants are kept as fallback aliases in case source exports don't use
# exact PascalCase column names.

FIELD_NAME_MAP = {
    # CaseMaster -- FIR core record
    "casemasterid": "fir_internal_id", "case_master_id": "fir_internal_id",
    "crimeno": "crime_no", "crime_no": "crime_no",
    "caseno": "case_no", "case_no": "case_no",
    "crimeregistereddate": "registered_date", "crime_registered_date": "registered_date",
    "policepersonid": "registering_officer_id", "police_person_id": "registering_officer_id",
    "policestationid": "unit_id", "police_station_id": "unit_id",
    "casecategoryid": "case_category_id", "case_category_id": "case_category_id",
    "gravityoffenceid": "gravity_offence_id",
    "crimemajorheadid": "crime_head_id", "crime_major_head_id": "crime_head_id",
    "crimeminorheadid": "crime_sub_head_id", "crime_minor_head_id": "crime_sub_head_id",
    "casestatusid": "case_status_id",
    "courtid": "court_id",
    "incidentfromdate": "incident_from", "incident_from_date": "incident_from",
    "incidenttodate": "incident_to", "incident_to_date": "incident_to",
    "inforeceivedpsdate": "info_received_at_station",
    "latitude": "lat", "longitude": "lon",
    "brieffacts": "narrative", "brief_facts": "narrative",

    # ComplainantDetails
    "complainantid": "complainant_id",
    "complainantname": "complainant_name",
    "ageyear": "age_years",  # shared name across Complainant/Victim/Accused -- disambiguate by table context
    "occupationid": "occupation_id",
    "religionid": "religion_id",
    "casteid": "caste_id",
    "genderid": "gender_id",

    # Victim
    "victimmasterid": "victim_id",
    "victimname": "victim_name",
    "victimpolice": "victim_is_police",

    # Accused
    "accusedmasterid": "accused_id",
    "accusedname": "accused_name",
    "personid": "accused_sort_label",  # e.g. "A1", "A2" -- display ordering, not a real ID

    # ArrestSurrender
    "arrestsurrenderid": "arrest_surrender_id",
    "arrestsurrendertypeid": "arrest_or_surrender_type_id",
    "arrestsurrenderdate": "arrest_surrender_date",
    "arrestsurrenderstateid": "arrest_state_id",
    "arrestsurrenderdistrictid": "arrest_district_id",
    "ioid": "investigating_officer_id",
    "isaccused": "is_primary_accused",
    "iscomplainantaccused": "complainant_is_also_accused",

    # Act / Section
    "actcode": "act_code",
    "actdescription": "act_description",
    "sectioncode": "section_code",
    "sectiondescription": "section_description",

    # Crime classification lookups
    "crimeheadid": "crime_head_id",
    "crimegroupname": "crime_head_name",
    "crimesubheadid": "crime_sub_head_id",
    "crimeheadname": "crime_sub_head_name",  # NOTE: real schema reuses "CrimeHeadName" as the column
                                                #   name inside CrimeSubHead -- this is the sub-head's
                                                #   own name, not a duplicate of CrimeHead.CrimeGroupName.
                                                #   Easy to misread; flagged explicitly.

    # Location / org hierarchy
    "districtid": "district_id",
    "districtname": "district_name",
    "stateid": "state_id",
    "statename": "state_name",
    "unitid": "unit_id",
    "unitname": "unit_name",

    # Employee
    "employeeid": "employee_id",
    "kgid": "govt_employee_id",
    "rankid": "rank_id",
    "designationid": "designation_id",

    # Chargesheet
    "csid": "chargesheet_id",
    "csdate": "chargesheet_date",
    "cstype": "chargesheet_outcome",  # A=Chargesheet, B=False Case, C=Undetected
}

PLACEHOLDER_VALUES = {"", "n/a", "na", "nil", "none", "null",
                       "unknown", "-", "--", "0", "00", "."}

def clean_placeholder(v):
    if v is None or str(v).strip().lower() in PLACEHOLDER_VALUES:
        return None
    return v

def parse_crime_no(crime_no: str) -> dict:
    """
    CrimeNo format per official schema: 1-digit category + 4-digit district
    + 4-digit unit (police station) + 4-digit year + 5-digit serial = 18 digits.

    VERIFIED against all 4 worked examples in the official ER diagram doc
    (FIR, UDR, Zero FIR, PAR), which share the same district/unit/year/serial
    and differ only in the leading category digit -- exactly as the field
    layout predicts:
      FIR      "104430006202600001" -> category=1
      UDR      "304430006202600001" -> category=3
      Zero FIR "804430006202600001" -> category=8
      PAR      "404430006202600001" -> category=4
      (all four: district=0443, unit=0006, year=2026, serial=00001)
    Also cross-checked against a second, independent claim in the same
    document -- "CaseNo follows YYYY + 5-digit serial (last 9 digits from
    CrimeNo)" -- which predicts the last 9 digits should be "2026"+"00001".
    Slicing confirms this exactly. Two independent descriptions in the source
    document agree with each other and with all 4 examples, so this is on
    solid footing -- though still worth a sanity check against one real
    production CrimeNo once data is available, since all of this was
    verified against the document's own worked examples, not independent data.
    """
    if len(crime_no) != 18:
        raise ValueError(f"Expected 18-digit CrimeNo, got {len(crime_no)} digits: {crime_no}")
    return {
        "case_category_code": crime_no[0:1],
        "district_id": crime_no[1:5],
        "unit_id": crime_no[5:9],
        "year": crime_no[9:13],
        "serial_no": crime_no[13:18],
    }

def map_ksp_to_canonical(raw: dict) -> dict:
    canonical = {FIELD_NAME_MAP.get(k.lower().strip(), k.lower().strip()): v
                 for k, v in raw.items()}
    canonical = {k: clean_placeholder(v) for k, v in canonical.items()}
    return canonical
```

### Open Decisions -- Need Team Input, Not Further Research

These are genuine design choices the real schema surfaces, not bugs to fix:

1. **Demographic fields on `ComplainantDetails`** (`OccupationID`, `ReligionID`, `CasteID`) exist in the real schema. Decide explicitly whether PS-1 ingests these at all -- they were never part of the original design. **Reassuring finding on closer check:** Architecture Section 24 already states "Gender, religion, caste -- never included under any circumstance" as an absolute rule for `activityScore`, written before this schema arrived but broad enough to already cover it -- so even if these fields are ingested, the existing rule already forbids them from touching the score, no rule change needed there. What's still a genuine open decision: whether to ingest them *at all* (for display/context purposes, separate from scoring), and if so, whether they should be visible anywhere in the officer-facing UI or stripped at the ingestion boundary entirely. The bias-audit script itself doesn't need new scope -- it audits the *score's* output distribution, which the exclusion rule already protects.
2. ~~**`Victim` vs. `ComplainantDetails` vs. `Accused` as three separate tables**~~ -- **RESOLVED by precedent already in Architecture Section 15.** The architecture doc's graph schema already modeled `Victim` as a node type distinct from `Accused` before this schema correction -- following that same precedent, `Complainant` is now added as its own node type too (three distinct labels: `:Victim`, `:Complainant`, `:Accused`), rather than collapsing them into one `:Person` label with a role property. This was a natural extension of an existing decision, not a new one requiring fresh team input. **What this does require:** Implementation Section 14's Cypher constraints currently only define `:Accused`, `:FIR`, `:Vehicle`, `:Phone`, `:Location` -- missing `:Victim` (already specified in Architecture) and `:Complainant` (new). This is a documentation drift to fix, not a decision to make -- Section 14 needs its constraints block and any Cypher queries referencing person nodes brought in line with Architecture Section 15.
3. **District attribution is now contextual, not a flat field** (FIR's location comes via `PoliceStationID` -> `Unit` -> `DistrictID`; an arrest's location is separately `ArrestSurrenderDistrictId`, which can differ). Decide which one the NER/retrieval layer should treat as "the" district for a case when an officer asks "show me cases in Mysuru" -- likely the FIR's filing district, but worth being explicit since the two can diverge (e.g. accused arrested in a different district than where the FIR was filed).
4. **`CrimeNo` parsing (district/year/category embedded in the ID) could replace some lookup joins** with simple string slicing for fast filtering. The slicing itself is now verified against all 4 worked examples in the source document (FIR/UDR/Zero FIR/PAR) plus a second independent cross-check (`CaseNo` = last 9 digits), so this is solid enough to build against -- the remaining open item is just confirming it holds against one real production `CrimeNo`, not re-deriving the format.

Field coverage audit: `python data/scripts/audit_schema_coverage.py path/to/data.json`
Surfaces unknown fields automatically. Add to `FIELD_NAME_MAP` -- no other code changes.

---

## 18. NER Few-Shot Library

`shared/ner_examples.py` -- 30+ examples, single source of truth for both live prompt and eval suite.

Coverage: pure English, romanized Kannada, mixed code-switched, all 6 intents, both urgency levels, edge cases (single word, vague references, pure Kannada pronouns).

`data/scripts/eval_ner.py` -- runs all examples against Qwen 14B, reports pass rate.
Target: 90%+ before any demo or judging. Failing patterns: add new examples, re-run, repeat.

```bash
python data/scripts/eval_ner.py     # must pass >= 90% before demo
```

---

## 19. Evaluation -- Breaking Circularity, Trap Scenario, Calibration

Planted stories validate ingestion correctness (`verify_stories.py`), not whether confidence tiers mean anything -- that requires ground truth we didn't define ourselves.

### Blind Evaluation Set

```python
# data/scripts/blind_evaluation_set.py

"""
A team member who has NOT seen the planted-story design reviews a
random sample of accused pairs, seeing only raw narratives/MO/profiles
-- no graph data, no system output, no story labels. They label each
pair CONNECTED / LIKELY_CONNECTED / UNRELATED / UNCERTAIN independently.
This labeled set becomes ground truth for calibration measurement,
separate from verify_stories.py.
"""

import random, json

def sample_pairs_for_blind_labeling(all_accused_ids: list, n: int = 50) -> list:
    random.seed(42)  # reproducible
    return [dict(zip(["accused_a", "accused_b"], random.sample(all_accused_ids, 2)))
            for _ in range(n)]

def build_labeling_packet(pairs: list, fir_lookup: dict) -> list:
    """Raw narrative text only -- no system metadata, no story labels."""
    packet = []
    for pair in pairs:
        firs_a = [f for f in fir_lookup.values() if pair["accused_a"] in f.get("accused_ids", [])]
        firs_b = [f for f in fir_lookup.values() if pair["accused_b"] in f.get("accused_ids", [])]
        packet.append({
            "pair_id": f"{pair['accused_a']}_{pair['accused_b']}",
            "person_a_narratives": [f["narrative"] for f in firs_a[:2]],
            "person_a_mo": [f["mo_descriptor"] for f in firs_a[:2]],
            "person_b_narratives": [f["narrative"] for f in firs_b[:2]],
            "person_b_mo": [f["mo_descriptor"] for f in firs_b[:2]],
            "label": None  # filled in by blind labeler
        })
    return packet
```

Packet handed to teammate as plain JSON/spreadsheet -- no code access, no system exposure. ~1 hour manual work for 50 pairs.

### Trap Scenario -- Deliberate False-Positive Test

```python
# data/scripts/plant_trap_scenario.py

"""
Two accused, near-identical MO, ZERO other connection -- different
districts, different years, no shared network/tattoos/vehicle.
MO similarity alone is the weakest evidence type in the Confidence
Engine (RAG-only, 0.50-0.55 base, flagged). If the system assigns
HIGH/MEDIUM here, the Confidence Engine is overweighting similarity
alone. LOW/UNVERIFIED with the correct flag means it's working.
"""

TRAP_PAIR = {
    "accused_a": {
        "id": "ACC-TRAP-001", "district": "Belagavi", "fir_date": "2021-04-12",
        "mo_descriptor": ("Accused approached victim near bus stop on foot, "
                          "snatched gold chain, fled on foot towards market area. "
                          "Morning hours, elderly female victim."),
        "tattoos": [], "vehicle": None, "network": []
    },
    "accused_b": {
        "id": "ACC-TRAP-002", "district": "Kalaburagi", "fir_date": "2024-09-03",
        "mo_descriptor": ("Accused approached victim near bus stop on foot, "
                          "snatched gold chain, fled on foot towards market area. "
                          "Morning hours, elderly female victim."),
        "tattoos": [], "vehicle": None, "network": []
    }
}

async def verify_trap_scenario():
    from shared.catalyst_client import kb_search
    from shared.graph_client import run_query
    from pipeline.confidence_engine import compute_confidence
    from pipeline.evidence import EvidenceItem

    # RAG should find them similar
    results = await kb_search(query=TRAP_PAIR["accused_a"]["mo_descriptor"], top_k=10)
    found_b = any(TRAP_PAIR["accused_b"]["id"] in r.get("accused_ids", [])
                  for r in results["results"])
    print(f"RAG found trap pair via MO: {found_b} (expected True)")

    # Graph should find zero connection
    graph_result = await run_query("""
        MATCH (a:Accused {id: $a})-[*1..3]-(b:Accused {id: $b})
        RETURN count(*) as connections
    """, {"a": TRAP_PAIR["accused_a"]["id"], "b": TRAP_PAIR["accused_b"]["id"]})
    connections = graph_result[0]["connections"] if graph_result else 0
    print(f"Graph connections: {connections} (expected 0)")

    # Run through actual Confidence Engine -- the real test
    test_item = EvidenceItem(
        fir_id="FIR-TRAP-B", relevance_score=0.85, sources=["rag"],
        convergent=False, evidence_path=None,
        similarity_reason=TRAP_PAIR["accused_b"]["mo_descriptor"],
        fir_date=TRAP_PAIR["accused_b"]["fir_date"]
    )
    signal = compute_confidence(test_item)
    print(f"Confidence tier: {signal.tier} (expected low or unverified)")
    print(f"Flags: {signal.flags}")

    assert signal.tier in ("low", "unverified"), (
        f"TRAP SCENARIO FAILED: assigned {signal.tier} to a pair with zero "
        f"real connection -- Confidence Engine overweighting MO similarity"
    )
    assert len(signal.flags) > 0, "TRAP SCENARIO FAILED: no flag raised"
    print("TRAP SCENARIO PASSED")

if __name__ == "__main__":
    import asyncio
    asyncio.run(verify_trap_scenario())
```

This is a launch blocker -- wired into the same pre-demo sequence as `verify_stories.py`, not optional.

### Confidence Calibration Measurement

```python
# data/scripts/measure_confidence_calibration.py

"""
Uses the blind-labeled set + trap scenario as ground truth. For each
labeled pair, runs the actual pipeline and checks whether the assigned
tier matches the human label. Target: HIGH tier >= 85% actually
connected. If not, tighten thresholds in confidence_engine.py --
do not relabel data to match.
"""

import json

async def run_calibration_check(labeled_packet_path: str):
    with open(labeled_packet_path) as f:
        labeled_pairs = json.load(f)

    results_by_tier = {"high": [], "medium": [], "low": [], "unverified": []}

    for pair in labeled_pairs:
        if pair["label"] is None:
            continue
        system_tier = await get_system_confidence_for_pair(
            pair["accused_a"], pair["accused_b"]
        )
        human_connected = pair["label"] in ("CONNECTED", "LIKELY_CONNECTED")
        results_by_tier[system_tier].append(human_connected)

    targets = {"high": (">=85%", lambda p: p >= 85),
               "medium": (">=50%", lambda p: p >= 50),
               "low": ("<40%", lambda p: p < 40),
               "unverified": ("<25%", lambda p: p < 25)}

    print(f"{'Tier':<12} {'N':<6} {'% Connected':<14} {'Target':<8} {'Status'}")
    for tier in ["high", "medium", "low", "unverified"]:
        items = results_by_tier[tier]
        if not items:
            print(f"{tier:<12} 0      no data"); continue
        pct = sum(items) / len(items) * 100
        target_str, check_fn = targets[tier]
        status = "OK" if check_fn(pct) else "MISCALIBRATED"
        print(f"{tier:<12} {len(items):<6} {pct:<14.1f} {target_str:<8} {status}")

    high = results_by_tier["high"]
    if high:
        high_acc = sum(high) / len(high) * 100
        if high_acc < 85:
            print(f"\nWARNING: HIGH tier {high_acc:.1f}% correct against blind "
                  f"labels. Revisit sub-score weights in confidence_engine.py "
                  f"-- the 0.80 cutoff or individual evidence-strength weights.")
        else:
            print(f"\nHIGH tier calibration acceptable: {high_acc:.1f}%")
```

If HIGH tier underperforms, the fix is revisiting weights in `compute_confidence()` (Section 12) -- e.g. SHARED_TATTOO's 0.65 producing too many false HIGH classifications -- not adjusting the labels to fit.

### Pre-Demo / Pre-Submission Sequence

```bash
python data/scripts/plant_trap_scenario.py          # one-time: adds trap pair
python data/scripts/blind_evaluation_set.py         # generates labeling packet
# -- hand to teammate, ~1hr manual labeling --
python data/scripts/verify_trap_scenario.py         # MUST PASS -- launch blocker
python data/scripts/measure_confidence_calibration.py  # informational, cite if good
```

If a judge asks "how do you know your confidence levels mean anything," the answer becomes "measured against blind human labels, here's the calibration result" rather than an unverified design claim.

---

## 20. OCR Layer

### Format Detection + Routing

```python
# ingestion/format_detector.py
import magic, fitz

def detect_format(file_bytes: bytes) -> str:
    mime = magic.from_buffer(file_bytes, mime=True)
    if mime in ("application/json", "text/plain", "text/csv"):
        return "structured_text"
    elif mime == "application/pdf": return "pdf"
    elif mime in ("image/jpeg", "image/png", "image/tiff"): return "image"
    return "unknown"

def pdf_to_image(pdf_bytes: bytes, dpi: int = 200) -> bytes:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    return doc[0].get_pixmap(dpi=dpi).tobytes("png")

async def route_fir_input(file_bytes: bytes) -> dict:
    fmt = detect_format(file_bytes)
    if fmt == "structured_text":
        import json; return json.loads(file_bytes.decode())
    img = pdf_to_image(file_bytes) if fmt == "pdf" else file_bytes
    from ingestion.ocr_extractor import extract_from_image
    return await extract_from_image(img)
```

Dependencies: `pymupdf>=1.23.0`, `python-magic>=0.4`

---

## 21. Input Validation Middleware

Runs before anything else on every request. Synchronous, fast, no AI involved. Protects against memory exhaustion, prompt injection, and malformed input crashing the server for all users.

### Limits

```python
MAX_QUERY_CHARS    = 500
MAX_AUDIO_BYTES    = 5 * 1024 * 1024    # 5MB
MAX_DOCUMENT_BYTES = 10 * 1024 * 1024   # 10MB for scanned FIR PDFs
```

### Injection Pattern Denylist

```python
INJECTION_PATTERNS = [
    # Cypher injection
    r'\bMATCH\b', r'\bMERGE\b', r'\bCREATE\b', r'\bDELETE\b',
    r'\bDETACH\b', r'\bCALL\b.*\bgds\b',
    # SQL injection
    r'\bDROP\b', r'\bTRUNCATE\b', r'\bUNION\b.*\bSELECT\b',
    r'\bINSERT\b.*\bINTO\b', r'\bEXEC\b',
    # Prompt injection
    r'ignore (previous|all|above) instructions',
    r'you are now', r'new persona', r'system prompt',
    r'<\|.*\|>',
]
```

### Validation Functions

```python
# backend/api/middleware/input_validator.py

def validate_text_query(query: str) -> str:
    if not query or not query.strip():
        raise HTTPException(400, "Query cannot be empty")
    if len(query) > MAX_QUERY_CHARS:
        raise HTTPException(400, f"Query too long. Maximum {MAX_QUERY_CHARS} chars.")
    for pattern in COMPILED_PATTERNS:
        if pattern.search(query):
            raise HTTPException(400, "Query contains invalid keywords.")
    return query.strip()

def validate_audio(audio_bytes: bytes) -> bytes:
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise HTTPException(413, "Audio file too large. Maximum 5MB.")
    mime = magic.from_buffer(audio_bytes[:2048], mime=True)
    if mime not in {"audio/webm", "audio/wav", "audio/mp4",
                    "audio/mpeg", "audio/ogg", "audio/x-m4a"}:
        raise HTTPException(415, f"Unsupported audio format: {mime}")
    return audio_bytes

def validate_document(doc_bytes: bytes) -> bytes:
    if len(doc_bytes) > MAX_DOCUMENT_BYTES:
        raise HTTPException(413, "Document too large. Maximum 10MB.")
    mime = magic.from_buffer(doc_bytes[:2048], mime=True)
    if mime not in {"application/pdf", "image/jpeg",
                    "image/png", "image/tiff", "application/json"}:
        raise HTTPException(415, f"Unsupported document format: {mime}")
    return doc_bytes
```

### Integration

Called as the first line in every route handler before any pipeline code:

```python
# /api/query
clean_query = validate_text_query(request.query)

# /api/transcribe
validated_audio = validate_audio(await audio.read())

# /api/ingest (document upload)
validated_doc = validate_document(await doc.read())
```

### Protection Coverage

| Threat | Without | With |
|---|---|---|
| 50MB audio upload | Memory exhaustion, server crash for all users | Rejected at 5MB before read |
| 10K character query | Sent to Qwen 14B, token waste, injection risk | Rejected at 500 char limit |
| Cypher keyword in query | Reaches pipeline, unpredictable behavior | Rejected with 400 |
| Wrong file type | Pipeline errors | Rejected with 415 |
| Empty query | NER call made with empty input | Rejected with 400 |

Note: denylist catches obvious attacks. In production this combines with RBAC so only authenticated officers reach the API at all.

---

## 22. RBAC + Audit Logging

**Split across the two services (Section 6):** RBAC gatekeeping happens in AppSail's middleware (`backend/api/middleware/rbac.py`) -- it runs before a job is ever dispatched, same as before. Audit logging of the *result* (`intent`, `firs_returned`, `confidence_breakdown`) now happens inside the pipeline Event Function (`pipeline_function/pipeline/audit.py`), not AppSail, since that data only exists once the pipeline has actually run -- AppSail's middleware never sees `intent` or `confidence_breakdown` because it no longer executes NER, planning, retrieval, or synthesis itself. The audit write happens as the final step of `pipeline_function/main.py`'s handler, alongside the `status="done"` write to the job-status document.

### Minimum Viable (Hackathon)

Single hardcoded Inspector context. Audit logging running and visible in Catalyst NoSQL during demo.

### Audit Log Structure

```python
# pipeline_function/pipeline/audit.py -- called from the Event Function handler
# after synthesis completes, not from AppSail

log_entry = {
    "timestamp": datetime.utcnow().isoformat(),
    "session_id": session_id,
    "officer_id": officer.officer_id,
    "badge_number": officer.badge_number,
    "officer_role": officer.role.name,
    "officer_district": officer.district,
    "query": query,
    "intent": intent,
    "firs_returned": [item.fir_id for item in evidence.items],
    "confidence_breakdown": {"high": N, "medium": N, "low": N, "unverified": N},
    "result_count": len(evidence.items)
}
content_str = json.dumps(log_entry, sort_keys=True)
log_entry["integrity_hash"] = hashlib.sha256(content_str.encode()).hexdigest()
await nosql_insert("audit_logs", log_entry)
```

---

## 23. Frontend

### Tech Stack

React (Vite) + Tailwind + Recharts + Leaflet.js + Cytoscape.js + SSE

No DB credentials in frontend. NetworkGraph receives JSON from `/api/graph/{accused_id}`.

### Component Tree

```
App
  Layout
    Sidebar (session history, new chat)
    MainPanel
      ChatWindow (owns SSE connection)
        StatusIndicator (renders 'progress' events -- "Retrieving evidence...", etc.)
        MessageList
          UserMessage
          AssistantMessage
            TextResponse (renders full answer on 'token' event -- arrives once, not
                          incrementally, since the pipeline now runs off-AppSail)
            ConfidenceBadge (per-FIR tier)
            EvidenceCitations
            ReasoningTrace (collapsible)
        DashboardPanel (analytical mode only)
          NetworkGraph    (Cytoscape.js, JSON-fed)
          CrimeMap        (Leaflet.js + OpenStreetMap)
          TrendChart      (Recharts)
          DonutChart      (Recharts)
        InputBar
          TextInput
          VoiceButton     (hold-to-record -> /api/transcribe -> Catalyst ASR)
          SendButton
```

### SSE Event Routing

**Changed from the original design:** the pipeline now runs in a separately-triggered Event Function (Section 6), not inside the AppSail request LangGraph used to stream from directly. AppSail polls a job-status document in Catalyst NoSQL and forwards transitions as SSE events, so the frontend now gets a `progress` event per pipeline stage instead of live token-by-token streaming, and the full answer arrives in one `token` event when the job completes rather than incrementally. `ChatWindow` should render `progress` events as a status indicator ("Understanding query...", "Retrieving evidence...", etc., mapped from `status` values like `ner_complete`, `retrieval_complete`) rather than appending partial text.

```javascript
await streamQuery(query, sessionId, {
    onProgress:      (status) => update status indicator (e.g. "Retrieving evidence..."),
    onToken:         (token)  => render full answer text (arrives once, not incrementally),
    onEvidence:      (data)   => populate EvidenceCitations,
    onVisualization: (data)   => push to DashboardPanel,
    onDone:          ()       => mark query complete,
    onError:         (err)    => surface pipeline failure to officer
})
```

### VoiceButton

MediaRecorder captures audio -> sends to `/api/transcribe` -> Catalyst Kannada ASR -> text returned to InputBar. No local ASR model.

### State Management

React Context only. No Redux.
- `SessionContext` -- session_id + message history
- `UIContext` -- urgency mode toggle, sidebar state

---

## 24. Build Phases

### Phase 1 -- Foundations (Week 1)

**Already done, ahead of Phase 1 proper (console-verified 28 June 2026):**
- [x] Catalyst project created (`PS1-CIS`, confirmed Development tier -- closes the dev/prod question below)
- [x] Signals Custom Publisher (`ps1-query-publisher`) created and reachable via plain HTTP POST
- [x] Signals Rule (`cis_query_rule`) created, routing the publisher's `query_job` event to a Function target with no filter condition
- [x] Pipeline Function skeleton (`ps_1_cis_function`, Python 3.13) deployed and triggered successfully end-to-end from an external `curl` POST -- not just a console click. Delivery confirmed `Success` on attempt #1; dashboard shows `Total Invocations: 1`, `Invocation Errors: 0`
- [x] Timeout question fully resolved, exact figure confirmed: `context.get_max_execution_time_ms()` returned **900000ms (exactly 15 minutes)** from inside a live invocation -- the platform's own configured ceiling, not estimated. A 60-second sleep and a separate ~400-second sleep both completed clean with `Time-Outs: 0`, consistent with this figure.

**Day 1 confirmations remaining (cheap, do before deeper build work):**
- [ ] Now that dev tier is confirmed, add up actual planned ZTSQL row counts against the 5,000-per-table / 25,000-per-project caps, using the real schema's tables (Section 15): `cases` (~4,000, leaving 1,000 rows of headroom below the per-table cap), `accused` (~1,500), plus `victims`, `complainants`, `arrest_surrenders`, and `case_act_sections` -- not yet totaled. This is now a real constraint to plan around, not a hypothetical.
- [ ] Email support@zohocatalyst.com (or check for updated docs) about Qwen/Zia LLM-specific rate limits -- the consequence is known (≈10-min stall) but the exact threshold isn't. Don't wait on a reply to start building.

**Infrastructure setup remaining:**
- [ ] Update `pipeline_function/main.py`'s handler to the corrected envelope-unwrapping version (Section 6) -- the version tested above was a minimal logging/sleep test, not the real pipeline handler yet
- [ ] Memgraph on Oracle Cloud -- Docker running, MAGE verified, constraints created
- [ ] AppSail FastAPI skeleton -- thin front door only (validation, cache check, job dispatch, SSE poll loop); no Catalyst LLM/VLM/KB/SQL clients here
- [ ] Qwen 14B test call from the pipeline Function (not AppSail) returning valid JSON
- [ ] KB test FIR document uploaded and searchable
- [ ] React shell on Catalyst Slate
- [ ] Integration contracts frozen (graph schema, API shapes, Evidence Object schema, job-status document schema)
- [ ] Configure pipeline Function memory explicitly at 512MB (`catalyst functions:config --memory 512`) rather than leaving it at the 256MB default -- the ~250MB usage estimate (Architecture Section 4) leaves almost no margin otherwise

**Gate: PASSED.** Custom Publisher -> Rule -> Function target triggers end-to-end, console-verified via external trigger, not just documentation. This was the single most important unclosed item from planning across three design corrections (Circuit, Custom Event Listener, Signals) -- it is now closed by direct evidence. Remaining Phase 1 work can proceed without this caveat hanging over it.

### Phase 2 -- Core Pipeline + Template Router Scaffold (Week 2)

- [ ] Template router scaffold (5 templates -- gets pipeline working fast) inside the pipeline Function
- [ ] NER + intent extraction working on Kannada + English test queries
- [ ] Memgraph traversal returning results from seeded data
- [ ] Catalyst KB RAG returning ranked FIR matches
- [ ] Evidence Object assembly + Confidence Engine
- [ ] Synthesis producing field_urgent + analytical responses
- [ ] Catalyst Kannada ASR wired to VoiceButton (via AppSail proxy, Section 6)
- [ ] Chat UI connected via SSE -- polling-based progress + single-shot answer render (Section 23), not live token streaming
- [ ] 600 FIR initial dataset ingested for pipeline testing

Gate: Full pipeline end-to-end on 600 FIRs, running inside the Event Function and reported back to the officer via AppSail's SSE poll loop. "Find associates of [accused]" returns ranked evidence.

### Phase 3 -- DAG Planner + Full Dataset (Week 3)

- [x] Full LangGraph DAG planner replacing template router
- [x] DAG planner tested against chaos query suite
- [x] 4,000 FIR dataset generated (overnight narrative run)
- [x] Full dataset ingested -- KB + Memgraph + ZTSQL
- [x] MAGE algorithms run on full graph -- performance benchmarked
- [x] field_urgent latency validated < 10s at 5K FIR scale
- [x] Dashboard panels live -- Cytoscape, Leaflet, Recharts
- [x] Multi-turn coreference working
- [x] All 4 planted stories verified at expanded scale

Gate: DAG planner handles chaos queries gracefully. All latency targets met.

### Phase 4 -- Robustness + Production Readiness (Week 4)

- [x] Zero-result handler in synthesis
- [x] Graceful degradation on API failures
- [x] OCR feature demo -- Qwen 7B VLM on one realistic scanned FIR
- [x] PDF export (WeasyPrint)
- [x] Catalyst TTS for voice response
- [ ] Memgraph Oracle VM hardened (persistent volume, restart policy)
- [x] NER eval suite >= 90% pass rate
- [x] verify_stories.py passing on full 5K dataset
- [x] Trap scenario planted, verify_trap_scenario.py passing -- launch blocker
- [ ] Blind evaluation packet labeled by teammate not involved in story design
- [ ] Confidence calibration measured -- HIGH tier >= 85% against blind labels
- [x] Chaos test suite passing
- [ ] Full Catalyst deployment verified end-to-end

Gate: Any query, any phrasing, English or Kannada -- sensible response always returned. Trap scenario passes. Confidence calibration measured and acceptable.

---

## 25. Pre-Demo Checklist

```
At least 30 minutes before judging:
  [ ] Confirm keep-warm GitHub Action has been running continuously --
      check last successful ping was within 5 minutes
      (AppSail instance lifetime is exactly 5 minutes -- any gap
      longer than this guarantees a cold start on next request)
  [ ] Qwen 14B test call from the pipeline Function -- confirm responsive
      (not from AppSail -- AppSail no longer calls Qwen directly, Section 6)
  [ ] Custom Publisher -> Rule -> Function trigger path -- confirm a test
      job dispatched from AppSail reaches "done" status in Catalyst NoSQL
  [ ] Confirm CATALYST_SIGNALS_PUBLISHER_URL in AppSail's .env points at the
      PRODUCTION publisher URL, not the development one -- these are
      different URLs for the same publisher (Architecture Section 16);
      using the dev URL during judging is a silent failure mode, not a
      loud error, so this needs an explicit check, not just "it worked once"
  [ ] Memgraph on Oracle VM -- confirm running (bolt connection test)
  [ ] Catalyst KB -- confirm FIR collection loaded and searchable
  [ ] Run full compound query end-to-end -- confirm pipeline warm and
      AppSail's SSE poll picks up "done" status at a comfortable latency
      (no 30s wall to worry about now -- the pipeline Function has 15 minutes;
      what matters here is officer-perceived latency, not a hard platform cutoff)
  [ ] Pre-load session with Story 1 context
  [ ] Scanned FIR image for OCR demo ready on desktop
  [ ] Screen recording started as fallback

Before judging week (one-time, not same-day):
  [ ] verify_trap_scenario.py passes -- launch blocker if it fails
  [ ] Confidence calibration measured against blind labels --
      have the actual HIGH-tier accuracy number ready to cite
      if a judge asks how confidence levels were validated

During judging:
  [ ] Keep-warm pings continue running in background throughout --
      do not let the session run long enough to risk a 5+ minute
      gap between officer/judge queries on the AppSail side

Fallback plan:
  [ ] Recorded demo video ready (full pipeline, open floor queries)
  [ ] If Memgraph unreachable: restart Oracle VM Docker container
  [ ] If Catalyst LLM slow: check Catalyst status page
  [ ] If a query takes noticeably long: this is no longer an AppSail
      30s hard timeout risk (that limit no longer applies to the pipeline
      itself, Section 6) -- it's perceived latency only. Narrate progress
      via the status indicator and let it finish, or retry with
      field_urgent mode if it's genuinely stalled past a minute or two
```

---


## To Discuss / Remaining

**Resolved across three sync passes with Architecture Section 16:**
- [x] **Pass 1:** this document previously described the pipeline running synchronously inside one AppSail request via SSE streaming -- corrected to the AppSail-front-door + separately-triggered-Function split, originally via a Custom Event Listener.
- [x] **Pass 2:** the Custom Event Listener itself turned out to be a deprecated, EOL'd Catalyst component (Event Listeners deprecation reached EOL 30 April, 2026; new Catalyst projects cannot access it). Every reference has been corrected to **Catalyst Signals** -- Custom Publisher -> Rule -> Function target -- which carries the same confirmed 15-minute budget. Updated throughout Sections 2, 4, 6, 23, 24, and 25. See Architecture Section 16 for the full verification against `docs.catalyst.zoho.com`, including both corrections.
- [x] **Pass 3:** Data Store dev-cap math actually computed (see Phase 1 Day 1 confirmations above) -- `firs` table will sit at 4,000 rows to leave headroom if the project lands in dev tier. Job Scheduling confirmed as a real, non-deprecated Signals fallback (was previously listed as plausible-but-unverified). A previously-cited "25 publishers / 100 rules per project" Signals limit could not be re-confirmed and has been removed from the architecture doc; the real confirmed limits (64KB/event, 5 targets/rule) aren't a constraint at PS-1's scale regardless. Pipeline Function got its own RAM estimate for the first time (Architecture Section 4) instead of double-counting LangGraph under AppSail.

**Pass 4 (this revision) -- hackathon workshop Q&A + KSP schema received:**
- [~] **Rate limit consequence confirmed, design updated.** Organizers confirmed hitting the Qwen/Zia rate limit causes a ~10-minute stall before reset (exact threshold still unknown), and hackathon credits should cover normal usage. The retry logic (Section 8) has been updated to explicitly fail fast into degraded-response mode rather than attempt to wait out a stall that long -- waiting it out inside a 15-minute pipeline budget isn't viable. New open question: whether the stall is scoped per-call-type, per-project, or per-account, which determines whether one rate-limit event degrades one LLM call or compounds across a query's three sequential calls.
- [x] **Catalyst-first principle confirmed.** Organizers confirmed: use Catalyst's in-house services wherever available (ASR/TTS via Catalyst Kannada NLP, as already planned), external services only when Catalyst has no equivalent. Validates Memgraph as the one intentional exception (no Catalyst graph DB) and confirms no other component should default to external.
- [x] **30s timeout question -- RESOLVED by console test, supersedes the ambiguous workshop answer.** The workshop answer named Job Scheduling without confirming Signals specifically -- that ambiguity is now moot. A real Custom Publisher + Rule + Function target was built and tested end-to-end (see Pass 5 below); Signals works, console-confirmed, not just consistent with what organizers said.
- [x] **KSP schema received and reconciled -- structural update, not just renaming.** Official ER diagram for the Police FIR System database (`CaseMaster`, `Victim`, `ComplainantDetails`, `Accused`, `ArrestSurrender`, `Act`/`Section`, `CrimeHead`/`CrimeSubHead`, full org hierarchy) replaces the original guessed flat schema. Key changes carried through `FIELD_NAME_MAP` (Section 17), the ZTSQL table design (Section 15), and the Pydantic models (Section 5): crime classification is now lookup-driven (`CrimeHeadID`/`CrimeSubHeadID`) instead of a flat `crime_type` string; Act+Section is genuinely many-to-many via a junction table instead of a flat comma-separated field; `Victim`, `Complainant`, and `Accused` are three distinct entities instead of one `accused` list with a `role` field; and `CrimeNo` is a parseable 18-digit composite key (category+district+unit+year+serial) rather than an opaque ID -- the parser for this has been verified against all 4 worked examples in the source document plus an independent cross-check, so it's safe to build against.

**New team decisions surfaced by the real schema -- need your input, not further research (see Section 17 "Open Decisions" for full detail):**
- [ ] **Whether to ingest demographic fields on `ComplainantDetails`** (occupation, religion, caste) at all, for display/context purposes. **Already protected:** Architecture Section 24's "never included under any circumstance" rule for `activityScore` already covers religion/caste regardless of this decision, so no scoring-side risk either way -- the remaining question is purely about ingestion and UI display, not bias-audit scope.
- [x] ~~How to model `Victim`/`Complainant`/`Accused` in Memgraph~~ -- RESOLVED by precedent already in Architecture Section 15 (Victim was already a distinct node type; Complainant follows the same pattern). Implementation Section 14's Cypher constraints have been brought in line with this (added `:Victim` and `:Complainant` constraints) -- this was a doc-sync fix, not a new decision needed from the team.
- [ ] **Which district "counts" for a case when they diverge** -- a case's filing district (via `PoliceStationID` -> `Unit` -> `District`) vs. an arrest's district (`ArrestSurrenderDistrictId`) can be different. Decide which the NER/retrieval layer treats as "the" district when an officer asks a district-scoped question.

**Pass 5 (this revision) -- hands-on Signals console verification, 28 June 2026:**
- [x] **The single biggest open item across both documents is now closed by direct evidence.** A real Catalyst project (`PS1-CIS`) was used to create a Custom Publisher (`ps1-query-publisher`), a Rule (`cis_query_rule`), and a Function target (`ps_1_cis_function`, Python 3.13). The chain was triggered externally via `curl` -- not a console button click -- and confirmed working: publisher accepted the event, Rule delivery log shows `Status: Success` on attempt #1, and the Function's own dashboard shows `Total Invocations: 1`, `Invocation Errors: 0`. A 60-second test sleep completed clean with `Time-Outs: 0`, directly ruling out a 30-second-style cap on this Function type.
- [x] **Real payload envelope shape discovered and corrected in the handler code (Section 6).** `event.get_raw_data()` returns Catalyst's full Signals envelope (`{'version', 'account', 'events': [{'data': {...actual job fields...}}], 'rule_id', 'target_id', 'attempt'}`), not the posted JSON body directly. An earlier draft assumed `event_data["job_id"]` worked at the top level -- corrected to unwrap `raw_data['events'][0]['data']` first, based on a real captured payload, not a guess.
- [x] **Dev tier confirmed directly from the test payload** (`"environment": "Development"`), closing the dev-vs-prod ambiguity that had been gating the Data Store capacity question.

**Genuinely still open -- requires further testing or further organizer contact:**
- [x] **Full 15-minute budget -- RESOLVED, exact figure confirmed (28 June 2026, same session as the initial Signals test).** `context.get_max_execution_time_ms()` called from inside a live invocation returned **900000ms exactly** -- the platform's own SDK reporting its configured ceiling, not inferred from docs or a single survived sleep. A ~400-second sleep test completed cleanly in the same run with no timeout. The Signals Analytics dashboard separately confirms **4 events received, 2 success (100% of routed events), 0 failed, 0 unmatched, 2 unprocessed** (the 2 unprocessed are the original pre-Rule test events from before the chain was wired up, consistent with everything observed earlier) -- the platform-level view fully agrees with the function-level logs.
- [ ] **Concurrent/load behavior under Signals untested.** Only a single test invocation has been verified so far. Worth a multi-request test before judging day -- the scenario that actually matters (several officers/judges querying at once) hasn't been simulated yet.
- [ ] **Job Scheduling side-by-side test, now lower priority.** With Signals proven working end-to-end, there's less urgency here, though it remains the documented fallback and is still worth a console test eventually.
- [ ] Exact Qwen/Zia rate limit threshold (requests/min or concurrent) -- consequence is known, number isn't. Worth a follow-up question if there's another chance to ask.
- [ ] Whether the rate-limit stall is scoped per-call-type, per-project, or per-account (open question from Section 8 update).
- [ ] **Data Store capacity -- now actionable, dev tier confirmed.** Confirm actual row counts using the real schema's table set (Section 15) -- `cases` (~4,000, leaving headroom below the 5,000/table cap) + `accused` (~1,500) + `victims` + `complainants` + `arrest_surrenders` + `case_act_sections`, none of which have been totaled yet against the 25,000/project dev cap. This is now a real, confirmed-tier constraint, not a hypothetical -- worth doing soon.
- [x] Pipeline Function memory tier -- RESOLVED. Confirmed range 128-512MB, default 256MB. The ~250MB estimate (Architecture Section 4) leaves almost no margin at default -- explicitly configure 512MB via `catalyst functions:config --memory 512` once the function is deployed, rather than leaving it at the unconfigured default.
- [~] Catalyst Function keep-warm -- PARTIALLY RESOLVED. Cold starts are confirmed real (independent developer reports), but no documented idle-timeout threshold was found (unlike AppSail's clean 5-minute spec). Plan to observe this empirically now that the pipeline Function is actually deployed and reachable.
- [ ] Confirm Catalyst NoSQL read latency from AppSail's polling loop is low enough that a 0.5s poll interval feels responsive; widen if not (Section 6, Architecture Section 16) -- now testable, since console access exists.
- [ ] Source real or realistic Kannada/code-switched query samples earlier rather than discovering NER gaps mid-Phase-2 -- the 90%+ target is currently validated only against 30 hand-written examples.
- [ ] Begin Phase 1 in earnest -- the Signals gate is now passed; real build work (catalyst_client.py, entity_lookup_resolver.py, sql_client.py, ingestion) can proceed
