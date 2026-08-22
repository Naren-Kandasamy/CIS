# Structuring Suspicion Modeling — Addendum to Deterministic Pattern Injection

**Supersedes:** Sections 2.2 (Financial Layering) and 3.3 (Smurfing) of `deterministic_pattern_injection.md`, specifically the fixed ₹50,000 threshold used in both. Everything else in that document is unaffected.

## 1. Why the Original Threshold Was Wrong

The original layering/smurfing generators split amounts into chunks "just under ₹50,000" and framed this as evading a bank reporting flag. That threshold does not correspond to any real Indian AML reporting rule:

| Real Indian rule | Threshold | What it actually triggers |
|---|---|---|
| PMLA Cash Transaction Report (reporting entity → FIU-IND) | ₹10,00,000 | Automatic report, no suspicion required |
| PAN mandatory for cash transaction | ₹50,000 | Identity verification requirement, not a fraud/AML flag |
| NPCI UPI daily P2P transfer cap | ₹1,00,000 per day, per user, across all apps | Hard transaction failure, not a reporting trigger |

₹50,000 is a real number in the Indian financial system, but it means "you must show your PAN," not "the bank will flag this to FIU-IND." Using it as an AML-evasion threshold is not accurate to how Indian structuring actually works, and is the kind of detail a domain-aware judge would catch.

## 2. Reframing: Behavioral Signature, Not a Single Threshold

FIU-IND's own Suspicious Transaction Report guidance defines "value just under the reporting threshold amount in an apparent attempt to avoid reporting" as one red flag among several — suspicion is explicitly **not** a fixed-number rule in the real regulatory framework; it is a composite, pattern-based judgment. The corrected design reflects this: three narrative-tagged sub-patterns, each tied to a real threshold and a distinct crime narrative, evaluated through a shared multi-signal suspicion score rather than a single amount check.

## 3. Three Narrative-Tagged Sub-Patterns

| Sub-pattern | Real threshold evaded | Crime narrative | Typical KSP crime-head fit |
|---|---|---|---|
| `structuring_ctr` | ₹10,00,000 (PMLA CTR) | Large-scale laundering of cash-heavy predicate offense proceeds | Extortion, trafficking, organized crime |
| `structuring_pan` | ₹50,000 (PAN mandate) | Smaller operator avoiding an identity trail on cash deposits | Localized fraud, small-scale extortion |
| `structuring_upi_cap` | ₹1,00,000/day (NPCI UPI cap) | Digital mule-network fraud, splitting across accounts/days to route around a hard transfer ceiling | Loan-app scams, UPI phishing, mule-account fraud — likely the most common real KSP digital-fraud narrative |

```python
STRUCTURING_PROFILES = {
    "structuring_ctr":     {"threshold": 1_000_000, "chunk_margin": (10_000, 50_000)},
    "structuring_pan":     {"threshold": 50_000,    "chunk_margin": (500, 5_000)},
    "structuring_upi_cap": {"threshold": 100_000,   "chunk_margin": (2_000, 15_000)},
}

def inject_structuring_pattern(profile_name: str, source_account: str, total_amount: int,
                                num_hops: int = 3, hop_delay_minutes: int = 15) -> None:
    """Parameterized replacement for inject_layering_pattern / inject_smurfing_pattern.
    Tags each injected edge with profile_name so ground-truth evaluation can
    distinguish which real-world rule the signature is meant to evade."""
    profile = STRUCTURING_PROFILES[profile_name]
    margin = random.randint(*profile["chunk_margin"])
    chunk_size = profile["threshold"] - margin
    num_chunks = math.ceil(total_amount / chunk_size)
    base_time = random_base_datetime()

    for i in range(num_chunks):
        chain = [source_account] + [f"mule_acct_{uuid4().hex[:8]}" for _ in range(num_hops)]
        amount = min(chunk_size, total_amount - i * chunk_size)
        ts = base_time + timedelta(minutes=i * hop_delay_minutes)
        for hop_index in range(len(chain) - 1):
            create_transfer_edge(chain[hop_index], chain[hop_index + 1], amount,
                                  ts + timedelta(minutes=hop_index * hop_delay_minutes),
                                  pattern_tag=profile_name)
```

## 4. Benign Distractor — True Negatives

Without a benign counter-population, every sub-threshold transaction in the graph is, by construction, part of an injected crime signature — which means a naive `WHERE amount < 50000` query would achieve perfect precision without the retrieval engine doing any real work. Ordinary transactions in that same amount range (rent, shopping, family transfers) are common and must be represented, or the demo doesn't actually test anything.

```python
def inject_benign_small_transactions(account_id: str, num_transactions: int = 15,
                                      amount_range: tuple = (500, 45000)) -> None:
    """True negatives -- ordinary spending with no structuring signature:
    random amounts, random unrelated recipients, no time clustering,
    no repetition toward a common destination."""
    for _ in range(num_transactions):
        recipient = f"acct_{uuid4().hex[:8]}"
        amount = random.randint(*amount_range)
        ts = random_datetime_over_months(6)
        create_transfer_edge(account_id, recipient, amount, ts, pattern_tag=None)
```

**Injection ratio guidance:** for a credible demo, benign small transactions should substantially outnumber structuring-pattern transactions in the same amount band (e.g. 10:1 or higher) — the point is to make the composite score in Section 5 do the separating work, not amount-range membership alone.

## 5. Composite Structuring Suspicion Score

Mirrors the weighted multi-signal confidence-scoring approach already used elsewhere in PS-1 (source convergence / evidence strength / recency), for architectural consistency rather than introducing a one-off scoring method.

```python
def compute_structuring_suspicion(account_id: str, window_days: int = 30) -> float:
    txns = get_transactions(account_id, window_days)
    if not txns:
        return 0.0

    proximity_score = mean([
        1 - abs(t.amount - nearest_threshold(t.amount)) / nearest_threshold(t.amount)
        for t in txns
    ])
    repetition_score = min(len(txns) / 5, 1.0)
    concentration_score = 1 - (len(set(t.recipient for t in txns)) / len(txns))
    time_clustering_score = clustering_tightness(txns)

    return (0.35 * proximity_score +
            0.25 * repetition_score +
            0.25 * concentration_score +
            0.15 * time_clustering_score)
```

| Signal | Weight | What it captures |
|---|---|---|
| Threshold proximity | 0.35 | How close each transaction sits to a known real threshold (CTR/PAN/UPI) |
| Repetition | 0.25 | Multiple near-threshold transactions from the same account, not a one-off |
| Destination concentration | 0.25 | Few distinct recipients relative to transaction count — fan-out/fan-in shape |
| Time clustering | 0.15 | Transactions bunched in a tight window rather than spread naturally |

`nearest_threshold(amount)` should resolve to whichever of {50,000 / 100,000 / 1,000,000} the amount is closest to and below, so the same scoring function works across all three sub-patterns without needing to know in advance which one it's looking at.

## 6. Ground-Truth Tagging

Every injected edge carries a `pattern_tag` (`structuring_ctr` / `structuring_pan` / `structuring_upi_cap` / `None` for benign) at generation time, consistent with the ground-truth metadata requirement in the base document (Section 5, Architectural Notes). This allows evaluation of `compute_structuring_suspicion` against a known answer set — precision/recall on distinguishing tagged structuring accounts from benign accounts in the same amount range — rather than visual inspection of query output.

## 7. Summary of What Changed vs. the Original Document

| Aspect | Original (Sections 2.2 / 3.3) | This Addendum |
|---|---|---|
| Threshold | Single fixed ₹50,000, not tied to a real rule | Three profiles, each tied to a real, verifiable Indian threshold |
| Detection basis | Implicit amount check | Weighted composite score across four behavioral signals |
| Negative examples | None — every sub-threshold transaction was part of a signature | Explicit benign distractor generator with a recommended injection ratio |
| Ground truth | Signature membership only | Adds `pattern_tag` per profile for precision/recall evaluation |
