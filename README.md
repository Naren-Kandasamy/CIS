# PS-1 CIS — Conversational Crime Intelligence System

A conversational intelligence assistant for the Karnataka State Police. An officer
asks a question in plain language (English, Hindi or Kannada, typed or spoken) and
the system runs a multi-stage retrieval pipeline across a case graph, a document
knowledge base and a structured case store, then returns a synthesised field
report with **cited, confidence-scored evidence** rather than a bare answer.

Built entirely on Zoho Catalyst.

---

## Contents

- [What it does](#what-it-does)
- [Architecture](#architecture)
- [Repository layout](#repository-layout)
- [Local setup](#local-setup)
- [Running the tests](#running-the-tests)
- [Deployment](#deployment)
- [Environment variables](#environment-variables)
- [Troubleshooting](#troubleshooting)

---

## What it does

| Capability | Notes |
|---|---|
| Natural-language case queries | NER + intent extraction, DAG-planned retrieval, streamed synthesis |
| Evidence citations | Every claim links to FIR records with a confidence tier and reasoning trace |
| Confidence scoring | Source convergence, evidence strength and recency, weighted by methodology trust |
| Voice input | Zia ASR — English, Hindi, Kannada |
| Text-to-speech | Zia TTS for reading field reports aloud |
| Translation | Zia Translate normalises non-en/hi/kn evidence before reasoning |
| Investigative hypotheses | Officers log theories, re-check them against new evidence, confirm or refute |
| Negative evidence | Alibi/exclusion records demote (never silently delete) contradicted links |
| Reasoning feedback loop | Officer confirm/correct signals adjust future trust weighting |
| RBAC | Rank hierarchy from DySP down to Constable, session tokens with TTL |

---

## Architecture

```
Client (React + Vite, Catalyst Web Client Hosting)
   │  HTTPS
   ▼
Backend (FastAPI on Catalyst AppSail)
   │  publishes a job via Catalyst Signals
   ▼
ps_1_cis_function (Catalyst Function)
   └── LangGraph pipeline:
         NER & Intent → Entity Match → DAG Planner → Retrieval
                      → Confidence → Visualiser → Synthesis
                                │
              ┌─────────────────┼──────────────────┐
              ▼                 ▼                  ▼
          Memgraph        Catalyst KB        Catalyst Data Store
        (case graph)      (RAG documents)    (structured cases)

Shared services: Catalyst NoSQL (users, sessions, job status),
                 Catalyst QuickML (LLM/VLM), Zia (ASR/TTS/Translate)
```

The backend does **not** run the pipeline inline. It writes a job record and
publishes a Signals event; the Function executes the pipeline and writes progress
back to NoSQL, which the backend streams to the client over SSE. If the Signals
URL is unset the backend falls back to running inline, which can time out on long
queries.

### The `functions/` mirror

`ps_1_cis_function` is deployed as a self-contained bundle, so it needs its own
copies of `shared/` and `pipeline_function/`:

```
shared/            ──copy──▶  functions/ps_1_cis_function/shared/
pipeline_function/ ──copy──▶  functions/ps_1_cis_function/pipeline_function/
```

**Any edit to `shared/` or `pipeline_function/` must be mirrored.** CI does this
automatically before deploying. When working locally, mirror and verify:

```bash
rm -rf functions/ps_1_cis_function/shared && cp -r shared functions/ps_1_cis_function/
rm -rf functions/ps_1_cis_function/pipeline_function && cp -r pipeline_function functions/ps_1_cis_function/
diff -rq shared functions/ps_1_cis_function/shared --exclude=__pycache__
```

---

## Repository layout

```
backend/              FastAPI app (AppSail) — routes, RBAC + validation middleware
pipeline_function/    LangGraph pipeline: query understanding, retrieval, synthesis
shared/               Code used by BOTH backend and function
                      (Catalyst clients, auth, feedback/exclusion/hypothesis engines)
functions/            Deployed Catalyst Function bundle (contains mirrored copies)
client/               React + Vite frontend
ingestion/            Data ingestion into Memgraph / Data Store / KB
data/                 Datasets, seed and evaluation scripts
tests/                Test suite (see below)
Docs/                 Architecture, design docs, audits, testing plans
```

---

## Local setup

**Prerequisites:** Python 3.13, Node 22+, a running Memgraph, and a `.env`
(ask a teammate — it holds live credentials and is git-ignored).

```bash
# Backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r backend/requirements.txt

# Frontend
cd client && npm install && cd ..
```

Run both servers:

```bash
./start_all.sh          # backend :8000, frontend :5173
```

Or individually:

```bash
python -m uvicorn backend.main:app --reload --port 8000
cd client && npm run dev
```

Seed the demo accounts (writes to Catalyst NoSQL):

```bash
python data/scripts/seed_users.py
```

| Username | Password | Role |
|---|---|---|
| `dysp1` | `demo1234` | DySP |
| `inspector1` | `demo1234` | Inspector |
| `si1` | `demo1234` | Sub-Inspector |
| `constable1` | `demo1234` | Constable |

> Demo credentials only — rotate before any non-demo use.

The Vite dev server proxies `/api` to `127.0.0.1:8000`. Note this means a missing
API base URL will *work locally but break when deployed*, since the client and
backend are on different origins in production.

---

## Running the tests

Tests live in `tests/`. `pytest.ini` sets `pythonpath = .` so they can import
`backend`, `shared` and `pipeline_function` from the repo root.

```bash
pytest                      # whole suite
pytest tests/test_auth.py   # one file
pytest -k lock              # by keyword
```

Some tests hit live Catalyst services and need a valid `.env`; a few integration
tests set `MOCK_NOSQL_ONLY=true` themselves to stay offline.

---

## Deployment

Pushing to `main` triggers `.github/workflows/catalyst-deploy.yml`, which builds
the client, bundles backend dependencies, mirrors `shared/` and
`pipeline_function/` into `functions/`, and deploys everything.

> The Catalyst CLI **exits 0 even when a deploy fails** (e.g. an expired
> `CATALYST_TOKEN` prints `Authentication failure` / `No components deployed!`).
> The workflow therefore inspects the CLI output and fails explicitly — without
> that check, runs went green for a full day while shipping nothing.

Manual deploy:

```bash
catalyst deploy                                   # everything
catalyst deploy --only client
catalyst deploy --only appsail:backend
catalyst deploy --only functions:ps_1_cis_function
```

**After any deploy, check the AppSail logs for this line:**

```
[STARTUP] ✅ NoSQL target: real Catalyst AppKeyValueStore
```

If it instead reads `LOCAL MOCK FILE`, the backend is running against an empty
local store — no account will be able to log in. The message names the exact
cause.

---

## Environment variables

Deployed Catalyst environments reject variable names containing the reserved word
`CATALYST`, so the console sets them under a `ZC_` prefix. `shared/catalyst_client.py`'s
`_env()` helper checks the `ZC_` name first, then the local `CATALYST_` name — so
both work.

| Local (`.env`) | Deployed | Purpose |
|---|---|---|
| `CATALYST_PROJECT_ID` | `ZC_PROJECT_ID` | Project id — **required for NoSQL** |
| `CATALYST_CLIENT_ID` / `_SECRET` | `ZC_CLIENT_ID` / `ZC_CLIENT_SECRET` | OAuth self client |
| `CATALYST_REFRESH_TOKEN` | `ZC_REFRESH_TOKEN` | Long-lived grant (NoSQL, QuickML) |
| `ZIA_REFRESH_TOKEN` | `ZC_ZIA_REFRESH_TOKEN` | Zia ASR/TTS/Translate — needs `QuickML.deployment.READ` |
| `CATALYST_LLM_ENDPOINT` / `_VLM_` | `ZC_LLM_ENDPOINT` / `ZC_VLM_ENDPOINT` | Inference |
| `CATALYST_KB_ENDPOINT` / `_KB_DOCUMENTS` | `ZC_KB_ENDPOINT` / `ZC_KB_DOCUMENTS` | RAG knowledge base |
| `CATALYST_SIGNALS_PUBLISHER_URL` | `ZC_SIGNALS_PUBLISHER_URL` | Async pipeline dispatch |
| `MEMGRAPH_URI` / `_USERNAME` / `_PASSWORD` | same | Graph database |
| `CORS_ALLOWED_ORIGINS` | same | Comma-separated origins |
| `MOCK_NOSQL_ONLY` | — | **Local only.** `true` uses a local JSON file instead of real NoSQL |

`.env` is only loaded outside Catalyst. Inside a deployment the platform-injected
variables are the sole source of truth, so a stray `.env` in a deploy bundle
cannot override them.

---

## Troubleshooting

**"Invalid username or password" for a known-good password**
The backend is probably on the mock store. Check the startup log for
`NoSQL target:`. Five failed attempts trigger a 15-minute lockout (HTTP 429,
"Too many failed login attempts"), which is a *symptom*, not the cause.

**CI is green but nothing deployed**
Check the run log for `Authentication failure` / `No components deployed!`.
Regenerate with `catalyst token:generate` and update the `CATALYST_TOKEN` secret.

**Voice input fails**
Zia ASR validates by file extension and accepts `.wav`, `.mp3`, `.ogg`, `.flac` —
it rejects `.webm`, which is what `MediaRecorder` produces in Chrome. The client
encodes WAV in-browser (`client/src/lib/wavRecorder.ts`) for this reason.

**Zia returns `401 INVALID_OAUTHSCOPE`**
The Zia endpoints need a token granted `QuickML.deployment.READ`; the general
Catalyst refresh token does not carry it.

**AppSail deploy fails on Windows with `EMFILE: too many open files`**
The CLI walks `client/node_modules` despite `.catalystignore`. Deploy from a
clean clone (which has no `node_modules`), or from Linux/WSL.
