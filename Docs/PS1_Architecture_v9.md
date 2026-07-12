# PS-1: Conversational Crime Intelligence System
## Architecture Document v9 — Consolidated Design

**Supersedes:** `PS1_Architecture_v8.md`
**Folds in (previously separate addenda, now merged into the single source of truth):**
- `PS1_Voice_Language_Layer_v2.md` — Zia ASR/TTS/Translation, replacing the generic "Catalyst Kannada NLP" placeholder
- `PS1_Evidence_Language_Detection.md` — ingestion-time language tagging of FIR evidence + retrieval-time fallback
- `PS1_Reasoning_Feedback_Loop.md` — methodology-scoped trust weighting, giving Layer 7's feedback claim an actual mechanism

**Why consolidate now:** the three addenda were written and reviewed as standalone documents, each correctly scoped to one problem. But they all touch the same pipeline, and two of them (Voice/Language and Evidence-Language) share a dependency (`translate_text`, `VIABLE_LANGUAGES`) that only makes sense read together. Left as four separate files, Antigravity would have to manually reconcile section numbers, node names, and env vars across documents before writing a line of code. This v9 is that reconciliation, done once, so the addenda can be retired as standalone build references.

---

## 0. Changelog — v8 → v9 (Read This First)

This section exists because the user's instruction was explicit: additions/changes/deletions must be called out, not buried in prose, or they're hard to detect against the pre-existing architecture. Every row below maps to a section further down.

### Additions (net-new capability, nothing removed)

| # | Addition | New Section(s) | Why |
|---|---|---|---|
| A1 | Zia Text Translation as a named, wired capability (was not in v8 at all) | §3, §7 (Layer 1b), §17 | KSP officers and CCTNS records include Tamil/Telugu/Marathi text (Bengaluru border-district overlap); v8 had no handling for any language outside Kannada/English code-switching |
| A2 | Evidence-language detection + tagging at ingestion (`narrative`, `mo_descriptor`) | §14 (Layer 8b/8c), §15 (schema fields) | Evidence *inside* the system (FIR narratives) could already be in a non-target language with zero detection — a gap distinct from A1, which only fixed the officer's own query language |
| A3 | Retrieval-time conditional edge (`should_translate_evidence`) as a fallback for untagged evidence | §9 (Layer 3 addendum) | Legacy/out-of-band records that bypass ingestion still need a safety net; deliberately a deterministic rule, not an LLM decision |
| A4 | Methodology-scoped trust weighting (`MethodologyTrust`, `CorrectionEvent`) | §10 (Confidence Engine addendum), §13 (Layer 7 addendum), new §19a | v8 Section 13 claimed "officer feedback... used to improve results over time" with zero mechanism behind it. This is that mechanism |
| A5 | Per-citation confirm/correct UI controls (not a whole-answer thumbs up/down) | §12 (Layer 6 addendum) | Needed so a correction can be traced to a specific `edge_type`/`edge_id`/`crime_type`, which is what A4 operates on |
| A6 | `shared/language_utils.py`, `shared/feedback_models.py`, `shared/feedback_engine.py` | §17 (Shared Library) | New modules required by A2–A4 |
| A7 | New API route `/api/feedback/correction` | §12, §17 | Entry point for A4/A5 |
| A8 | `langdetect` dependency | §17, §5 | Local, deterministic language ID — no LLM call, no network round trip |

### Changes (existing v8 content modified, not replaced wholesale)

| # | Change | Old (v8) | New (v9) | Why |
|---|---|---|---|---|
| C1 | Voice/language line item in tech stack | Single row: "Catalyst Kannada NLP — handles Kannada/Hindi/English natively" | Three explicit rows: Zia Audio-to-Text Transcription, Zia Text-to-Audio Synthesis, Zia Text Translation, each with real endpoint | The generic placeholder was written before the real Zia model catalog was inspected; the console shows 3 distinct models with real endpoints, not one bundled service |
| C2 | Layer 1 (Preprocessing) | 3 flat steps (ASR, transliteration, code-switch) | 4 sub-steps with an explicit conditional short-circuit for translation (1a–1d) | Translation only fires for non-en/hi/kn input — must be a cheap short-circuit, not a step run on every query |
| C3 | `FIRSchema` | No language fields at all | 6 new optional fields: `narrative_language`, `narrative_original`, `narrative_is_translated`, and the same three for `mo_descriptor` | Additive only — see §15. Does not conflict with the real-schema reconciliation work already done in v8 §22/Implementation §17 |
| C4 | Layer 3 (Retrieval) evidence ranking | Ranks purely on existing `relevance_score` | Multiplies `relevance_score` by `trust_weight` (from A4) and an ephemeral same-session penalty | Closes the v8 gap where corrections were logged but never fed back into anything |
| C5 | Confidence Engine formula | Three sub-scores (convergence/strength/recency) only | Same three sub-scores, now dampened by `trust_weight` as a fourth multiplicative input | Trust weighting must affect confidence, not just retrieval ranking, or a historically-unreliable methodology could still be presented as high-confidence |
| C6 | "What Was Eliminated" table (§3) | Did not mention Sarvam AI (was never in v8 to begin with) | Adds an explicit "Evaluated and Rejected" sub-table: Sarvam AI considered, rejected for hackathon scope | Documents a real design decision that was made and reasoned through — omitting it would make the decision invisible to anyone reading only v9 |
| C7 | Layer 8 (Ingestion) | 6 stages (parse → normalize → dedup → 3-destination write → derived edges → MAGE/score) | Same 6 stages, with two new sub-stages (8b language detection, 8c conditional translation) inserted between parse and the three-destination write | Detection/translation must happen once, at ingestion, before any of the three destinations receive the data — not repeatedly guessed at query time |
| C8 | Environment variables | `CATALYST_ASR_ENDPOINT`, `CATALYST_TTS_ENDPOINT` as generic per-project env vars | Removed as env vars; ASR/TTS/Translate URLs are hardcoded stable Zia platform constants in `catalyst_client.py`, plus new `CATALYST_ORG_ID` | These are stable platform endpoints, not per-project deployment URLs like the LLM/VLM/KB endpoints — treating them as configurable env vars was itself a minor inaccuracy in v8 |
| C9 | Production Gap table (§29→§31) | 5 rows | 8 rows — adds Zia ASR field-validation gap, translation JSON-key verification gap, trust-weight tuning-under-real-load gap | Honest-narration principle already established in v8; new capabilities need the same honesty about what's unverified |

### Deletions

None. No v8 capability, decision, or verified fact is removed in v9 — this is a strict superset. Where a v8 line item's *specifics* changed (e.g. the ASR/TTS placeholder), the old line is struck through in context and replaced, not silently dropped, so the reasoning trail stays intact (consistent with how v8 itself handled the DBSCAN→Circuit→Signals corrections).

---

## 1. Problem Framing

### PS-1 vs PS-2

*(Unchanged from v8.)*

| Dimension | PS-1 | PS-2 |
|---|---|---|
| User | Field investigator / KSP officer | SCRB analyst / policymaker |
| Interaction | Natural language (chat + voice) | Visual dashboards, maps |
| Goal | Case-specific reasoning | Trend analysis & strategic insights |
| Output | Direct answers, evidence-backed explanations | Charts, aggregated statistics |

Both systems share the same crime graph, ML models, and data pipelines. They differ only in interface layer.

---

## 2. Core Architecture: Hybrid GraphRAG

*(Unchanged from v8 — no addendum touched this section.)*

**Pure RAG** fails for multi-hop relationships, entity-specific queries, precise filtering.
**Pure Graph DB** fails for ambiguous natural language, conversational context, vague references ("that guy from Shivajinagar").

Combine:
- **Graph traversal** — relationships, network analysis (Memgraph)
- **Semantic search** — MO similarity, narrative search (Catalyst KB + RAG)
- **SQL** — aggregations, statistics, filtering (Catalyst Data Store / ZTSQL)
- **LLM** — planning, routing, synthesis, explanation (GLM-4.7-Flash via Catalyst)

**Key principle, restated and now load-bearing for two new additions too:** LLM plans and synthesizes. Systems retrieve. **The LLM never directly queries raw data, never decides whether evidence needs translating (A2/A3), and never decides how a correction should be applied (A4).** All three of these are deterministic, rule-based, or arithmetic — this is the same architectural boundary, just now explicitly defended against two new places it could have been violated.

---

## 3. Confirmed Tech Stack (v9)

### AI Layer (Catalyst Native — No External AI Platforms)

| Component | Choice | Notes |
|---|---|---|
| LLM | GLM-4.7-Flash Instruct (Catalyst hosted) | 128k context, data private, no external key |
| LLM fallback | Groq + Llama 3.1 70B (offline/dev only) | Not for production |
| NER + Intent | GLM-4.7-Flash via structured prompt | Single call, combined NER + intent |
| Embeddings | Catalyst KB managed | No model loaded in AppSail |
| Semantic search | Catalyst KB + RAG | Built-in chunking, reranking, citations |
| ~~Kannada ASR~~ **Zia Audio-to-Text Transcription** | Catalyst Zia (`quickml/.../zia/audio/transcribe`) | **[C1]** en/hi/kn; multipart/form-data; see §7 |
| ~~Kannada TTS~~ **Zia Text-to-Audio Synthesis** | Catalyst Zia (`quickml/.../zia/tts/synthesize`) | **[C1]** en/hi/kn; pinned neutral emotion/moderate speed for officer-facing use; see §7 |
| **Zia Text Translation** `[NEW — A1]` | Catalyst Zia (`quickml/.../zia/translate`) | Covers en, hi, kn, ta, te, ml, mr, bn, gu, pa, or — used for (a) officer query normalization and (b) evidence normalization (A2) |
| OCR | Qwen 3.6 35B VLM (Catalyst hosted) | For scanned FIR documents only |

### Data Layer

| Component | Choice | Notes |
|---|---|---|
| Graph DB | Memgraph Community (Docker) | Full MAGE algorithms, no GDS license needed |
| Graph hosting | Oracle Cloud Free Tier ARM VM (4GB) | Always free, Docker-ready |
| Structured DB | Catalyst Data Store (ZTSQL) | Replaces PostgreSQL |
| Session memory | Catalyst NoSQL | Per-conversation state; now also holds ephemeral same-session correction penalties `[NEW — A4]` |
| Audit logs | Catalyst NoSQL | Tamper-evident with SHA-256 hash |
| Correction library / trust scoreboard `[NEW — A4]` | Catalyst NoSQL | `CorrectionEvent` (append-only) + `MethodologyTrust` (updated in place) — no new infrastructure, new keys in the existing store |

### Application Layer

*(Unchanged from v8 — Signals/AppSail/Function-target hosting design, §8 below, is untouched by any addendum.)*

| Component | Choice | Notes |
|---|---|---|
| Front door | FastAPI on Catalyst AppSail | Thin layer only — validation, cache check, Signals dispatch, SSE poll loop, **feedback route (`/api/feedback/correction`, `[NEW — A7]`)**. ~160MB RAM |
| Pipeline runtime | Catalyst Function, triggered via Signals | Hosts LangGraph + NER/planning/retrieval/synthesis. 15-min budget |
| Orchestration | LangGraph | Now includes the `should_translate_evidence` conditional edge `[NEW — A3]` |
| Frontend | React on Catalyst Slate | Static hosting; gains per-citation confirm/correct controls `[NEW — A5]` |
| Graph visualization | Cytoscape.js | JSON-fed, no DB credentials in browser |
| Map | Leaflet.js + OpenStreetMap | No API key needed |
| Charts | Recharts | React-native, open source |

### What Was Eliminated (v8, unchanged) + What Was Evaluated and Rejected (v9, new — `[C6]`)

**Eliminated (replaced by a chosen alternative), from v8:**

| Removed | Replaced By |
|---|---|
| faster-whisper (local) | Catalyst Kannada ASR API → now specifically Zia Audio-to-Text Transcription |
| gTTS / pyttsx3 | Catalyst Kannada TTS API → now specifically Zia Text-to-Audio Synthesis |
| Qdrant Cloud | Catalyst KB + RAG |
| multilingual-e5-large | Catalyst managed embeddings |
| MuRIL / IndicBERT | GLM-4.7-Flash prompt-based NER |
| Cross-encoder reranker | Custom Python Evidence assembler |
| PostgreSQL | Catalyst Data Store (ZTSQL) |
| Neo4j AuraDB | Memgraph on Oracle Cloud |
| networkx + cdlib | Memgraph MAGE native algorithms |
| Neovis.js | Cytoscape.js (no browser DB connection) |
| riskScore | activityScore (heuristic, not ML) |

**Evaluated and rejected (new in v9 — a candidate was seriously considered and explicitly turned down, not silently absent):**

| Candidate | Considered For | Verdict | Why (full reasoning in §7) |
|---|---|---|---|
| Sarvam AI (Shuka / ASR API) | Replacing Zia ASR for stronger Kanglish/dialect accuracy | **Rejected for hackathon build; kept as a documented Phase 3 idea** | Wins on raw linguistic accuracy alone, but loses on every other axis: external dependency, adds RAM to an already-thin AppSail container, separate API key management outside Catalyst's OAuth flow, cuts against the organizer-confirmed "Catalyst-first" principle. The accuracy gap is the one risk this architecture already partially mitigates (Layer 1 code-switch normalization) |
| LoRA fine-tuning of GLM-4.7-Flash / Qwen VLM | Making the reasoning loop (A4) "real learning" instead of system-level adaptation | **Ruled out — not feasible, not just undesirable** | Both models are Catalyst-*hosted* inference endpoints called via API (`QuickML.deployment.READ` scope is for invoking a deployed model, not training one). There is no verified path to attaching a LoRA adapter to a hosted model you don't have parameter access to. This is a hard platform constraint, not a design preference — see §10 |

---

## 4. Resource Footprint — AppSail + Pipeline Function

*(Unchanged from v8. The new additions (A1–A8) are deliberately architected to avoid touching this budget:)*

- Zia ASR/TTS/Translation calls are outbound HTTP the same shape as existing LLM/VLM/KB calls — no new client library, no local model, no RAM delta.
- `langdetect` is a small, pure-Python statistical classifier with no model download — negligible RAM addition to whichever process calls it (ingestion, or the pipeline Function's retrieval-fallback path).
- The feedback engine (`shared/feedback_engine.py`) does cheap arithmetic (Beta-Bernoulli smoothing) against existing Catalyst NoSQL — no new compute-heavy component.

**Net effect: the AppSail (~160MB) and pipeline Function (~250MB, provisioned at 512MB) budgets from v8 are unchanged by this revision.** This is worth stating explicitly since three new capabilities were added without a resource footprint review would normally be a yellow flag — the reason it isn't here is that all three were deliberately designed to slot into the existing thin-client/managed-service pattern rather than add local compute.

### AppSail (Front Door Only)

| Component | RAM |
|---|---|
| FastAPI (validation, cache check, SSE poll loop, feedback route) | ~100MB |
| Catalyst NoSQL client | ~30MB |
| httpx (Signals dispatch only) | ~30MB |
| **Total** | **~160MB** |

### Pipeline Function (Signals Function Target)

| Component | RAM (estimated) |
|---|---|
| LangGraph compiled graph + state (now includes `translate_evidence_node`, `should_translate_evidence`) | ~100MB |
| Memgraph driver + connection pool | ~50MB |
| httpx clients (Qwen LLM, VLM, KB, ZTSQL, **Zia ASR/TTS/Translate**) | ~50MB |
| Retrieval/confidence/synthesis Python logic (**now includes trust-weight lookup**) | ~50MB |
| **Total (estimated)** | **~250MB** |

Configured explicitly at 512MB per v8's decision (`catalyst functions:config --memory 512`) — unchanged.

---

## 5. High-Level Pipeline (v9)

This replaces v8 §5's diagram. Changed lines are marked; everything else is verbatim from v8.

```
Layer 0  -- Input (text / voice / scanned document)
Layer 0a -- Input Validation Gate (size limits, MIME checks, injection denylist)
Layer 0b -- Format Detection + OCR (Qwen 3.6 35B VLM if PDF/image)
Layer 0c -- Schema Mapping (CCTNS -> canonical FIRSchema)
Layer 1  -- Preprocessing                                          [CHANGED -- C2]
            ├─ 1a. Voice -> Text          : Zia Audio-to-Text Transcription (en/hi/kn)
            ├─ 1b. Non-target-language -> English/Kannada : Zia Text Translation  [NEW -- A1]
            ├─ 1c. Transliteration        : indic-transliteration (local, unchanged)
            └─ 1d. Code-switch normalize  : GLM-4.7-Flash prompt-based (unchanged)
Layer 2  -- Query Understanding (NER + Intent + DAG Planner)
Layer 3  -- Retrieval (Memgraph + Catalyst KB + ZTSQL + Evidence Assembly)
            + ranking now multiplies relevance_score by trust_weight   [NEW -- A4/C4]
            + should_translate_evidence conditional edge (fallback)    [NEW -- A3]
Layer 4  -- Confidence Engine
            + trust_weight folded in as a 4th multiplicative input     [NEW -- A4/C5]
Layer 5  -- LLM Synthesis + XAI (GLM-4.7-Flash)
            + citations now expose edge_type/edge_id/crime_type        [NEW -- A5, prerequisite]
Layer 6  -- Output (chat / voice / dashboard / PDF)
            + per-citation confirm/correct controls                    [NEW -- A5]
Layer 7  -- Session Memory + Feedback (Catalyst NoSQL)
            + this is where "Feedback" in the name finally has a       [NEW -- A4]
              real mechanism behind it (v8 had the label, not the loop)
Layer 8  -- Offline Ingestion Pipeline (ingestion time only)
            8b. Language Detection (langdetect, per free-text field)    [NEW -- A2]
            8c. Conditional Translation (Zia, only if non-viable lang)  [NEW -- A2]
```

---

## 6. Layer 0 — Input Validation + OCR

*(Unchanged from v8 — no addendum touched Layer 0.)*

### Input Validation Gate (First Boundary)

| Input | Limit | Rejection |
|---|---|---|
| Text query | 500 characters | 400 if exceeded or empty |
| Audio upload | 5MB | 413 if exceeded |
| Document upload (scanned FIR) | 10MB | 413 if exceeded |
| File type | Verified by MIME sniffing, not filename | 415 if mismatched |
| Cypher/SQL/prompt-injection keywords | Denylist pattern match | 400 if detected |

### Model Usage Clarification `[CHANGED — C1]`

Replaces v8's table (which had a single generic "Catalyst Kannada NLP" row):

| Model | Purpose | When Called |
|---|---|---|
| GLM-4.7-Flash Instruct | NER, intent, planning, synthesis | Every query — all text reasoning |
| Qwen 3.6 35B VLM | Scanned FIR OCR extraction | Only when input is image or PDF |
| Zia Audio-to-Text Transcription | ASR (voice → text) | Voice input, language ∈ {en, hi, kn} |
| Zia Text-to-Audio Synthesis | TTS (text → voice) | Voice output mode |
| Zia Text Translation `[NEW]` | Cross-language normalization | Only when input language ∉ {en, hi, kn} — Tamil/Telugu/Malayalam/Marathi/Bengali/Gujarati/Punjabi/Odia (query-side, Layer 1b) **or** evidence-side (Layer 8c / Layer 3 fallback) |

---

## 7. Layer 1 — Preprocessing `[CHANGED — C2]`

### Verified Zia Endpoints (all three console-confirmed, `CATALYST-ORG` IN data center)

#### 7.1 Audio-to-Text Transcription

```
POST https://api.catalyst.zoho.in/quickml/api/v1/models/zia/audio/transcribe
```

| Field | Value |
|---|---|
| Request Content-Type | `multipart/form-data` |
| OAuth scope | `QuickML.deployment.READ` |
| Supported languages | English, Hindi, Kannada |

#### 7.2 Text-to-Audio Synthesis

```
POST https://api.catalyst.zoho.in/quickml/api/v1/models/zia/tts/synthesize
```

| Field | Value |
|---|---|
| Request Content-Type | `application/json` |
| Response Content-Type | `audio/wav` |
| Supported languages | en, hi, kn |
| Pitch / Speed / Emotion | low-mod-high / slow-mod-fast / neutral-happy-sad-angry |
| **Design rule** | Pinned to `emotion="neutral"`, `speed="moderate"` for officer-facing responses — a "happy" or "angry" synthesized tone on a crime-intelligence answer reads as tonally wrong in front of judges |

#### 7.3 Text Translation `[NEW — A1]`

```
POST https://api.catalyst.zoho.in/quickml/api/v1/models/zia/translate
```

| Field | Value |
|---|---|
| Request/Response Content-Type | `application/json` |
| Supported languages | English, Hindi, Kannada, Tamil, Telugu, Malayalam, Marathi, Bengali, Gujarati, Punjabi, Odia |

**Why this exists:** KSP is a Karnataka force, but officers and CCTNS records routinely include Tamil, Telugu, and Marathi border-district names, victim/witness statements, and cross-jurisdictional notes (Bengaluru sees heavy Tamil/Telugu speaker overlap). Before this addition, anything in a third language fell through to the LLM's general multilingual ability with no dedicated, deterministic handling.

### Why Zia Over Sarvam AI (Full Reasoning — Referenced by §3's Rejection Table)

| Factor | Sarvam AI | Catalyst Zia |
|---|---|---|
| Hosting | External API, called from AppSail/pipeline Function | Fully platform-native, zero external call |
| RAM footprint | Adds outbound client + buffering to an already-thin container | Zero additional RAM — same call shape as existing LLM/VLM/KB |
| API key management | Separate key/secret outside Catalyst's OAuth flow | Same `Zoho-oauthtoken` + `CATALYST-ORG` pattern already used everywhere |
| Organizer guidance | Not mentioned | Directly confirmed: use in-house Catalyst services wherever available |
| Code-switching accuracy | Likely stronger out of the box | Weaker on paper, backstopped by existing Layer 1d code-switch normalization |
| Judging optics | Introduces a second AI vendor into a Catalyst-first narrative | Reinforces single-platform story |

**Recommendation, unchanged from the source addendum:** keep Sarvam as a documented Phase 3 idea, not a hackathon-week pivot.

### Updated Preprocessing Steps

1. **1a. Voice → Text:** Zia Audio-to-Text Transcription. Requires a declared language up front (`en`/`hi`/`kn`) — no auto-detect confirmed on the model card; a language picker in the `VoiceButton` UI component is required, not optional. `[VERIFY]` against the real Sample Request/Response tab.
2. **1b. Translation short-circuit `[NEW]`:** Only fires when the input language tag is outside `{en, hi, kn}`. Cheap check, not a call on every query — keeps common-case (Kannada/English/Hindi) latency identical to pre-v9.
3. **1c. Transliteration:** Kannada script → Roman (`indic-transliteration`, local, unchanged).
4. **1d. Code-switch normalization:** GLM-4.7-Flash prompt-based (e.g. "case-alli" → "in case"), unchanged.

### `shared/catalyst_client.py` — New/Replaced Functions

```python
import httpx, os

CATALYST_TOKEN  = os.getenv("CATALYST_API_TOKEN")
CATALYST_ORG_ID = os.getenv("CATALYST_ORG_ID")   # [CHANGED -- C8] new env var

# Zia voice/language endpoints -- stable platform constants, not per-project
# deployment URLs, so hardcoded rather than env-configured  [CHANGED -- C8]
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
    async with httpx.AsyncClient() as client:
        r = await client.post(
            ZIA_ASR_URL, headers=ZIA_HEADERS,
            files={"audio": (filename, audio_bytes, "audio/webm")},
            data={"language": language}, timeout=20.0,
        )
        r.raise_for_status()
        return r.json()["transcript"]


async def text_to_speech(text: str, language: str = "kn", speaker: str | None = None,
                          pitch: str = "moderate", speed: str = "moderate",
                          emotion: str = "neutral") -> bytes:
    async with httpx.AsyncClient() as client:
        payload = {"text": text, "language": language, "pitch": pitch,
                   "speed": speed, "emotion": emotion}
        if speaker:
            payload["speaker"] = speaker
        r = await client.post(ZIA_TTS_URL, headers=ZIA_HEADERS_JSON, json=payload, timeout=15.0)
        r.raise_for_status()
        return r.content


async def translate_text(text: str, source_lang: str, target_lang: str = "en") -> dict:
    """New -- A1. Reused by both Layer 1b (query normalization) and Layer 8c /
    the Layer 3 fallback (evidence normalization, A2/A3)."""
    async with httpx.AsyncClient() as client:
        r = await client.post(
            ZIA_TRANSLATE_URL, headers=ZIA_HEADERS_JSON,
            json={"source_language": source_lang, "target_language": target_lang, "text": text},
            timeout=15.0,
        )
        r.raise_for_status()
        return r.json()   # {"translated_text": ..., "processing_time": ...}
```

`[VERIFY]` The exact JSON key names above (`transcript`, `translated_text`) are inferred from the model cards' plain-English description, not a captured sample response. Confirm against the "Sample Request and Response" tab on each model card before wiring in — one click, removes all guesswork.

---

## 8. Layer 2 — Query Understanding

*(Unchanged from v8 — no addendum touched NER/Intent or the DAG planner directly. Trust weighting, §10, affects retrieval and confidence, not NER.)*

### NER + Intent (Single GLM-4.7-Flash Call)

Combined into one call. Temperature 0.0. Entities: PERSON, LOCATION, FIR_ID, DATE, IPC_SECTION, CRIME_TYPE. Coreference flagged as `coreference_needed` sub_intent, resolved against session memory in LangGraph.

### Query Planner — Full LangGraph DAG

Production uses full DAG planner via LangGraph (`langgraph_router.py`). This file now also hosts the new conditional edge from §9.

---

## 9. Layer 3 — Retrieval `[CHANGED — C4, adds A3]`

### Evidence Object (Architectural Spine, unchanged)

```
EvidenceItem:
  fir_id, relevance_score, sources[], convergent,
  evidence_path, similarity_reason, confidence,
  confidence_reasons[], confidence_flags[], fir_date
  edge_type, edge_id, crime_type          [NEW fields -- required for A4/A5 citation tracing]
  language, text_original, is_translated   [NEW fields -- required for A2/A3]
```

### Retrieval Sources, Convergence Boosting, Per-Source Timeouts

*(Unchanged from v8 — Memgraph/Catalyst KB/ZTSQL sources, 30%-boost convergence rule, and the 5.0s/4.0s/3.0s per-source timeout budgets all carry forward untouched.)*

### `[NEW — A3]` Evidence-Language Fallback: Retrieval-Time Conditional Edge

**Why this exists, distinct from A1/A2:** A1 fixed the *officer's query* language. A2 fixed *evidence tagged at ingestion*. This is the safety net for evidence that reaches query time **without** a language tag at all — legacy CCTNS records predating this pipeline, or records inserted outside the normal ingestion flow. It must be rare if A2 is wired correctly, but it must exist.

**Why a deterministic rule and not an LLM decision:** the first instinct considered — and deliberately rejected — was letting the LLM notice mid-synthesis that it doesn't recognize a piece of evidence and call a translation tool itself. This violates the Section 2 principle (LLM never directly decides retrieval-adjacent facts) and would add a non-deterministic 4th sequential LLM call to a pipeline that already has a documented 10-minute rate-limit stall risk (§11).

```
... existing nodes ...
  -> retrieval_node                  (existing -- Memgraph + KB + ZTSQL fetch)
  -> should_translate_evidence?      [NEW conditional edge]
       ├─ NO  -> confidence_engine_node   (existing, unchanged)
       └─ YES -> translate_evidence_node  [NEW] -> confidence_engine_node
```

```python
# pipeline_function/pipeline/langgraph_router.py  (additions)

from shared.language_utils import detect_language, is_viable
from shared.catalyst_client import translate_text


def should_translate_evidence(state: dict) -> str:
    """Deterministic rule-based check -- NOT an LLM call, NOT an LLM decision."""
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
# StateGraph wiring
graph.add_node("translate_evidence_node", translate_evidence_node)
graph.add_conditional_edges(
    "retrieval_node", should_translate_evidence,
    {"confidence_engine_node": "confidence_engine_node",
     "translate_evidence_node": "translate_evidence_node"}
)
graph.add_edge("translate_evidence_node", "confidence_engine_node")
```

`[VERIFY]` Exact existing node name for the retrieval/evidence-assembly step, and the real shape of `state["retrieved_evidence"]` — the snippet assumes a list-of-dicts shape consistent with §9's Evidence Object, should be checked against the actual current file.

### `[NEW — A4/C4]` Trust-Weighted Ranking

```python
# pipeline_function/pipeline/retrieval_node.py (or wherever ranking currently lives)

from shared.feedback_engine import get_trust_weight

async def rank_evidence(evidence_items: list[dict], session_id: str) -> list[dict]:
    penalized = await _get_session_penalized_ids(f"session_penalty:{session_id}")
    for item in evidence_items:
        base_score = item["relevance_score"]  # existing scoring, unchanged
        trust = await get_trust_weight(item.get("edge_type", "NARRATIVE_SIMILARITY"),
                                        item.get("crime_type"))
        session_penalty = 0.5 if item.get("edge_id") in penalized else 1.0
        item["relevance_score"] = base_score * trust * session_penalty
    return sorted(evidence_items, key=lambda x: x["relevance_score"], reverse=True)
```

Full mechanism (`get_trust_weight`, the smoothing math, the session penalty) is defined once in §19a and referenced from here — see that section for the complete implementation rather than duplicating it in two places.

`[VERIFY]` Exact existing ranking function name and evidence-item shape.

---

## 10. Layer 4 — Confidence Engine `[CHANGED — C5]`

### Three Sub-Scores Per Evidence Item (unchanged from v8)

**Source Convergence (45%):** Graph + RAG = 1.0, Graph only = 0.75, SQL only = 0.65, RAG only = 0.55
**Evidence Strength (40%):** CO_ACCUSED = 1.0, SHARED_VEHICLE/PHONE_CONTACT = 0.85, SHARED_MO = 0.75, SHARED_TATTOO = 0.65+flag, TEMPORAL_CLUSTER = 0.55+flag, RAG similarity only = 0.50+flag
**Recency (15%):** Within 90 days = 1.0, 1 year = 0.8, 2 years = 0.6, older = 0.4

```
final = (convergence * 0.45) + (strength * 0.40) + (recency * 0.15)

HIGH       >= 0.80, no flags
MEDIUM     >= 0.60
LOW        >= 0.40
UNVERIFIED < 0.40 OR any flags + score < 0.70
```

### `[NEW — A4/C5]` Fourth Input: Trust Weight

```python
async def compute_confidence(evidence_item: dict, existing_signals: dict) -> float:
    trust = await get_trust_weight(evidence_item.get("edge_type", "NARRATIVE_SIMILARITY"),
                                    evidence_item.get("crime_type"))
    base_confidence = existing_confidence_formula(existing_signals)  # unchanged, v8 formula above
    return base_confidence * trust
```

**Why this must live here, not just in retrieval ranking (§9):** if trust weighting only affected ranking order, a historically-unreliable methodology could still surface as high-confidence once retrieved — it would just appear lower in the list. Folding `trust_weight` into the confidence formula itself ensures the *language* the LLM uses about that evidence (§11's Confidence Language Rules) also reflects accumulated reliability, not just its position.

`[VERIFY]` Real current confidence formula's shape and exact location — this is a conceptual splice point (multiplicative dampener on the existing v8 formula), not a full replacement.

### OCR Penalty (unchanged from v8)

Fields extracted via Qwen 3.6 35B VLM carry `ocr_extracted: true`. Confidence score multiplied by 0.90.

---

## 11. Layer 5 — LLM Synthesis + XAI

*(Unchanged from v8, except the XAI citation requirement below, which is a prerequisite the reasoning feedback loop depends on rather than a new capability itself.)*

### Confidence Language Rules, Legal Constraints, Resilience/Rate-Limit Handling

All unchanged from v8 — three-layer defense (response caching, bounded retry-with-backoff, graceful degradation to template synthesis), and the 10-minute-stall risk from the Catalyst Zia/LLM rate-limit workshop finding.

### `[Prerequisite for A5]` Citation Structure Requirement

Every piece of evidence cited in a synthesized answer must already trace back to something concrete — a specific Memgraph edge or Catalyst KB document — for the existing XAI/explainability requirement (v8 §1's "evidence-backed explanations" framing). The reasoning feedback loop (§19a) assumes this citation-to-source mapping already exists. **If it doesn't yet in the current codebase, it is a prerequisite for A4/A5, not something either addendum builds — flag as `[VERIFY]` against the actual current synthesis/XAI code before wiring in the feedback loop.**

---

## 12. Layer 6 — Output `[CHANGED — adds A5]`

### Output Routing, Dashboard Panels, Graph Visualization, PDF Export

*(Unchanged from v8.)*

### `[NEW — A5]` Per-Citation Feedback Controls

Each cited piece of evidence in a synthesized answer needs a **per-citation control**, not a single whole-answer control:

- **Confirm (✓):** lightweight positive signal, no explanation required. Feeds the confirm/correct ratio (§19a).
- **Correct (✗):** opens a **required** free-text explanation field. This captures "explain your point from this standpoint" — stored verbatim, never auto-parsed, never fed to any LLM call automatically.
- Both actions POST to `/api/feedback/correction` (§17), tagged with that citation's `edge_type` / `edge_id` / `crime_type`.

**Why per-citation and not whole-answer:** a single upvote/downvote carries no information about *which* piece of reasoning was wrong, which is exactly the information the trust-weighting mechanism (§19a) needs to scope corrections to a methodology (edge type) rather than an entire answer.

---

## 13. Layer 7 — Session Memory + Feedback `[CHANGED — A4 gives this section's name a real mechanism]`

- **Session memory:** Catalyst NoSQL stores conversation state per `session_id` — resolved entities, prior results, investigator corrections. Now also stores the ephemeral same-session correction penalty (`session_penalty:{session_id}`), TTL'd to session length (8 hours).
- **Multi-turn coreference:** unchanged from v8.
- **Investigator corrections — previously an unbacked claim, now a real mechanism (§19a):** every correction/confirmation writes a `CorrectionEvent` (permanent audit trail + correction library) and updates the `MethodologyTrust` scoreboard (persistent, slow-moving), in addition to the instant same-session penalty.
- **Audit logs:** unchanged — SHA-256 tamper-evident hash on every query.

---

## 14. Layer 8 — Ingestion Pipeline `[CHANGED — C7, adds A2]`

### Ingestion Run Order (unchanged structure, two new sub-stages inserted)

```
1. extract_distributions.py      -- real distributions from public data
2. generate_base_firs.py         -- 3,500 base FIRs
3. plant_stories.py              -- 4 expanded stories (500 FIRs)
4. generate_narratives.py        -- GLM-4.7-Flash narratives via Catalyst LLM
   4b. tag_and_normalize_language()   [NEW -- A2, runs per-FIR before ingest_one's write]
5. ingest_all.py                 -- KB + Memgraph + ZTSQL simultaneously
6. compute_derived_edges.py      -- SHARED_MO, SHARED_TATTOO, TEMPORAL_CLUSTER
7. run_mage_algorithms.py        -- Louvain, Betweenness, PageRank, WCC via MAGE
8. compute_scores.py             -- activityScore per accused
9. verify_stories.py             -- assertion suite, all 4 stories must pass
```

### `[NEW — A2]` Language Detection + Conditional Translation (Layer 8b/8c)

**Design principles (each closes a specific rejected alternative):**

1. **Detection is never an LLM call.** `langdetect` — a local statistical n-gram classifier, milliseconds, zero network cost. Never ask GLM-4.7-Flash "what language is this?"
2. **Translation-or-not is a rule, not a judgment:** `if detected_language not in {"en", "hi", "kn"}: translate`. No LLM discretion.
3. **Ingestion time is the primary path.** The vast majority of evidence should never reach query time untagged.
4. **The retrieval-time conditional edge (§9/A3) is a fallback, not the main mechanism** — document it as a safety net so it's never mistaken for the primary design.
5. **Always preserve the original text alongside the translation** — never overwrite. Matters for evidentiary integrity (a translated witness statement is not the same legal artifact as the original) and because RAG semantic search may perform better against the original language in some cases.
6. **Tagging and viability-checking are two separate steps** — worth tracking separately in eval (how many records hit the untagged path vs. the non-viable-language path).

```python
# ingestion/pipeline.py

from shared.language_utils import detect_language, is_viable
from shared.catalyst_client import translate_text


async def tag_and_normalize_language(fir: FIRSchema) -> FIRSchema:
    fir = await _tag_field(fir, field="narrative")
    fir = await _tag_field(fir, field="mo_descriptor")
    return fir


async def _tag_field(fir: FIRSchema, field: str) -> FIRSchema:
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
    fir = await tag_and_normalize_language(fir)   # NEW -- runs before the write
    await asyncio.gather(
        upload_fir_to_kb(fir),       # gets canonical/translated text for indexing
        write_fir_to_memgraph(fir),  # unchanged structural data
        write_fir_to_ztsql(fir)      # stores both original and canonical text
    )
```

**Why only `narrative` and `mo_descriptor`:** these are the two free-text fields on `FIRSchema` where unconstrained natural language can plausibly appear in a non-target language. `VictimSchema`, `ComplainantSchema`, `AccusedSchema`, `ArrestSurrenderSchema` are all structured fields (IDs, ages, booleans, lookup keys) with no open-text field to tag. If a future witness-statement field is added, apply the same `<field>_language`/`<field>_original`/`<field>_is_translated` pattern to it.

### `shared/language_utils.py` `[NEW]`

```python
from langdetect import detect, LangDetectException

VIABLE_LANGUAGES = {"en", "hi", "kn"}  # matches ZIA_VOICE_LANGS in catalyst_client.py,
                                        # kept separate so this module stays a
                                        # lightweight, no-network-call utility

def detect_language(text: str) -> str | None:
    if not text or not text.strip():
        return None
    try:
        return detect(text)
    except LangDetectException:
        return None

def is_viable(language_code: str | None) -> bool:
    return language_code in VIABLE_LANGUAGES
```

### Derived Edge Computation, Edge Pruning, MAGE Algorithms

*(Unchanged from v8 — incremental O(M log N) derived-edge computation via Catalyst KB semantic search, monthly archival pruning of SHARED_MO/TEMPORAL_CLUSTER, MAGE algorithm suite. Not touched by any addendum.)*

---

## 15. Crime Graph Schema `[CHANGED — C3]`

### Nodes (unchanged from v8 — Accused, FIR, Location, Victim, Complainant, Vehicle, Phone, Gang, CrimeType)

### `FIRSchema` — New Language Fields `[NEW — A2]`

Additive only — no existing field removed or renamed, no conflict with the real-schema reconciliation already done in v8 §22.

```python
class FIRSchema(BaseModel):
    # ... all existing fields unchanged (id, crime_no, case_no, date,
    #     crime_head_id, crime_sub_head_id, district, unit_id, lat, lon,
    #     victims, complainants, accused, arrest_surrenders, act_sections,
    #     status, mo_descriptor, narrative, ocr_extracted) ...

    # --- NEW: language tagging ---
    narrative_language: Optional[str] = None        # ISO 639-1, e.g. "ta", "te", "kn"
    narrative_original: Optional[str] = None        # untouched source text, always preserved
    narrative_is_translated: bool = False

    mo_descriptor_language: Optional[str] = None
    mo_descriptor_original: Optional[str] = None
    mo_descriptor_is_translated: bool = False
```

### ZTSQL Schema Addition

```sql
ALTER TABLE cases ADD COLUMN narrative_language VARCHAR(8);
ALTER TABLE cases ADD COLUMN narrative_original TEXT;
ALTER TABLE cases ADD COLUMN narrative_is_translated BOOLEAN DEFAULT FALSE;
ALTER TABLE cases ADD COLUMN mo_descriptor_language VARCHAR(8);
ALTER TABLE cases ADD COLUMN mo_descriptor_original TEXT;
ALTER TABLE cases ADD COLUMN mo_descriptor_is_translated BOOLEAN DEFAULT FALSE;
```

`[VERIFY]` Confirm ZTSQL's actual `ALTER TABLE` support and column-count limits — this is genuinely new ground, the project hasn't previously needed a schema migration on an already-populated table.

### Explicit Edges, Derived Edges, Constraints + Indexes

*(Unchanged from v8 — including the Victim/Complainant/ArrestSurrender additions already folded into v8 from the KSP schema reconciliation. This section is not touched further by any of the three v9 addenda.)*

---

## 16. Hosting Architecture

*(Fully unchanged from v8 — the Signals Custom Publisher → Rule → Function target design, the console-verified 15-minute budget, the Job Scheduling fallback, and all env vars except the ASR/TTS delta below. None of the three addenda touch hosting.)*

### Environment Variables — Delta `[CHANGED — C8]`

```
CATALYST_API_TOKEN=
CATALYST_ORG_ID=                  # NEW -- e.g. 60075634347, used for Zia header auth
CATALYST_SIGNALS_PUBLISHER_URL=   # unchanged from v8
CATALYST_LLM_ENDPOINT=
CATALYST_VLM_ENDPOINT=
CATALYST_KB_ENDPOINT=
# CATALYST_ASR_ENDPOINT / CATALYST_TTS_ENDPOINT -- REMOVED. Zia ASR/TTS/Translate
#   URLs are stable platform constants hardcoded in catalyst_client.py (see Section 7),
#   not per-project deployment URLs, so they don't need an env var.
CATALYST_DATASTORE_URL=
CATALYST_NOSQL_URL=
CATALYST_PROJECT_ID=
MEMGRAPH_URI=bolt://your-oracle-vm-ip:7687
MEMGRAPH_USERNAME=
MEMGRAPH_PASSWORD=
SESSION_SECRET=
ENVIRONMENT=development
```

---

## 17. Shared Library `[CHANGED — adds A6]`

```
shared/
  models.py            -- Pydantic schemas (FIR, Accused, Location) + new language fields (Sec 15)
  graph_client.py       -- Memgraph async driver
  catalyst_client.py    -- All Catalyst API calls, now including translate_text (Sec 7)
  ner_examples.py       -- 30+ few-shot NER examples
  ner_prompt.py         -- builds full prompt from examples + schema + query
  language_utils.py     -- [NEW] detect_language, is_viable, VIABLE_LANGUAGES (Sec 14)
  feedback_models.py     -- [NEW] CorrectionEvent, MethodologyTrust (Sec 19a)
  feedback_engine.py     -- [NEW] get_trust_weight, record_feedback_event, smoothing (Sec 19a)
```

Import rule unchanged: `shared/` imports nothing from `backend/` or `data/`.

### New API Route `[NEW — A7]`

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

Consistent with AppSail's "thin front door only" principle (§16) — this route validates and writes; the smoothing/update arithmetic is cheap enough to run inline without routing through the pipeline Function.

---

## 18. NER Few-Shot Library

*(Unchanged from v8.)*

---

## 19. Confidence Engine — Purpose & Differentiation

*(Unchanged narrative from v8 — see §10 above for the formula itself, now including the trust-weight input.)*

---

## 19a. Reasoning Feedback Loop `[NEW SECTION — A4]`

This section gives v8 §13's unbacked claim ("officer feedback... used to improve results over time") an actual mechanism. It is placed here, adjacent to the Confidence Engine, because that's the layer it most directly modifies.

### Why This Design Looks the Way It Does

**LoRA fine-tuning was ruled out first** — not as a preference, but as infeasible. GLM-4.7-Flash and Qwen VLM are Catalyst-*hosted* endpoints called via API; `QuickML.deployment.READ` is an invocation scope, not a training/parameter-access scope. There is nothing to attach an adapter to. This pointed toward system-level adaptation: adjusting how the *pipeline* uses evidence, not how the model computes.

**Four levels of "what can feedback correct" were considered, and two were deliberately scoped out:**

- **Entity extraction (names, IPC sections, dates)** — rejected as this loop's concern. Closer to a *memory* problem than a *reasoning* problem, already substantially covered by existing session memory (§13).
- **Retrieved evidence relevance** — kept, reframed below.
- **Confidence tier disputes** — originally considered "log only," but the actual fix that emerged was scoping adjustments *narrowly* (by edge type × crime type) rather than not adjusting at all.
- **Disputing the LLM's synthesized narrative** — rejected entirely as an automated loop. Free text with no unambiguous resolution; automating a response here would require the LLM to *interpret* the correction, the same "LLM decides" anti-pattern rejected for evidence-language detection (§9). Captured as an honest audit-log entry, never acted on.

**The reframe that unifies the kept levels:** a correction against a specific retrieved connection isn't really about that one edge — it's about the *reasoning pattern* (graph edge type: `SHARED_MO`, `CO_ACCUSED`, `SHARED_TATTOO`, etc.) that produced it. So the system tracks "how reliable has *this type* of reasoning been," not "was this one edge right."

**Two overcorrection risks, both addressed structurally, not dismissed:**

1. *A mistake once or twice shouldn't swing it* → Bayesian-style smoothing (below): a small number of corrections barely moves the needle.
2. *Narrow specialization skew* (e.g. punishing MO-matching globally when it's only unreliable for one crime type) → scoped to (edge type × crime type) where enough data exists, falling back to edge-type-only when sparse.

### Two Distinct Signals, Two Different Speeds

```
Officer flags a cited piece of evidence in a synthesized answer
                    │
        ┌───────────┴────────────┐
        ▼                        ▼
 SAME-SESSION,              CROSS-SESSION,
 SAME-EDGE-INSTANCE         METHODOLOGY-SCOPED
 penalty (instant,          trust weight (slow,
 session-scoped)            smoothed, floor-clamped)
```

Why two, not one: the demo needs an *instant*, visible effect ("flag it, ask again, see it drop") — but an instant, permanent, global effect from one correction is exactly the overcorrection risk above. The same-session penalty gives the safe, live demo moment; the cross-session trust weight gives the real, statistically-damped improvement.

### Data Model

```python
# shared/feedback_models.py

from pydantic import BaseModel
from typing import Optional

class CorrectionEvent(BaseModel):
    event_id: str
    session_id: str
    officer_id: str
    timestamp: str
    query_text: str
    edge_type: str                     # e.g. "SHARED_MO"
    crime_type: Optional[str] = None   # crime_sub_head_id, if applicable
    edge_id: Optional[str] = None      # specific graph edge/KB doc, for same-session penalty
    verdict: str                       # "confirmed" | "corrected"
    explanation: Optional[str] = None  # free text, stored verbatim, NEVER auto-parsed

class MethodologyTrust(BaseModel):
    scope_key: str              # "SHARED_MO" or "SHARED_MO::burglary"
    confirmations: int = 0
    corrections: int = 0
    # trust_weight is computed on read, not stored, so the smoothing
    # formula can be retuned later without a data migration
```

### Core Logic — `shared/feedback_engine.py`

```python
from shared.catalyst_client import nosql_get, nosql_set
from shared.feedback_models import CorrectionEvent, MethodologyTrust
import json

PRIOR_STRENGTH = 10          # virtual sample size of "neutral" prior evidence
PRIOR_TRUST = 0.7            # neutral starting trust
TRUST_WEIGHT_FLOOR = 0.3     # evidence deprioritized, never hidden
MIN_SAMPLES_FOR_NARROW_SCOPE = 15  # below this, fall back to edge_type-only


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
    await nosql_set(f"correction:{event.event_id}", event.json())  # 1. permanent library

    is_confirm = event.verdict == "confirmed"                       # 2. trust scoreboard
    broad = await _load_trust(event.edge_type)
    (broad.confirmations if is_confirm else broad.corrections)  # (illustrative; see += below)
    if is_confirm: broad.confirmations += 1
    else: broad.corrections += 1
    await _save_trust(broad)

    if event.crime_type:
        narrow = await _load_trust(f"{event.edge_type}::{event.crime_type}")
        if is_confirm: narrow.confirmations += 1
        else: narrow.corrections += 1
        await _save_trust(narrow)

    if not is_confirm and event.edge_id:                            # 3. same-session penalty
        await _apply_session_penalty(event.session_id, event.edge_id)


async def _apply_session_penalty(session_id: str, edge_id: str):
    key = f"session_penalty:{session_id}"
    existing = await nosql_get(key)
    penalized_ids = set(json.loads(existing["value"])) if existing else set()
    penalized_ids.add(edge_id)
    await nosql_set(key, json.dumps(list(penalized_ids)), ttl=3600 * 8)
```

**Worked example (sanity check the smoothing):** zero data → exactly `PRIOR_TRUST` (0.7). One correction, zero confirmations → `(0 + 7) / (1 + 10) = 0.636` — a small nudge, not a collapse. It takes sustained, repeated correction well past `PRIOR_STRENGTH` before the estimate approaches the real observed ratio.

`MIN_SAMPLES_FOR_NARROW_SCOPE = 15` is a starting guess, not a verified constant — with limited officer/judge interaction volume during a hackathon window, the narrow scope may rarely activate live unless synthetic correction history is seeded for the demo (see §21 Migration Checklist).

### Explicitly Out of Scope (Restated So Scope Doesn't Creep Back In During Build)

- **Entity-extraction corrections** — a session-memory concern, not this loop.
- **Confidence-tier disputes as a standalone complaint** — not a separate button; implicitly handled since confidence is now partly a function of trust-weighted evidence.
- **Narrative/synthesis disagreement** — free-text audit log only, no automated response.
- **Any global confidence-formula coefficient retuning** — not built. The formula's *inputs* now include trust weight; its *coefficients* are untouched.

---

## 20. OCR Layer

*(Unchanged from v8.)*

---

## 21. Memgraph — Confirmed Graph DB

*(Unchanged from v8.)*

---

## 22. Schema Mapping Layer

*(Unchanged from v8 — the 7-stage KSP schema reconciliation pipeline is not touched by any of the three addenda.)*

---

## 23. RBAC + Audit Logging

*(Unchanged from v8.)*

---

## 24. activityScore Methodology + Bias Audit

*(Unchanged from v8.)*

---

## 25. Synthetic Dataset — 4,000 FIRs

*(Unchanged from v8.)*

---

## 26. Planted Stories

*(Unchanged from v8.)*

---

## 27. Evaluation — Breaking Circularity, Trap Scenario, Calibration

*(Unchanged from v8 — the blind-labeling protocol and trap scenario are not modified by v9. New test cases from the three addenda are appended to the Chaos Test Suite, §28, rather than treated as a separate pass.)*

---

## 28. Demo Approach + Chaos Test Suite `[CHANGED — new test cases added]`

*(Structure unchanged from v8. New test cases from the three addenda, added to the existing suite rather than run separately:)*

**From Evidence-Language Detection (A2/A3):**
- Ingest a synthetic FIR with a Tamil-language `narrative` → confirm `narrative_language == "ta"`, original preserved, canonical field holds the translation
- Ingest a FIR with an English `narrative` → confirm no unnecessary translation call
- Simulate an untagged legacy record reaching `retrieval_node` → confirm the fallback tags and routes it correctly
- Confirm `langdetect` behavior on short/ambiguous strings — a known weak point; decide whether very short text should default to "non-viable, needs review" rather than a low-confidence guess

**From Reasoning Feedback Loop (A4):**
- Zero corrections for an edge type → `get_trust_weight` returns exactly `PRIOR_TRUST` (0.7)
- One correction, zero confirmations → trust weight drops modestly (~0.636), not sharply
- Many consistent corrections (>50) → trust weight approaches but never goes below `TRUST_WEIGHT_FLOOR` (0.3)
- Narrow scope with fewer than `MIN_SAMPLES_FOR_NARROW_SCOPE` observations → falls back to broad edge_type-only weight
- Same-session correction on a specific `edge_id` → immediately re-running the query in the same session shows it ranked lower; a new session shows it back at normal rank
- Free-text explanation stored verbatim, never passed to any LLM call automatically

---

## 29. RBAC / Ops Note

*(Unchanged from v8's schema-arrival note on Employee/Rank/Designation/Unit mapping.)*

---

## 30. Production Gap — Honest Narration `[CHANGED — C9, adds 3 new rows]`

| Gap | Current State | Production Fix |
|---|---|---|
| GLM-4.7-Flash NER on real KSP Kannada | 30 few-shot examples | Expand from real officer query logs |
| CCTNS schema mapping | Designed against provided schema | Validate against real CCTNS export |
| MAGE at true lakh scale | Fast at 5K FIRs | Scheduled overnight job |
| RBAC | Inspector context hardcoded | Connect to KSP officer identity system |
| Handwritten Kannada OCR | Qwen 3.6 35B VLM best effort | Fine-tune on KSP-specific scanned samples |
| **`[NEW]` Zia ASR/TTS/Translate field accuracy** | Validated only against console model cards, not real Kanglish recordings | Load-test against real KSP Kanglish audio; same "real query logs" gap as NER, same fix applies |
| **`[NEW]` Zia response JSON key assumptions** | Inferred from model card prose (`transcript`, `translated_text`), not a captured sample | Capture real Sample Request/Response tab before Phase 1 build completes |
| **`[NEW]` Trust-weight tuning under real load** | `PRIOR_STRENGTH`, `MIN_SAMPLES_FOR_NARROW_SCOPE` are starting guesses, untested against real officer correction volume | Re-tune both constants once real correction/confirmation volume exists post-hackathon |

---

## 31. To Discuss / Remaining

*(All v8 items carry forward unchanged — the Signals verification, rate-limit stall design response, Data Store capacity headroom, etc. New open items from the three addenda, appended:)*

**New from Voice & Language Layer v2:**
- [ ] `[VERIFY]` Exact JSON key names in Zia ASR/TTS/Translate response bodies — capture real Sample Request/Response tab
- [ ] `[VERIFY]` Zia ASR auto-detect capability — model cards don't show one; may require an explicit language picker in `VoiceButton`

**New from Evidence-Language Detection:**
- [ ] `[VERIFY]` ZTSQL's actual `ALTER TABLE` support and column-count limits on an already-populated table — genuinely new ground for this project
- [ ] `[VERIFY]` Exact current node name for the retrieval/evidence-assembly step in `langgraph_router.py`, and the real shape of `state["retrieved_evidence"]`

**New from Reasoning Feedback Loop:**
- [ ] `[VERIFY]` Whether citation-to-source mapping (edge_type/edge_id/crime_type exposed per citation) already exists in current synthesis/XAI code — this is a hard prerequisite for A4/A5, not something either addendum builds
- [ ] `[VERIFY]` Exact current confidence-formula location and evidence-ranking function name, for the trust-weight splice points
- [ ] Re-tune `MIN_SAMPLES_FOR_NARROW_SCOPE` and `PRIOR_STRENGTH` based on realistic officer interaction volume — starting guesses, not measured
- [ ] Consider seeding synthetic (genuinely representative, not fabricated-to-impress) correction history before judging day, so the narrow-scope fallback has a chance to activate live rather than only showing the neutral prior

**Other:**
- [ ] Begin Phase 1 implementation incorporating all three addenda — the Signals gate was already passed in v8; this revision adds three capabilities on top of an otherwise-unchanged hosting/retrieval/confidence foundation
