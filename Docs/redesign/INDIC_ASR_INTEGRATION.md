# Indic-ASR integration plan — folding `feat/indic-asr` into the redesigned frontend

**Status:** not started. Execute **after** `feature/ui-redesign-v2` is merged to
`main`. Owner: whoever rebases the voice work (Hemnath, or us on his behalf).

This branch (the UI redesign) deleted `client/src/App.tsx`, which is where
Hemnath wired his voice feature. His backend pieces are mostly independent of
our changes; his frontend pieces must be **re-applied onto the new component
structure** (`components/chat/*`, `hooks/useVoiceRecorder.ts`, `lib/api.ts`).
Nothing of his needs to be lost — this doc is the port map.

---

## Source

- Branch: `origin/feat/indic-asr`, single squashed commit `93f2412`
  *("feat(indic-asr): add in-repo ONNX Indic model, Bengaluru gazetteer, and
  chat deletion fixes")*.
- Forked from `22b5666` — the **same** base as our redesign. He does **not**
  have our `1203739` token-refresh fix or the `33dd1df` swagger commit.
- His PR to `main` had "0 conflicts with main" only because `main` hadn't moved.
  Against our merged branch there are real overlaps (below).

---

## What the feature actually is (three independent layers)

1. **Browser live ASR** — `IndicSpeechRecognizer` (Web Speech API,
   `SpeechRecognition`) transcribes speech to text in the browser, live, with
   interim results. Chrome/Edge only; audio goes to Google. No server audio
   upload.
2. **Cloud ASR cascade** (server, in `transcribe_audio()`) — tries, in order:
   in-repo ONNX → HuggingFace Inference API → Groq/OpenAI Whisper → **Zia**
   (our existing path). Each hop is best-effort; a missing key or dep just
   falls through. **Net effect with no new keys set: identical to today (Zia).**
3. **Normalization** (server, `normalize_transcript_text()`) — the valuable
   deterministic part: `INDIC_PHONETIC_PATTERNS` (Bengaluru police-station
   gazetteer, IPC/BNS section forms, code-mixed verb→English across Kn/Hi/Ta/
   Te/Mr/Ml/Bn) run as regex, then an LLM pass with a Karnataka-Police prompt
   that turns `"Belagavi station case 142 nalli Section 302 IPC ... torisi"`
   into `"Show crime details for FIR No. 142 under Section 302 IPC ... at
   Belagavi station"`. Exposed as `POST /api/transcribe/normalize`.

His client flow: mic → `IndicSpeechRecognizer` fills the input box live →
on stop / on final result → `POST /api/transcribe/normalize {text, language}`
→ replace input box with the normalized query. The audio-upload path
(`POST /api/transcribe`) is left in place server-side but no longer called
from his client.

---

## One piece is unfinished scaffolding — hold it until it's complete

`shared/onnx_indic_asr.py` + `models/indic_asr_tiny.onnx` + `models/vocab.json`
is the **plumbing for an in-repo ONNX ASR path, with the inference engine
stubbed out**. It is committed deliberately fail-safe so it doesn't disturb the
working Zia path while the model is still being chosen (see the
`data/scripts/test_onnx_indic_asr.py` / `test_huggingface_indic_asr.py` /
`eval_hinglish_compressed.py` experiments in the same commit).

What's built vs stubbed in `ONNXIndicASR.transcribe()`:

- ✅ WAV bytes → float32 PCM decode (real).
- ✅ ONNX session as a CPU singleton, thread-capped (correct for serverless).
- ❌ Feeds the model `np.zeros((1, 80, 3000))` — a placeholder mel-spectrogram
  — instead of the decoded audio. No feature-extraction (STFT/mel) step exists.
- ❌ `session.run(...)` output is not captured; `return ""` unconditionally.
- ❌ `vocab.json` has only `{model_type, sample_rate, languages}` — no token
  vocabulary, so logits couldn't be decoded to text even if inference ran.
- ❌ `onnxruntime` / `numpy` are not in any `requirements.txt`, so on a clean
  deploy the `import` raises, is caught by `transcribe_audio()`'s outer
  try/except, logged, and skipped.

**Net effect at runtime today: contributes nothing** (returns `""` → the
cascade moves to the HF / Whisper / Zia fallbacks).

**Recommendation for the merge:** do **not** land `models/indic_asr_tiny.onnx`
(10 MB blob), `models/vocab.json`, `shared/onnx_indic_asr.py`, or the ONNX
branch in `transcribe_audio()` into `main` yet. Either:
- Hemnath finishes it (mel feature extraction + token decode + real
  `vocab.json` + `onnxruntime`/`numpy` in requirements + Git LFS for the blob),
  and it comes in as its own follow-up, or
- it stays on `feat/indic-asr` until then.

Everything else in his commit — the gazetteer, `normalize_transcript_text`, the
HuggingFace / Whisper cascade, the browser recognizer — is finished and comes
in per the table below. The HF / Whisper cascade is the meaningful upgrade over
Zia-only.

---

## Inventory & verdict

| His file | Δ | Verdict |
|---|---|---|
| `shared/catalyst_client.py` | +302 | **Port, 3-way merge.** His ASR section (`INDIC_PHONETIC_PATTERNS`, `preprocess_indic_phonetics`, `transcribe_audio` cascade, `normalize_transcript_text`, `transcribe_and_normalize` refactor) is ~line 347+. Our token-lock + retry changes are ~lines 43 / 136 / 478 / 560. Orthogonal — **keep both**. |
| `functions/ps_1_cis_function/shared/catalyst_client.py` | +296 | Same merge, mirror. Must stay byte-equal to `shared/` (minus the deploy import prefix). |
| `shared/onnx_indic_asr.py` | new | **Hold** — inference is stubbed (see above). Land only when finished; add `onnxruntime`+`numpy` to requirements then. |
| `models/indic_asr_tiny.onnx`, `models/vocab.json` | new (10 MB) | **Hold** — belongs with a finished `onnx_indic_asr.py`, and via Git LFS, not a plain blob. |
| `backend/api/routes/transcribe.py` | +22 | **Port.** He appends `POST /api/transcribe/normalize` + `NormalizeRequest`. Our version of this file has extra bug-fix comments and the WAV/size guards — keep ours, append his route. Move the `from pydantic import ...` / `from shared.catalyst_client import normalize_transcript_text` to the top with the other imports. |
| `backend/api/routes/cases.py` | +26 | **Drop his hunk.** He adds `DELETE /api/sessions/{id}` in `cases.py`; we already have a functionally identical one in `backend/api/routes/sessions.py` (same `get_case_lock` + `_require_collaborator` + `case_sessions` index cleanup + `session_meta`/`history` delete). Two registrations for one path = route collision. **Do port his two small hardenings into `sessions.py`:** return `{"status":"deleted"}` instead of `404` when `session_meta` is absent (idempotent delete), and `meta.get("case_id")` instead of `meta["case_id"]`. |
| `client/src/lib/indicSpeech.ts` | new (128) | **Adopt as-is.** Pure browser API, no deps. |
| `client/src/lib/audioRecorder.ts` | new (226) | **Adopt** — it's a better recorder than our `lib/wavRecorder.ts`: VAD auto-stop on silence, RMS level callback, pause/resume, clean teardown, 16 kHz mono WAV. Either replace `wavRecorder.ts` with it or keep both and have `useVoiceRecorder` use `AudioRecorderVAD`. |
| `client/src/App.tsx` | 170 | **Cannot cherry-pick — file is gone.** Re-apply the logic per "Frontend port" below. The 3 removed `alert()` / `confirm()` calls are already handled in our tree by `ConfirmDialog` + inline error states — nothing to do there. |
| `data/scripts/{download_onnx_indic_model,eval_hinglish_compressed,test_cloud_indic_asr_e2e,test_delete_session,test_huggingface_indic_asr,test_onnx_indic_asr}.py` | new | **Optional.** Additive standalone scripts. `test_delete_session.py` is useful; the ONNX/HF eval scripts only matter if the cloud cascade is finished. `tests/conftest.py` already `collect_ignore`s `test_*` probe scripts, but these live in `data/scripts/` so they're outside pytest collection anyway. |

---

## Backend port — steps

1. **`shared/catalyst_client.py`** — take `origin/feat/indic-asr:shared/catalyst_client.py`
   as the base for the ASR section, then re-apply our token changes on top:
   - `_NOSQL_TOKEN_LOCK` / `_ZIA_TOKEN_LOCK` + `_get_nosql_token_lock()` /
     `_get_zia_token_lock()` (near `_get_mock_db_lock`).
   - the `async with _get_*_token_lock():` + re-check blocks in
     `_get_nosql_access_token()` and `_get_zia_access_token()`.
   - `RETRYABLE_STATUS` + the `except httpx.HTTPStatusError` retry arm in
     `_nosql_request()`.
   Verify `preprocess_indic_phonetics` / `normalize_transcript_text` /
   `transcribe_audio` land intact. Decide the ONNX branch (drop vs keep-with-dep).
2. Mirror every line into `functions/ps_1_cis_function/shared/catalyst_client.py`.
   Run `diff <(sed 's/pipeline_function\.//g' shared/catalyst_client.py) …` to
   confirm parity.
3. **`backend/api/routes/transcribe.py`** — keep ours; append his
   `/api/transcribe/normalize` route + `NormalizeRequest` model; hoist his
   imports to the top. Route needs auth like the others — add the RBAC-guarded
   `request: Request` param pattern the file's other route uses if the global
   middleware doesn't already cover `/api/transcribe/*` (it does — verify).
4. **`sessions.py`** — apply the two hardenings noted above. Do **not** add his
   `cases.py` route.
5. **Env vars** — the HF / Whisper hops read `HF_API_KEY` /
   `HUGGINGFACE_API_KEY`, `GROQ_API_KEY` / `OPENAI_API_KEY`, `WHISPER_API_URL` /
   `OPENAI_AUDIO_URL`. Add them (empty is fine — cascade falls through to Zia)
   to **each** of `backend/.env`, `pipeline_function/.env`,
   `client/.env.production` as needed. **Keep the three files separate.**
6. **Deps** — only if the ONNX branch is kept: add `onnxruntime` + `numpy` to
   `requirements.txt` *and* the function's requirements. Otherwise no dep change
   (HF/Whisper/Zia all use `httpx`, already present).

---

## Frontend port — map his `App.tsx` wiring onto our components

His logic lives in `handleMicClick` / `normalizeTranscriptText` / the input-bar
JSX. Target files: `hooks/useVoiceRecorder.ts`, `components/chat/InputBar.tsx`,
`lib/api.ts`, plus the two new `lib/` files.

1. **`lib/api.ts`** — add:
   ```ts
   export const normalizeTranscript = (text: string, language: string) =>
     apiFetch<{ normalized_text: string; original_text: string }>(
       '/api/transcribe/normalize', { method: 'POST', body: { text, language } });
   ```
2. **`lib/audioRecorder.ts`, `lib/indicSpeech.ts`** — copy in verbatim from his
   branch.
3. **`hooks/useVoiceRecorder.ts`** — rework to his dual-path model:
   - On start: `new AudioRecorderVAD()` for the analyser/visualizer; if
     `IndicSpeechRecognizer.isSupported()`, start it and stream `onResult` →
     `onTranscript(text)` (live). Else fall back to our current
     `startWavRecording()` → `POST /api/transcribe` path.
   - On stop: stop both; call `normalizeTranscript(currentText, language)` and
     hand the normalized string back via `onTranscript` (or a new
     `onNormalized`). Keep `isTranscribing` around the normalize call.
   - Keep `togglePause` / `getAnalyser` working off `AudioRecorderVAD`
     (`pause()` / `resume()` / `getAnalyser()` exist on it).
   - Preserve our silent-failure behaviour (no `alert`).
4. **`components/chat/InputBar.tsx`** —
   - Language `<select>`: swap the 3 hardcoded `<option>`s for
     `INDIC_LANGUAGES.map(...)` (7 options, `-IN` codes). Keep it styled with
     our tokens, not his inline `#1e293b`.
   - **Query-language mapping:** our `onSend(text, language)` and
     `/api/query` expect `"en" | "hi" | "kn"`. His voice `voiceLanguage` is
     `kn-IN | hi-IN | en-IN | ta-IN | te-IN | mr-IN | mix-IN`. Add a mapper:
     `kn-IN → kn`, `hi-IN → hi`, everything else → `en`, and pass the mapped
     value to `onSend`. The full `-IN` code still goes to
     `normalizeTranscript` and `IndicSpeechRecognizer`.
   - "Recording…/Pause/Resume" affordance: his version drops the pause button
     and shows "Listening… — Speak into your microphone". Keep whichever UX the
     team prefers; the pause button still works if `AudioRecorderVAD` is the
     recorder.
5. **`types/chat.ts`** — either widen `QueryLanguage` or add a separate
   `VoiceLanguage` type for the 7 `-IN` codes; keep `QueryLanguage` as the
   pipeline's `en|hi|kn`.

---

## Verification checklist (post-port)

- `npx tsc --noEmit -p tsconfig.app.json` clean; `npx vite build`; `npx vitest run`.
- `npx oxlint src/` 0.
- Backend: `python -m pytest tests/ -q` (clear `.nosql_mock_db.json` rate keys
  first) → 124+; add a test for `POST /api/transcribe/normalize`.
- `shared/` ↔ `functions/ps_1_cis_function/shared/` `catalyst_client.py` diff
  clean.
- Manual: mic in Chrome → words appear live → stop → input box shows a cleaned
  English query (e.g. say "Belagavi" garbled → resolves to "Belagavi") → send →
  pipeline runs. Then in a non-SpeechRecognition browser → falls back to
  audio-upload + Zia and still normalizes.
- `DELETE /api/sessions/{id}` still single-registered (grep both `sessions.py`
  and `cases.py`); deleting a session removes its sidebar entry with no orphan.
- No new console `alert()`.
