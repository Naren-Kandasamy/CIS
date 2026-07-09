# Catalyst Production LLM Switchover & Validation Plan

## 1. Overview
Throughout local development, the pipeline has relied on a fallback routing mechanism in `shared/catalyst_client.py` to forward LLM inference requests to Groq (Llama-3.3-70B) for speed and cost-saving. As we move to production readiness on Zoho Catalyst AppSail, we must fully transition to the provisioned models:
*   **Text/Reasoning:** `GLM-4.7-Flash` (30B MoE model: `crm-di-glm47b_30b_it`)
*   **Vision/OCR:** `Qwen 3.6 35B VLM` (`VL-Qwen3.6-35B-A3B`)

Moving from a 70B model to a 30B Mixture-of-Experts model introduces potential risks in instruction adherence and JSON formatting. This report outlines the strict path to transitioning and validating these models.

---

## 2. Step-by-Step Migration Plan

### Step 1: Disable the Fallback Proxy
Currently, `shared/catalyst_client.py` masks Catalyst connectivity issues by silently failing over to Groq if the `GROQ_API_KEY` is present.
**Action:** Remove the `if os.getenv("GROQ_API_KEY"):` logic entirely. For production testing, the pipeline must fail loudly if Catalyst is unreachable. The only endpoints that should be hit are the `ZC_LLM_ENDPOINT` and `ZC_VLM_ENDPOINT`.

### Step 2: Validate API Contract & Payload Strictness
Groq utilizes a standard OpenAI-compatible API layer. Catalyst QuickML often enforces stricter or slightly different payload requirements.
**Action:** Verify the exact JSON body format expected by Catalyst. Ensure that the payload dictionary structure `{"model": "...", "system": "...", "prompt": "..."}` is perfectly aligned with the live QuickML endpoint documentation. Run a simple manual `httpx.post` ping test before running the full pipeline.

### Step 3: Re-Run the NER Evaluation Suite (Crucial)
The 70B Llama model is highly resilient to complex structured prompting. `GLM-4.7-Flash` is lightweight and efficient, but its prompt-following behavior must be verified.
**Action:** Run `python data/scripts/eval_ner.py`. 
*   **Target:** The model must maintain a > 90% pass rate.
*   **Watch for:** Hallucinated JSON keys, dropped `IPC_SECTION` resolutions, or failure to wrap the output in raw JSON (e.g., adding conversational filler like "Here is the JSON:").

### Step 4: Stress-Test the DAG Planner
The LangGraph DAG Planner is the most complex LLM task in the system, requiring the LLM to output a JSON array of step objects with a strict `__dependencies` array for parallel execution.
**Action:** Run `python test_chaos.py` or submit 3-4 highly complex compound queries (e.g., "Find all associates of Ravi who were involved in vehicle theft in Mysuru and map their locations"). Ensure `GLM-4.7-Flash` successfully orchestrates the DAG without syntax errors.

### Step 5: Calibrate Rate Limits & Resilience
Groq's generous rate limits may have masked potential stalls in the pipeline. Catalyst will enforce its own RPM (Requests Per Minute) limits.
**Action:** Verify that `pipeline/catalyst_resilient_client.py` correctly intercepts Catalyst-specific rate limit errors (often HTTP 429). Ensure the exponential backoff mechanism triggers successfully, and if exhausted, the pipeline correctly degrades to the safe `lookup` default rather than crashing.

---

## 3. Summary of Success Criteria
The switchover is considered successful when:
1. All local `.env` files no longer contain external provider keys (Groq/OpenAI).
2. `eval_ner.py` yields a > 90% pass rate via `GLM-4.7-Flash`.
3. An OCR test of a scanned FIR successfully returns extracted fields using `Qwen 3.6 35B VLM`.
4. A full compound query completes end-to-end in the deployed cloud environment.
