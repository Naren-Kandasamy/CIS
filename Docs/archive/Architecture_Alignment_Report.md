# PS-1 Codebase vs. Architecture Alignment Report

**Date:** July 6, 2026
**Reference Documents:** `Docs/PS1_Architecture_v8.md`, `Implementing StemFlow Audio Interface` (Audio/Transcribe Context)

This report highlights where the current codebase diverges from the confirmed Phase 1 architecture and outlines the beneficial components that must be implemented to achieve full production readiness. 

---

### 1. DAG Planner Urgency Handling (Layer 2)
**Architectural Goal:** The DAG planner must restrict execution plans based on urgency. Specifically, `field_urgent` queries should cap graph traversal depth to 1 and omit visualization steps, while `analytical` queries allow full multi-hop traversal and dashboard elements.
**Current Codebase State:** In `pipeline_function/pipeline/query_understanding/dag_planner.py`, the system prompt (`DAG_PLANNER_SYSTEM`) has no instructions regarding the `urgency` field. The LLM is generating plans completely blind to whether the officer is in the field or at a desk.
**Required Action:** Inject the `urgency` value from the intent JSON directly into the prompt and explicitly instruct the LLM on the depth limits for `field_urgent` vs `analytical`.

### 2. Prompt Injection & SQL/Cypher Denylist (Layer 0a)
**Architectural Goal:** A strict input validation gate must exist before any AI is called, including a pattern-matching denylist to block SQL/Cypher injection attempts and prompt hijacking.
**Current Codebase State:** `backend/api/routes/query.py` successfully validates the 500-character max limit and UUID structure, but completely lacks the required denylist validation for the `query` text.
**Required Action:** Implement a regex-based keyword denylist (e.g., blocking `DROP`, `DELETE`, `MATCH (n)`, `System Prompt:`) directly in the Pydantic `QueryRequest` validation logic.

### 3. Qwen VLM for Scanned FIR OCR (Layer 0b)
**Architectural Goal:** If a user uploads a scanned image or PDF of an FIR, the system should route it to the Catalyst-hosted `Qwen 3.6 35B VLM` to extract structured fields before the pipeline runs.
**Current Codebase State:** While audio transcription (`transcribe.py`) is well-implemented with 5MB strict size limits and MIME validation (aligning well with streaming audio concepts), there is no endpoint or pipeline logic to accept document/image uploads and route them to the VLM.
**Required Action:** Create an `/api/upload` endpoint matching the rigorous validation of `transcribe.py` (10MB limit, image/pdf MIME checks) and connect it to a VLM completion function in `catalyst_client.py`.

### 4. Confidence Engine - OCR Penalty
**Architectural Goal:** Any evidence extracted via the VLM OCR should carry an `ocr_extracted: true` flag, multiplying its confidence score by 0.90 and generating an explicit warning to the officer.
**Current Codebase State:** This logic does not currently exist because the OCR layer itself is missing. 
**Required Action:** Once the OCR endpoint is implemented, ensure the extraction payload appends the OCR flag so the downstream Confidence Engine can penalize it automatically.

---
**Summary:** The foundational pipeline (LangGraph Orchestrator, Database Retrievers, SSE Streaming, Audio Validation) is solid and well-aligned. The next immediate steps to reach 100% compliance with `v8` involve tightening security (Denylist) and adding the missing VLM document OCR route.
