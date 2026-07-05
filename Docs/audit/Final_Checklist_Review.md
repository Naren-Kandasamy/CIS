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

## Phase 2: Core Pipeline Integration
*These items finalize the integration of external Catalyst services into the core application logic.*

- [ ] **Voice/ASR Integration**: Test and wire the frontend `VoiceButton` directly to the live Catalyst Kannada ASR endpoint (replacing the local mock).
- [x] **Full KB & ZTSQL Hydration**: Load the entire 5K FIR dataset into the Catalyst Knowledge Base and the ZTSQL Datastore.

## Phase 3: DAG Planner + Full Dataset
*All items in this phase (DAG Planner, Chaos Tests, Visualization UI, Dataset generation) were successfully completed and verified during local development!*

## Phase 4: Robustness + Production Readiness
*These items focus on hardening the deployed system and conducting strict evaluations before demo day.*

- [x] **Codebase Hardening & Test Stabilization**: Pin Catalyst dependencies (`sse-starlette`, `python-multipart`), fix DAG fallback graph query tripling, and resolve test suite flakiness/auth issues.
- [ ] **Production LLM Switchover**: Transition from the local/Groq fallback models (Llama 3.3 70B) to the live Catalyst production models (GLM-4.7-Flash and Qwen 3.6 35B VLM) and verify pipeline behavior.

- [ ] **Memgraph Oracle VM Hardened**: Add persistent Docker volumes and a restart policy (`--restart unless-stopped`) to the Oracle VM.
- [ ] **Blind Evaluation Packet**: Generate a packet of AI outputs and have a teammate (not involved in the narrative design) label them.
- [ ] **Confidence Calibration**: Measure the Confidence Engine against these blind labels to ensure the `HIGH` confidence tier is >= 85% accurate.
- [x] **Full Catalyst Deployment Verified**: End-to-end cloud execution is confirmed. Fixed AppSail React routing (`/app/` base path), backend environment variable limits (`ZC_` prefix), and `sys.path` dependency loading.

## Pre-Demo Checklist (Judging Day Operations)
*Tasks to execute strictly 30 minutes before presenting.*

- [ ] **Keep-Warm Uptime Service**: Configure an external pinging service (like UptimeRobot) to hit the AppSail `/health` endpoint every 4 minutes to prevent the 5-minute cold start sleep.
- [ ] **Production Publisher Check**: Confirm `CATALYST_SIGNALS_PUBLISHER_URL` in AppSail's `.env` points at the PRODUCTION publisher URL, not the dev URL.
- [ ] **Live System Health Checks**: Confirm Oracle VM connection, Catalyst KB searchability, and run a test compound query.
