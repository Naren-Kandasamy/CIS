# PS-1: Extended Investigative Capabilities
## Roadmap Items 2–8 — CDR/Financial Trail, Proactive Matching, Contradicted Confidence, Vehicle/ANPR, RBAC, Hypothesis Workspace, Interstate Handoff

**Status:** Combined addendum to Architecture v8 / Implementation v8, covering the remaining items from the senior-investigator review roadmap (Item 1 — Negative Evidence & Exclusion Tracking — is a separate, already-completed doc: `PS1_Negative_Evidence_Exclusion_Tracking.md`, and everything below assumes it exists)
**Written for:** direct hand-off to Antigravity. Each item follows the same structure: current state, target state, architecture, implementation, testing, migration.

---

## 0. How to Read This Doc

This is seven features in one document, not one feature described seven ways. They vary a lot in size — RBAC is a cross-cutting filter, the Hypothesis Workspace is a genuinely new UI surface, Absconder Flagging is a small derived-field check. Read the section for the item you're building; don't assume uniform effort across all seven.

Two pieces of shared infrastructure are introduced once in Section 1 and reused by multiple items afterward — read Section 1 first regardless of which item you're implementing, since Items 2, 3, 4, 5, and 8 all depend on it.

Dependency order matters and is not arbitrary:
- Item 3 (proactive cold-case matching) depends on Item 1 (exclusion tracking) already existing, so proactively-flagged matches can be suppressed if already ruled out.
- Item 4 (contradicted confidence) depends on Item 1's exclusion/contradiction records as its trigger.
- Item 8 (absconder flagging) is independent and can be built any time.
- Items 2, 5, 6, 7 are largely independent of each other but Item 2 establishes the "pluggable data source" pattern that Item 5 reuses directly.

---

## 1. Cross-Cutting Infrastructure (Build Once, Use Throughout)

### 1.1 The Pluggable Data Source Provider Pattern

This exists because of a real constraint surfaced in discussion: **real CDR (Call Detail Records) and real financial/UPI transaction data are not just hard to find — they are legally restricted.** Real CDR access requires a lawful interception/production request through telecom operators under Indian telecom law. Real bank/UPI transaction data requires a CrPC Section 91-style production order or an FIU-IND channel. There is no legitimate "authentic dataset" a hackathon team should be sourcing here — anything offered outside that legal process is a red flag, not a resource.

The correct response isn't to fake having real data or to skip the capability — it's to build the **data source as a swappable interface**, with a synthetic provider today and a clear seam for a real, legally-integrated provider later. This is architecturally honest and should be presented to judges exactly this way: *"this is a synthetic data source today by design — the graph schema and reasoning logic don't change when a real lawful-access integration replaces it, only the provider does."*

```python
# shared/data_sources/base.py

from abc import ABC, abstractmethod
from datetime import datetime

class CDRProvider(ABC):
    @abstractmethod
    async def fetch_call_records(self, phone_number: str,
                                  start: datetime, end: datetime) -> list[dict]:
        """Returns [{caller, callee, timestamp, duration_sec, tower_id}, ...]"""

class FinancialProvider(ABC):
    @abstractmethod
    async def fetch_transactions(self, account_id: str,
                                  start: datetime, end: datetime) -> list[dict]:
        """Returns [{from_account, to_account, amount, timestamp, channel}, ...]"""

class ANPRProvider(ABC):
    @abstractmethod
    async def fetch_plate_reads(self, plate_number: str,
                                 start: datetime, end: datetime) -> list[dict]:
        """Returns [{plate_number, camera_id, lat, lon, timestamp}, ...]"""
```

**Every record from every provider must carry explicit provenance** — this is non-negotiable, not a style preference. Downstream code, and any officer viewing this evidence, must always be able to tell synthetic demo data apart from anything real:

```python
# Every record written to the graph or data store from ANY provider includes:
{
    "source_provenance": "synthetic_demo" | "verified_legal_process",
    # never omit this field, never default it silently
}
```

Provider selection is a config switch, never a code branch scattered through business logic:

```python
# shared/data_sources/config.py
import os

DATA_SOURCE_MODE = os.getenv("DATA_SOURCE_MODE", "synthetic")  # "synthetic" | "production"

def get_cdr_provider() -> "CDRProvider":
    if DATA_SOURCE_MODE == "synthetic":
        from shared.data_sources.synthetic_cdr import SyntheticCDRProvider
        return SyntheticCDRProvider()
    raise NotImplementedError(
        "Production CDR provider requires a real lawful-access integration -- "
        "not something to stub in. Wire in the actual telecom-operator integration here."
    )
```

### 1.2 `ReviewQueueItem` — Shared Proactive-Alert Primitive

Several items below (3, 4, 5, 8) need to push something to an officer *without being asked* — that's the "proactive, not just reactive" gap identified in the senior-investigator review. Rather than each item inventing its own notification shape, there's one shared primitive:

```python
# shared/review_queue_models.py

from pydantic import BaseModel
from typing import Optional

class ReviewQueueItem(BaseModel):
    item_id: str
    item_type: str            # "cold_case_match" | "contradiction_alert" |
                               # "anpr_wanted_hit" | "interstate_handoff"
    fir_id: str
    related_fir_id: Optional[str] = None    # e.g. the matched cold case
    accused_id: Optional[str] = None
    summary: str                            # short, human-readable, deterministic
                                             # string built from data -- NOT an
                                             # LLM-generated summary (see note below)
    score: Optional[float] = None           # match/confidence score, if applicable
    created_date: str
    status: str = "pending"                 # "pending" | "reviewed" | "dismissed"
    reviewed_by: Optional[str] = None
    reviewed_date: Optional[str] = None
```

**Why `summary` is built from a template, not an LLM call:** these are alerts that fire automatically, in bulk, at ingestion time, with no officer in the loop yet to sanity-check phrasing. An LLM-generated summary here would be an uncontrolled text generation running unsupervised at ingestion scale — a bad place for it. A deterministic template (`f"New FIR {fir.crime_no} shares MO similarity ({score:.0%}) with unsolved case {matched_fir.crime_no}"`) is fully sufficient and fully predictable.

```python
# shared/review_queue_engine.py

from shared.catalyst_client import nosql_set, nosql_query_by_prefix

async def push_review_item(item: "ReviewQueueItem"):
    await nosql_set(f"review_queue:{item.item_id}", item.json())

async def get_pending_review_items(fir_id: str | None = None) -> list["ReviewQueueItem"]:
    items = await nosql_query_by_prefix("review_queue:")
    parsed = [ReviewQueueItem(**i) for i in items]
    parsed = [i for i in parsed if i.status == "pending"]
    if fir_id:
        parsed = [i for i in parsed if i.fir_id == fir_id or i.related_fir_id == fir_id]
    return parsed
```

`[VERIFY]` `nosql_query_by_prefix` — confirm this or an equivalent listing function actually exists against your current `catalyst_client.py`; if not, it needs to be added since several items here rely on listing queue items, not just point lookups.

**New API surface, shared across items:**

```python
# backend/api/routes/review_queue.py

from fastapi import APIRouter
from shared.review_queue_engine import get_pending_review_items, push_review_item

router = APIRouter()

@router.get("/api/review-queue")
async def list_review_queue(fir_id: str | None = None):
    return await get_pending_review_items(fir_id)

@router.post("/api/review-queue/{item_id}/resolve")
async def resolve_review_item(item_id: str, payload: dict):
    # payload: {"status": "reviewed" | "dismissed", "reviewed_by": str}
    ...  # load, update status/reviewed_by/reviewed_date, save
```

This is the officer-facing "Flagged for Review" dashboard's backing API. The frontend piece (a dashboard list, separate from the chat/query interface) is a prerequisite UI surface for Items 3, 4, 5, and 8 — build it once, feed it from all four.

---

## 2. Item 2 — CDR & Financial Trail Integration

### 2.1 Current State vs. Target State

| Aspect | Current | Target |
|---|---|---|
| Call/communication data | No node types, no ingestion path | New `CALLED` edges between `Phone` nodes (already exists as a node type in your Cypher constraints), sourced via `CDRProvider` |
| Financial data | Doesn't exist at all | New `Account`/`Transaction` model, `TRANSFERRED` edges, sourced via `FinancialProvider` |
| Data source | N/A | Synthetic providers today, pluggable per Section 1.1, with deliberately injected investigative patterns (burner numbers, mule chains) for demo purposes |
| Confidence Engine awareness | N/A | New edge types (`CALL_PROXIMITY`, `FINANCIAL_LAYERING`) feed into the existing methodology trust-weighting mechanism from the Reasoning Feedback Loop — no new confidence logic needed, just new edge types plugged into what already exists |

### 2.2 Architecture

```cypher
// New node/edge additions
(:Phone {number: string})-[:CALLED {
    timestamp: string, duration_sec: int, tower_id: string,
    source_provenance: string
}]->(:Phone)

(:Account {account_id: string, holder_name: string, account_type: string})
(:Account)-[:TRANSFERRED {
    amount: float, timestamp: string, channel: string,  // "UPI" | "NEFT" | "cash_deposit"
    source_provenance: string
}]->(:Account)
```

**New derived edge types feeding the existing Confidence Engine / retrieval ranking** (reusing the trust-weighting mechanism already built in the Reasoning Feedback Loop — no new scoring logic needed):
- `CALL_PROXIMITY` — two accused/persons-of-interest had first-ever contact within a short window before/after an incident
- `FINANCIAL_LAYERING` — rapid transfer chains, especially structured just under a reporting threshold

### 2.3 Implementation

**Synthetic providers, with deliberately injected patterns (not random noise):**

```python
# shared/data_sources/synthetic_cdr.py

import random
from datetime import datetime, timedelta
from shared.data_sources.base import CDRProvider

class SyntheticCDRProvider(CDRProvider):
    """
    Deterministic, seeded generator. Deliberately injects investigatively
    interesting patterns (e.g. a 'burner' number active only in a tight
    window around an incident, then dead) rather than pure random noise --
    the point is to let the graph algorithms prove they catch real patterns,
    not to simulate volume for its own sake.
    """
    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)

    async def fetch_call_records(self, phone_number: str,
                                  start: datetime, end: datetime) -> list[dict]:
        records = []
        n_calls = self.rng.randint(5, 40)
        for _ in range(n_calls):
            ts = start + timedelta(seconds=self.rng.randint(0, int((end - start).total_seconds())))
            records.append({
                "caller": phone_number,
                "callee": f"+91{self.rng.randint(7000000000, 9999999999)}",
                "timestamp": ts.isoformat(),
                "duration_sec": self.rng.randint(10, 900),
                "tower_id": f"TWR-{self.rng.randint(1, 200)}",
                "source_provenance": "synthetic_demo",
            })
        return records

    async def inject_burner_pattern(self, incident_datetime: datetime,
                                     accused_phone: str, contact_phone: str) -> list[dict]:
        """
        Explicit pattern injection for demo purposes: a number that is
        active ONLY in a narrow window around the incident and never
        seen before or after -- the classic 'burner phone' signature.
        """
        window_start = incident_datetime - timedelta(days=2)
        window_end = incident_datetime + timedelta(hours=6)
        return [{
            "caller": accused_phone, "callee": contact_phone,
            "timestamp": (window_start + timedelta(hours=i * 3)).isoformat(),
            "duration_sec": self.rng.randint(30, 300),
            "tower_id": f"TWR-{self.rng.randint(1, 20)}",  # tight tower cluster near incident
            "source_provenance": "synthetic_demo",
        } for i in range(self.rng.randint(3, 8))]
```

```python
# shared/data_sources/synthetic_financial.py

import random
from datetime import datetime, timedelta
from shared.data_sources.base import FinancialProvider

class SyntheticFinancialProvider(FinancialProvider):
    """
    Transaction categories modeled on PaySim's well-established mobile-money
    pattern taxonomy (CASH_IN, CASH_OUT, TRANSFER, PAYMENT) -- PaySim exists
    specifically because real transaction data can't be freely shared, and
    its underlying behavioral patterns (structuring, layering, mule chains)
    are the same ones real financial-crime investigation looks for,
    UPI or otherwise. This provider generates NEW synthetic data using
    that same pattern taxonomy -- it does not reuse PaySim's actual rows.
    """
    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)

    async def fetch_transactions(self, account_id: str,
                                  start: datetime, end: datetime) -> list[dict]:
        records = []
        n_txns = self.rng.randint(5, 30)
        for _ in range(n_txns):
            ts = start + timedelta(seconds=self.rng.randint(0, int((end - start).total_seconds())))
            records.append({
                "from_account": account_id,
                "to_account": f"ACC{self.rng.randint(100000, 999999)}",
                "amount": round(self.rng.uniform(500, 45000), 2),
                "timestamp": ts.isoformat(),
                "channel": self.rng.choice(["UPI", "NEFT", "cash_deposit"]),
                "source_provenance": "synthetic_demo",
            })
        return records

    async def inject_layering_pattern(self, source_account: str,
                                       total_amount: float, n_hops: int = 4) -> list[dict]:
        """
        Explicit structuring/layering injection: splits a larger amount
        into several transfers just under a notional reporting threshold
        (e.g. INR 50,000), moved through a short chain of accounts in
        rapid succession -- a well-known money-laundering signature.
        """
        THRESHOLD = 49000
        per_hop = min(total_amount / n_hops, THRESHOLD)
        records, current = [], source_account
        base_time = datetime.utcnow()
        for i in range(n_hops):
            next_account = f"ACC{self.rng.randint(100000, 999999)}"
            records.append({
                "from_account": current, "to_account": next_account,
                "amount": round(per_hop, 2),
                "timestamp": (base_time + timedelta(minutes=i * 15)).isoformat(),
                "channel": "UPI",
                "source_provenance": "synthetic_demo",
            })
            current = next_account
        return records
```

**Ingestion hook:**

```python
# ingestion/cdr_financial_ingest.py

from shared.data_sources.config import get_cdr_provider, get_financial_provider
from shared.catalyst_client import memgraph_write

async def ingest_call_records(phone_number: str, start, end):
    provider = get_cdr_provider()
    records = await provider.fetch_call_records(phone_number, start, end)
    for r in records:
        await memgraph_write("""
            MERGE (a:Phone {number: $caller})
            MERGE (b:Phone {number: $callee})
            MERGE (a)-[c:CALLED {timestamp: $timestamp}]->(b)
            SET c.duration_sec = $duration_sec, c.tower_id = $tower_id,
                c.source_provenance = $source_provenance
        """, r)
```

`[VERIFY]` Confirm `Phone` and `Vehicle` node labels/constraints match your actual current Cypher schema names exactly before merging against them.

### 2.4 Testing / Migration

- [ ] Injected burner-pattern calls are detectable via a Cypher query for "phone pairs with calls only within a tight window before an incident, no history before/after"
- [ ] Injected layering-pattern transfers are detectable via a query for "rapid transfer chains with per-hop amounts near but under a threshold"
- [ ] Every record in the graph carries `source_provenance` — no record is missing this field
- [ ] `DATA_SOURCE_MODE=production` raises `NotImplementedError` cleanly rather than silently falling back to synthetic data

1. Build `shared/data_sources/base.py`, `config.py`
2. Build `synthetic_cdr.py`, `synthetic_financial.py`
3. Build `ingestion/cdr_financial_ingest.py`
4. Add `Phone`/`Account` Cypher constraints if not already present
5. Confirm new edge types (`CALLED`, `TRANSFERRED`, derived `CALL_PROXIMITY`/`FINANCIAL_LAYERING`) are recognized by the existing trust-weighting code from the Reasoning Feedback Loop (they're just new `edge_type` string values — no code change needed there if that code is generic over edge type, which it should already be)

---

## 3. Item 3 — Proactive Cold-Case Matching

### 3.1 Current State vs. Target State

| Aspect | Current | Target |
|---|---|---|
| SHARED_MO computation | Runs incrementally at ingestion, but only used reactively (query time) | Same computation, additionally scanned for matches against **unsolved/cold** cases specifically, pushed to `ReviewQueueItem` proactively |
| Exclusion awareness | N/A | Proactive matches suppressed if an active exclusion already rules out that accused/case pair (reuses Item 1 directly) |

### 3.2 Architecture

```
Layer 8 -- Ingestion (extends the EXISTING incremental SHARED_MO step)
    ├─ (existing) compute SHARED_MO/CO_ACCUSED/etc for the new FIR
    │   against the full population
    └─ (NEW) filter those matches to ones where the matched FIR's
             status is "open"/"cold" AND score >= threshold
             AND no active exclusion exists for that accused/matched-FIR pair
             → push a ReviewQueueItem (item_type = "cold_case_match")
```

### 3.3 Implementation

```python
# ingestion/cold_case_matcher.py

import uuid
from datetime import datetime
from shared.exclusion_engine import get_active_exclusions
from shared.review_queue_models import ReviewQueueItem
from shared.review_queue_engine import push_review_item

COLD_CASE_MATCH_THRESHOLD = 0.75   # reuse whatever similarity scale SHARED_MO already uses
COLD_STATUS_VALUES = {"open", "cold"}

async def run_cold_case_match(new_fir, shared_mo_matches: list[dict]):
    """
    Called right after the existing incremental SHARED_MO computation
    for a newly ingested FIR (Implementation v8's create_shared_mo_edge
    step). `shared_mo_matches` is whatever that existing step already
    computed -- this function does NOT recompute matching, it filters
    and routes the existing output.
    """
    for match in shared_mo_matches:
        if match["matched_fir_status"] not in COLD_STATUS_VALUES:
            continue
        if match["score"] < COLD_CASE_MATCH_THRESHOLD:
            continue

        exclusions = await get_active_exclusions(match["matched_fir_id"])
        if match.get("accused_id") in exclusions:
            continue  # already ruled out for that case -- don't proactively re-surface it

        item = ReviewQueueItem(
            item_id=str(uuid.uuid4()),
            item_type="cold_case_match",
            fir_id=new_fir.id,
            related_fir_id=match["matched_fir_id"],
            accused_id=match.get("accused_id"),
            summary=(f"New FIR {new_fir.crime_no} shares MO similarity "
                     f"({match['score']:.0%}) with unsolved case "
                     f"{match['matched_fir_crime_no']}"),
            score=match["score"],
            created_date=datetime.utcnow().isoformat(),
        )
        await push_review_item(item)
```

`[VERIFY]` The exact shape of the existing `create_shared_mo_edge` output — this assumes it's accessible as a list of match dicts with `matched_fir_id`, `matched_fir_status`, `score`, `accused_id`, `matched_fir_crime_no` keys; adjust field names to whatever the real function actually returns.

### 3.4 Testing / Migration

- [ ] A new FIR matching an existing **open/cold** case above threshold generates a `ReviewQueueItem`
- [ ] A new FIR matching an existing **closed** case does not generate one
- [ ] A match against a case where the accused already has an active exclusion does not generate one
- [ ] Dashboard correctly lists pending cold-case-match items, dismissible/reviewable via the shared review-queue API

1. Build `ingestion/cold_case_matcher.py`
2. Hook it into the existing ingestion flow, immediately after the existing SHARED_MO step
3. Confirm FIR status field includes a genuine "cold"/"open" distinction (vs. just "open"/"closed") — `[VERIFY]` against actual `FIRSchema.status` usage; may need a new status value

---

## 4. Item 4 — Confidence Engine "Contradicted" State

### 4.1 Current State vs. Target State

| Aspect | Current | Target |
|---|---|---|
| Confidence tiers | HIGH / MEDIUM / LOW | Adds a fourth state: **CONTRADICTED** |
| Reaction to new exclusions | None — a past HIGH-confidence answer stays looking valid forever, even after the accused it named is later ruled out | Creating an exclusion (Item 1) or a contradiction record retroactively checks past synthesized claims referencing that accused/evidence, flips them to CONTRADICTED, and raises a `ReviewQueueItem` alert |

This is distinct from the Reasoning Feedback Loop's gradual trust erosion — that mechanism handles *slow, statistical* unreliability of a reasoning type. This handles a *single, hard, factual* contradiction of a *specific past claim*.

### 4.2 Architecture

```
Layer 5 -- Synthesis (existing)
    Every HIGH/MEDIUM confidence claim synthesis produces is now
    ALSO written as a ClaimRecord -- a lightweight append, not a
    change to synthesis logic itself.

Item 1's create_exclusion() / contradiction-marking  (existing, extended)
    After writing the exclusion/contradiction, checks ClaimRecords
    for that accused_id/evidence_ref + fir_id, flips matching ones
    to CONTRADICTED, and pushes a ReviewQueueItem alert.
```

### 4.3 Implementation

```python
# shared/claim_models.py

from pydantic import BaseModel
from typing import Optional

class ClaimRecord(BaseModel):
    claim_id: str
    fir_id: str
    accused_id: Optional[str] = None
    evidence_ref: Optional[str] = None
    confidence_tier: str          # "HIGH" | "MEDIUM" | "LOW"
    synthesized_snippet: str      # short excerpt of what was claimed, for the alert
    timestamp: str
    contradicted: bool = False
    contradicted_date: Optional[str] = None
```

```python
# Extension to Layer 5 synthesis -- write a ClaimRecord alongside every
# HIGH/MEDIUM confidence output. Cheap append, no change to the
# synthesis logic itself.

async def log_claim(fir_id, accused_id, evidence_ref, confidence_tier, snippet):
    if confidence_tier not in {"HIGH", "MEDIUM"}:
        return  # LOW-confidence claims aren't worth tracking for contradiction alerts
    record = ClaimRecord(
        claim_id=str(uuid.uuid4()), fir_id=fir_id, accused_id=accused_id,
        evidence_ref=evidence_ref, confidence_tier=confidence_tier,
        synthesized_snippet=snippet, timestamp=datetime.utcnow().isoformat(),
    )
    await nosql_set(f"claim:{record.claim_id}", record.json())
```

```python
# Extension to shared/exclusion_engine.py -- called from create_exclusion()
# and from contradiction-marking, right after the exclusion/contradiction
# record itself is written.

async def check_and_flag_contradicted_claims(fir_id: str, accused_id: str | None,
                                              reason: str):
    claims = await nosql_query_by_prefix("claim:")
    for raw in claims:
        claim = ClaimRecord(**raw)
        if claim.fir_id != fir_id or claim.contradicted:
            continue
        if accused_id and claim.accused_id != accused_id:
            continue

        claim.contradicted = True
        claim.contradicted_date = datetime.utcnow().isoformat()
        await nosql_set(f"claim:{claim.claim_id}", claim.json())

        await push_review_item(ReviewQueueItem(
            item_id=str(uuid.uuid4()), item_type="contradiction_alert",
            fir_id=fir_id, accused_id=accused_id,
            summary=(f"Earlier analysis rated a connection as {claim.confidence_tier} "
                     f"confidence (\"{claim.synthesized_snippet}\"); this has since "
                     f"been contradicted: {reason}. Recommend reviewing any decisions "
                     f"made based on that assessment."),
            created_date=datetime.utcnow().isoformat(),
        ))
```

**Why the alert text is template-built from stored fields, not LLM-generated:** same reasoning as Section 1.2 — this fires automatically, unsupervised, and needs to be exactly predictable. It quotes the original snippet verbatim rather than trying to "explain" the contradiction in generated prose.

### 4.4 Testing / Migration

- [ ] A HIGH-confidence claim referencing an accused, followed later by an exclusion for that same accused/FIR, produces a `contradiction_alert` `ReviewQueueItem`
- [ ] The original `ClaimRecord` is flipped to `contradicted=True` and is retrievable/queryable as such (e.g. for an audit view showing "here's everything that was said before it was contradicted")
- [ ] A LOW-confidence claim does not get logged as a `ClaimRecord` at all (by design, to keep this table from growing unmanageably with low-value entries)

1. Build `shared/claim_models.py`
2. Add `log_claim()` call into Layer 5 synthesis output path — `[VERIFY]` exact current synthesis function location
3. Extend `shared/exclusion_engine.py`'s `create_exclusion()` (and the equivalent contradiction-marking route) to call `check_and_flag_contradicted_claims()`
4. Add a "Contradicted" badge/filter to whatever surfaces past synthesized answers (chat history, audit view)

---

## 5. Item 5 — Vehicle/ANPR Cross-Referencing

### 5.1 Current State vs. Target State

| Aspect | Current | Target |
|---|---|---|
| Vehicle data | `Vehicle` node type exists in schema, used for `SHARED_VEHICLE` matching between FIRs | Adds ANPR plate-read events and a wanted/stolen vehicle registry cross-check |
| Wanted-vehicle matching | Doesn't exist | Deterministic plate-string match against a `WantedVehicleRecord` list, auto-flagged via the shared `ReviewQueueItem` mechanism |

### 5.2 Architecture

Reuses the Section 1.1 provider pattern directly:

```cypher
(:Vehicle {plate_number: string})-[:ANPR_HIT {
    timestamp: string, camera_id: string, lat: float, lon: float,
    source_provenance: string
}]->(:Location)
```

```python
# shared/data_sources/synthetic_anpr.py

import random
from datetime import datetime, timedelta
from shared.data_sources.base import ANPRProvider

class SyntheticANPRProvider(ANPRProvider):
    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)

    async def fetch_plate_reads(self, plate_number: str,
                                 start: datetime, end: datetime) -> list[dict]:
        reads = []
        for _ in range(self.rng.randint(1, 10)):
            ts = start + timedelta(seconds=self.rng.randint(0, int((end - start).total_seconds())))
            reads.append({
                "plate_number": plate_number,
                "camera_id": f"CAM-{self.rng.randint(1, 150)}",
                "lat": 12.9 + self.rng.uniform(-0.3, 0.3),   # Bengaluru-area jitter, adjust per district
                "lon": 77.6 + self.rng.uniform(-0.3, 0.3),
                "timestamp": ts.isoformat(),
                "source_provenance": "synthetic_demo",
            })
        return reads
```

```python
# shared/models.py addition
class WantedVehicleRecord(BaseModel):
    plate_number: str
    reason: str            # "stolen" | "linked_to_open_case"
    fir_id: Optional[str] = None
    flagged_date: str
```

```python
# ingestion/anpr_ingest.py

async def ingest_and_check_anpr(plate_number: str, start, end):
    provider = get_anpr_provider()
    reads = await provider.fetch_plate_reads(plate_number, start, end)
    for r in reads:
        await memgraph_write("""
            MERGE (v:Vehicle {plate_number: $plate_number})
            CREATE (v)-[h:ANPR_HIT {timestamp: $timestamp, camera_id: $camera_id,
                                     lat: $lat, lon: $lon,
                                     source_provenance: $source_provenance}]->(:Location)
        """, r)

    wanted = await get_wanted_vehicle(plate_number)   # simple lookup, deterministic
    if wanted and reads:
        await push_review_item(ReviewQueueItem(
            item_id=str(uuid.uuid4()), item_type="anpr_wanted_hit",
            fir_id=wanted.fir_id or "unknown",
            summary=(f"Wanted vehicle {plate_number} ({wanted.reason}) detected "
                     f"at {reads[-1]['camera_id']} on {reads[-1]['timestamp']}"),
            created_date=datetime.utcnow().isoformat(),
        ))
```

### 5.3 Testing / Migration

- [ ] A plate read matching a `WantedVehicleRecord` produces an `anpr_wanted_hit` review item
- [ ] A plate read with no wanted match produces no alert, but the `ANPR_HIT` edge is still written for later query-time use
- [ ] `SHARED_VEHICLE` (existing) and `ANPR_HIT` (new) are distinct edge types and don't get conflated

1. Build `shared/data_sources/synthetic_anpr.py`
2. Add `WantedVehicleRecord` model + a simple lookup store (NoSQL is fine for hackathon scale)
3. Build `ingestion/anpr_ingest.py`
4. Add `Location` node type if not already present in your Cypher constraints — `[VERIFY]`

---

## 6. Item 6 — RBAC / Jurisdiction Scoping (The 3D Access Matrix)

### 6.1 Current State vs. Target State

| Aspect | Current | Target |
|---|---|---|
| Access control | None — Architecture v8's own gap table already flags this as hardcoded/missing | The **3D Access Matrix**: Officer profile contains Rank, Geography (District/Unit), and Department. Access is not a binary "God Mode vs. Invite Only"; it balances implicit oversight (Pull) with explicit alerts (Push). |

This replaces the naive "rank grants total visibility" model with a realistic law-enforcement structure. Just because two officers work at the same station doesn't mean the Cyber Crimes Inspector oversees a routine traffic collision.

### 6.2 Architecture (Push vs. Pull)

```python
# shared/models.py
class OfficerProfile(BaseModel):
    officer_id: str
    name: str
    rank: str            # "constable" | "inspector" | "dysp" | "sp"
    home_district: str
    unit_id: str
    department: str      # "law_order" | "cyber" | "narcotics" | "financial"
```

**1. The "Pull" (Implicit Oversight)**
A supervisor natively searches and views cases in their `home_district` AND their `department`. These cases do not clutter their active dashboard, but are queryable for audits.
**Compartmentalization:** If a case is flagged as `is_sensitive=True` (e.g. internal affairs), "Pull" access is broken. It becomes strictly invite-only, breaking the implicit hierarchy.

**2. The "Push" (Elevation)**
When an IO needs a supervisor's attention, they click `[ ⬆ Elevate for Review ]`. This drops a `ReviewQueueItem` directly onto the Supervisor's active dashboard. The supervisor only gets alerted when their attention is actively requested.

### 6.3 Implementation

```python
# shared/rbac_engine.py

ELEVATED_RANKS = {"inspector", "dysp", "sp"}

async def get_officer_scope(officer_id: str) -> dict:
    """
    Returns the required District and Department filters for an officer.
    """
    officer = await get_officer_profile(officer_id)  # simple NoSQL lookup
    
    # Even elevated ranks only see their department natively.
    scope = {
        "department": officer.department,
        "district": officer.home_district
    }
    
    # Exceptions like SPs might oversee all departments in a district.
    if officer.rank == "sp":
        scope["department"] = None  # No department filter
        
    return scope


async def apply_jurisdiction_filter(cypher_query: str, params: dict,
                                    officer_id: str,
                                    cross_jurisdiction_reason: str | None = None) -> tuple[str, dict]:
    scope = await get_officer_scope(officer_id)

    if cross_jurisdiction_reason:
        # Explicit override -- logged, not silently allowed
        await log_cross_jurisdiction_access(officer_id, cross_jurisdiction_reason)
        return cypher_query, params

    # Inject district and department filters.
    # [VERIFY] This replace logic is a placeholder. Integrate this properly into the Retrieval query builder.
    filter_clause = "MATCH (f:FIR {district: $officer_district"
    if scope["department"]:
        filter_clause += ", crime_type: $officer_department"
    filter_clause += "})"
    
    filtered_query = cypher_query.replace("MATCH (f:FIR)", filter_clause)
    
    params["officer_district"] = scope["district"]
    if scope["department"]:
        params["officer_department"] = scope["department"]
        
    return filtered_query, params
```

`[VERIFY]` The naive `.replace()` on the Cypher query string above is a placeholder illustrating intent — the real integration point should inject the district/department filters properly into whatever query-builder abstraction the retrieval layer actually uses.

### 6.4 Testing / Migration

- [ ] A constable's query is scoped to only their home district's FIRs within their department.
- [ ] An Inspector (Cyber) cannot implicitly query cases in the Narcotics department, despite their elevated rank.
- [ ] An SP (Superintendent) can query across all departments in their district.
- [ ] A constable using an explicit cross-jurisdiction override with a reason gets unrestricted results for that query, and the override is logged.
- [ ] Sensitive cases (`is_sensitive=True`) are omitted from all implicit queries unless the officer is an explicit collaborator.

1. Build `shared/models.py` addition (`OfficerProfile`).
2. Build `shared/rbac_engine.py`.
3. Wire `apply_jurisdiction_filter` into the actual query-construction code path.
4. Seed a handful of demo `OfficerProfile` records (different ranks/districts/departments) to show this 3D matrix working during the judging demo.

---

## 7. Item 7 — Hypothesis Workspace

### 7.1 Current State vs. Target State

| Aspect | Current | Target |
|---|---|---|
| Investigation model | Every query is independent; no persistent working theory across a session or investigation | Officers can pin a hypothesis ("A and B are connected through C") tied to a case; subsequent queries can check it, logging what was found each time |
| Who decides confirm/refute | N/A | Always the officer, explicitly — the system surfaces what retrieval found, it never marks a hypothesis confirmed or refuted on its own |

### 7.2 Architecture

```python
# shared/hypothesis_models.py

class HypothesisRecord(BaseModel):
    hypothesis_id: str
    fir_id: str
    officer_id: str
    statement: str                    # free text, officer-authored
    linked_entity_ids: list[str]      # accused_ids / fir_ids the hypothesis references
    status: str = "open"              # "open" | "confirmed" | "refuted"
    created_date: str
    resolved_by: Optional[str] = None
    resolved_reason: Optional[str] = None
    resolved_date: Optional[str] = None

class HypothesisCheckLog(BaseModel):
    check_id: str
    hypothesis_id: str
    checked_date: str
    new_supporting_evidence_count: int
    new_contradicting_evidence_count: int   # e.g. new exclusions/contradictions
                                             # touching the linked entities
    notes: str                              # deterministic summary, not LLM-generated
```

**Why "check" is deterministic counting, not an LLM verdict:** a "check" run re-queries retrieval for the hypothesis's linked entities and counts how much new supporting vs. contradicting evidence (including Item 1's exclusion/contradiction records) has appeared since the last check. It reports the count. It never concludes "therefore this hypothesis is confirmed" — that conclusion stays an explicit officer action (`resolve`), consistent with the "LLM plans and synthesizes, never decides investigative facts" boundary held throughout every doc in this series.

### 7.3 Implementation

```python
# shared/hypothesis_engine.py

async def check_hypothesis(hypothesis_id: str) -> HypothesisCheckLog:
    hyp = await get_hypothesis(hypothesis_id)
    last_check = await get_last_check(hypothesis_id)
    since = last_check.checked_date if last_check else hyp.created_date

    supporting = await count_new_evidence_since(hyp.linked_entity_ids, since, kind="supporting")
    contradicting = await count_new_evidence_since(hyp.linked_entity_ids, since, kind="contradicting")

    log = HypothesisCheckLog(
        check_id=str(uuid.uuid4()), hypothesis_id=hypothesis_id,
        checked_date=datetime.utcnow().isoformat(),
        new_supporting_evidence_count=supporting,
        new_contradicting_evidence_count=contradicting,
        notes=f"{supporting} new supporting item(s), {contradicting} new contradicting item(s) since last check.",
    )
    await nosql_set(f"hyp_check:{log.check_id}", log.json())
    return log


async def resolve_hypothesis(hypothesis_id: str, status: str,
                              resolved_by: str, resolved_reason: str):
    if status not in {"confirmed", "refuted"}:
        raise ValueError("status must be 'confirmed' or 'refuted'")
    hyp = await get_hypothesis(hypothesis_id)
    hyp.status = status
    hyp.resolved_by = resolved_by
    hyp.resolved_reason = resolved_reason
    hyp.resolved_date = datetime.utcnow().isoformat()
    await nosql_set(f"hypothesis:{hypothesis_id}", hyp.json())
```

**API routes:**

```python
# backend/api/routes/hypothesis.py
# POST /api/investigation/hypothesis            -- create
# GET  /api/investigation/hypothesis/{fir_id}    -- list open hypotheses for a case
# POST /api/investigation/hypothesis/{id}/check  -- run a check, returns HypothesisCheckLog
# POST /api/investigation/hypothesis/{id}/resolve -- officer marks confirmed/refuted
```

`[VERIFY]` `count_new_evidence_since` needs a concrete definition of "supporting" vs. "contradicting" evidence for a given entity set — the simplest honest version is: supporting = new retrieval matches involving the linked entities since the timestamp; contradicting = new Item-1 exclusion/contradiction records involving those entities since the timestamp. Confirm this framing works before implementing, since it's doing real interpretive work despite being "just counting."

### 7.4 Testing / Migration

- [ ] Creating a hypothesis with linked entities stores correctly
- [ ] Running a check after new supporting evidence appears (e.g. a new `SHARED_MO` edge involving a linked accused) increments the supporting count
- [ ] Running a check after a new exclusion involving a linked accused increments the contradicting count
- [ ] Resolving a hypothesis requires an explicit officer action and reason — no automatic resolution path exists anywhere in the code

1. Build `shared/hypothesis_models.py`, `shared/hypothesis_engine.py`
2. Build `backend/api/routes/hypothesis.py`
3. Frontend: a per-case "hypothesis pinboard" — create, view check history, resolve
4. Confirm `count_new_evidence_since`'s definition with a real pass over Layer 3's retrieval code — `[VERIFY]` per above

---

## 8. Item 8 — Absconder / Interstate Handoff Flagging

### 8.1 Current State vs. Target State

| Aspect | Current | Target |
|---|---|---|
| Cross-jurisdiction awareness | None — `AccusedSchema` has no location-history field to compare against the FIR's district | A deterministic check flags when an accused's last known location crosses a district/state boundary from the originating FIR, or when their status indicates absconding |

### 8.2 Architecture

Requires one schema addition — `AccusedSchema` needs a location-history concept it doesn't currently have:

```python
# Addition to AccusedSchema (shared/models.py)
class AccusedSchema(BaseModel):
    # ... existing fields ...
    last_known_district: Optional[str] = None
    last_known_state: Optional[str] = None
    last_known_date: Optional[str] = None
    absconding_status: bool = False
```

### 8.3 Implementation

```python
# shared/absconder_engine.py

KARNATAKA_DISTRICTS = {...}  # existing district list, reused from wherever
                             # district canonicalization already lives

async def check_interstate_flag(accused, fir) -> ReviewQueueItem | None:
    if not accused.last_known_district and not accused.last_known_state:
        return None

    crosses_district = (accused.last_known_district
                         and accused.last_known_district != fir.district)
    crosses_state = (accused.last_known_state
                     and accused.last_known_state.lower() != "karnataka")

    if not (accused.absconding_status and (crosses_district or crosses_state)):
        return None

    scope = "state" if crosses_state else "district"
    return ReviewQueueItem(
        item_id=str(uuid.uuid4()), item_type="interstate_handoff",
        fir_id=fir.id, accused_id=accused.id,
        summary=(f"Accused {accused.id} last known in "
                 f"{accused.last_known_district or accused.last_known_state} "
                 f"-- crosses {scope} boundary from originating case "
                 f"({fir.district}). Recommend inter-{scope} coordination."),
        created_date=datetime.utcnow().isoformat(),
    )
```

Hook this into ingestion (on any FIR/accused update, not just creation, since "last known location" can change after the case is already open) and push the result via the shared `push_review_item` if not `None`.

### 8.4 Testing / Migration

- [ ] Accused marked absconding, last known district differs from FIR district → `interstate_handoff` item generated, scope = "district"
- [ ] Accused marked absconding, last known state is not Karnataka → item generated, scope = "state"
- [ ] Accused not marked absconding, even with a different last-known district → no item (the flag requires both conditions, not just location mismatch alone)
- [ ] No last-known-location data at all → no item, no crash

1. Add the four new fields to `AccusedSchema`
2. Build `shared/absconder_engine.py`
3. Hook `check_interstate_flag` into ingestion/update flow
4. Confirm `KARNATAKA_DISTRICTS` or equivalent canonical district list already exists somewhere in the project (district canonicalization is referenced elsewhere in Architecture v8) and reuse it rather than redefining it

---

## 9. Combined Build Order (All Seven Items)

Given the dependency notes in Section 0, a sensible build sequence:

1. Section 1 (shared infrastructure: data source pattern, `ReviewQueueItem`) — everything else needs this
2. Item 8 (absconder flagging) — fully independent, quick, good warm-up
3. Item 6 (RBAC) — independent, cross-cutting, worth doing early before more query paths exist to retrofit
4. Item 2 (CDR/financial) — establishes the provider pattern in practice
5. Item 5 (ANPR) — reuses the now-proven provider pattern from Item 2
6. Item 3 (proactive cold-case matching) — depends on Item 1 (already done) for exclusion checks
7. Item 4 (contradicted confidence) — depends on Item 1's exclusion/contradiction hooks
8. Item 7 (hypothesis workspace) — most UI-heavy, most novel, best done last with everything else stable underneath it

---

## 10. Summary for `agents.md` / Antigravity Context

> Seven extended capabilities added on top of the core PS-1 pipeline: (2) CDR and financial-trail data via a pluggable provider interface — synthetic today, swappable for a real lawful-access integration later, every record carrying explicit provenance; (3) proactive cold-case matching that reuses existing SHARED_MO computation to alert officers about unsolved-case matches without being asked, respecting active exclusions; (4) a CONTRADICTED confidence state that retroactively flags past claims invalidated by new exclusions; (5) vehicle/ANPR cross-referencing against a wanted-vehicle registry, same provider pattern as CDR; (6) lightweight RBAC scoping queries to an officer's home district unless elevated rank or a logged override; (7) a hypothesis workspace letting officers pin a working theory and get deterministic supporting/contradicting evidence counts over time, with confirm/refute always an explicit officer action; (8) deterministic absconder/interstate-handoff flagging based on last-known-location mismatches. All seven follow the standing project principles: the LLM never decides investigative facts (exclusions, contradictions, hypothesis resolution) — every decision point is deterministic code or an explicit officer action; nothing is silently deleted, only demoted or flagged; and proactive alerts use template-built summaries, not unsupervised LLM generation.
