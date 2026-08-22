# PS-1 Intent Firewall Proposal
**Objective**: Introduce safe conversational capabilities to PS-1 without risking LLM hallucinations, jailbreaks, or degradation of strict evidence-based GraphRAG synthesis.

## Current Problem
Right now, the NER module (`shared/ner_prompt.py`) is rigidly constrained to analytical lookup intents. If an officer types a greeting (e.g., "Hello, my name is Jenkins"), the NER engine defaults to `fallback -> lookup -> broad_search`. 
The `langgraph_router.py` pipeline then forces this "lookup" through the DAG planner, executes unfiltered GraphRAG queries against the database (pulling arbitrary FIRs), and instructs the synthesizer to write an analytical report on them. This produces a confusing, low-confidence report when the user simply said "hello".

If we simply add a generic "chat" intent and route it to an open-ended LLM, we open a massive vulnerability:
1. **Hallucination Risk**: The LLM could start giving ungrounded opinions on police work.
2. **Jailbreak Risk**: The LLM could bypass the mandatory verification disclaimers and output unverified claims.

## Proposed Solution: The "Intent Firewall"
We maintain strict control over the LLM by explicitly rejecting open-ended chat, instead categorizing conversational inputs into two highly constrained buckets:

### 1. The "Greeting / Small Talk" Short-Circuit
We update the NER engine to recognize a `greeting` intent for pleasantries, off-topic statements, and small talk.
* **Routing Logic (`langgraph_router.py`)**: If `intent == "greeting"`, the pipeline **short-circuits immediately**. It skips DAG planning, skips retrieval, and skips the synthesis LLM.
* **Response**: It returns a **deterministic, canned response** (e.g., *"Hello Officer. I am the PS-1 Intelligence System. Please provide your search parameters or query to begin."*).
* **Security Benefit**: Zero risk of hallucination or jailbreaking because the LLM is never invoked to generate the reply.

### 2. The "Follow-Up" Strict RAG Context
We update the NER engine to recognize a `follow_up` intent for queries that ask conversational questions about existing context (e.g., *"What do you think about this?"*, *"Summarize that again"*).
* **Routing Logic**: The DAG planner skips broad database retrieval (since no new search parameters are present), but LangGraph passes the existing **session history** and previous evidence directly into the Synthesizer.
* **Synthesis Constraints**: The Synthesizer is kept strictly on its existing `SYNTHESIS_SYSTEM` prompt. It is forced to perform analytical synthesis on the session history and remains legally bound to attach low-confidence warnings and the mandatory verification disclaimer.
* **Security Benefit**: The model is never allowed to "just chat". It treats the follow-up as a strict RAG operation over the previous turn's evidence, maintaining 100% adherence to the rules.

## Implementation Steps
1. **`shared/ner_prompt.py`**: Add `greeting` and `follow_up` to the allowed intent schema.
2. **`pipeline_function/pipeline/langgraph_router.py`**: Add a conditional routing edge after `understanding_query` that routes `greeting` intents to a new `canned_response_node` (returning deterministic text) and bypassing the rest of the graph.
3. **`pipeline_function/pipeline/query_understanding/dag_planner.py`**: Update logic to handle `follow_up`, generating a minimal or empty retrieval plan to avoid arbitrary NoSQL/Cypher searches, relying entirely on the session history for context.
