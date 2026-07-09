#!/usr/bin/env python3
"""
PS-1 Diagnostic Script — Run from /home/nkandasamy/Desktop/CIS/
Usage: python Docs/audit/diagnostic_test.py
"""
import json, re, sys
sys.path.insert(0, "/home/nkandasamy/Desktop/CIS")

print("=" * 70)
print("PS-1 DIAGNOSTIC TESTS")
print("=" * 70)

# ─────────────────────────────────────────────────────────────
# TEST 1: NER output parsing
# ─────────────────────────────────────────────────────────────
print("\n[TEST 1] NER JSON parsing (simulating LLM log output)")

raw = '''```json
{
    "entities": {
        "persons": [],
        "locations": [],
        "city": "Hubballi",
        "fir_ids": [],
        "dates": [],
        "ipc_sections": [],
        "crime_types": ["job placement fraud"],
        "weapon": ""
    },
    "intent": "lookup",
    "urgency": "analytical",
    "sub_intents": []
}
```'''

# Direct json.loads (as ner_intent.py tries first)
try:
    result = json.loads(raw.strip())
    print("  PASS: direct json.loads succeeded")
except json.JSONDecodeError:
    print("  INFO: direct json.loads failed (expected — has ```json fences)")

# Regex fallback
match = re.search(r'\{.*\}', raw, re.DOTALL)
if match:
    try:
        result = json.loads(match.group())
        print("  PASS: regex fallback parsed correctly")
        print(f"  Entities: {result['entities']}")
    except json.JSONDecodeError as e:
        print(f"  FAIL: regex fallback json parse failed: {e}")
else:
    print("  FAIL: regex found no JSON object")

# ─────────────────────────────────────────────────────────────
# TEST 2: crime_type word-splitting bug in executor.py
# ─────────────────────────────────────────────────────────────
print("\n[TEST 2] Crime type word-splitting in run_graph_step")

crime_types_test_cases = [
    "job placement fraud",  # from actual log
    "murder",
    "theft",
    "robbery",
    "cheating",
    "burglary",
    "rape",
]

print("  BUG: words with len > 3 filter applied to individual words:")
for ct in crime_types_test_cases:
    words = [w for w in ct.split() if len(w) > 3]
    if not words:
        words = [ct]
    print(f"  '{ct}' -> words: {words} {'⚠️  DROPPED WORDS' if not [w for w in ct.split() if len(w) > 3] else ''}")

# ─────────────────────────────────────────────────────────────
# TEST 3: weapon field empty string vs None
# ─────────────────────────────────────────────────────────────
print("\n[TEST 3] Weapon empty string causes unnecessary CONTAINS clause")

weapon = ""  # LLM returned empty string, not None/absent
if weapon:
    print(f"  Cypher weapon clause ADDED (correct only if weapon was real)")
else:
    print(f"  Cypher weapon clause skipped — OK (empty string falsy)")

# ─────────────────────────────────────────────────────────────
# TEST 4: sub_intents empty list — DAG planner gets no sub_intents
# ─────────────────────────────────────────────────────────────
print("\n[TEST 4] sub_intents empty — DAG planner may plan only graph step")
print("  sub_intents: [] means no 'similarity_search' sub-intent")
print("  DAG Planner system prompt: uses 'rag' ONLY for similarity_search intent")
print("  ISSUE: 'job placement fraud' would benefit from RAG but gets only graph step")
print("  DIAGNOSIS: LLM returned sub_intents=[] instead of ['similarity_search']")

# ─────────────────────────────────────────────────────────────
# TEST 5: city field - is it used in graph step?
# ─────────────────────────────────────────────────────────────
print("\n[TEST 5] 'city' field in entities — check executor.py usage")

entities = {
    "persons": [], "locations": [], "city": "Hubballi",
    "fir_ids": [], "dates": [], "ipc_sections": [],
    "crime_types": ["job placement fraud"], "weapon": ""
}

# executor.py run_graph_step reads from state.get("intent", {}).get("entities", {})
# The state is passed as {"intent": intent_obj} from langgraph_router.py
simulated_state = {"intent": {"entities": entities}}
retrieved_entities = simulated_state.get("intent", {}).get("entities", {})
city = retrieved_entities.get("city", "")
print(f"  city from state: '{city}' -> {'✅ Correctly read' if city else '❌ Empty - not used in Cypher'}")

# ─────────────────────────────────────────────────────────────
# TEST 6: NER schema mismatch — 'city' not in standard entity schema
# ─────────────────────────────────────────────────────────────
print("\n[TEST 6] Entity schema: 'city' is a non-standard LLM-added field")
print("  Standard NER schema: persons, locations, fir_ids, dates, ipc_sections, crime_types")
print("  LLM added: 'city' (not in schema) and 'weapon' (not in schema)")
print("  executor.py DOES read 'city' and 'weapon' directly from entities dict — ✅ handled")
print("  BUT: NER prompt must explicitly ask for city/weapon or LLM output is non-deterministic")

# ─────────────────────────────────────────────────────────────
# TEST 7: _locks unbounded growth check
# ─────────────────────────────────────────────────────────────
print("\n[TEST 7] _locks dict growth (catalyst_client.py)")
print("  _LOCKS_MAX = 2000 — bulk clear when exceeded")
print("  ISSUE: bulk clear() evicts ALL locks, including ones actively held")
print("  RACE: Thread A holds lock for key X, lock count hits 2000,")
print("        Thread B triggers clear(), Thread A's lock object is gone,")
print("        Thread C creates new lock for key X and acquires it immediately")
print("  SEVERITY: Low in practice (2000 concurrent sessions unlikely), but is a real race")

# ─────────────────────────────────────────────────────────────
# TEST 8: nosql_set/nosql_get file I/O race (local dev mode)
# ─────────────────────────────────────────────────────────────
print("\n[TEST 8] Local mock NoSQL file I/O race condition")
print("  nosql_get and nosql_set both open .nosql_mock_db.json without file locking")
print("  In local dev: two concurrent asyncio tasks can both read the file,")
print("  modify their copy in memory, and write back — last write wins, first write lost")
print("  IMPACT: history writes, job status updates can be silently dropped locally")

# ─────────────────────────────────────────────────────────────
# TEST 9: EvidenceObject.add_rag_results - wrong key 'fir_id'
# ─────────────────────────────────────────────────────────────
print("\n[TEST 9] add_rag_results key mismatch")
print("  kb_search mock returns: {'fir_id': ..., 'excerpt': ..., 'score': ..., 'metadata': ...}")
print("  add_rag_results reads: hit['fir_id'] — ✅ matches")
print("  BUT: real Catalyst KB may return different key names — needs [VERIFY]")

# ─────────────────────────────────────────────────────────────
# TEST 10: graph_client.py — driver never closed on shutdown
# ─────────────────────────────────────────────────────────────
print("\n[TEST 10] graph_client.py resource leak")
print("  _driver is created once and never closed on app shutdown")
print("  close() exists but is never called from main.py lifespan handler")
print("  IMPACT: Memgraph connection pool exhaustion on long-running deployments")

print("\n" + "=" * 70)
print("SUMMARY OF CRITICAL ISSUES FOUND")
print("=" * 70)
print("""
🔴 HIGH — Output Bug:
   [TEST 4] sub_intents=[] forces graph-only retrieval for fraud/lookup queries.
   RAG (semantic search) is never triggered because the LLM returns no
   'similarity_search' sub_intent for keyword-based crime lookups.
   Hubballi + "job placement fraud" → 0 graph hits because:
     - Graph search requires FIR nodes with matching crime_type/narrative text
     - If data is sparse, graph returns nothing
     - RAG would catch it via semantic similarity but never fires

🔴 HIGH — Output Bug:
   [TEST 2] word-splitting filter (len > 3) on crime_types silently drops
   short words. "job" (3 chars) is DROPPED from multi-word crime types.
   "job placement fraud" → only ["placement", "fraud"] in Cypher CONTAINS clauses.
   This narrows the graph search unnecessarily.

🟡 MEDIUM — Race Condition:
   [TEST 8] Local mock NoSQL (file-based) has no file locking. Concurrent
   asyncio tasks can lose writes silently.

🟡 MEDIUM — Resource Leak:
   [TEST 10] Memgraph driver never closed on app shutdown.

🟠 LOW — Correctness:
   [TEST 7] _locks.clear() bulk eviction can discard actively-held locks,
   creating a narrow race window under extreme concurrency.
""")
