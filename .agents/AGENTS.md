# Agent Instructions — PS-1 Conversational Crime Intelligence System

> Mirrored across CLAUDE.md, AGENTS.md, and GEMINI.md so the same instructions load in any AI environment.
> Ground truth for design decisions lives in `docs/PS1_Architecture.md` and `docs/PS1_Implementation.md` (v8). This file tells you *how to operate*, not *what the system does* — when the two ever conflict, the architecture/implementation docs win and this file should be updated to match.

You operate within a 3-layer architecture that separates concerns to maximize reliability. LLMs are probabilistic, business logic is deterministic and requires consistency. This system fixes that mismatch — and it is the exact same principle PS-1 itself is built on: **the LLM plans and synthesizes, deterministic systems retrieve** (Architecture §2). You are expected to apply that principle to your own work, not just implement it in the product.

---

## 0. Read this first — project shape, not generic advice

PS-1 is a hybrid GraphRAG system (Memgraph + Catalyst KB/RAG + ZTSQL + Qwen 14B) split across two Zoho Catalyst deployment targets:

- **`backend/`** — AppSail, thin front door only. Validates input, checks cache, fires a Signals Custom Publisher event, polls NoSQL job state over SSE. **Never** calls the LLM, VLM, Memgraph, KB, or ZTSQL directly. ~160MB RAM, 30s request budget.
- **`pipeline_function/`** — Catalyst Function, triggered as a Signals Function target (Custom Publisher → Rule → Function). This is where LangGraph, NER/intent, the DAG planner, all retrieval, the confidence engine, and synthesis actually run. 15-minute budget, configure memory to 512MB explicitly.
- **`ingestion/`** — offline batch only, driven by `data/scripts/`, never in the live query path.

**If you ever find yourself about to write LLM/Memgraph/KB/ZTSQL calls inside `backend/`, stop.** That violates the core hosting decision in Architecture §16 (reached after two design corrections — Circuits don't work in this data center and are 30s-capped anyway; Custom Event Listeners are deprecated/EOL as of 30 April 2026). Route through Signals instead, or flag the conflict and ask.

Before touching code in an unfamiliar area, grep the relevant section number below rather than reading the whole doc — both docs are large (1184 and 2566 lines) and re-reading them in full per task burns tokens for no benefit once you know the map.

| Topic | Architecture § | Implementation § |
|---|---|---|
| Hosting split / Signals trigger mechanics | 16 | 6 |
| NER + Intent (single Qwen call) | 8 | 7 |
| LLM resilience (cache/retry/degrade) | 11 | 8 |
| Evidence Object / retrieval timeouts | 9 | 10, 11 |
| Confidence Engine scoring | 10 | 12 |
| Synthesis + XAI + legal phrasing | 11 | 13 |
| Memgraph schema/algorithms | 15, 21 | 14 |
| ZTSQL schema | — | 15 |
| Ingestion pipeline | 14 | 16 |
| CCTNS schema mapping | 22 | 17 |
| RBAC + audit logging | 23 | 22 |
| Evaluation (trap scenario, calibration) | 27 | 19 |
| Open items / unresolved risk | "To Discuss / Remaining" | "To Discuss / Remaining" |

---

## 1. The 3-Layer Architecture (your operating model)

**Layer 1: Directive (What to do)**
- SOPs in Markdown, live in `directives/`. One directive per recurring task (e.g. `directives/run_ner_eval.md`, `directives/regenerate_derived_edges.md`, `directives/deploy_pipeline_function.md`).
- Define goal, inputs, which `execution/` or `data/scripts/` tool to call, expected output, edge cases, and known Catalyst-specific gotchas (rate-limit stall, dev-tier row caps, dev-vs-prod Signals URLs).

**Layer 2: Orchestration (Decision making)** — this is you.
- Read the directive, call the right script in `execution/`, `ingestion/`, `data/scripts/`, or `pipeline_function/pipeline/` in the right order, handle errors, ask for clarification, update directives with learnings.
- You do not hand-roll Cypher, hand-write Memgraph traversals, or manually compute confidence scores in conversation — those are deterministic logic that already lives in (or belongs in) `pipeline_function/pipeline/` and `pipeline_function/graph/`. If the script doesn't exist yet, write it there, not as throwaway code in your response.
- You do not directly call Qwen 14B / Qwen 7B VLM / Catalyst KB / ZTSQL "manually" to answer a question about the data — go through `shared/catalyst_client.py` so retries, timeouts, and resilience patterns are applied uniformly (Implementation §8). One-off bypasses are exactly how the rate-limit stall problem (Architecture §11) becomes invisible until demo day.

**Layer 3: Execution (Doing the work)**
- Deterministic Python in `execution/` (general tooling), `ingestion/` (offline pipeline), `pipeline_function/pipeline/` (live query pipeline), and `data/scripts/` (dataset generation + evaluation).
- Reads `.env` for Catalyst tokens, Memgraph URI, etc. — **never** hardcode credentials, and never echo `.env` contents into a response or commit.
- Handle API calls, data processing, file/DB operations. Commented well, especially anywhere a Catalyst-specific quirk was discovered the hard way (see §3 below).

**Why this works:** if you do everything yourself in conversation, errors compound — 90% accuracy per step = 59% success over 5 steps (Layer 2 reasoning chains: NER → planning → retrieval → confidence → synthesis is already 5 steps, Architecture §11). Push complexity into deterministic code in Layers 1/3; you focus on routing and decision-making in Layer 2.

---

## 2. Token-efficiency rules (specific to this project's scale)

The architecture and implementation docs are long and detailed by design — that detail is the source of truth, not filler. Burning context re-deriving it from scratch every session is the failure mode to avoid.

1. **Use the section table in §0**, not a full re-read, for any question already answered above. Grep for the section number/heading, view only that range.
2. **Don't paste large code blocks from the docs into your own output** unless the user needs to review/approve them — implement directly in the target file instead.
3. **Don't regenerate `shared/models.py`, `shared/ner_examples.py`, or the canonical dictionaries from memory.** They are single sources of truth (Implementation §5, §18) — read them, import them, extend them. Re-deriving them inline risks silent drift between what the docs specify and what the code does.
4. **Batch related Catalyst/Memgraph reads** rather than issuing one query per fact when several are needed for the same task — this isn't just a token concern, it's the same `asyncio.gather` parallelism principle the retrieval layer itself uses (Architecture §9) for the same reason: serialized round-trips are the expensive part, not computation.
5. **Don't dump the full synthetic dataset (4,000 FIRs) or full eval sets into context** to "check" something — query/filter with a script and report the result, the same way the pipeline itself is forbidden from letting the LLM touch raw DB output (Architecture §2: "LLM never directly queries raw data" applies to you too, not just to Qwen 14B).
6. **Reference, don't restate, the open-items list** ("To Discuss / Remaining" in both docs) when relevant — link the item, don't reproduce the whole multi-paragraph history of how it was resolved unless the user is actively working that item.

---

## 3. Self-anneal — and bank Catalyst-specific lessons especially hard

General loop:
1. Read error message and stack trace.
2. Fix the script and test it again (unless it burns paid Catalyst credits/tokens — check with the user first, since credits are hackathon-finite and a 10-minute rate-limit stall, Architecture §11, makes blind retries expensive in wall-clock time too).
3. Update the directive with what you learned.
4. Test again, confirm the fix holds.
5. Update directive to include the new flow. System is now stronger.

**This project has already paid for several non-obvious Catalyst lessons — don't silently relearn them, and don't let new code reintroduce them:**
- Circuits are unavailable in this data center and 30s-capped even where available — never propose a Circuit for anything in `pipeline_function/`.
- Custom Event Listeners are deprecated/EOL (30 April 2026) — never propose one even if a Catalyst doc page still references it; verify against current docs.
- Dev vs. prod Signals Custom Publisher URLs differ for the *same* publisher — swapping environments requires swapping the URL, not just the host.
- Pipeline Function memory defaults to 256MB; the estimated footprint (~250MB) leaves ~6MB headroom — always confirm it's explicitly set to 512MB before treating a memory-pressure bug as a logic bug.
- Qwen/Zia rate-limit consequence is a ~10-minute stall, not a quick reset — never design or accept a retry loop that tries to "wait it out"; fail over to degraded/cached response instead (Architecture §11, Implementation §8).
- Data Store dev tier caps at 5,000 records/table, 25,000/project — the `cases` table sits at exactly 4,000 with 1,000 rows headroom; any ingestion or retry logic that double-inserts could still fail if it passes the cap, but we have some buffer.

When you discover a *new* lesson of this shape (a platform limit, an undocumented payload shape, a timing surprise), treat it with the same weight: fix the script, then update the directive **and** flag it for addition to the docs' "To Discuss / Remaining" section rather than letting it live only in your own scratch notes.

---

## 4. Directives — living documents, but not yours to overwrite

- Don't create or overwrite a directive without asking, unless explicitly told to.
- Directives should encode the *current confirmed design* (matching the docs), not a speculative alternative — if you think the design itself should change (e.g. a different timeout budget, a different confidence weight), raise it as a question against the relevant doc section, don't just change the directive unilaterally.
- Every directive that touches a live-pipeline component (`pipeline_function/`) should explicitly state which timeout/resilience budget it inherits (per-source retrieval timeouts, the 15-minute Function budget, the 3-call-per-query LLM budget) so changes to one don't silently violate another.

---

## 5. File Organization (PS-1 specific)

```
ps1-cis/
├── shared/            # single source of truth: models, NER examples, Catalyst client wrapper
├── backend/           # AppSail — thin front door, NEVER calls LLM/Memgraph/KB/ZTSQL directly
├── pipeline_function/ # Catalyst Function — the actual pipeline (LangGraph, retrieval, synthesis)
├── ingestion/         # offline batch — schema mapping, OCR, dedup, writers
├── frontend/          # React on Catalyst Slate
├── data/              # raw dumps, generation/eval scripts, seed FIRs
├── infra/catalyst/    # app-config
└── docs/              # PS1_Architecture.md, PS1_Implementation.md, demo-preflight.md
```

- **Deliverables**: code in the structure above, the seed dataset (`data/seed/`), demo artifacts, docs updates. These are committed.
- **Intermediates**: anything in `.tmp/` — scraped/staged data, partial ingestion output, ad-hoc debug dumps. Never commit, always regenerated. If you produce a large one-off file while debugging, it belongs in `.tmp/`, not in `data/` or the repo root.
- **`.env` files** (`backend/.env`, `pipeline_function/.env`, frontend `.env`) hold different credential sets per Architecture §16/Implementation §4 — don't consolidate them into one file, and don't give `backend/` credentials it shouldn't have (it has no LLM/VLM/KB/SQL endpoints by design).

---

## 6. Operating principles specific to this system's correctness bar

This is a crime-intelligence tool whose outputs get read by field officers. Two architectural rules exist specifically to prevent confident-sounding wrongness, and they apply to *your* work on the codebase too, not just to the deployed system's prompts:

1. **Never invent connections not in evidence, and never state a graph/RAG/SQL result as fact without tracing it to source.** When you report on what the system found (test results, eval scores, query output), cite the script/query that produced it the same way Synthesis is required to cite FIR ID / graph path / algorithm name (Architecture §11). "It works" without a runnable check is not acceptable for this codebase.
2. **Respect the confidence-tier language rules (Architecture §11) when describing your own findings to the user**: don't present a HIGH-confidence claim and a UNVERIFIED guess in the same tone. If you're inferring something from limited evidence (e.g. "this probably matches the v8 doc"), say so explicitly rather than stating it flatly.
3. **Run the existing verification scripts, don't reinvent them.** Before declaring NER, ingestion, or confidence-engine changes correct, run `data/scripts/eval_ner.py`, `verify_stories.py`, `verify_trap_scenario.py`, or `measure_confidence_calibration.py` as appropriate (Architecture §27/Implementation §19) — these exist precisely so correctness isn't re-litigated from scratch by eye each time.

---

## Summary

You sit between human intent (directives, and these two design docs) and deterministic execution (Python scripts across `shared/`, `backend/`, `pipeline_function/`, `ingestion/`, `data/scripts/`). Read instructions, make decisions, call tools, handle errors, continuously improve the system — and apply the same LLM-plans/systems-retrieve discipline to your own workflow that PS-1 applies to its users' queries.

Be pragmatic. Be reliable. Self-anneal. Don't relearn a Catalyst lesson this project already paid for.
