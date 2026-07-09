# PS-1: Evidence-Language Detection & Normalization Layer
## New Capability — Detecting and Handling Non-Target-Language Evidence Inside FIR Records

**Status:** New addendum to Architecture v8 / Implementation v8 and to `PS1_Voice_Language_Layer_v2.md`
**Scope:** This is a *different* problem from the Voice & Language Layer v2 doc. That doc fixed the **officer's query** language. This doc fixes the **evidence itself** potentially being in a language the pipeline never accounted for.
**Written for:** direct hand-off to Antigravity as an implementation task — every section states current state, target state, and the exact files to touch.

---

## 1. Context — How This Requirement Was Found

This wasn't in Architecture v8 or the Voice & Language Layer v2 doc. It surfaced from a design conversation working through the voice/translation upgrade, and it's worth recording the reasoning trail because it shapes *why* the solution below looks the way it does, not just what it is.

1. Voice & Language Layer v2 added a Zia Translation model to handle officer queries typed/spoken in a language outside `{en, hi, kn}`.
2. The follow-on question: what about evidence **already inside the system** — FIR narratives, case notes, witness statements — that might be in Tamil, Telugu, Marathi, etc.? Nothing in Architecture v8 detects or handles this. A Tamil-language witness statement sitting inside an otherwise-normal Kannada FIR would currently just get passed straight into RAG/KB indexing and LLM synthesis with no flag that it's a different language at all.
3. The first instinct floated was: let the LLM notice, mid-synthesis, that it doesn't recognize a piece of evidence, and have it call a translation tool itself. **This was deliberately rejected.** It violates the core architectural principle that has held since Architecture v8 Section 2: *"LLM plans and synthesizes. Systems retrieve. LLM never directly queries raw data."* Letting the LLM decide when to translate makes the behavior non-deterministic (it might silently push through a garbled guess instead of flagging it), and it would add a 4th sequential LLM call to a pipeline that already has three and a documented 10-minute rate-limit stall risk (Architecture v8 Section 8/11, To Discuss log).
4. The corrected design: language detection is a **deterministic, rule-based check** — a language-ID library, not an LLM call — run primarily at **ingestion time** (Layer 8), so evidence is tagged and normalized once, in advance, rather than repeatedly guessed at query time.
5. The remaining edge case: evidence that slips past ingestion untagged (legacy CCTNS records predating this pipeline, or records added outside the normal ingestion flow). For that case, a **conditional edge in the LangGraph pipeline** (Layer 3, retrieval) acts as a safety net — still a deterministic rule ("no tag, or non-viable language → route through translate node"), not an LLM decision.
6. This keeps the LLM's role exactly where Architecture v8 already draws the line: it plans and synthesizes over evidence that retrieval has already normalized. It never decides whether something needs translating.

That's the full shape of the feature. The rest of this document is the concrete diff and code.

---

## 2. Current State vs. Target State

| Aspect | Current (Architecture v8 / Implementation v8) | Target (this doc) |
|---|---|---|
| Evidence language awareness | None. `FIRSchema.narrative` and `mo_descriptor` are ingested as opaque strings, no language field anywhere in `shared/models.py` | Every FIR gets a detected/tagged language on `narrative` and `mo_descriptor` at ingestion |
| Non-target-language evidence | Passed through untouched into Catalyst KB indexing and Memgraph — retrieved and handed to the LLM as-is, whatever language it's in | Detected via `langdetect` (no LLM call), translated via the Zia Translation model *before* KB upload, with the original text preserved alongside the canonical translation |
| Who decides translation is needed | Nobody — there's no check at all | A deterministic rule: `detected_language not in VIABLE_LANGUAGES` → translate. Never an LLM judgment call |
| Where this runs (primary path) | N/A | `ingestion/pipeline.py`, once per FIR, before the three-destination write (KB / Memgraph / ZTSQL) |
| Where this runs (fallback path) | N/A | A new conditional edge in `langgraph_router.py`, Layer 3 (retrieval), for evidence that reaches query time without a language tag |
| New external dependency | N/A | `langdetect` Python package (local, no network call, no LLM cost) |
| Reused dependency | N/A | `translate_text()` from `shared/catalyst_client.py`, already added in the Voice & Language Layer v2 doc |

**The one-sentence version:** language detection becomes a cheap, deterministic, ingestion-time step with a deterministic retrieval-time fallback — never something the LLM figures out on the fly.

---

## 3. Design Principles (Read Before Implementing)

These aren't optional stylistic preferences — each one closes off a specific failure mode that was discussed and rejected.

1. **Detection is never an LLM call.** Use `langdetect` (or equivalent local library) — it's a statistical n-gram classifier, runs in milliseconds, costs nothing, and needs no network round trip. Never ask GLM-4.7-Flash "what language is this?"
2. **Translation-or-not is a rule, not a judgment.** The rule is exactly: `if detected_language not in {"en", "hi", "kn"}: translate`. No ambiguity, no LLM discretion.
3. **Ingestion time is the primary path.** The vast majority of evidence should never reach query time untagged. Do the detection/translation work once, when the FIR is ingested, not on every query that happens to retrieve it.
4. **Retrieval-time conditional edge is a fallback, not the main mechanism.** It exists only for evidence that reaches Layer 3 without a tag — legacy records, out-of-band inserts, or anything that slipped through ingestion. Document it as a safety net so nobody mistakes it for the primary design later.
5. **Always preserve the original text alongside the translation.** Never overwrite the source-language narrative. Store both, tagged. This matters for evidentiary integrity (a translated witness statement is not the same legal artifact as the original) and for RAG narrative semantic search, which may perform better against the original language in some cases.
6. **Tagging and viability-checking are two separate steps**, even though they usually run back-to-back. "Is there a tag?" and "is the tag's language viable?" are different questions with different failure modes worth tracking separately (e.g. for eval: how many records hit the untagged path vs. the non-viable-language path).

---

## 4. Architecture Changes

### 4.1 Updated Pipeline Diagram

This extends the Layer 8 (ingestion) and Layer 3 (retrieval) sections of the pipeline already defined in Architecture v8 Section 5 and updated in Voice & Language Layer v2 Section 4:

```
Layer 8 -- Offline Ingestion Pipeline (per FIR, at ingestion time)
    ├─ 8a. Parse FIR (existing: schema mapping, canonicalization)
    ├─ 8b. Language Detection  [NEW]
    │       For each free-text field (narrative, mo_descriptor):
    │       run langdetect -> tag field with detected language
    ├─ 8c. Conditional Translation  [NEW]
    │       If tagged language not in {en, hi, kn}:
    │       call Zia Translation -> store canonical translation
    │       alongside original text + original-language tag
    └─ 8d. Three-Destination Write (existing, now writes tagged/translated fields)
            ├─ Catalyst KB upload   (canonical-language text indexed for RAG)
            ├─ Memgraph write       (unchanged structural data)
            └─ ZTSQL write          (both original + canonical text stored)

Layer 3 -- Retrieval (query time)                                  [NEW fallback]
    After evidence is retrieved, before Confidence Engine:
    ├─ Has a language tag already? (was it tagged at ingestion?)
    │     NO  -> run langdetect now, tag the field
    │     YES -> skip detection, tag already present
    ├─ Is the (now-confirmed) tagged language in {en, hi, kn}?
    │     YES -> pass through unchanged
    │     NO  -> route through Zia Translation node -> canonical text
    └─ Continue to Confidence Engine / Synthesis (Layer 4/5, unchanged)
```

### 4.2 Data Model Changes — `shared/models.py`

`FIRSchema` needs new optional fields to carry the language tags. This is additive — no existing field is removed or renamed, so it doesn't conflict with anything else in Implementation v8's schema reconciliation work (Section 17).

**Current `FIRSchema` (relevant excerpt, Implementation v8 lines ~294–318):**

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
```

**Target `FIRSchema` — add these fields:**

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

    # --- NEW: language tagging, added for evidence-language normalization ---
    narrative_language: Optional[str] = None        # ISO 639-1 code, e.g. "ta", "te", "kn"
    narrative_original: Optional[str] = None        # untouched source text, always preserved
    narrative_is_translated: bool = False           # True if narrative != narrative_original

    mo_descriptor_language: Optional[str] = None
    mo_descriptor_original: Optional[str] = None
    mo_descriptor_is_translated: bool = False
```

**Why only `narrative` and `mo_descriptor`:** these are the two free-text fields on `FIRSchema` where unconstrained natural language (as opposed to structured IDs, dates, or canonicalized district/name strings) can plausibly appear in a non-target language. `VictimSchema`, `ComplainantSchema`, `AccusedSchema`, and `ArrestSurrenderSchema` (Implementation v8 Section 5) are all structured fields (IDs, ages, booleans, lookup keys) with no open-text field to tag. If future schema work adds a free-text statement field to any of those (e.g. a witness statement field), apply the same `<field>_language` / `<field>_original` / `<field>_is_translated` pattern to it.

### 4.3 New Shared Utility — `shared/language_utils.py`

A new file, small and dependency-light, used by both the ingestion pipeline and the Layer 3 fallback.

```python
# shared/language_utils.py

from langdetect import detect, LangDetectException

# Languages the pipeline treats as "viable" without translation --
# matches the ZIA_VOICE_LANGS set already defined in catalyst_client.py
# for the ASR/TTS layer (Voice & Language Layer v2, Section 5). Kept as
# a separate constant here (not imported) because this module has no
# other dependency on catalyst_client and should stay a lightweight,
# no-network-call utility.
VIABLE_LANGUAGES = {"en", "hi", "kn"}


def detect_language(text: str) -> str | None:
    """
    Deterministic, local, no-LLM-call language detection.
    Returns an ISO 639-1 code (e.g. "en", "kn", "ta") or None if detection
    fails (empty/too-short text, or langdetect's own confidence floor).
    Never raises -- ingestion and retrieval callers should not need a
    try/except around this.
    """
    if not text or not text.strip():
        return None
    try:
        return detect(text)
    except LangDetectException:
        return None


def is_viable(language_code: str | None) -> bool:
    """
    True if the language is one the pipeline can work with directly
    (English, Hindi, Kannada) without a translation hop.
    A None/undetectable language is treated as NOT viable -- safer to
    attempt translation (or flag for review) than to silently assume
    it's fine.
    """
    return language_code in VIABLE_LANGUAGES
```

**Dependency to add:** `langdetect` — pure Python, no model download, no network call.

```
pip install langdetect
```

Add to `requirements.txt` (both `backend/` and `pipeline_function/` if they maintain separate dependency lists, per Implementation v8's project structure).

---

## 5. Implementation — Primary Path (Ingestion Time)

### 5.1 Updated `ingestion/pipeline.py`

This wraps the existing `ingest_one()` (Implementation v8 Section 16, lines ~1489–1495) with the new detection/translation step, run **before** the three-destination write so that all three destinations (KB, Memgraph, ZTSQL) receive already-normalized data.

**Current:**

```python
async def ingest_one(fir: FIRSchema):
    await asyncio.gather(
        upload_fir_to_kb(fir),
        write_fir_to_memgraph(fir),
        write_fir_to_ztsql(fir)
    )
```

**Target:**

```python
# ingestion/pipeline.py

from shared.language_utils import detect_language, is_viable
from shared.catalyst_client import translate_text


async def tag_and_normalize_language(fir: FIRSchema) -> FIRSchema:
    """
    Runs once per FIR at ingestion. Detects language on the two free-text
    fields and translates only if the detected language isn't one the
    pipeline already handles natively (en/hi/kn). Always preserves the
    original text -- never overwrites it.

    This is the PRIMARY path. The vast majority of FIRs should be fully
    tagged by the time they leave this function -- the Layer 3 conditional
    edge in langgraph_router.py exists only to catch records that bypass
    this ingestion path entirely (see Section 6 below).
    """
    fir = await _tag_field(fir, field="narrative")
    fir = await _tag_field(fir, field="mo_descriptor")
    return fir


async def _tag_field(fir: FIRSchema, field: str) -> FIRSchema:
    text = getattr(fir, field)
    if not text:
        return fir  # nothing to tag -- e.g. narrative is optional and may be None

    detected = detect_language(text)
    setattr(fir, f"{field}_original", text)
    setattr(fir, f"{field}_language", detected)

    if is_viable(detected):
        # No translation needed -- the "canonical" field (fir.narrative /
        # fir.mo_descriptor) stays exactly as it was, `_is_translated` stays False.
        return fir

    # Non-viable language (or undetectable) -- translate, but keep the
    # original text intact in the `_original` field set above.
    result = await translate_text(text, source_lang=detected or "auto", target_lang="en")
    setattr(fir, field, result["translated_text"])
    setattr(fir, f"{field}_is_translated", True)
    return fir


async def ingest_one(fir: FIRSchema):
    fir = await tag_and_normalize_language(fir)   # NEW -- runs before the write
    await asyncio.gather(
        upload_fir_to_kb(fir),
        write_fir_to_memgraph(fir),
        write_fir_to_ztsql(fir)
    )
```

**Notes for Antigravity:**

- `translate_text()` here is the function already specified in `PS1_Voice_Language_Layer_v2.md` Section 5 — no new Zia client code needed, just reuse it.
- The `source_lang="auto"` fallback covers the case where `langdetect` itself returned `None` (couldn't confidently detect) — Zia Translation may have its own auto-detect capability; `[VERIFY]` against the real Sample Request/Response tab for the Translation model card (same open item flagged in the Voice & Language Layer v2 doc, Section 5).
- `write_fir_to_kb`, `write_fir_to_memgraph`, `write_fir_to_ztsql` are unchanged in their own internals — they now simply receive a `fir` object with the new language fields populated, and should write those fields through (KB gets the canonical/translated narrative for indexing; ZTSQL should store both `narrative` and `narrative_original` as separate columns, per the "always preserve the original" principle in Section 3).

### 5.2 ZTSQL Schema Addition

The `cases` table (Implementation v8's real-schema table, see the "To Discuss" reconciliation log) needs new columns to store the tagging output:

```sql
ALTER TABLE cases ADD COLUMN narrative_language VARCHAR(8);
ALTER TABLE cases ADD COLUMN narrative_original TEXT;
ALTER TABLE cases ADD COLUMN narrative_is_translated BOOLEAN DEFAULT FALSE;

ALTER TABLE cases ADD COLUMN mo_descriptor_language VARCHAR(8);
ALTER TABLE cases ADD COLUMN mo_descriptor_original TEXT;
ALTER TABLE cases ADD COLUMN mo_descriptor_is_translated BOOLEAN DEFAULT FALSE;
```

`[VERIFY]` Confirm ZTSQL's actual `ALTER TABLE` support and column-count limits against `docs.catalyst.zoho.com` before running this — Implementation v8 hasn't previously needed a schema migration on an already-populated table, so this is genuinely new ground for the project, not a repeat of prior verified territory.

---

## 6. Implementation — Fallback Path (Retrieval-Time Conditional Edge)

This is the safety net described in Section 3, Principle 4. It only matters for evidence that reaches Layer 3 without a language tag — which should be rare if Section 5 is wired in correctly, but must exist for legacy/out-of-band records.

### 6.1 Where This Fits in `langgraph_router.py`

Implementation v8 confirms the DAG/state graph lives in `langgraph_router.py`, with existing nodes like `resolving_entities_node` (Section 7). The new node slots in **after retrieval, before the Confidence Engine** — i.e., after Layer 3's existing evidence-assembly node, before Layer 4.

```
... existing nodes ...
  -> retrieval_node                  (existing -- Memgraph + KB + ZTSQL fetch)
  -> should_translate_evidence?      [NEW conditional edge]
       ├─ NO  -> confidence_engine_node   (existing, unchanged)
       └─ YES -> translate_evidence_node  [NEW] -> confidence_engine_node
```

### 6.2 New Code

```python
# pipeline_function/pipeline/langgraph_router.py  (additions)

from shared.language_utils import detect_language, is_viable
from shared.catalyst_client import translate_text


def should_translate_evidence(state: dict) -> str:
    """
    Conditional edge function for LangGraph. Deterministic rule-based
    check -- NOT an LLM call, NOT an LLM decision. This is the retrieval-time
    fallback described in the Evidence-Language Detection design doc --
    it only fires for evidence that somehow reached this point without
    an ingestion-time language tag (legacy records, out-of-band inserts).

    Returns the name of the next node to route to.
    """
    for evidence_item in state["retrieved_evidence"]:
        tag = evidence_item.get("language")

        if tag is None:
            # Untagged -- run detection now (still local, still no LLM call)
            tag = detect_language(evidence_item.get("text", ""))
            evidence_item["language"] = tag  # tag it now, going forward

        if not is_viable(tag):
            return "translate_evidence_node"

    return "confidence_engine_node"


async def translate_evidence_node(state: dict) -> dict:
    """
    Only reached for evidence flagged non-viable by should_translate_evidence.
    Translates each non-viable evidence item in place, preserving the
    original text under a separate key -- mirrors the ingestion-time
    _tag_field() behavior in ingestion/pipeline.py so both paths produce
    the same shape of output for the Confidence Engine / Synthesis layers.
    """
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

**Wiring into the existing `StateGraph`:**

```python
# In the StateGraph construction, alongside existing add_node/add_edge calls:

graph.add_node("translate_evidence_node", translate_evidence_node)

graph.add_conditional_edges(
    "retrieval_node",                 # existing node name -- confirm exact name in current file
    should_translate_evidence,
    {
        "confidence_engine_node": "confidence_engine_node",
        "translate_evidence_node": "translate_evidence_node",
    }
)
graph.add_edge("translate_evidence_node", "confidence_engine_node")
```

`[VERIFY]` The exact existing node name for the retrieval/evidence-assembly step and the shape of `state["retrieved_evidence"]` (list of dicts with a `"text"` key, or a different structure) — the snippet above assumes a shape consistent with how evidence assembly is described in Architecture v8 Section 5 ("Evidence Assembly") but should be checked against the actual current `langgraph_router.py` file in the repo before wiring this in, since that file's full contents weren't reproduced in Implementation v8's text.

---

## 7. Testing / Verification Checklist

Add these to the existing Chaos Test Suite (Architecture v8 Section 27/28) rather than treating them as a separate test pass:

- [ ] Ingest a synthetic FIR with a Tamil-language `narrative` → confirm `narrative_language == "ta"`, `narrative_original` preserved, `narrative` field holds the English translation, `narrative_is_translated == True`
- [ ] Ingest a FIR with an English `narrative` → confirm `narrative_language == "en"`, `narrative_is_translated == False`, `narrative_original == narrative` (no unnecessary translation call)
- [ ] Ingest a FIR with an empty/`None` `narrative` → confirm no crash, fields stay `None`/`False`
- [ ] Simulate an untagged legacy record reaching `retrieval_node` (no `language` key on the evidence dict) → confirm `should_translate_evidence` runs `detect_language`, tags it, and routes correctly
- [ ] Simulate a retrieved evidence item already tagged `"kn"` → confirm it routes straight to `confidence_engine_node`, skipping `translate_evidence_node` entirely (no unnecessary Zia call)
- [ ] Confirm `langdetect` behavior on short/ambiguous strings (e.g. a 2-word narrative fragment) — this is a known weak point for statistical language detection; decide whether very short text should default to "non-viable, needs review" rather than trusting a low-confidence guess

---

## 8. Migration Checklist for Antigravity — Exact File Touch List

1. `pip install langdetect`, add to `requirements.txt`
2. Create `shared/language_utils.py` (Section 4.3)
3. Update `shared/models.py` — add the six new `FIRSchema` fields (Section 4.2)
4. Update `ingestion/pipeline.py` — add `tag_and_normalize_language()` and `_tag_field()`, wire into `ingest_one()` (Section 5.1)
5. Run the ZTSQL `ALTER TABLE` migration (Section 5.2) — `[VERIFY]` syntax against Catalyst docs first
6. Confirm `upload_fir_to_kb`, `write_fir_to_memgraph`, `write_fir_to_ztsql` pass through the new fields correctly (KB should index the canonical/translated text, not the original, for retrieval quality; ZTSQL should store both)
7. Update `pipeline_function/pipeline/langgraph_router.py` — add `should_translate_evidence()`, `translate_evidence_node()`, wire the conditional edge (Section 6.2) — `[VERIFY]` exact existing node names first
8. Add the six new test cases (Section 7) to the existing chaos/eval test scripts (`verify_stories.py` / `eval_ner.py` per Architecture v8 Section 28, or a new `eval_language_tagging.py` if kept separate)
9. Re-run the existing chaos test suite in full afterward — this change touches ingestion and one retrieval-path conditional edge, both shared infrastructure, so a regression check on the existing suite (not just the new cases) is worth the few minutes it costs

---

## 9. Summary for `agents.md` / Antigravity Context

> New capability: evidence (FIR `narrative` and `mo_descriptor`) is now language-tagged at ingestion using `langdetect` (local, no LLM call) and translated via the Zia Translation model only if the detected language isn't en/hi/kn. Original text is always preserved alongside the translation. A LangGraph conditional edge at retrieval time (`should_translate_evidence` → `translate_evidence_node`) acts as a fallback for any evidence that reaches query time without a tag (legacy/out-of-band records) — this is a safety net, not the primary mechanism. The LLM never decides whether translation is needed; that decision is always a deterministic rule (`language not in {en, hi, kn}`), preserving the existing "LLM plans and synthesizes, systems retrieve" boundary from Architecture v8 Section 2.
