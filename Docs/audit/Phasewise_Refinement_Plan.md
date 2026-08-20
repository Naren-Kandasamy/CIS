# Phase-Wise Refinement Plan
*Execution Guide for the PS-1 Refinement Phase*

This document breaks down the refinement tasks into a safe, logical sequence. The goal is to tackle debugging and simple UI cleanup first, before moving into the heavy architectural changes (Voice v2, RBAC, Multi-case). 

**Companion Document:** Please refer to `Docs/audit/Refinement_Architecture_Analysis.md` for the technical specifications of *how* these features work structurally.

---

## Phase 1: Debug Audit & Cleanup
*Focus: Stabilize the system and remove unused code to reduce surface area before adding new features.*

1. **System Health Check (Debug):**
   - Run existing E2E and graph query tests to ensure the local pipeline is healthy.
   - Verify the Voice Module hotfix (`WavRecorder` capturing PCM) is not throwing errors in the browser console.
2. **Remove CIS Console Sandbox:**
   - Strip `activeView === 'cis-console'` from `client/src/App.tsx`.
   - Delete `client/src/components/dashboard/CISDashboard.tsx`.
   - *Why: Removes deprecated code, freeing up UI space for the new Case Sidebar.*
3. **UI Dashboard Refinements:**
   - Fix any minor alignment, responsiveness, or data-loading bugs in the main dashboard view.
   - Ensure the `VoiceButton` language picker defaults properly (e.g., to Kannada).
4. **Environment & Limits Audit:**
   - Check `CATALYST_ORG_ID` and Publisher URLs for production sync.
   - Follow up on Qwen/Zia LLM-specific rate limits with Catalyst support.

---

## Phase 2: Voice & Language Layer v2
*Focus: Connect the Catalyst Zia native endpoints without touching the rest of the pipeline.*

1. **Zia Audio-to-Text (ASR) Integration:**
   - Ensure `backend/api/main.py` properly forwards the `.wav` payload from the frontend to `/quickml/api/v1/models/zia/audio/transcribe`.
2. **Zia Text Translation (Preprocessing):**
   - Wire the `/quickml/api/v1/models/zia/translate` API to normalize non-English/Kannada inputs before they hit the LLM (Layer 1).
3. **Zia Text-to-Audio (TTS):**
   - Add a TTS endpoint to the backend. Lock emotion to `neutral` and speed to `moderate`.
4. **Testing:**
   - Do a manual end-to-end test of the voice pipeline (speak -> translate -> query -> TTS).

---

## Phase 3: RBAC & Department Hierarchy
*Focus: Add the access control filters to the backend before we expose multiple cases to the frontend.*

1. **Middleware & Query Filters (`backend/api/middleware/rbac.py`):**
   - Implement the "Pull" logic: check officer's `department` and `supervisory_scope` against the case properties.
   - Inject these jurisdiction filters into Memgraph search queries (drop any cases marked `is_sensitive`).
2. **Governance (Anti-Corruption):**
   - Add the `is_sensitive` flag logic.
   - Enforce that only the `vigilance_cell` role can flip a case from `is_sensitive = True` back to `False`.
3. **Audit Hash-Chaining:**
   - Update the existing audit log logic so that every new log entry hashes the previous entry's hash, making silent deletions mathematically detectable.

---

## Phase 4: Multi-Case / Thread Management
*Focus: The largest architectural change. Introduces persistent cases that span multiple sessions.*

1. **NoSQL Data Model Setup:**
   - Implement `case:{case_id}`, `case_sessions:{case_id}`, and `user_cases:{username}` key patterns.
2. **Backend API Endpoints:**
   - Create `POST /api/cases` to initialize a new case folder.
   - Modify the query endpoint to attach sessions to a specific `case_id`.
   - Add the `get_case_lock(case_id)` to prevent race conditions when updating case metadata.
3. **Frontend UI Integration:**
   - Add the `CaseSidebar` component to `App.tsx` (fetching from `user_cases:{username}`).
   - Implement the "Case Board" where officers can pin findings.
   - Add the **[⬆ Elevate for Review]** button to push cases to supervisors.
4. **Final Evaluation:**
   - Run a live feedback E2E test to confirm cases isolate correctly, RBAC blocks unauthorized access, and the voice module interacts smoothly with a selected case.
