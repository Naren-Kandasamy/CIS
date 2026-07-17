# PS-1 Master Remaining Checklist (Phase-Wise)

This list aggregates all the unchecked items across the official project phases in `Docs/PS1_Implementation_v8.md`. Since we have successfully completed the core pipeline logic locally, everything remaining focuses on Catalyst cloud deployment, external API wiring, and final evaluation.

## Phase 1: Foundations & Infrastructure Setup
*These are the fundamental scaffolding and deployment tasks that must be completed before the system can run in the cloud.*

- [x] **ZTSQL Row Cap Audit**: Calculate actual planned ZTSQL row counts against the 5,000-per-table / 25,000-per-project dev tier caps.
- [ ] **Email Support**: Contact `support@zohocatalyst.com` about exact Qwen/Zia LLM-specific rate limits to understand thresholds.
- [ ] **Memgraph on Oracle Cloud (Initial Setup)**: Get the Oracle VM provisioned, install Docker, run Memgraph + MAGE, and create schema constraints.
- [x] **AppSail FastAPI Deployment**: Deploy the FastAPI backend skeleton to Zoho Catalyst AppSail.
- [x] **React Shell on Catalyst Slate**: Deploy the frontend React application to Zoho Catalyst Slate (Web Client).
- [x] **API Keys & LLM Connection**: Renew the `CATALYST_API_TOKEN` and confirm a Qwen 14B test call from the pipeline Function returns valid JSON in the cloud.
- [x] **KB Initialization**: Upload the first batch of FIR documents into the Catalyst KB and ensure they are searchable.
- [x] **Function Memory Limit**: Configure pipeline Function memory explicitly at 512MB (`catalyst functions:config --memory 512`) to prevent out-of-memory errors.
- [x] **Prompt Injection Denylist (Layer 0a)**: Add a regex-based denylist to the `QueryRequest` model in `query.py` to block Cypher/SQL injection keywords before reaching the LLM.

## Phase 2: Core Pipeline Integration
*These items finalize the integration of external Catalyst services into the core application logic.*

- [x] **Voice/ASR Integration**: Test and wire the frontend `VoiceButton` directly to the live Catalyst Kannada ASR endpoint (replacing the local mock).
- [x] **Full KB & ZTSQL Hydration**: Load the entire 5K FIR dataset into the Catalyst Knowledge Base and the ZTSQL Datastore.
- [x] **Qwen VLM for Scanned FIR OCR (Layer 0b)**: Create an `/api/upload` endpoint with strict MIME/size validation to accept FIR images and extract fields via the Qwen 3.6 35B VLM.

## Phase 3: DAG Planner + Full Dataset
*All items in this phase (DAG Planner, Chaos Tests, Visualization UI, Dataset generation) were successfully completed and verified during local development!*
- [x] **DAG Planner Urgency Handling (Layer 2)**: Inject the `urgency` variable into the `DAG_PLANNER_SYSTEM` prompt in `dag_planner.py` to correctly cap graph depth and disable viz steps for `field_urgent` queries.

## Phase 4: Robustness + Production Readiness
*These items focus on hardening the deployed system and conducting strict evaluations before demo day.*

- [x] **Codebase Hardening & Test Stabilization**: Pin Catalyst dependencies (`sse-starlette`, `python-multipart`), fix DAG fallback graph query tripling, and resolve test suite flakiness/auth issues.
- [x] **Production LLM Switchover**: Transition from the local/Groq fallback models (Llama 3.3 70B) to the live Catalyst production models (GLM-4.7-Flash and Qwen 3.6 35B VLM) and verify pipeline behavior.

- [x] **Memgraph Oracle VM Hardened**: Add persistent Docker volumes and a restart policy (`--restart unless-stopped`) to the Oracle VM.
- [x] **Blind Evaluation Packet**: Generate a packet of AI outputs and have a teammate (not involved in the narrative design) label them.
- [ ] **Confidence Calibration**: Measure the Confidence Engine against these blind labels to ensure the `HIGH` confidence tier is >= 85% accurate.
- [x] **Confidence Engine OCR Penalty (Layer 4)**: Ensure any evidence extracted via the Qwen VLM carries an `ocr_extracted: true` flag, applying a 0.90 multiplier to its confidence score.
- [x] **Full Catalyst Deployment Verified**: End-to-end cloud execution is confirmed. Fixed AppSail React routing (`/app/` base path), backend environment variable limits (`ZC_` prefix), and `sys.path` dependency loading.
- [x] **Serverless Asyncio Event Loop Hardening**: Removed global Neo4j driver caching in `graph_client.py` to prevent background task crashes across ephemeral function invocations.
- [x] **Catalyst Environment Synchronization**: Removed empty `env_variables` in `catalyst-config.json` to prevent deployment wiping of UI variables, fixing the silent NoSQL mock-database fallback bug.
- [x] **Signals Payload Deserialization**: Implemented robust stringified JSON unwrapping in the serverless handler to prevent `TypeError` crashes on webhook delivery.

## Phase 5: Extended Investigative Capabilities & Refinements
*These items reflect the recent senior-investigator roadmap and architecture addendums for advanced reasoning, feedback loops, and data source integration.*

- [x] **Negative Evidence & Exclusion Tracking**: Implement `EXCLUDED_FROM` relationships and contradiction tracking to safely demote ruled-out suspects. *(Consult: `Docs/PS1_Negative_Evidence_Exclusion_Tracking.md`)*
- [x] **Reasoning Feedback Loop**: Implement methodology-scoped trust weighting (slow-moving cross-session scoreboard) and instant same-session penalty. *(Consult: `Docs/PS1_Reasoning_Feedback_Loop.md`)*
- [ ] **Evidence-Language Detection**: Add offline language detection (`langdetect`) and conditional translation for FIR narratives at ingestion. *(Consult: `Docs/PS1_Evidence_Language_Detection.md`)*
- [ ] **Zia-Native Voice & Language Layer v2**: Upgrade to the actual Catalyst Zia endpoints for ASR, TTS, and Translation (replacing generic placeholders). *(Consult: `Docs/PS1_Voice_Language_Layer_v2.md`)* **[Backend Complete - UI Integration Pending]**
- [x] **Shared Proactive Alert Primitive**: Build `ReviewQueueItem` schema and API for proactive push notifications. *(Consult: `Docs/PS1_Extended_Investigative_Capabilities.md` - Section 1)*
- [ ] **CDR & Financial Trail Integration**: Build the pluggable data source provider pattern, `CALLED`/`TRANSFERRED` edges, and inject synthetic layering/burner patterns. *(Consult: `Docs/PS1_Extended_Investigative_Capabilities.md` - Section 2)*
- [ ] **Proactive Cold-Case Matching**: Extend `SHARED_MO` ingestion to flag open/cold cases with high similarity to new FIRs via the review queue. *(Consult: `Docs/PS1_Extended_Investigative_Capabilities.md` - Section 3)*
- [ ] **Confidence Engine "Contradicted" State**: Log HIGH/MEDIUM confidence claims and flag them as contradicted if new evidence/exclusion records surface later. *(Consult: `Docs/PS1_Extended_Investigative_Capabilities.md` - Section 4)*
- [ ] **Vehicle/ANPR Cross-Referencing**: Ingest synthetic ANPR plate reads and cross-check against a wanted-vehicle registry. *(Consult: `Docs/PS1_Extended_Investigative_Capabilities.md` - Section 5)*
- [ ] **RBAC / Jurisdiction Scoping**: Add an `OfficerProfile` with Rank, Geography, and Department (The 3D Access Matrix). Implement Push/Pull visibility mechanics and sensitive case rules. *(Consult: `Docs/PS1_RBAC_Case_Access_v1.md`)*
- [ ] **Integrity & Anti-Corruption Layer**: Implement governance overrides for lowering case sensitivity and audit-logging for cross-jurisdictional snooping. *(Consult: `Docs/PS1_Integrity_AntiCorruption_Layer_v1.md`)*
- [ ] **Hypothesis Workspace**: Allow officers to log investigative theories (`HypothesisRecord`) and run deterministic checks for new supporting/contradicting evidence. *(Consult: `Docs/PS1_Extended_Investigative_Capabilities.md` - Section 7)*
- [x] **Case & Session Management**: Implement the multi-officer case container model (Cases containing Sessions). *(Consult: `Docs/PS1_Case_Session_Management.md`)*
- [x] **RBAC Middleware Exposure**: Patch `backend/api/middleware/rbac.py` to explicitly inject `session["username"]` into ASGI `scope["state"]`. **Why**: Required so that downstream case/session routes know *who* is making the request to verify case ownership.
- [x] **Collaborator Validation**: Ensure `POST /api/cases/{case_id}/collaborators` explicitly calls `get_user(body.username)`. **Why**: Without this, typo'd usernames will silently write to the database and the intended officer will never receive access to the case.

## Pre-Demo Checklist (Judging Day Operations)
*Tasks to execute strictly 30 minutes before presenting.*

- [ ] **Keep-Warm Uptime Service**: Configure an external pinging service (like UptimeRobot) to hit the AppSail `/health` endpoint every 4 minutes to prevent the 5-minute cold start sleep.
- [ ] **Production Publisher Check**: Confirm `CATALYST_SIGNALS_PUBLISHER_URL` in AppSail's `.env` points at the PRODUCTION publisher URL, not the dev URL.
- [ ] **Live System Health Checks**: Confirm Oracle VM connection, Catalyst KB searchability, and run a test compound query.
- [ ] **Zia Environment Check**: Confirm `CATALYST_ORG_ID` is set correctly for the production Catalyst org, not a dev org.
- [ ] **VoiceButton Default**: Ensure the language picker defaults to a sensible value (e.g., Kannada) rather than requiring manual selection every time.
- [ ] **Trust-Weight Environment Lock**: Confirm the `trust:` keys in Catalyst NoSQL are NOT accidentally wiped between dev and prod environments.
- [ ] **Live Feedback E2E Test**: Run through one citation confirm + one citation correct live, end-to-end, before judging starts to confirm the penalties apply visibly.
