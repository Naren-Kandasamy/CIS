# PS-1: Conversational Crime Intelligence System
## Architecture Document — Confirmed Design (Clean Revision)

---

## 1. Problem Framing

### PS-1 vs PS-2

| Dimension | PS-1 | PS-2 |
|---|---|---|
| User | Field investigator / KSP officer | SCRB analyst / policymaker |
| Interaction | Natural language (chat + voice) | Visual dashboards, maps |
| Goal | Case-specific reasoning | Trend analysis & strategic insights |
| Output | Direct answers, evidence-backed explanations | Charts, aggregated statistics |

Both systems share the same crime graph, ML models, and data pipelines. They differ only in interface layer.

---

## 2. Core Architecture: Hybrid GraphRAG

### Why single-system approaches fail

**Pure RAG** fails for multi-hop relationships, entity-specific queries, precise filtering.

**Pure Graph DB** fails for ambiguous natural language, conversational context, vague references ("that guy from Shivajinagar").

### Solution

Combine:
- **Graph traversal** -- relationships, network analysis (Memgraph)
- **Semantic search** -- MO similarity, narrative search (Catalyst KB + RAG)
- **SQL** -- aggregations, statistics, filtering (Catalyst Data Store / ZTSQL)
- **LLM** -- planning, routing, synthesis, explanation (GLM-4.7-Flash via Catalyst)

**Key principle:** LLM plans and synthesizes. Systems retrieve. LLM never directly queries raw data.

---

## 3. Confirmed Tech Stack

### AI Layer (Catalyst Native -- No External AI Platforms)

| Component | Choice | Notes |
|---|---|---|
| LLM | GLM-4.7-Flash Instruct (Catalyst hosted) | 128k context, data private, no external key |
| LLM fallback | Groq + Llama 3.1 70B (offline/dev only) | Not for production |
| NER + Intent | GLM-4.7-Flash via structured prompt | Single call, combined NER + intent |
| Embeddings | Catalyst KB managed | No model loaded in AppSail |
| Semantic search | Catalyst KB + RAG | Built-in chunking, reranking, citations |
| Kannada ASR | Catalyst NLP (audio to text) | Handles Kannada/Hindi/English natively |
| Kannada TTS | Catalyst NLP (text to audio) | For voice response output |
| OCR | Qwen 3.6 35B VLM (Catalyst hosted) | For scanned FIR documents only |

### Data Layer

| Component | Choice | Notes |
|---|---|---|
| Graph DB | Memgraph Community (Docker) | Full MAGE algorithms, no GDS license needed |
| Graph hosting | Oracle Cloud Free Tier ARM VM (4GB) | Always free, Docker-ready |
| Structured DB | Catalyst Data Store (ZTSQL) | Replaces PostgreSQL |
| Session memory | Catalyst NoSQL | Per-conversation state |
| Audit logs | Catalyst NoSQL | Tamper-evident with SHA-256 hash |

### Application Layer

| Component | Choice | Notes |
|---|---|---|
| Front door | FastAPI on Catalyst AppSail | Thin layer only -- validation, cache check, Signals dispatch, SSE poll loop. ~300MB RAM. No LLM/Memgraph calls here (Section 16) |
| Pipeline runtime | Catalyst Function, triggered via Signals | Hosts LangGraph + the full NER/planning/retrieval/synthesis pipeline. 15-min budget, not AppSail's 30s (Section 16) |
| Orchestration | LangGraph | Stateful multi-turn conversation -- runs inside the pipeline Function, not on AppSail |
| Frontend | React on Catalyst Slate | Static hosting |
| Graph visualization | Cytoscape.js | JSON-fed, no DB credentials in browser |
| Map | Leaflet.js + OpenStreetMap | No API key needed |
| Charts | Recharts | React-native, open source |

### What Was Eliminated

| Removed | Replaced By |
|---|---|
| faster-whisper (local) | Catalyst Kannada ASR API |
| gTTS / pyttsx3 | Catalyst Kannada TTS API |
| Qdrant Cloud | Catalyst KB + RAG |
| multilingual-e5-large | Catalyst managed embeddings |
| MuRIL / IndicBERT | GLM-4.7-Flash prompt-based NER |
| Cross-encoder reranker | Custom Python Evidence assembler |
| PostgreSQL | Catalyst Data Store (ZTSQL) |
| Neo4j AuraDB | Memgraph on Oracle Cloud |
| networkx + cdlib | Memgraph MAGE native algorithms |
| Neovis.js | Cytoscape.js (no browser DB connection) |
| riskScore | activityScore (heuristic, not ML) |

---

## 4. Resource Footprint -- AppSail + Pipeline Function

Per the Section 16 hosting split, AppSail and the pipeline Function are separate deployments with separate resource profiles. AppSail's original "FastAPI + LangGraph" combined estimate no longer reflects what runs where -- LangGraph now runs inside the pipeline Function, not on AppSail.

### AppSail (Front Door Only)

All AI inference via Catalyst APIs, called from the pipeline Function, not from AppSail. No models loaded in AppSail, and no LangGraph compiled here either.

| Component | RAM |
|---|---|
| FastAPI (validation, cache check, SSE poll loop) | ~100MB |
| Catalyst NoSQL client | ~30MB |
| httpx (Signals dispatch only) | ~30MB |
| **Total** | **~160MB** |

Comfortably within 512MB default -- narrower than the original 300MB estimate, since AppSail no longer holds Memgraph driver or the compiled LangGraph state machine.

### Pipeline Function (Signals Function Target)

This is a rough estimate, not yet measured against an actual deployed Function -- flagged as an open item below.

| Component | RAM (estimated) |
|---|---|
| LangGraph compiled graph + state | ~100MB |
| Memgraph driver + connection pool | ~50MB |
| httpx clients (Qwen LLM, VLM, KB, ZTSQL) | ~50MB |
| Retrieval/confidence/synthesis Python logic | ~50MB |
| **Total (estimated)** | **~250MB** |

**Resolved:** Catalyst Function memory is configurable between 128MB and 512MB, default 256MB if unset (confirmed via official docs; CPU scales automatically with memory and isn't separately configurable). The pipeline Function's ~250MB estimate above fits inside the 256MB default with only ~6MB of margin -- too tight given the estimate itself is still rough, not measured against an actual deployment. **Decision: configure the pipeline Function explicitly at 512MB** (`catalyst functions:config --memory 512`) once it exists, rather than relying on the unconfigured default. Still genuinely open: the ~250MB estimate itself hasn't been measured against a real cold/warm invocation -- 512MB gives comfortable headroom for that uncertainty without needing to measure precisely before Phase 1 starts.

---

## 5. High-Level Pipeline

```
Layer 0  -- Input (text / voice / scanned document)
Layer 0a -- Input Validation Gate (size limits, MIME checks, injection denylist)
Layer 0b -- Format Detection + OCR (Qwen 3.6 35B VLM if PDF/image)
Layer 0c -- Schema Mapping (CCTNS -> canonical FIRSchema)
Layer 1  -- Preprocessing (transliteration, code-switch normalization)
Layer 2  -- Query Understanding (NER + Intent + DAG Planner)
Layer 3  -- Retrieval (Memgraph + Catalyst KB + ZTSQL + Evidence Assembly)
Layer 4  -- Confidence Engine
Layer 5  -- LLM Synthesis + XAI (GLM-4.7-Flash)
Layer 6  -- Output (chat / voice / dashboard / PDF)
Layer 7  -- Session Memory + Feedback (Catalyst NoSQL)
Layer 8  -- Offline Ingestion Pipeline (ingestion time only)
```

---

## 6. Layer 0 -- Input Validation + OCR

### Input Validation Gate (First Boundary)

Before any input reaches OCR, NER, or the pipeline, a synchronous validation layer enforces hard limits. No AI involved -- pure size, type, and pattern checks.

**Why this matters:** Without it, a single oversized upload or malformed query can exhaust memory on a shared 512MB AppSail container and degrade the system for every concurrent officer. This is the same class of risk as SQL/Cypher injection -- the fix is the same class of defense: validate before trusting.

**Enforced limits:**

| Input | Limit | Rejection |
|---|---|---|
| Text query | 500 characters | 400 if exceeded or empty |
| Audio upload | 5MB | 413 if exceeded |
| Document upload (scanned FIR) | 10MB | 413 if exceeded |
| File type | Verified by MIME sniffing, not filename | 415 if mismatched |
| Cypher/SQL/prompt-injection keywords | Denylist pattern match | 400 if detected |

**Design principle:** This is a denylist, not a complete security solution -- it catches obvious attacks fast and cheap. In production this combines with RBAC (Section 23) so only authenticated officers reach the API at all. For the hackathon prototype, this layer demonstrates the right defensive posture to judges evaluating production-readiness.

This gate runs first, before format detection, before OCR, before anything else in Layer 0.

---

### Three Input Types (Post-Validation)

**Structured text (synthetic data / CCTNS digital exports):** parsed directly, no OCR.

**PDF or scanned image (real KSP FIRs):** Qwen 3.6 35B VLM extracts structured fields before ingestion pipeline runs.

**Voice:** Catalyst Kannada ASR transcribes audio to text, feeds into same text pipeline.

### Model Usage Clarification

| Model | Purpose | When Called |
|---|---|---|
| GLM-4.7-Flash Instruct | NER, intent, planning, synthesis | Every query -- all text reasoning |
| Qwen 3.6 35B VLM | Scanned FIR OCR extraction | Only when input is image or PDF |
| Catalyst Kannada NLP | ASR (voice->text), TTS (text->voice) | Voice input/output only |

### OCR Strategy for Demo

OCR is a production capability demonstrated as a feature moment, not a core demo dependency. Demo data is synthetic structured JSON -- OCR passes through immediately. Feature moment: upload one realistic scanned FIR, show Qwen 3.6 35B VLM extract fields live, narrate production relevance.

---

## 7. Layer 1 -- Preprocessing

### Voice
Catalyst Kannada ASR handles audio -> text. No local model. Supports Kannada, Hindi, English, and code-switched input.

### Text Normalization
1. **Transliteration:** Kannada script -> Roman (indic-transliteration library, runs locally, minimal RAM)
2. **Code-switch normalization:** GLM-4.7-Flash prompt-based (e.g. "case-alli" -> "in case")
3. **Name/place canonicalization:** Canonical dictionary of KSP districts, stations -- fuzzy matched via rapidfuzz

---

## 8. Layer 2 -- Query Understanding

### NER + Intent (Single GLM-4.7-Flash Call)

Combined into one call to avoid 4-6s extra latency. Temperature 0.0 for deterministic output.

**Entities extracted:** PERSON (name, role), LOCATION (name, district), FIR_ID, DATE, IPC_SECTION, CRIME_TYPE

**Coreference:** "him", "same case", "avan" flagged as `coreference_needed` sub_intent. Resolved against session memory in LangGraph, not in NER call itself.

**Example output:**
```json
{
  "entities": {
    "persons": [{"name": "Ravi Kumar", "role": "accused"}],
    "locations": [{"name": "Mysuru", "district": "Mysuru"}],
    "fir_ids": [], "dates": [], "ipc_sections": [], "crime_types": []
  },
  "intent": "network_analysis",
  "urgency": "field_urgent",
  "sub_intents": ["find_associates", "location_filter"]
}
```

**NER example library:** 30+ examples in `shared/ner_examples.py` covering all 6 intents, pure English, romanized Kannada, mixed code-switched, and edge cases. Single source of truth used by both live prompt and eval suite. Target: 90%+ pass rate on eval before any demo.

**Entity-to-Lookup Resolution:** `CRIME_TYPE` and `IPC_SECTION` are extracted from officer queries as free text ("murder", "302"), but the real schema resolves these via lookup tables (`CrimeSubHead`, `Act`/`Section`), not flat strings. This is natively solved directly within the LangGraph pipeline via `resolve_crime_sub_head` and `resolve_act_section` running in parallel to translate free-text outputs into database-ready lookup IDs before retrieval.

### Query Planner -- Full LangGraph DAG

Production uses full DAG planner via LangGraph. The formal state machine is fully implemented (`langgraph_router.py`), replacing the temporary template router from Phase 2.

**Why DAG planner is necessary at production scale:** Real KSP officer queries are compound and unpredictable. Five templates cannot cover the query variety of hundreds of officers. The DAG planner asks GLM-4.7-Flash to generate an execution plan as a JSON array of steps, with dependency tracking for parallel execution.

**Urgency effect:**
- `field_urgent`: graph depth capped at 1, no viz steps, synthesis max_tokens=300
- `analytical`: full depth 2-3, viz steps included, full synthesis

---

## 9. Layer 3 -- Retrieval

### Evidence Object (Architectural Spine)

All retrievers fill one Evidence Object. GLM-4.7-Flash only reads it -- never touches raw DB output.

```
EvidenceItem:
  fir_id, relevance_score, sources[], convergent,
  evidence_path, similarity_reason, confidence,
  confidence_reasons[], confidence_flags[], fir_date
```

### Retrieval Sources

**Memgraph Graph Traversal**
- Node lookup, multi-hop traversal, community fetch, shortest path, tattoo search
- Explicit edges: CO_ACCUSED, PHONE_CONTACT, CO_LOCATION, FAMILY_RELATION, FINANCIAL_LINK, USED_VEHICLE, MEMBER_OF
- Derived edges (computed at ingestion): SHARED_MO, SHARED_TATTOO, SHARED_VEHICLE, TEMPORAL_CLUSTER
- Pre-computed MAGE properties on each Accused node: communityId, centralityScore, pageRankScore, componentId

**Catalyst KB + RAG**
- FIR narratives + MO descriptors indexed as structured plain text documents
- Semantic MO similarity search, narrative search
- Built-in chunking, embedding, reranking, citations -- no embedding model in AppSail
- Returns FIR IDs + similarity scores + excerpt citations

**Catalyst Data Store (ZTSQL)**
- Aggregations, time-series queries, structured filtering
- Source of truth for structured facts (counts, dates, demographics)
- Note: no native geospatial types -- lat/lon stored as TEXT, distance computed in Python via geopy

### Convergence Boosting

If the same FIR appears in both Memgraph and Catalyst KB results:
- Marked `convergent: true`
- Relevance score boosted by 30%
- Confidence tier upgraded to HIGH

### Per-Source Timeout Budgets

Each retrieval source runs under its own timeout. If a source exceeds its budget, the pipeline proceeds without it rather than blocking every officer's query on one slow component.

| Source | Timeout | Rationale |
|---|---|---|
| Graph (Memgraph) | 5.0s | Multi-hop traversal is most expensive, needs most headroom |
| SQL (ZTSQL) | 4.0s | Aggregations can be slow on large ranges, simpler than graph |
| RAG (Catalyst KB) | 3.0s | Managed service, should be consistently fast, tightest budget |

Sources run in parallel via `asyncio.gather`, so actual wait time is `max()` not `sum()` -- worst case ~5 seconds for retrieval, leaving headroom inside the field_urgent 10s target.

**On timeout:** the source is skipped, not retried. The gap is logged in the reasoning trace and surfaced to the officer as a partial-results notice ("Network/relationship data did not respond in time -- consider re-running"). The Confidence Engine treats results missing a source as potentially incomplete rather than presenting them as the full picture. This is a deliberate fail-soft design -- one slow component degrades gracefully instead of degrading every concurrent user's experience.

---

## 10. Layer 4 -- Confidence Engine

### Three Sub-Scores Per Evidence Item

**Source Convergence (45%):** Graph + RAG = 1.0, Graph only = 0.75, SQL only = 0.65, RAG only = 0.55

**Evidence Strength (40%):**
- CO_ACCUSED = 1.0
- SHARED_VEHICLE / PHONE_CONTACT = 0.85
- SHARED_MO = 0.75
- SHARED_TATTOO = 0.65 + flag
- TEMPORAL_CLUSTER = 0.55 + flag
- RAG similarity only = 0.50 + flag

**Recency (15%):** Within 90 days = 1.0, 1 year = 0.8, 2 years = 0.6, older = 0.4

### Tier Assignment

```
final = (convergence * 0.45) + (strength * 0.40) + (recency * 0.15)

HIGH       >= 0.80, no flags
MEDIUM     >= 0.60
LOW        >= 0.40
UNVERIFIED < 0.40 OR any flags + score < 0.70
```

### OCR Penalty

Fields extracted via Qwen 3.6 35B VLM carry `ocr_extracted: true`. Confidence score multiplied by 0.90 and flagged: "Fields extracted via OCR -- verify against original document."

---

## 11. Layer 5 -- LLM Synthesis + XAI

### GLM-4.7-Flash Synthesis

Receives structured Evidence Object. Never raw DB output.

**field_urgent:** 3-5 bullets, key facts only, no reasoning trace shown.

**analytical:** Full paragraph synthesis, evidence section, reasoning trace available on request.

### Confidence Language Rules

- HIGH: State as established fact with citation
- MEDIUM: State with qualifier ("shows MO similarity though no direct link confirmed")
- LOW: Surface with explicit flag ("temporal proximity alone does not establish connection")
- UNVERIFIED: Always flag for manual review, do not present as fact

### Legal Constraints (System Prompt)

- Use "appears as accused in FIR" -- never "committed"
- Cite every claim: FIR ID / graph path / algorithm name
- Never invent connections not in evidence
- Always append: "All outputs require officer verification before action"

### XAI Components

1. **Evidence citations** -- every claim tagged to source
2. **Reasoning trace** -- collapsible, shows retrieval path and confidence computation
3. **Confidence badges** -- per-FIR tier display in UI
4. **Overall confidence bar** -- if aggregate < 0.5, warning header shown

### Resilience -- Rate Limit Handling Across All LLM Calls

Every query makes three separate GLM-4.7-Flash calls (NER+intent, DAG planning, synthesis). A rate limit hit on any one breaks the response unless handled explicitly. Three layers of defense:

**1. Response caching.** NER+intent output is cached by query hash (1hr TTL) in Catalyst NoSQL -- identical or repeated queries skip the LLM call entirely. Removes a meaningful fraction of load, especially during demo open-floor segments where similar questions recur.

**2. Retry with exponential backoff -- bounded, not a wait-out strategy.** On a rate-limit response, retry up to 3 times with exponential backoff plus jitter (avoids many requests retrying in lockstep). Non-rate-limit errors fail fast, no retry. **Workshop Q&A finding:** organizers confirmed the actual rate-limit consequence is an approximately 10-minute stall before reset -- far longer than this backoff is designed to absorb. The retry loop is deliberately kept short (under 5 seconds across all 3 attempts) specifically so it fails over to graceful degradation quickly rather than attempting to wait out a 10-minute stall inside the pipeline's 15-minute budget, which isn't a viable strategy at that scale. See Implementation Section 8 for the corrected retry code and the open question of whether the stall is scoped per-call, per-project, or per-account.

**3. Graceful degradation, not crash.** If retries are exhausted: NER and DAG planning already fall back to safe defaults (broad_search intent, default plan -- designed earlier). Synthesis additionally falls back to a template-built response constructed directly from the Evidence Object -- the officer sees real evidence with confidence tiers, not an error screen, even if natural-language synthesis is temporarily unavailable.

This matters specifically for the demo: if GLM-4.7-Flash hiccups mid-judging, the system visibly keeps working rather than appearing broken.

**Known limitation -- partially resolved via workshop Q&A.** Catalyst's actual rate limit thresholds (requests/minute, concurrent requests) remain undisclosed, but organizers confirmed the consequence of hitting the limit (≈10-minute stall, then resets) and that hackathon credits should cover normal usage. This design handles rate limiting gracefully whenever it occurs and now explicitly accounts for a stall of that length rather than assuming a brief one, but the exact threshold is still unverified until load-tested or clarified further.

---

## 12. Layer 6 -- Output

### Output Routing

| Input | Urgency | Output |
|---|---|---|
| Voice | field_urgent | Chat bullets + Catalyst TTS voice response |
| Text | field_urgent | Chat bullets only, no panels |
| Text | analytical | Chat full + dashboard panels |
| Any | "export" requested | PDF (WeasyPrint) |

### Dashboard Panels (analytical mode only)

Query-driven -- panels appear because the officer asked something, not because they navigated there.

| Query Type | Visualization | Library |
|---|---|---|
| Network / associates | Network graph (nodes sized by centralityScore, edges color-coded) | Cytoscape.js |
| Crime locations | Map with pins + heatmap + gang territory polygons | Leaflet.js |
| Trends over time | Line / bar chart with burst annotations | Recharts |
| Crime type distribution | Donut chart | Recharts |
| Repeat offender | Timeline per accused | Recharts |

### Graph Visualization

Cytoscape.js fed pre-formatted JSON from FastAPI -- no browser-to-Memgraph connection, no credentials in frontend.

Edge colors: CO_ACCUSED=red, SHARED_MO=orange, SHARED_TATTOO=yellow, PHONE_CONTACT=blue.
Node size mapped to centralityScore. Node color mapped to communityId.

### PDF Export

Contents: query + timestamp, full synthesis, evidence table, confidence summary, graph paths as text, audit trail, legal disclaimer. Officer-requested only, never auto-generated.

---

## 13. Layer 7 -- Session Memory + Feedback

- **Session memory:** Catalyst NoSQL stores conversation state per session_id -- resolved entities, prior results, investigator corrections
- **Multi-turn coreference:** "his associates" in turn 2 resolves to entity from turn 1 without restarting pipeline
- **Investigator corrections:** Officer feedback logged and used to improve results over time
- **Audit logs:** Every query logged with officer identity, intent, FIR IDs returned, confidence breakdown, SHA-256 integrity hash

---

## 14. Layer 8 -- Ingestion Pipeline

### Ingestion Run Order

```
1. extract_distributions.py      -- real distributions from public data
2. generate_base_firs.py         -- 3,500 base FIRs
3. plant_stories.py              -- 4 expanded stories (500 FIRs)
4. generate_narratives.py        -- GLM-4.7-Flash narratives via Catalyst LLM
5. ingest_all.py                 -- KB + Memgraph + ZTSQL simultaneously
6. compute_derived_edges.py      -- SHARED_MO, SHARED_TATTOO, TEMPORAL_CLUSTER
7. run_mage_algorithms.py        -- Louvain, Betweenness, PageRank, WCC via MAGE
8. compute_scores.py             -- activityScore per accused
9. verify_stories.py             -- assertion suite, all 4 stories must pass
```

### Three-Destination Write (Per FIR, Parallel)

```python
await asyncio.gather(
    upload_fir_to_kb(fir),       # Catalyst KB -- plain text document
    write_fir_to_memgraph(fir),  # Memgraph -- nodes + explicit edges
    write_fir_to_ztsql(fir)      # ZTSQL -- structured row
)
```

### Derived Edge Computation -- Incremental, Not Brute-Force

The original design implied pairwise all-FIR comparison for SHARED_MO, which is O(n^2) -- fine at 4,000 FIRs (~8M comparisons), never finishes at lakh scale (~5B comparisons).

**Corrected approach:** each newly ingested FIR is compared against the existing population via Catalyst KB semantic search (top-K, threshold-filtered) instead of brute-force pairwise comparison. Catalyst KB's underlying vector index is sub-linear, so cost per new FIR is independent of total population size. A batch of M new FIRs costs O(M log N) against a population of N, not O(N^2).

```
New FIR batch ingested
        |
For each new FIR:
  Query Catalyst KB (semantic search, top-20) -- not brute-force pairwise
  For each candidate above threshold (0.82):
    MERGE SHARED_MO edge (create new, or reinforce existing)
        |
Tattoo + temporal computation: scoped to new batch only,
  compared against existing population via indexed Cypher query
```

**Reinforcement tracking:** if a SHARED_MO match already has an edge between the same accused pair, the edge is reinforced (`lastReinforced` updated, `reinforcementCount` incremented) rather than duplicated. This is what makes pruning safe -- genuinely active patterns keep getting reinforced and never age out.

### Edge Pruning -- Bounding Graph Growth Over Time

Monthly background job archives (not deletes) SHARED_MO and TEMPORAL_CLUSTER edges older than 2 years with no reinforcement since. CO_ACCUSED, SHARED_TATTOO, and SHARED_VEHICLE are never pruned -- these are durable facts (same FIR, same physical descriptor, same vehicle), not probabilistic inference that should decay.

Archived edges are preserved as `ArchivedEdge` nodes with full metadata -- audit trail, not silent deletion. This keeps the active graph bounded so MAGE algorithm runtime and traversal latency don't degrade indefinitely as the dataset grows across years of operation.

| Approach | 4,000 FIRs | 100,000 FIRs |
|---|---|---|
| Brute-force all-pairs | ~12.5M comparisons, minutes | ~5B comparisons, never finishes |
| Incremental via Catalyst KB search | M searches | M searches -- same cost regardless of total population |

### MAGE Algorithms (Replaces networkx)

Memgraph MAGE runs all four algorithms natively in-DB after derived edges are computed:

```cypher
CALL community_detection.get(...)   -- communityId
CALL betweenness_centrality.get(...)-- centralityScore
CALL pagerank.get(...)              -- pageRankScore
CALL weakly_connected_components.get() -- componentId
```

Results written back as node properties. Read at query time. Never recomputed at query time.

---

## 15. Crime Graph Schema

**Updated against the official KSP ER diagram.** Two corrections from the real schema: (1) a `Complainant` node is added below -- the original design already had `Victim` separate from `Accused`, but never had `Complainant` as its own entity, and the real schema treats all three as genuinely distinct (a complainant is not assumed to be the victim, and can even later be found to be an accused -- see `IsComplainantAccused` in Implementation Section 17); (2) `FIR.crimeType` and `FIR.ipcSections[]` are noted below as derived/denormalized convenience fields, since the real source of truth is lookup-driven (`CrimeHeadID`/`CrimeSubHeadID`) and junction-based (Act+Section pairs), not flat strings -- see Implementation Sections 15/17 for the relational structure this is denormalized from.

### Nodes

```
Accused    {id, name, aliases[], dob, gender, district, tattoos[],
            priorFIRCount, activityScore, communityId, centralityScore,
            pageRankScore, componentId}

FIR        {id, date, crimeType, ipcSections[], narrative,
            moDescriptor, status, station, district, lat, lon}
            -- crimeType and ipcSections[] are denormalized for fast graph
            -- traversal/filtering; the real source of truth is relational
            -- (CrimeHeadID/CrimeSubHeadID lookups, Act+Section junction --
            -- see Implementation Section 15). Populate these as flattened
            -- copies at ingestion time, not as independently-entered data.

Location   {id, name, district, lat, lon, crimeHotspot, hotspotScore}
Victim     {id, age, gender, victimType, district}
Complainant{id, age, gender, occupationId, district}
            -- NEW node type -- the original design had Victim separate from
            -- Accused but folded Complainant into an implicit assumption
            -- that the victim files the complaint. The real schema treats
            -- these as independently-tracked entities; deliberately
            -- excludes religion/caste fields pending the team decision in
            -- Implementation Section 17, Open Decision 1.
Vehicle    {regNo, type, stolen, linkedFIRCount}
Phone      {number, carrier}
Gang       {id, name, territory[], knownMO, memberCount, detectedBy}
CrimeType  {name, moDescriptor, typicalTimeWindow, typicalTargetProfile}
```

### Explicit Edges (from FIR data directly)

```
ACCUSED_IN      {role}
VICTIM_IN
FILED_COMPLAINT {complainantIsAlsoAccused}
            -- NEW edge -- Complainant -> FIR. The complainantIsAlsoAccused
            -- property carries the real schema's IsComplainantAccused flag
            -- directly, so a query can detect this divergent case without
            -- a separate join.
OCCURRED_AT     {exactAddress}
USED_VEHICLE    {firId}
HAS_PHONE
MEMBER_OF       {role, since}
OF_TYPE
CO_ACCUSED      {firId, crimeType, date}
ARRESTED_FOR    {arrestDate, arrestDistrict, investigatingOfficerId}
            -- NEW edge -- Accused -> FIR, distinct from ACCUSED_IN.
            -- ACCUSED_IN reflects being named in the FIR; ARRESTED_FOR
            -- reflects the ArrestSurrender event specifically, which can
            -- happen in a different district than where the FIR was filed
            -- (Implementation Section 17, Open Decision 3) -- keeping
            -- these as separate edges preserves that distinction instead
            -- of collapsing arrest district into the FIR's filing district.
```

### Derived Edges (computed at ingestion)

```
SHARED_MO       {similarityScore, crimeType, count}
SHARED_TATTOO   {descriptor, confidence}
SHARED_VEHICLE  {vehicleId, occasions}
PHONE_CONTACT   {frequency, lastContact, towerOverlap}
CO_LOCATION     {locationId, timeDeltaHours, crimeType}
TEMPORAL_CLUSTER{timeWindowHours, distanceKm, crimeType}
```

### Constraints + Indexes (create before any data load)

```cypher
CREATE CONSTRAINT FOR (a:Accused)     REQUIRE a.id IS UNIQUE;
CREATE CONSTRAINT FOR (f:FIR)         REQUIRE f.id IS UNIQUE;
CREATE CONSTRAINT FOR (vc:Victim)     REQUIRE vc.id IS UNIQUE;
CREATE CONSTRAINT FOR (cp:Complainant)REQUIRE cp.id IS UNIQUE;
CREATE CONSTRAINT FOR (v:Vehicle)     REQUIRE v.regNo IS UNIQUE;
CREATE CONSTRAINT FOR (p:Phone)       REQUIRE p.number IS UNIQUE;
CREATE CONSTRAINT FOR (l:Location)    REQUIRE l.id IS UNIQUE;

CREATE INDEX FOR (f:FIR)      ON (f.district);
CREATE INDEX FOR (f:FIR)      ON (f.date);
CREATE INDEX FOR (f:FIR)      ON (f.crimeType);
CREATE INDEX FOR (a:Accused)  ON (a.district);
CREATE INDEX FOR (a:Accused)  ON (a.communityId);
```

**Synced with Implementation Section 14:** that section's Cypher constraints previously only defined `:Accused`, `:FIR`, `:Vehicle`, `:Phone`, `:Location` -- missing `:Victim` (already specified here) and `:Complainant` (new). Both documents now define the same five-plus-two node set consistently.

---

## 16. Hosting Architecture

```
Catalyst Platform
  AppSail (~300MB RAM) -- THIN FRONT DOOR ONLY
    FastAPI backend
      Input validation (Section 6)
      Cache check (Catalyst NoSQL) -- identical/near-identical query short-circuit
      Fire Custom Publisher event -- fire-and-forget, returns instantly
      SSE connection -- polls Catalyst NoSQL internally, streams
        progress to officer as pipeline states complete
      Does NOT run NER, planning, retrieval, or synthesis directly
  Signals -- Custom Publisher ("ps1-backend")
    REST API URL (one per environment -- dev/prod differ) accepts the
      query job as a JSON event, returns 200 immediately, queues it
    Up to 500 requests/min; briefly locks if exceeded -- not a concern
      at hackathon-demo query volume
  Signals -- Rule ("ps1_query_to_pipeline")
    Routes the Custom Publisher's event to a Function target
    No filter needed -- every event from this publisher goes to the
      one pipeline function
  Function Target ("ps1_pipeline") -- THE ACTUAL PIPELINE, 15-MINUTE BUDGET
    Runs NER + intent -> DAG planning -> retrieval (asyncio.gather) ->
      confidence engine -> synthesis sequentially inside ONE function
      invocation, writing intermediate status to Catalyst NoSQL after
      each stage so AppSail's SSE poll has something to report
    Final write: result + status="done" to Catalyst NoSQL, keyed by job_id
    -- single 15-minute budget for the whole function body, not
       per-stage -- ample headroom for 3 sequential GLM-4.7-Flash calls
       plus parallel retrieval, even with retries
    -- this is the same Event Function type used elsewhere (15-min
       budget per official docs); what changed is only how it's
       triggered -- via a Signals Function target, not the deprecated
       Custom Event Listener
  Catalyst Slate
    React frontend (static) -- unaware of the architecture change,
      still consumes one SSE connection per query as before
  Catalyst KB + RAG
    FIR narratives indexed
  Catalyst Data Store (ZTSQL)
    Structured FIR records + accused table
  Catalyst NoSQL
    Session memory + audit logs + job state (NEW -- see below)
  GLM-4.7-Flash Instruct (Catalyst hosted)
  Qwen 3.6 35B VLM (Catalyst hosted)
  Catalyst Kannada NLP (ASR + TTS)

External (Oracle Cloud Free Tier ARM VM -- 4GB RAM, always free)
  Memgraph Community Edition (Docker + MAGE)
    Criminal network graph
    All derived edges
    Pre-computed algorithm properties
```

> **✅ CONSOLE-VERIFIED, NOT JUST DOC-VERIFIED -- 28 June 2026**
>
> Everything below was previously verified only against `docs.catalyst.zoho.com`. It has now been tested hands-on in a real Catalyst project (`PS1-CIS`, Development environment) and the full chain works exactly as designed:
>
> - **Custom Publisher** (`ps1-query-publisher`) created, generates a working REST API URL.
> - **Rule** (`cis_query_rule`) created, source = `query_job` event from the publisher, target = Function, no filter.
> - **Function target** (`ps_1_cis_function`, Python 3.13, type `Event`) receives the event.
> - **Externally triggered via `curl`** (not a console button click) -- the publisher returned `{"status":"success"}`, the Rule's delivery log shows `Status: Success` on attempt #1, and the Function's own dashboard shows `Total Invocations: 1`, `Invocation Errors: 0`.
> - **Payload shape confirmed:** `event.get_raw_data()` returns the full Signals envelope, not just the posted body -- the actual payload sits at `raw_data['events'][0]['data']`. The pipeline Function's real handler needs to unwrap this, not assume the posted fields are top-level (see corrected handler code below).
> - **Timeout fully confirmed -- exact number, not estimated.** A test invocation with `time.sleep(60)` ran for a platform-recorded **60.02 seconds average invocation time** with **0 Time-Outs** and **0 Invocation Errors**, ruling out a 30-second-style cap. A follow-up test then called `context.get_max_execution_time_ms()` directly from inside a running invocation: it returned **900000ms -- exactly 15 minutes**, confirming the platform's own configured ceiling in writing, not inferred from documentation or a single survived sleep. A ~400-second sleep in the same run also completed cleanly (`remaining_execution_time_ms` dropped from 899500 to 499499, consistent with the sleep duration), with no timeout. This is no longer an estimate.
>
> This closes the single biggest open item across both documents. The "Hands-on Signals verification" action item that appeared in every prior revision of this section's open-items list is now resolved, not just attempted.

> **⚠️ SECOND CORRECTION TO THIS SECTION -- VERIFIED AGAINST `docs.catalyst.zoho.com`**
>
> The previous revision of this section fixed the Circuit problem (see "Why a Plain Event Function, Not a Circuit" below -- that finding still holds) by routing through a Custom Event Listener. Direct verification has since found that **Catalyst Event Listeners -- including Custom Event Listeners -- are deprecated and past End-Of-Life.** Per Zoho's official deprecation announcement: Event Listeners, File Store, and Cron entered deprecation on **27 August 2025** and reached **EOL on 30 April, 2026**. New Catalyst signups after the deprecation date cannot even see the component in their console; for any account created for this hackathon, it will not be available to build on. The design below replaces the Custom Event Listener with **Catalyst Signals** -- the officially documented successor, confirmed to support the same 15-minute Function-target budget the redesign depends on.

### Why This Section Has Been Corrected Twice

First correction: the original design wrapped the pipeline in a Circuit triggered by a Custom Event Listener. Verification found Circuits only execute 30s-capped Basic I/O functions and are unavailable in the IN data center -- so the design moved to a Custom Event Listener triggering a plain Event Function directly.

Second correction (this revision): further verification found the Custom Event Listener itself is a deprecated, EOL'd component as of this writing. The underlying problem this section solves (AppSail's 30-second hard timeout can't safely hold three sequential GLM-4.7-Flash calls) and the underlying fix (move the pipeline into something with a 15-minute budget) are both still correct and unchanged. What keeps moving is the specific Catalyst primitive used to **trigger** that 15-minute function from AppSail -- first Custom Event Listener -> Circuit, then Custom Event Listener -> plain Event Function, now **Signals Custom Publisher -> Rule -> Function target**. The Function target itself is the same kind of Event Function described throughout this document; only its trigger mechanism changed.

### The 30-Second Problem (Unchanged)

The original design ran the entire pipeline (NER, DAG planning, retrieval, confidence, synthesis) inside one AppSail request. Even with per-source retrieval timeouts, three sequential GLM-4.7-Flash calls plus a single rate-limit retry (Section 8 -- exponential backoff) could realistically exceed AppSail's 30-second hard request limit on analytical queries. This was a structural risk, not an edge case -- bounding retrieval alone was never sufficient because the LLM calls sit outside that budget entirely.

**Confirmed via official docs** (`docs.catalyst.zoho.com/en/serverless/help/functions/basic-io/`, `.../event-functions/`, `.../faq/serverless/`): Basic I/O and Advanced I/O functions are capped at 30 seconds; Event and Cron functions get a 15-minute budget. This is the load-bearing fact the redesign depends on, and it holds regardless of which trigger mechanism fires the function.

### Why a Plain Event Function, Not a Circuit (Still Holds)

The original draft proposed wrapping the pipeline in a Circuit. Verification of `docs.catalyst.zoho.com/en/serverless/help/circuits/` overturned this for two independent reasons, neither affected by the Signals correction below:

**1. Circuits cannot execute Event functions at all.** Per the official Circuits introduction page: *"You will not be able to execute Cron, Event, or Advanced I/O functions in a Catalyst circuit... the functional elements of a circuit [are] Basic I/O functions alone."* Every state in a Circuit is individually 30-second-capped, with no path to inherit a 15-minute budget.

**2. Circuits are unavailable in the data center this project will run in.** Per the same documentation: *"Circuits is currently not available to Catalyst users accessing from the EU, AU, IN, JP, SA or CA data centers."* A Karnataka State Police hackathon project provisions in Catalyst's IN data center, ruling Circuits out independent of finding #1.

Both findings are about Circuits specifically and are unrelated to the Event Listener deprecation -- they still apply. The pipeline still runs as a single plain Function (Event Function type), not a multi-state Circuit.

### Why Not a Custom Event Listener (New Finding -- Corrects the Previous Revision)

Per Zoho's official announcement page (`docs.catalyst.zoho.com/en/announcements/2025/fs-el-cron-deprecation-announcement/`): *"Catalyst File Store, Catalyst Event Listeners, and Catalyst Cron... are now in their deprecation phase and will reach End Of Life (EOL) on 30 April, 2026... New users who sign up for Catalyst [after 27 August, 2025] will not be able to view or access these components in their Catalyst projects... After the EOL date, these services will not function, and any business logic configured with them will not work."*

The Event Listeners documentation page itself (`docs.catalyst.zoho.com/en/cloud-scale/help/event-listeners/introduction/`) confirms "Custom Event Listeners" is explicitly one of the three Event Listener types alongside Component and Zoho Event Listeners -- not a separate, surviving component. There is no carve-out for Custom Event Listeners specifically; the deprecation covers the whole component family. Today's date (per this document's last edit) is past the EOL date, and any new Catalyst project for this hackathon would be a post-deprecation signup regardless.

**The corrected design:** Catalyst Signals, the officially named successor (the same announcement page directs migrating users to it), replaces the Custom Event Listener:

1. **Custom Publisher** -- created once in the Signals console. Generates a REST API URL (separate URLs for dev and prod environments -- must swap when promoting). AppSail POSTs the job (`job_id`, `session_id`, `query`) to this URL. Confirmed limits: **500 requests/minute** (locks for 60s if exceeded -- far above hackathon-demo volume), **64KB max payload** per event (well above what a query+session_id JSON body needs).
2. **Rule** -- routes events from the Custom Publisher to a target. No filter condition needed since this publisher only ever carries query jobs; a single unconditional rule sends every event to one target.
3. **Function target** -- the actual pipeline. Per the official Signals target-timeout table, **Function targets get a 15-minute dispatch timeout** (both queue and batch dispatch), identical to the Event Function budget the whole redesign depends on. This is the number that makes the fix work, and it survives the Signals migration unchanged -- only Circuits (5-15s) and Webhooks (5-15s) are short-timeout target types; Functions are not.

This preserves every property the previous (now-corrected) design relied on: fire-and-forget dispatch from AppSail, a 15-minute budget for the actual pipeline, and a NoSQL job-status document that AppSail's SSE loop polls. Only the specific Catalyst component issuing the trigger changed.

### Job State in Catalyst NoSQL

```python
# Job document written/updated through the pipeline, keyed by job_id

{
    "job_id": "uuid",
    "session_id": "...",
    "status": "queued" | "ner_complete" | "planning_complete" |
              "retrieval_complete" | "confidence_complete" |
              "synthesis_complete" | "done" | "failed",
    "query": "...",
    "created_at": "...",
    "updated_at": "...",
    "result": null,            # populated when status == "done"
    "error": null               # populated when status == "failed"
}
```

The Function target updates `status` (and relevant partial data) in this document after each pipeline stage completes -- NER, planning, retrieval, confidence, synthesis -- inside its single 15-minute invocation. AppSail's SSE loop polls this document internally on a short interval (sub-second) and forwards meaningful transitions to the officer as SSE events -- preserving the token-by-token / staged feel of the original design even though the heavy work now happens off AppSail.

**Still open, not load-bearing:** Catalyst NoSQL read latency and whether sub-second internal polling from AppSail is sensible practice on this platform (cost, rate limits, recommended polling patterns) is not yet confirmed against official docs -- assumed reasonable by analogy to typical NoSQL document stores. This doesn't change the architecture if wrong, only the polling interval -- worth a quick test once the console is accessible: write a document, measure round-trip read latency from AppSail, and widen the poll interval if needed.

### Why Persistent SSE Over Client-Side Polling

Two options were considered for how the officer's browser learns the job is done: client-side polling (`GET /api/query/{job_id}` on an interval) or a persistent SSE connection with AppSail polling NoSQL internally. Persistent SSE was chosen because:

- No visible lag between job completion and the officer seeing it -- AppSail's internal poll interval can be sub-second, controlled by us, rather than a client poll interval that trades off frequency against load
- Preserves the existing SSE event design (`token`, `evidence`, `visualization`, `done`) and the frontend code built around it -- the frontend does not need to know the pipeline moved off AppSail, or that the trigger mechanism changed from a Custom Event Listener to Signals
- Lets us stream meaningful intermediate progress ("NER complete" -> "retrieval complete" -> final synthesis) as the Function target's pipeline stages finish, rather than one lump result at the end, which client polling would force

**Note:** this preference is a frontend/UX decision independent of how the backend pipeline is triggered (Custom Event Listener vs. Signals, Circuit vs. plain Function) -- it would have held through every revision of this section.

### Why AppSail Not Serverless Functions (For the Front Door)

AppSail and Serverless Functions both have the same 30-second hard request timeout -- this was never the differentiator. AppSail is still the right choice for the thin front door specifically because:

- It supports persistent process patterns (FastAPI, connection pooling, the warm SSE loop) better suited to holding many open officer connections than per-invocation function semantics
- An AppSail instance, once spawned, stays warm for 5 minutes and serves multiple requests in that window
- The front door's job (validate, cache-check, fire the Signals event, hold SSE) is fast and lightweight -- well within 30s regardless, since it no longer does any LLM or retrieval work itself

### Cold Starts -- Still Relevant, Narrower Scope Now

Cold-start mitigation (keep-warm pings, startup pre-warming) still applies to AppSail, since it's still the first thing an officer's request hits. The scope is narrower now: AppSail's startup no longer needs to warm Memgraph or run a full Catalyst LLM round-trip before serving traffic, since it doesn't call those directly anymore -- it only needs the NoSQL client and the Signals Custom Publisher URL ready. This makes the 10-second port-binding window easier to respect, not harder.

Confirmed platform behavior (unchanged from prior verification): instances spawn on-demand, stay active 5 minutes once spawned, must bind their port within 10 seconds, and every request -- cold or warm -- is still subject to the 30-second timeout. The keep-warm-every-5-minutes mitigation still stands.

### Environment Variables

Backend (.env):
```
CATALYST_API_TOKEN=
CATALYST_SIGNALS_PUBLISHER_URL=  # NEW -- Custom Publisher REST API URL.
                                   #   Dev and prod environments have DIFFERENT
                                   #   URLs for the same publisher -- must be
                                   #   swapped when promoting, not just re-pointed
                                   #   at a different host
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
SESSION_SECRET=
ENVIRONMENT=development
```

Frontend (.env):
```
VITE_API_BASE_URL=https://your-appsail.catalyst.zoho.com
```

No DB credentials in frontend. Frontend talks to AppSail only -- never directly to Signals, the pipeline Function, or NoSQL.

### Remaining Open Items (Not Launch-Blocking)

The items that genuinely changed the design across both corrections (Circuit state timeout inheritance, Custom Event Listener invocation contract, and now the Event-Listener-to-Signals migration) are resolved via official docs, as covered above -- and the trigger mechanism itself (Custom Publisher -> Rule -> Function target) is now also console-verified, not just doc-verified (see the callout at the top of this section). Items that remain open, none of which threaten the architecture if they don't hold:

1. **Sub-second NoSQL polling latency from AppSail** -- covered in "Job State in Catalyst NoSQL" above. If actual read latency is higher than assumed, widen the SSE poll interval; no architectural change needed.
2. **Custom Publisher event payload limits** -- confirmed: 64KB per single event, up to 256KB / 25 events when sent as a batched array. PS-1's job payload (job_id, session_id, query text) is a single small event, comfortably within this. (A prior version of this document cited "25 publishers per project, 100 rules per project" as confirmed limits -- on closer verification this was not found in official docs and has been removed; if a per-project publisher/rule count limit exists, it was not located in the documentation checked. Not a concern at PS-1's scale of 1 publisher + 1 rule regardless.)
3. **Rule target limit** -- confirmed: a single Rule supports up to 5 targets. PS-1 needs exactly 1 (the pipeline Function), so this is closed, not open.
4. **Dev-vs-prod Custom Publisher URL swap** -- confirmed this is a real, documented gotcha (the REST API URL differs by environment). Added to the pre-demo checklist (Implementation Section 25) so it isn't missed when moving from development to a production-tier project before judging.
5. **Full 15-minute budget -- RESOLVED, exact figure confirmed.** `context.get_max_execution_time_ms()` called directly from inside a running invocation returned **900000ms (exactly 15 minutes)** -- not inferred, the platform's own SDK reporting its configured ceiling. A ~400-second sleep test in the same run completed cleanly with no timeout, consistent with this figure. This closes the item -- no longer "narrowed but not pinned," it's pinned exactly.

**Signals is now the console-confirmed primary path, not a documentation-only design.** Job Scheduling remains documented below as a fallback, but with Signals proven working end-to-end (Custom Publisher -> Rule -> Function target, externally triggered, delivery status "Success" on attempt #1), there is no current need to also stand up the fallback unless Signals shows a problem under real load later. **If Signals turns out unsuitable for this pattern for some unanticipated reason** (e.g. unexpected behavior under concurrent load, which hasn't been tested yet -- only a single test invocation has been verified so far), the fallback remains: **Catalyst Job Scheduling** -- confirmed via official docs as a current, non-deprecated service (it is in fact named in Zoho's own announcement as the successor to the deprecated Cron component). It can submit a job that triggers a **Job Function** target directly with a configurable number of retries and retry interval, eliminating the need for AppSail to poll a "pending jobs" table at all -- the job submission itself is the trigger, immediate or cron-scheduled. The setup cost is real and separate from Signals: it requires its own Job Pool (typed at creation as a "Functions" pool, and the type cannot be changed afterward) before any job can be created against it. This is a clean, confirmed fallback, not a hand-wave -- but it is a second piece of infrastructure to set up, not a free safety net, so it is worth treating as a real (if unlikely to be needed) Phase 1 contingency rather than something to discover mid-build if Signals has problems. The Circuit option remains excluded from the fallback chain entirely, for the reasons given above.

---

## 17. Shared Library

```
shared/
  models.py           -- Pydantic schemas (FIR, Accused, Location)
                         canonical maps for district + crime type
  graph_client.py     -- Memgraph async driver (run_query, run_write, close)
  catalyst_client.py  -- All Catalyst API calls (LLM, VLM, KB, ASR, TTS, ZTSQL)
  ner_examples.py     -- 30+ few-shot NER examples, single source of truth
  ner_prompt.py       -- builds full prompt from examples + schema + query
```

Import rule: shared/ imports nothing from backend/ or data/. Both backend/ and data/scripts/ import from shared/. They never import from each other.

---

## 18. NER Few-Shot Library

30+ examples in `shared/ner_examples.py` covering:
- Pure English, romanized Kannada, mixed code-switched
- All 6 intent types (lookup, network_analysis, similarity_search, aggregation, prediction, compound)
- Both urgency levels with realistic phrasing differences
- Edge cases: single word inputs, vague references, pure Kannada pronouns, IPC-first queries

**Key decisions:**
- NER + intent in single GLM-4.7-Flash call (saves 4-6s latency)
- Temperature 0.0 (deterministic)
- Coreference flagged as sub_intent, not resolved in NER
- sub_intents are additive (compound queries produce multiple)

**Eval target:** 90%+ pass rate on `data/scripts/eval_ner.py` before any demo or judging.

---

## 19. Confidence Engine

### Purpose

Makes PS-1 legally defensible. Every retrieved evidence item gets a computed confidence tier before GLM-4.7-Flash sees it. LLM calibrates language to tier.

### Three Sub-Scores

| Sub-Score | Weight | Highest Value | Lowest Value |
|---|---|---|---|
| Source convergence | 45% | Graph + RAG both (1.0) | Unknown source (0.3) |
| Evidence strength | 40% | CO_ACCUSED direct (1.0) | No path available (0.3) |
| Recency | 15% | Within 90 days (1.0) | Older than 2 years (0.4) |

### Why This Is the Differentiator

Most teams return results with no calibration. A judge familiar with law enforcement will ask "what happens when it's wrong?" PS-1's answer: every result is tiered, every tier is explained, low-confidence results are flagged not hidden, the system tells the officer what to verify. Decision-support with explicit uncertainty quantification.

---

## 20. OCR Layer

### Purpose

Real KSP FIRs arrive as scanned documents. Catalyst hosts Qwen 3.6 35B VLM which can extract structured fields from document images -- purpose-built for this.

### Revised Ingestion with Stage 0

```
Stage 0:  Format detection (JSON / PDF / image)
Stage 0b: Qwen 3.6 35B VLM extraction if PDF or image
Stage 0c: Schema mapping (KSP source field names -> canonical, per the real ER diagram -- Implementation Section 17)
Stage 1:  Pydantic validation + value normalization
Stage 2:  Entity resolution (rapidfuzz dedup)
Stage 3:  Three-destination write (KB + Memgraph + ZTSQL)
Stage 4:  Derived edge computation
Stage 5:  MAGE algorithms
Stage 6:  activityScore computation
```

---

## 21. Memgraph -- Confirmed Graph DB

### Why Memgraph Over Neo4j AuraDB

| Factor | Neo4j AuraDB Free | Memgraph Community |
|---|---|---|
| Graph algorithms | None (requires Enterprise) | Full MAGE library native |
| Node/edge limit | 200K / 400K | No cap (RAM-bound) |
| Inactivity pause | Pauses after 3 days | Never pauses |
| Production story | Needs paid upgrade | Already production-grade |

### MAGE Algorithms

```cypher
CALL community_detection.get(...)      -- communityId
CALL betweenness_centrality.get(...)   -- centralityScore (coordinators)
CALL pagerank.get(...)                 -- pageRankScore (senior figures)
CALL weakly_connected_components.get()-- componentId (isolation check)
```

Pre-computed after ingestion. Stored as node properties. Never recomputed at query time.

### Oracle Cloud Hosting

```bash
docker run -d --name memgraph -p 7687:7687 \
  -v mg_lib:/var/lib/memgraph \
  memgraph/memgraph-mage:latest
```

4GB ARM VM, always free, no expiry, Docker support. FastAPI connects via bolt:// protocol.

---

## 22. Schema Mapping Layer

**Updated against the official KSP Police FIR System ER diagram (received from organizers).** The pipeline below was originally designed for an assumed flat CCTNS-style export; the real schema is a normalized relational design with lookup tables and genuine many-to-many relationships, which changes two of the seven stages below. Full field-level reconciliation is in Implementation Section 17.

### Why Needed

Real KSP source data still has the same data-quality problems this layer was designed for: inconsistent field names across stations, mixed date formats, placeholder values instead of null, and location names not matching canonical district names. What's changed is that the *target* schema (what we're mapping into) is now the real structured one instead of a guess -- so the mapper's job is the same, but several stages map into structured lookups/junctions instead of flat strings.

### 7-Stage Pipeline (Revised)

```
Field Name Mapper    -> KSP field names (CaseMaster/Victim/ComplainantDetails/
                         Accused/ArrestSurrender/Act/Section/etc.) to canonical
                         internal names -- see Implementation Section 17 for the
                         full corrected FIELD_NAME_MAP
Value Normalizer      -> dates, phone numbers; CrimeNo decomposed into its
                         component parts via parse_crime_no() rather than
                         treated as an opaque string
Placeholder Cleaner   -> "N/A", "Unknown", "0", "-" to null
Location Resolver     -> fuzzy match to canonical district (75% threshold) --
                         unchanged, but now needs an explicit decision on which
                         district "counts" when a case's filing district and an
                         arrest's district diverge (Implementation Section 17,
                         Open Decision 3)
Act/Section Mapper    -> CHANGED: was "IPC Normalizer" assuming one flat
                         comma-separated string per case. Real schema has a
                         genuine many-to-many junction (case <-> Act+Section
                         pairs, each with its own display order) -- this stage
                         now maps into that junction structure directly when
                         source data is already structured, and falls back to
                         the original regex-based section-number extraction
                         only when source data is unstructured free text
Person Splitter       -> CHANGED: was "Accused Splitter" assuming one list
                         with a role field. Real schema has Victim,
                         ComplainantDetails, and Accused as three distinct
                         tables with different field sets -- this stage now
                         routes incoming person records to the correct one of
                         three schemas based on source table/context, not a
                         single splitter producing one list
Pydantic Validation   -> FIRSchema (now composed of VictimSchema,
                         ComplainantSchema, AccusedSchema, and
                         ArrestSurrenderSchema -- see Implementation Section 5)
```

### Extensibility

`FIELD_NAME_MAP` dict in `ingestion/schema_mapper.py` (top-level, not under `backend/` -- ingestion is an offline batch process, separate from both the AppSail front door and the pipeline Function, see Implementation Section 2). New variants from real data added as one line. Field coverage audit script surfaces unknown fields automatically after every new data batch.

---

## 23. RBAC + Audit Logging

### Role Hierarchy

```
DYSP/SP    -- all districts, all data, all intents, graph depth 3
Inspector  -- own + adjacent districts, all except prediction, depth 2
SI/ASI     -- own district, lookup/similarity/aggregation, depth 1
Constable  -- own station, lookup only, depth 0
```

### Tamper-Evident Audit Log

Every query logged to Catalyst NoSQL with SHA-256 hash of content. If hash doesn't match content, log was tampered. Required for legal defensibility if case goes to court.

### Hackathon Scope

Single hardcoded Inspector context for demo. Audit logging running and visible in Catalyst NoSQL. Full RBAC architecture documented. Demo narration: "Production deployment includes four-level RBAC connecting to KSP officer identity system -- the permission layer wraps the pipeline without changing it."

**Note following KSP schema arrival:** the role hierarchy above maps cleanly onto the real `Employee`/`Rank`/`Designation`/`Unit` tables now available (Implementation Section 17) -- `RankID` and `DesignationID` give a direct binding point for the four tiers, and `Employee.DistrictID`/`UnitID` give the "own district" / "own station" scoping a real column to check against, rather than a conceptual placeholder. This doesn't change hackathon scope (still a single hardcoded context), but confirms the production RBAC design was already pointed at real, available fields rather than something that would need inventing later.

---

## 24. activityScore Methodology + Bias Audit

### Why This Needed Explicit Documentation

Renaming riskScore to activityScore (Section 3, "What Was Eliminated") signaled "heuristic indicator, not risk prediction" -- but the rename alone doesn't fix the underlying problem if the formula's weights are still arbitrary and untested. A score that elevates a 22-year-old from a high-crime district based on demographics rather than individual history is the same problem whether it's called riskScore or activityScore. The fix has to be in the formula and its governance, not the label.

### Four Factors, Weighted by How Directly They Reflect the Individual

| Factor | Weight | Why this weight |
|---|---|---|
| prior_fir_count | 0.4 (highest) | Court-documented history of this specific person's own actions -- least likely to encode bias, so weighted highest |
| centrality_score | 0.3 | Network position (MAGE betweenness) -- one step removed from individual action, weighted lower |
| community_size > 5 | 0.2 (binary) | Deliberately binary, not graded -- a weak signal shouldn't swing the score continuously |
| has_recent_fir | 0.1 (binary, lowest) | Recency alone says little; mainly deprioritizes cold/inactive profiles |

### Explicitly Excluded Factors

- **Age** -- correlates with district-level crime statistics reflecting historical policing patterns, not individual behavior
- **District as a direct multiplier** -- would systematically elevate scores for anyone in over-policed areas; appears only indirectly via community_size, never as a standalone factor
- **Gender, religion, caste** -- never included under any circumstance

### Bias Audit

Runs against the actual 4,000-FIR dataset, checking whether mean activityScore varies suspiciously by district or age bucket. A spread above 0.15 in either dimension is flagged as a warning requiring investigation -- it would indicate the formula is functioning as a demographic proxy rather than an investigative signal, even with age/district excluded as direct factors (correlation can still leak in indirectly via prior_fir_count or network position if the underlying data has demographic skew).

### Human Sign-Off Requirement

Structural, not just documented policy. Any workflow letting an officer act (not merely view) based partly on an activityScore >= 0.70 requires supervising officer sign-off. Viewing the score never requires sign-off -- only escalation, inclusion in formal reports, or surveillance flagging does. Reinforced at the synthesis layer: any evidence item crossing this threshold triggers an explicit disclaimer appended to the response.

**Hackathon scope:** threshold constant and synthesis disclaimer implemented. Full sign-off workflow UI is production scope, consistent with RBAC scoping (Section 23).

---

## 25. Synthetic Dataset -- 4,000 FIRs

### Composition

```
3,500  base FIRs -- 5 districts, realistic NCRB distributions, 2020-2024
  400  complex FIRs -- multi-accused, cross-district, edge cases
  100  planted story FIRs
-----
4,000  total
~1,500 accused profiles, 5 districts, 5 years
```

### Why 4,000 Not 600

600 FIRs doesn't stress-test Memgraph MAGE at scale, doesn't reveal KB reranking quality under noise, doesn't validate latency targets, doesn't test entity resolution with realistic name variant collisions. 4,000 FIRs reveals all of these.

---

## 26. Planted Stories (Expanded for 5K)

### Story 1: Three-Cell Chain Snatching Network
3 cells (Mysuru + Mandya + Shivamogga), 12 accused, 20 FIRs. Coordinator connects all 3 cells. All share cobra:right_forearm tattoo + same stolen vehicle. Alternating district activity pattern. Tests: Louvain clustering, betweenness centrality, SHARED_TATTOO edges, TEMPORAL_CLUSTER, SHARED_MO.

### Story 2: Lone Wolf
1 accused, 10 FIRs, 3 districts, 2 years. Zero graph associates. Identical MO to Story 1 -- RAG links him. Tests: WCC isolation, vector-graph disagreement, MEDIUM confidence assignment.

### Story 3: Rising Wave
6 months, Bengaluru escalating, geographic spillover months 4-6. Jan=4, Feb=9, Mar=17 (burst fires), Apr=22, May=28, Jun=31 incidents. Tests: trend chart, temporal burst detection, map geographic spread.

### Story 4: Cold Case Chain
5 years (2020-2024), 30 FIRs, Mysuru East PS, progressively more identified accused. No graph edges between any. RAG links all via identical MO. Tests: cross-year MO linking, recency penalty on old FIRs, investigative recommendation generation.

---

## 27. Evaluation -- Breaking Circularity, Trap Scenario, Calibration

### The Core Problem

We planted 4 stories, defined ground truth as what we planted, and tested whether the system finds it. This validates "did we implement the planting correctly," not "does the system make correct confidence judgments on data it wasn't told the answer to." All confidence-tier claims to judges need evaluation independent of our own design, or "the system is 85% accurate at HIGH confidence" is an unverified assertion, not a measured result.

### Breaking Circularity -- Blind Labeling

A team member who has not seen the planted-story design, has not read the planting scripts, and was not present when stories were designed reviews a random sample of 50 accused pairs from the full 4,000-FIR dataset. They see only raw FIR narratives, MO descriptors, and accused profiles -- no graph data, no system output, no indication of which story (if any) a pair came from. They label each pair CONNECTED / LIKELY_CONNECTED / UNRELATED / UNCERTAIN based on independent judgment.

This labeled set -- not our planted-story ground truth -- becomes the basis for measuring whether the system's confidence tiers mean anything. `verify_stories.py` still runs separately and remains useful (it validates ingestion correctness), but it is no longer the only evaluation.

### Trap Scenario -- Deliberate False-Positive Test

A planted pair with near-identical MO descriptions but zero other connection: different districts (Belagavi vs Kalaburagi), different years (2021 vs 2024), no shared network, no shared physical descriptors. MO similarity alone is the weakest evidence type in the Confidence Engine (RAG-only, 0.50-0.55 base score, explicitly flagged) -- if the system assigns this pair HIGH or MEDIUM confidence, the Confidence Engine's weighting is broken. If it assigns LOW or UNVERIFIED with the correct "similarity-only" flag, the system is behaving as designed.

This is the single most important pre-demo test for catching the most dangerous failure mode: confident wrongness. A launch blocker, not a nice-to-have -- wired into the same pre-demo sequence as `verify_stories.py`.

### Confidence Calibration Measurement

Using the blind-labeled set as ground truth, every labeled pair runs through the actual retrieval + confidence pipeline. The system's assigned tier is checked against the human label.

| Tier | Target |
|---|---|
| HIGH | >=85% actually connected (per blind label) |
| MEDIUM | >=50% actually connected |
| LOW | <40% actually connected |
| UNVERIFIED | <25% actually connected |

If HIGH tier comes back below 85%, the fix is not relabeling data to match -- it's revisiting the sub-score weights in the Confidence Engine (Section 10): the 0.80 tier cutoff, or individual evidence-strength weights (e.g. is SHARED_TATTOO's 0.65 producing too many false HIGH classifications). This is the empirical validation that turns the confidence tier system from "looks reasonable" into "measured to work" -- and the honest answer to a judge asking "how do you know your confidence levels mean anything."

### Pre-Demo Sequence

```
plant_trap_scenario.py        -- one-time, adds trap pair to dataset
blind_evaluation_set.py       -- generates packet for blind labeler
[hand to teammate, ~1hr manual labeling]
verify_trap_scenario.py       -- MUST PASS, launch blocker
measure_confidence_calibration.py  -- informational, cite in demo if results are good
```

---

## 28. Demo Approach

### Framing

PS-1 is a working prototype of a production system. Not a scripted demo. Robust enough to hand the keyboard to a judge and say "try anything."

Narration to judges: "PS-1 is a production-architecture criminal intelligence system built against the KSP schema. It works on synthetic data today. Connecting to real CCTNS data requires schema mapping, ingestion pipeline validation, and iterative NER tuning. The architecture requires no changes -- only the data and prompt library need to adapt."

### Structure

| Segment | Duration |
|---|---|
| Live ingestion -- one KSP-schema-compliant FIR | 60 seconds |
| Anchor query 1 -- voice input, network analysis | 90 seconds |
| Anchor query 2 -- trend query, chart renders | 60 seconds |
| Open floor -- judges type/speak any query | 5+ minutes |
| Production gap narration | 60 seconds |

Open floor is the most important segment. Stay quiet and let the system work.

### Graceful Failure Requirements

- Zero-result queries return useful suggestions, never silence
- Every retrieval step wrapped in try/except -- one source failing does not crash pipeline
- NER fallback returns broad_search intent if GLM-4.7-Flash returns malformed JSON
- Fuzzy name/location resolution handles common variants

### Chaos Test Suite

Run before judging day alongside verify_stories.py and eval_ner.py:
- Minimal input: "Ravi", "him", "avan", "same case"
- Unexpected IPC sections: "Show me all 302 IPC cases in Hubballi 2023"
- Queries with no matching data in dataset
- Pure Kannada queries
- Typos: "Suresh Babu assosiates", "Shivajinagara theft"
- Empty intent: "hello", "what can you do"

All must return a sensible response. None must crash.

**Note:** the sequence above covers data/evaluation readiness (trap scenario, calibration, chaos queries). It does not cover infrastructure readiness (Signals dev-vs-prod URL swap, keep-warm ping status, Memgraph connectivity) -- that checklist lives in Implementation Section 25 and should be run alongside this one, not instead of it.

---

## 29. Production Gap -- Honest Narration

| Gap | Current State | Production Fix |
|---|---|---|
| GLM-4.7-Flash NER on real KSP Kannada | 30 few-shot examples | Expand from real officer query logs |
| CCTNS schema mapping | Designed against provided schema | Validate against real CCTNS export, extend FIELD_NAME_MAP |
| MAGE at true lakh scale | Fast at 5K FIRs | Scheduled overnight job (architecture already anticipates this) |
| RBAC | Inspector context hardcoded | Connect to KSP officer identity system |
| Handwritten Kannada OCR | Qwen 3.6 35B VLM best effort | Fine-tune on KSP-specific scanned document samples |

---

## To Discuss / Remaining

**Resolved across two verification passes against `docs.catalyst.zoho.com`:**
- [x] **AppSail 30s timeout fix (Section 16)** -- now corrected twice. **First pass:** the proposed Circuit-based design was wrong on two independent grounds -- Circuits only execute Basic I/O functions (30s-capped, no exceptions), and Circuits are unavailable in the IN data center this project runs in. Design moved to a Custom Event Listener triggering a plain Event Function (15-min budget) directly. **Second pass:** further verification found Catalyst Event Listeners -- including Custom Event Listeners -- are a deprecated component that reached End-Of-Life on 30 April, 2026; new Catalyst projects cannot access them at all. **Design corrected again:** a Catalyst Signals Custom Publisher fires the job, a Rule routes it to a Function target, which carries the same confirmed 15-minute dispatch budget the fix has relied on throughout. The 30s-vs-15min split and the AppSail-as-thin-front-door shape are unchanged across both corrections -- only the specific trigger mechanism moved. See Section 16 for full detail.
- [x] **AppSail/pipeline Function resource split (Section 4)** -- the RAM table previously double-counted LangGraph as part of AppSail's footprint after it had already moved to the pipeline Function. Split into two separate tables; AppSail's estimate dropped from ~300MB to ~160MB, and the pipeline Function got its own ~250MB estimate for the first time.
- [x] **Stale file paths (Sections 4, 22)** -- `backend/ingestion/schema_mapper.py` corrected to `ingestion/schema_mapper.py`, matching the top-level `ingestion/` directory in the Implementation doc's project structure.
- [x] **Job Scheduling fallback (Section 16)** -- previously documented as a plausible-but-unverified fallback ("poll a pending-jobs table"); now confirmed via official docs as a live, non-deprecated service that can trigger a Function target directly via job submission, with its own retry configuration. Requires its own typed Job Pool as a one-time setup cost.
- [x] **Signals publisher/rule limits (Section 16)** -- a previous claim of "25 publishers/100 rules per project" could not be re-confirmed on closer verification and has been removed. What is confirmed: 64KB per single custom-publisher event (256KB/25 events if batched), and a maximum of 5 targets per Rule. Neither is a constraint at PS-1's scale (1 publisher, 1 rule, 1 target).

**Second-round council review -- all 9 issues resolved:**
- [x] Input validation -- DONE (Section 6)
- [x] Step timeouts -- DONE (Section 9)
- [x] O(n^2) edge computation -- DONE (Section 14)
- [x] GLM-4.7-Flash rate limits + fallback -- DONE (Section 11)
- [x] AppSail cold starts -- DONE (Section 16) -- also corrected an inaccurate "no timeout" claim
- [x] activityScore methodology -- DONE (Section 24)
- [x] Trap scenario, blind/circular evaluation, confidence calibration -- DONE (Section 27)

**Partially resolved via hackathon workshop Q&A (organizers' answers, not console-verified):**
- [~] **Catalyst Zia/LLM rate limits -- PARTIALLY RESOLVED, NEW RISK SURFACED.** Organizers confirmed the *consequence* of hitting the limit rather than the exact threshold: hitting the rate limit causes roughly a **10-minute stall before it resets**, and the credits provided for the hackathon should be sufficient for normal usage. This is a meaningfully different shape of risk than originally assumed. The resilience design (Section 8) was built around short retries with exponential backoff -- a few seconds, maybe tens of seconds. A 10-minute stall is a different category of failure: it would consume nearly the entire 15-minute pipeline Function budget on a single query, and during concurrent judge/officer testing, one rate-limited query could make the system look broken for 10 minutes even though nothing crashed. **This needs a design response, not just documentation** -- see new action item below. The exact requests-per-minute threshold itself is still unknown.
- [~] **30-second AppSail timeout fix -- ANSWER DOESN'T CLEANLY CONFIRM THE BUILT DESIGN.** Organizers' answer referenced "Catalyst Job Scheduling... to manage crons and job tools... 15-minute timeout" when asked about the 30s AppSail limit. This confirms a 15-minute async mechanism exists on the platform, consistent with what Section 16 already relies on -- but Job Scheduling is documented in this section as the **fallback** to Signals, not the primary design. The organizers' answer didn't explicitly mention Signals (Custom Publisher / Rule / Function target), so it's unclear whether they are (a) describing the fallback path as if it were the only path, (b) recommending Job Scheduling as the preferred approach over Signals, or (c) simply not aware of the Signals-specific mechanics we asked about. **This still needs the hands-on console test** (unchanged from before) -- and the test should now specifically also try Job Scheduling's Job Pool + Function target as a parallel check, given organizers led with that name unprompted.
- [x] **Catalyst-first platform principle -- CONFIRMED.** Organizers confirmed explicitly: use in-house Catalyst services (ASR/TTS via Catalyst Kannada NLP, as already planned) wherever available, and only reach for an external service when Catalyst has no equivalent. This validates the one external-service exception already in the design -- Memgraph, since Catalyst has no native graph database -- and confirms no other component should be planned as external by default.

**Resolved -- KSP schema received (see schema reconciliation below):**
- [x] Await KSP schema to validate schema mapping layer FIELD_NAME_MAP -- received via official ER diagram. See Architecture Section 22 / Implementation Section 17 for the full reconciliation against the original guessed schema.

**New action item from the rate-limit answer:**
- [ ] **Design a graceful-degradation path for a 10-minute rate-limit stall**, not just a retry. Options to evaluate: (a) cap retry attempts at 1 and fail over to a degraded/cached response rather than blocking the Function for 10 minutes, (b) pre-emptively throttle AppSail's dispatch rate during demo/judging windows to stay under whatever the real limit turns out to be, (c) surface a clear "high demand, please retry shortly" message to the officer rather than a silent 10-minute hang. This is now a Phase 2 design task, not just a documentation gap.

**Resolved -- hands-on console verification, 28 June 2026:**
- [x] **Hands-on Signals verification -- DONE, FOR REAL THIS TIME.** Custom Publisher (`ps1-query-publisher`) + Rule (`cis_query_rule`) + Function target (`ps_1_cis_function`) created in a real Catalyst project and tested end-to-end via an externally-fired `curl` request, not a console button click. Delivery confirmed `Success` on attempt #1. The Function's own dashboard confirms `Total Invocations: 1`, `Invocation Errors: 0`, and a 60-second test sleep completed clean with `Time-Outs: 0` -- directly ruling out a 30-second-style cap on this Function type. This was the single most important unclosed item in this entire document across three design corrections; it is now closed by direct evidence, not documentation. See Section 16's top callout for full detail, and Implementation Section 6 for the corrected handler code reflecting the real payload envelope shape discovered during this test.
- [x] **Dev vs. production Catalyst environment tier -- CONFIRMED: Development.** Visible directly in the captured event payload (`"environment": "Development"`) during the Signals test above. This closes the ambiguity that was gating the Data Store capacity question below.

**Still genuinely open -- requires further testing or an external answer, not further doc research:**
- [x] **Full 15-minute budget -- RESOLVED, exact figure confirmed.** `context.get_max_execution_time_ms()` returned **900000ms (exactly 15 minutes)** from inside a live invocation -- the platform's own configured ceiling, not inferred. A ~400-second sleep test completed cleanly with no timeout in the same run, consistent with this figure.
- [ ] **Job Scheduling side-by-side test -- now lower priority.** With Signals proven working end-to-end, there's less urgency to also console-verify Job Scheduling as a parallel primary path. Still worth doing eventually as the documented fallback, but no longer blocking Phase 1 the way it did before Signals was confirmed.
- [ ] **Concurrent/load behavior under Signals -- not yet tested.** Only a single test invocation has been verified. Behavior under multiple simultaneous officer/judge queries (the scenario that actually matters for the demo) is still unverified -- worth a multi-request test before judging day, even if informal.
- [ ] **Exact Qwen/Zia rate limit threshold** (requests/min or concurrent requests) -- the consequence is now known (10-min stall) but the actual number isn't. Worth a follow-up question if there's another chance to ask, though the consequence answer may be sufficient to design around without the exact number.
- [ ] **Data Store dev-tier capacity headroom -- now actionable, dev tier confirmed above.** Confirmed caps: 5,000 records/table, 25,000/project in development. The `cases` table (formerly estimated as `firs` before the KSP schema correction, Implementation Section 15) sits at 4,000 rows with 1,000 rows of headroom. The real schema also adds new tables (`victims`, `complainants`, `arrest_surrenders`, `case_act_sections`) beyond the original 3-table guess, each contributing their own rows toward the 25,000/project total -- still not totaled against real data composition, and now worth doing soon given dev tier is confirmed, not hypothetical.
- [x] **Pipeline Function memory tier -- RESOLVED.** Confirmed via official docs: Catalyst Function memory is configurable from 128MB to 512MB, default 256MB if unset (CPU is allocated automatically based on the memory chosen, not separately configurable). The pipeline Function's ~250MB estimate (Section 4) fits inside the *default* tier, but with almost no margin -- 256MB default vs. ~250MB estimated usage leaves roughly 6MB of headroom, which is too tight given the estimate itself was never measured against a real deployment. **Action:** explicitly set the pipeline Function's memory to 512MB (`catalyst functions:config --memory 512`) rather than leaving it at the unconfigured 256MB default, once the function exists. This is a one-line CLI command, not an investigation -- listed here as a decision to make, not an open question.
- [ ] **NoSQL polling latency from AppSail** -- still assumed reasonable by analogy, never measured. Five-minute test now that console access exists: write a document, read it back in a loop, time it.
- [ ] **Real or realistic Kannada/code-switched query samples** -- the 90%+ NER target is currently validated only against 30 hand-written examples. Worth sourcing earlier rather than discovering gaps mid-Phase-2.

**Other:**
- [ ] Begin Phase 1 implementation in earnest (the Signals gate is now passed -- Catalyst project setup, Memgraph on Oracle Cloud, and real build work can proceed)
