# PS-1: Voice & Language Layer v2
## Zia-Native ASR / TTS / Translation — Replacing the "Catalyst Kannada NLP" Placeholder

**Status:** Proposed upgrade to Architecture v8, Sections 3 / 6 / 7 / 16 and Implementation v8 `catalyst_client.py`
**Supersedes:** The line-item `Catalyst Kannada NLP -- ASR (voice->text), TTS (text->voice)` in Architecture v8 Section 3
**Decision:** Stay on Catalyst-native Zia models. Do **not** migrate to Sarvam AI. Reasoning below.

---

## 1. What Changed

Architecture v8 has referred to the voice layer as a single umbrella component: "Catalyst Kannada NLP." That was accurate in spirit but wrong in specifics — it was written before the actual Zia model catalog on your Catalyst console was inspected. You've now pulled the real model cards, and there are **three** distinct Zia models available, not one:

| Zia Model | Function | Was it in v8? |
|---|---|---|
| Audio-to-Text Transcription | ASR | Yes, as generic "Catalyst Kannada NLP" |
| Text-to-Audio Synthesis | TTS | Yes, as generic "Catalyst Kannada NLP" |
| Text Translation | Cross-language text translation | **No — new capability, not previously in the architecture** |

This document formalizes all three into the architecture with their real endpoints, gives the code that was written against a vague `CATALYST_ASR_ENDPOINT` env var a concrete, correct implementation, and adds Translation as a genuinely new Layer 1 capability the current design was missing.

---

## 2. Decision: Zia (Catalyst-native) over Sarvam AI

Your instinct to flag Sarvam is a good one to have raised, and the underlying critique is correct — a generic ASR model *will* struggle more on Kanglish code-switching, district-name variants, and police jargon than a model trained specifically on Indian linguistic patterns. But "which model is linguistically stronger in isolation" isn't the only axis that matters for this specific hackathon. Here's the full comparison:

| Factor | Sarvam AI (Shuka / ASR API) | Catalyst Zia (native) |
|---|---|---|
| Hosting | External API — called from inside your AppSail container or pipeline Function | Fully platform-native — no external call leaves Catalyst's network |
| RAM footprint | Adds an outbound HTTP client + potentially local buffering/queuing inside your already resource-constrained AppSail container (Section 4 of Architecture v8 has AppSail at ~160MB and the pipeline Function at ~250MB, both deliberately kept thin) | Zero additional RAM cost — it's an API call to another Catalyst service, same as your existing LLM/VLM/KB calls |
| API key management | Requires provisioning, storing, and rotating a separate Sarvam API key/secret outside Catalyst's OAuth token flow | Uses the same `Zoho-oauthtoken` + `CATALYST-ORG` header pattern already wired for every other Catalyst service call in `catalyst_client.py` |
| Network dependency | New external dependency, new failure domain, new latency floor (cross-cloud round trip) | Same data-center round trip as your existing GLM-4.7-Flash / Qwen VLM / KB calls — no new latency class introduced |
| Organizer guidance | Not mentioned | **Directly confirmed by organizers** (Architecture v8, "To Discuss" log): *"use in-house Catalyst services... wherever available, and only reach for an external service when Catalyst has no equivalent."* Catalyst has an equivalent here — three of them |
| Rate limit / stall risk | Unknown, unverified, no hackathon credit allocation | Same known Qwen/Zia rate-limit shape already designed around in Section 8/11 (10-min stall, fail-fast fallback) — no new risk category |
| Code-switching / dialect accuracy | Likely stronger out of the box (native Indian-language foundation model) | Weaker on paper, but scoped to exactly 3 languages your demo needs (English, Hindi, Kannada) and can be backstopped by the GLM-4.7-Flash code-switch normalization step you already have in Layer 1 |
| Judging optics | Introduces a second AI vendor into a "Catalyst-first" hackathon, which cuts against the platform-native narrative you've built the rest of the system around | Reinforces the single-platform story: LLM, VLM, KB, ASR, TTS, Translation, Data Store all under one Catalyst project |

**Verdict:** For this hackathon, Zia wins on every axis except raw linguistic accuracy, and the accuracy gap is the one you have the most existing mitigation for (Layer 1 code-switch normalization + fuzzy name/place canonicalization already handle exactly this class of error). Sarvam's strength is real but it's solving a problem your architecture already has a partial answer for, at the cost of reintroducing the exact AppSail-RAM and external-dependency risks the rest of this document has spent nine sections eliminating.

**Recommendation:** Keep Sarvam AI in your back pocket as a documented Phase 3 idea (see Section 8 below) — it's a legitimate production upgrade path, just not the right call for a RAM-constrained, single-platform hackathon build with a 10-minute rate-limit stall risk you're already managing.

---

## 3. Verified Zia Endpoints

All three confirmed live on your Catalyst console (`CATALYST-ORG: 60075634347`, IN data center). Treat the org ID below as illustrative — pull the live value from your own console/env, don't hardcode it in source.

### 3.1 Audio-to-Text Transcription

```
POST https://api.catalyst.zoho.in/quickml/api/v1/models/zia/audio/transcribe
```

| Field | Value |
|---|---|
| Request Content-Type | `multipart/form-data` |
| Response Content-Type | `application/json` |
| Input format | Binary audio (WAV, MP3, etc.) |
| OAuth scope | `QuickML.deployment.READ` |
| Auth | `Zoho-oauthtoken <access_token>` |
| Supported languages | English, Hindi, Kannada |
| Headers | `CATALYST-ORG: <org_id>`, `Authorization: Zoho-oauthtoken <access_token>` |

### 3.2 Text-to-Audio Synthesis

```
POST https://api.catalyst.zoho.in/quickml/api/v1/models/zia/tts/synthesize
```

| Field | Value |
|---|---|
| Request Content-Type | `application/json` |
| Response Content-Type | `audio/wav` |
| OAuth scope | `QuickML.deployment.READ` |
| Supported languages | en, hi, kn |
| Pitch | low / moderate / high |
| Speed | slow / moderate / fast |
| Emotion | neutral / happy / sad / angry |
| Speakers | EN — Thomas, Adam, Brian (M), Mary, Anna, Beth (F) · HI — Rohit, Aman (M), Divya, Rani (F) · KN — Suresh, Chetan (M), Anu, Vidya (F) |

**Design note:** for the officer-facing voice response use case, emotion should stay pinned to `neutral` and speed to `moderate` — a synthesized "happy" or "angry" tone on a crime-intelligence answer would read as tonally wrong in front of judges. Pitch/speed customization is worth exposing later as an accessibility setting, not a default.

### 3.3 Text Translation *(new capability)*

```
POST https://api.catalyst.zoho.in/quickml/api/v1/models/zia/translate
```

| Field | Value |
|---|---|
| Request Content-Type | `application/json` |
| Response Content-Type | `application/json` |
| Response format | JSON with translated text + processing time |
| OAuth scope | `QuickML.deployment.READ` |
| Supported languages | English, Hindi, Kannada, Tamil, Telugu, Malayalam, Marathi, Bengali, Gujarati, Punjabi, Odia |

**Where this fits that v8 didn't have:** KSP is a Karnataka force, but officers and CCTNS records routinely include Tamil, Telugu, and Marathi border-district names, victim/witness statements, and cross-jurisdictional case notes (Bengaluru alone sees heavy Tamil and Telugu speaker overlap). Right now Layer 1 only handles Kannada-script transliteration and English/Kannada code-switch normalization — anything in a third language falls through to the LLM's general multilingual ability with no dedicated handling. Wiring in the Translation model gives you a cheap, deterministic normalization step for the other 8 supported languages before the query ever reaches GLM-4.7-Flash, which is both more reliable and materially cheaper than asking the LLM to translate-and-reason in one call.

---

## 4. Updated Pipeline Placement

```
Layer 0  -- Input (text / voice / scanned document)
Layer 0a -- Input Validation Gate (size limits, MIME checks, injection denylist)
Layer 0b -- Format Detection + OCR (Qwen 3.6 35B VLM if PDF/image)
Layer 0c -- Schema Mapping (CCTNS -> canonical FIRSchema)
Layer 1  -- Preprocessing
            ├─ 1a. Voice -> Text          : Zia Audio-to-Text Transcription (en/hi/kn)
            ├─ 1b. Non-target-language -> English/Kannada : Zia Text Translation  [NEW]
            ├─ 1c. Transliteration        : indic-transliteration (local, unchanged)
            └─ 1d. Code-switch normalize  : GLM-4.7-Flash prompt-based (unchanged)
Layer 2  -- Query Understanding (NER + Intent + DAG Planner)
Layer 3  -- Retrieval (Memgraph + Catalyst KB + ZTSQL + Evidence Assembly)
Layer 4  -- Confidence Engine
Layer 5  -- LLM Synthesis + XAI (GLM-4.7-Flash)
Layer 6  -- Output
            ├─ 6a. Chat / dashboard / PDF (unchanged)
            └─ 6b. Voice response         : Zia Text-to-Audio Synthesis
Layer 7  -- Session Memory + Feedback (Catalyst NoSQL)
Layer 8  -- Offline Ingestion Pipeline
```

**Placement logic for 1b (Translation):** it only fires when the ASR/text-input language tag is outside `{en, hi, kn}` — cheap short-circuit, not a call on every query. This keeps the common-case (Kannada/English/Hindi officer query) latency identical to v8; the new hop only adds cost for the genuinely new capability it enables.

---

## 5. Updated `shared/catalyst_client.py`

This replaces the `transcribe_audio` / `text_to_speech` stubs in Implementation v8 (lines ~422–436) with endpoint-accurate versions, and adds `translate_text` as a new function.

```python
import httpx, os, base64

CATALYST_TOKEN         = os.getenv("CATALYST_API_TOKEN")
CATALYST_ORG_ID        = os.getenv("CATALYST_ORG_ID")          # e.g. 60075634347
CATALYST_LLM_URL       = os.getenv("CATALYST_LLM_ENDPOINT")
CATALYST_VLM_URL       = os.getenv("CATALYST_VLM_ENDPOINT")
CATALYST_KB_URL        = os.getenv("CATALYST_KB_ENDPOINT")
CATALYST_DATASTORE_URL = os.getenv("CATALYST_DATASTORE_URL")

# Zia voice/language endpoints -- verified against console model cards
ZIA_ASR_URL         = "https://api.catalyst.zoho.in/quickml/api/v1/models/zia/audio/transcribe"
ZIA_TTS_URL         = "https://api.catalyst.zoho.in/quickml/api/v1/models/zia/tts/synthesize"
ZIA_TRANSLATE_URL   = "https://api.catalyst.zoho.in/quickml/api/v1/models/zia/translate"

ZIA_HEADERS = {
    "CATALYST-ORG": CATALYST_ORG_ID,
    "Authorization": f"Zoho-oauthtoken {CATALYST_TOKEN}",
}
ZIA_HEADERS_JSON = {**ZIA_HEADERS, "Content-Type": "application/json"}

# Languages Zia ASR/TTS actually support -- everything else must route through translate first
ZIA_VOICE_LANGS = {"en", "hi", "kn"}


async def transcribe_audio(audio_bytes: bytes, language: str = "kn", filename: str = "recording.webm") -> str:
    """Zia Audio-to-Text Transcription. multipart/form-data per the verified model card."""
    async with httpx.AsyncClient() as client:
        r = await client.post(
            ZIA_ASR_URL,
            headers=ZIA_HEADERS,   # no Content-Type -- httpx sets multipart boundary itself
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
        r = await client.post(ZIA_TTS_URL, headers=ZIA_HEADERS_JSON, json=payload, timeout=15.0)
        r.raise_for_status()
        return r.content   # audio/wav


async def translate_text(text: str, source_lang: str, target_lang: str = "en") -> dict:
    """Zia Text Translation. New Layer 1b hop -- only called when source_lang not in ZIA_VOICE_LANGS."""
    async with httpx.AsyncClient() as client:
        r = await client.post(
            ZIA_TRANSLATE_URL,
            headers=ZIA_HEADERS_JSON,
            json={"source_language": source_lang, "target_language": target_lang, "text": text},
            timeout=15.0,
        )
        r.raise_for_status()
        return r.json()   # {"translated_text": ..., "processing_time": ...}


async def transcribe_and_normalize(audio_bytes: bytes, declared_language: str) -> str:
    """
    Layer 1 orchestrator: ASR -> (conditional) translate -> plain text into Layer 2.
    declared_language should come from the client's language picker / detected tag,
    not guessed after the fact -- Zia ASR requires the language up front.
    """
    if declared_language in ZIA_VOICE_LANGS:
        return await transcribe_audio(audio_bytes, language=declared_language)

    # Fallback path for non-ASR-supported languages: this assumes upstream text input
    # (e.g. a typed query in Tamil/Telugu/etc.), since Zia ASR itself only covers en/hi/kn.
    raise ValueError(
        f"Zia ASR does not support '{declared_language}'. "
        f"Route typed text in this language through translate_text() instead."
    )
```

**Two things worth calling out explicitly, in the spirit of the `[VERIFY]` discipline the rest of this project uses:**

1. `[VERIFY]` The exact JSON key names in the ASR/TTS/Translate response bodies (`transcript`, `translated_text`, `processing_time`) are inferred from the model cards' plain-English description, not from a captured sample response. Grab a real `Sample Request and Response` tab screenshot (visible as a second tab on all three of your model cards) before wiring this into `transcribe.py` — it's one click away and removes all guesswork.
2. `[VERIFY]` Zia ASR takes a `language` parameter but the model cards don't show an auto-detect option. If an officer's language isn't known ahead of time, you need a language picker in the `VoiceButton` UI component (Implementation v8, line ~2349) rather than relying on the model to infer it — confirm this against the Sample Request tab too.

---

## 6. Updated Model Usage Clarification Table

Replaces Architecture v8 Section 6's table:

| Model | Purpose | When Called |
|---|---|---|
| GLM-4.7-Flash Instruct | NER, intent, planning, synthesis | Every query — all text reasoning |
| Qwen 3.6 35B VLM | Scanned FIR OCR extraction | Only when input is image or PDF |
| Zia Audio-to-Text Transcription | ASR (voice → text) | Voice input, language ∈ {en, hi, kn} |
| Zia Text-to-Audio Synthesis | TTS (text → voice) | Voice output mode |
| Zia Text Translation | Cross-language normalization | Only when input language ∉ {en, hi, kn} — Tamil/Telugu/Malayalam/Marathi/Bengali/Gujarati/Punjabi/Odia |

---

## 7. Environment Variables — Delta

Replaces `CATALYST_ASR_ENDPOINT` / `CATALYST_TTS_ENDPOINT` in Architecture v8 Section 3 `.env` block:

```
CATALYST_ORG_ID=60075634347
# ASR / TTS / Translate URLs are hardcoded constants in catalyst_client.py per the
# verified model cards -- they are stable Zia platform endpoints, not per-project
# deployment URLs like the LLM/VLM/KB endpoints below, so they don't need an env var.
CATALYST_LLM_ENDPOINT=
CATALYST_VLM_ENDPOINT=
CATALYST_KB_ENDPOINT=
```

---

## 8. Phase Plan

| Phase | Item |
|---|---|
| Phase 1 (hackathon build) | Wire all three Zia endpoints into `catalyst_client.py` as above. Add language picker to `VoiceButton`. Pin TTS to neutral/moderate defaults. |
| Phase 1 (hackathon build) | Capture the real Sample Request/Response for all three model cards and correct the JSON key assumptions in Section 5 above. |
| Phase 1 (hackathon build) | Add Translation short-circuit to Layer 1 — only for text input tagged outside en/hi/kn; do not call it on every query. |
| Phase 2 (post-hackathon hardening) | Load-test Zia ASR against real KSP Kanglish recordings (same "real query logs" gap already flagged in Architecture v8's Production Gap table for GLM-4.7-Flash NER — same fix applies here: current validation is few-shot/synthetic, not field-recorded). |
| Phase 3 (production, explicitly deferred) | Re-evaluate Sarvam AI / Shuka as a drop-in ASR replacement once off the hackathon platform, where the AppSail RAM constraint and Catalyst-first judging incentive no longer apply. Native voice-to-voice reasoning (mentioned in your original note) is a legitimate Phase 3+ direction, not a hackathon-week one. |

---

## 9. One-Line Summary for `agents.md` / Antigravity Context

> Voice layer uses three named Zia models (not a generic "Catalyst Kannada NLP" placeholder): `audio/transcribe` for ASR, `tts/synthesize` for TTS, `translate` for cross-language normalization outside en/hi/kn. Sarvam AI was evaluated and explicitly rejected for the hackathon build — external dependency, AppSail RAM risk, and it runs against the organizer-confirmed Catalyst-first principle. Revisit Sarvam only post-hackathon.
