# Deterministic Pattern Injection — Synthetic Investigative Signature Library

## 1. Design Rationale

Real CDR (Call Detail Record) and UPI/banking transaction data are legally restricted and cannot be used for a hackathon/demo graph database. Pure-random synthetic data fills the graph volumetrically but contains no exploitable structure, which makes it impossible to demonstrate that a retrieval/reasoning engine (Cypher queries, GraphRAG, LLM-orchestrated traversal) actually surfaces meaningful criminal signatures rather than noise.

**Deterministic Pattern Injection** addresses this via seeded generator functions that construct known, named sub-graph signatures and embed them inside an otherwise-random background graph. Determinism (fixed seeds, explicit parameters) guarantees reproducible test fixtures — the same inputs always produce the same graph topology, which is required for regression testing of retrieval logic and for reliably reproducing a "ground truth" during a live demo.

This is implemented as a **pluggable data source** architecture: a synthetic provider today, swappable for a real (access-controlled) CDR/banking/ANPR feed later, without changing the schema or the downstream reasoning layer.

Each pattern below is defined by:
- **Investigative logic** — why this shape is operationally meaningful to an investigator, and what naive query it evades.
- **Graph schema** — nodes, edges, and required timestamp/attribute fields.
- **Injection function** — a deterministic Python generator producing the signature sub-graph given seed parameters.

---

## 2. Baseline Patterns (Already Designed)

### 2.1 Burner Phone (Call Proximity / Isolated Burst)

**Logic:** Coordinated actors communicate at unusually high frequency in a narrow window immediately surrounding an incident, with no communication history before or after — consistent with a purpose-acquired device used once and discarded.

**Schema:**
```
(:Phone {number, imei})
(:Phone)-[:CALLED {timestamp, duration_sec, cell_tower_id}]->(:Phone)
```

**Signature:** 5–10 CALLED edges between phone_a and phone_b, timestamps strictly bounded to `[incident_time - 48h, incident_time + 6h]`, zero edges outside that window, `cell_tower_id` biased toward towers near the incident location.

```python
def inject_burner_pattern(incident_time: datetime, phone_a: str, phone_b: str,
                           tower_near_incident: str, num_calls: int = 7) -> None:
    window_start = incident_time - timedelta(hours=48)
    window_end = incident_time + timedelta(hours=6)
    for _ in range(num_calls):
        ts = random_datetime_between(window_start, window_end)
        create_called_edge(phone_a, phone_b, ts,
                            duration_sec=random.randint(15, 300),
                            cell_tower_id=tower_near_incident)
```

### 2.2 Financial Layering (Structuring)

**Logic:** Large illicit sums are split into sub-threshold amounts and moved rapidly through a chain of intermediary ("mule") accounts to defeat single-transaction reporting thresholds and obscure source-to-destination linkage.

**Schema:**
```
(:Account {account_id, is_mule: bool})
(:Account)-[:TRANSFERRED {amount, timestamp}]->(:Account)
```

**Signature:** Fan-out-then-chain topology — `source → A → B → C → D`, each hop amount capped just under the reporting threshold (e.g. ₹49,000 against a ₹50,000 threshold), hops spaced ~15 minutes apart.

```python
def inject_layering_pattern(source_account: str, total_amount: int,
                             threshold: int = 50000, chunk_size: int = 49000,
                             hop_delay_minutes: int = 15) -> None:
    num_chunks = math.ceil(total_amount / chunk_size)
    base_time = random_base_datetime()
    for i in range(num_chunks):
        chain = [source_account] + [f"mule_acct_{uuid4().hex[:8]}" for _ in range(3)]
        amount = min(chunk_size, total_amount - i * chunk_size)
        ts = base_time + timedelta(minutes=i * hop_delay_minutes)
        for hop_index in range(len(chain) - 1):
            create_transfer_edge(chain[hop_index], chain[hop_index + 1], amount,
                                  ts + timedelta(minutes=hop_index * hop_delay_minutes))
```

---

## 3. Additional Patterns (New)

### 3.1 Silent Meetup (Tower Co-Location, Call-Absent)

**Investigative logic:** Sophisticated actors who anticipate CDR subpoena avoid direct calls/SMS entirely and instead coordinate via physical co-presence. The tell is repeated spatiotemporal co-location — both phones pinging the same cell tower within a tight time window on multiple distinct occasions — combined with the **explicit absence** of any direct communication edge between the two devices. This pattern specifically stress-tests whether the retrieval engine can surface an association from location data alone, which a naive "who called who" query would completely miss.

**Schema:**
```
(:Phone {number, imei})
(:CellTower {tower_id, lat, lon})
(:Phone)-[:PINGED {timestamp}]->(:CellTower)
-- No CALLED edge is ever created between the co-located pair
```

**Signature:** N (e.g. 4–6) co-location events on distinct dates, both phones pinging the same tower within a `window_minutes` band of each other; zero CALLED edges between the pair anywhere in the graph.

```python
def inject_silent_meetup_pattern(phone_a: str, phone_b: str, tower_id: str,
                                  meetup_dates: list[date], window_minutes: int = 20) -> None:
    for meetup_date in meetup_dates:
        meetup_time = random_time_on(meetup_date)
        for phone in (phone_a, phone_b):
            offset = random.randint(-window_minutes, window_minutes)
            create_pinged_edge(phone, tower_id, meetup_time + timedelta(minutes=offset))
    # Invariant enforced at generation time: no CALLED edge between phone_a and phone_b
```

**Detection query shape:** self-join on `PINGED` by `tower_id` with a timestamp-proximity predicate between two distinct `Phone` nodes, filtered to pairs with no matching `CALLED` edge — a NOT EXISTS pattern in Cypher.

---

### 3.2 IMEI Churn (Device Persistence Across Rotated SIMs)

**Investigative logic:** Phone number rotation ("burner phones") is a common evasion tactic on the assumption that a new number breaks the identity trail. The physical device (IMEI) is rotated far less often, since replacing hardware is costlier than replacing a SIM. A single `Device` node associated with 3+ sequential, non-overlapping `Phone` (number) nodes over time is a strong same-actor signal that link-analysis on phone number alone cannot surface.

**Schema:**
```
(:Device {imei})
(:Phone {number})
(:Device)-[:USED_AS {activated_at, deactivated_at}]->(:Phone)
```

**Signature:** One `Device` node with 3–4 outgoing `USED_AS` edges to distinct `Phone` nodes, activation windows sequential and non-overlapping (each SIM deactivates shortly before the next activates).

```python
def inject_imei_churn_pattern(imei: str, phone_numbers: list[str],
                               first_activation: datetime,
                               gap_days: tuple[int, int] = (2, 10)) -> None:
    current_start = first_activation
    for phone in phone_numbers:
        active_days = random.randint(15, 45)
        deactivated_at = current_start + timedelta(days=active_days)
        create_used_as_edge(imei, phone, current_start, deactivated_at)
        current_start = deactivated_at + timedelta(days=random.randint(*gap_days))
```

**Detection query shape:** group `USED_AS` edges by `imei`, filter for `count(distinct phone) >= 3`, optionally order activation windows to confirm sequential (non-overlapping) usage.

---

### 3.3 Smurfing (Fan-In Structuring)

**Investigative logic:** The structural inverse of the layering pattern (2.2). Rather than one large sum fanning *out* through a chain, many individually unremarkable deposits from otherwise-unrelated accounts fan *in* to a single collection account within a short window. Each individual transaction stays under the reporting threshold, so no single transaction trips an automated flag — the signal only exists at the aggregate in-degree/in-volume level, which requires graph-level (not row-level) analysis to detect.

**Schema:**
```
(:Account {account_id, is_mule: bool})
(:Account)-[:TRANSFERRED {amount, timestamp}]->(:Account)
```

**Signature:** N (e.g. 8) previously-unconnected mule accounts, each transferring a sub-threshold amount to one `collection_account` within a tight window (e.g. 24–36 hours).

```python
def inject_smurfing_pattern(collection_account: str, total_amount: int,
                             num_mules: int = 8, threshold: int = 50000,
                             window_hours: int = 36) -> None:
    per_mule = min(total_amount // num_mules, threshold - random.randint(500, 5000))
    window_start = random_base_datetime()
    for _ in range(num_mules):
        mule = f"mule_acct_{uuid4().hex[:8]}"
        create_account(mule, is_mule=True)
        ts = window_start + timedelta(hours=random.uniform(0, window_hours))
        create_transfer_edge(mule, collection_account, per_mule, ts)
```

**Detection query shape:** aggregate `TRANSFERRED` edges by destination `account_id` within a rolling time window, filter for `count(distinct source) >= N` and `all(amount < threshold)`.

---

### 3.4 Recce Pattern (ANPR Pre-Incident Casing Behavior)

**Investigative logic:** Vehicles involved in planned offenses (robbery, burglary, targeted assault) are frequently detected by ANPR cameras near the target location on multiple occasions in the days preceding the incident — typically at atypical hours and without a corresponding stop/transaction — followed by one detection during the incident window itself, then no further detections. This is a pre-crime signal distinct from post-incident "getaway route" reconstruction and demonstrates the system's ability to surface planning-stage behavior, not just after-the-fact linkage.

**Schema:**
```
(:Vehicle {plate_number})
(:ANPRCamera {camera_id, lat, lon, near_location})
(:Vehicle)-[:DETECTED {timestamp, speed}]->(:ANPRCamera)
```

**Signature:** 3–5 pre-incident detections at the target camera, clustered in odd hours (e.g. 23:00–04:00) within a `lookback_days` window before `incident_time`; one detection during the incident window; zero detections after.

```python
def inject_recce_pattern(plate_number: str, camera_id: str, incident_time: datetime,
                          num_recce_visits: int = 4, lookback_days: int = 14) -> None:
    for _ in range(num_recce_visits):
        days_before = random.randint(1, lookback_days)
        visit_time = (incident_time - timedelta(days=days_before)).replace(
            hour=random.choice([23, 0, 1, 2, 3]), minute=random.randint(0, 59))
        create_detected_edge(plate_number, camera_id, visit_time,
                              speed=random.uniform(15, 35))
    incident_detection_time = incident_time + timedelta(minutes=random.randint(-15, 15))
    create_detected_edge(plate_number, camera_id, incident_detection_time,
                          speed=random.uniform(30, 60))
    # Invariant enforced at generation time: no DETECTED edges after incident_time
```

**Detection query shape:** filter `DETECTED` edges by `camera_id` near a target location, bucket by `hour(timestamp)` to isolate odd-hour clustering, confirm a detection inside the incident window and none after it.

---

## 4. Summary Table

| Pattern | Domain | Topology | Evasion Assumption Defeated |
|---|---|---|---|
| Burner Phone | Telecom | Dense dyadic burst, time-bounded | "New number, no history" |
| Silent Meetup | Telecom/Spatial | Co-location, zero direct edge | "We never called each other" |
| IMEI Churn | Telecom | One device, sequential SIM edges | "New number breaks the trail" |
| Layering (Structuring) | Financial | Fan-out chain, sub-threshold hops | "Each transfer is below the flag limit" |
| Smurfing | Financial | Fan-in, sub-threshold, short window | "No single deposit looks suspicious" |
| Recce (ANPR) | Spatial | Pre-incident cluster + incident hit + silence after | "No link before the crime happened" |

## 5. Architectural Notes for Implementation

- All generators should accept an explicit RNG seed (or a seeded `random.Random` instance) rather than relying on global `random` state, to preserve determinism when patterns are injected in parallel or in varying order.
- Each generator should be registered in a single `inject_pattern_registry.py` (or equivalent) exposing a uniform interface — e.g. `PatternInjector.run(pattern_name, **params) -> InjectionResult` — so the pluggable data source layer can enumerate, parameterize, and log which signatures were planted in a given graph build, independent of the eventual real-data provider implementation.
- Each injected pattern should record its own ground-truth metadata (which nodes/edges belong to the signature) separately from the graph itself, so evaluation harnesses can check retrieval precision/recall against a known answer set rather than visual inspection.
- Background/noise generation should be run first, then signature injection second, to avoid the injected signature's nodes/edges being accidentally overwritten or merged into unrelated background structure.
