# PS-1: Integrity & Anti-Corruption Layer v1

**Companion to:** `PS1_RBAC_Case_Access_v1.md` (access model). This doc covers what stops
that access model — and the system generally — from being misused, in either direction:
senior officers abusing legitimate authority, or junior officers concealing information.

**Framing:** access control answers "can they see it." This doc answers "if they can see
it (or shouldn't be able to, but try anyway), is it invisible, permanent, or unaccountable."
Those are different problems and need different mechanisms.

---

## 1. Threat model

**Top-down (rank misusing authority):**
1. A senior officer uses legitimate Pull access to snoop on a specific person (checking if
   an associate, relative, or contact is under investigation) with no real oversight
   purpose, then tips them off or interferes.
2. A senior officer downgrades a case's `is_sensitive` flag to expose it to people who
   shouldn't see it (a protected witness, an internal-affairs matter, an ATS operation).
3. A supervisor invokes the cross-jurisdiction override under a thin or fabricated reason.
4. A supervisor repeatedly "corrects" (rejects) accurate evidence connections via the
   reasoning feedback loop to suppress a pattern implicating someone they're protecting.
5. Someone with access edits or deletes evidence, or removes a collaborator from a case to
   cut off a threatening line of inquiry.

**Bottom-up (concealment):**
6. An Investigating Officer never elevates a case that should be escalated, so it stays
   invisible to anyone doing a Pull-based check.
7. An officer marks real evidence as "contradicted" or excludes it, making a genuine lead
   disappear rather than as an honest investigative judgment.
8. An officer looks up a specific named person for personal reasons unrelated to any real
   case — the classic unauthorized-lookup pattern (an ex-partner, a neighbor, a journalist).

The common thread: every one of these is invisible today unless someone happens to go
looking. The existing plan for tamper-evident logging (SHA-256 hash "on every query," per
Architecture v9) protects *integrity* — proves a log entry wasn't edited after the fact —
but does nothing about *detection* or *deletion of an entire entry*. Integrity is not the
same thing as oversight.

---

## 2. Named-entity search logging (replaces the earlier "provisional case" idea)

**Not every search needs a case behind it.** Browsing crime patterns ("recent thefts in
this area," "similar MOs to this case") is normal, low-risk police work with no
person-specific target — no logging burden needed beyond what's already logged for any
query.

**The actual risk is narrower: searching for one specific named person, vehicle, or
property.** That's where vector #8 lives. The fix doesn't require creating a case object at
all — it's a single log line:

```
SearchLog {
  officer_id
  timestamp
  query_target_type     # person | vehicle | property | none (pattern search)
  query_target_id       # the specific ID/name searched, if applicable
  linked_case_id         # nullable — filled if this search happened inside a case session
  reason                # optional free-text or dropdown: routine_stop | informant_tip |
                         # case_followup | other
}
```

No new object type, no expiring placeholder, no burden on the officer beyond the system
already knowing what they searched. If a name/ID search has no `linked_case_id`, that's not
blocked — it's just a fact recorded, which is what makes it investigable later if a leak or
tip-off is ever traced back.

---

## 3. Hash-chained audit log (not just hashed records)

Individually hashing each audit entry (as currently planned) proves an entry wasn't
*altered*. It does not prove an entry wasn't *deleted outright* — nothing forces a gap in
the log to be noticed.

**Fix:** each new audit entry's hash includes the previous entry's hash (a hash chain — the
same core idea a blockchain uses, without needing any blockchain infrastructure). Deleting
or reordering any past entry breaks every hash computed after it, so tampering is
detectable by anyone recomputing the chain, not just someone who happens to spot a missing
row.

**Reads get logged, not just writes.** Viewing another officer's session, viewing a case's
evidence, viewing the Case Board, and every `is_sensitive` toggle in either direction all go
into the same chain. This is the actual anti-corruption lever — knowing *who looked at*
something matters as much as knowing who changed it.

---

## 4. Append-only evidence — generalizing a principle you already have

The evidence-language layer already establishes: never overwrite an original narrative,
always preserve it alongside a translation. This should generalize into a hard rule, not a
feature-specific convention: **FIRs, evidence items, and audit entries are never mutated in
place — only superseded, with the prior version's hash preserved.** Same spirit as the Case
Session doc's "closed, not deleted" principle for cases — extended to evidence. This makes
quietly editing a narrative to remove an inconvenient detail architecturally impossible,
not just against policy.

---

## 5. Governance on sensitive-case downgrades and jurisdiction overrides

Covered in detail in the RBAC doc (§3, §5) — restated here as the corruption-relevant
summary:

- Raising a case's sensitivity: open to any collaborator, low risk, routine log.
- **Lowering** a case's sensitivity: restricted to the Vigilance Cell oversight role (§6
  below), never the case's own chain of command, always a mandatory review item.
- Cross-jurisdiction override: reason field is mandatory, not optional. A single override
  with a genuine reason is normal; a pattern of frequent overrides from one officer is the
  actual signal, and needs to be reviewable (§7) even if not auto-flagged yet.

---

## 6. Vigilance Cell — a real oversight role, not an invented one

The scariest failure mode is a senior officer abusing *legitimate* access — nothing in a
normal chain-of-command model stops that, because the abuser and the reviewer are the same
hierarchy.

KSP already has a real structure this can model: the **Vigilance wing** at KSP
headquarters, which handles departmental misconduct (distinct from the ISD, which is
intelligence/counter-terrorism-focused, and the SPCA, which is an external,
judge-chaired body for public complaints). Modeling the oversight role on Vigilance — call
it `vigilance_cell` — gives this a real institutional anchor instead of a role invented for
the system.

This role:
- reads the full hash-chained audit log across all districts and departments,
- is the only role that can downgrade `is_sensitive`,
- is itself logged with the same rigor as everyone else — no role is exempt from the chain.

**Open question, flagged rather than guessed at:** whether any Vigilance-adjacent action
should require two people to jointly sign off (dual control), to prevent this role itself
becoming a single point of corruption. Worth a real conversation with someone who
understands how KSP Vigilance actually operates before committing to a specific workflow.

---

## 7. Anomaly review — documented as a known risk, not built for the hackathon

Detecting patterns like "an officer's correction ratio departs from department norms" (the
feedback-loop gaming vector, #4 above) needs a real baseline population and enough usage
data to be statistically meaningful. Building a detector on top of an already-unvalidated
trust-smoothing model (the `MIN_SAMPLES_FOR_NARROW_SCOPE` constant is itself an untested
guess) compounds uncertainty on uncertainty.

**Decision: don't build the detection logic for the hackathon.** Instead:
- name the vector explicitly in this doc (done, above),
- make sure everything needed to investigate it *later* is captured for free once the
  hash-chain (§3) exists — correction events, override frequency, search logs are all
  already being recorded,
- frame it in the demo/pitch as "here's the vector, and here's why our audit design makes
  it forensically traceable after the fact" rather than a live statistical model.

This is honest scoping, not a gap being hidden — consistent with how Architecture v9
already separates production gaps from the core build rather than overselling them.

---

## 8. Demo vs. foundation — what to actually show

| Mechanism | Demo-able live? | Why |
|---|---|---|
| Sensitive-flag downgrade blocked / routed to Vigilance | **Yes** | Clear, visual, judge can watch it happen |
| Named-entity search logged with officer attribution | **Yes** | Show the log entry appear in real time |
| Cross-jurisdiction override requiring a reason | **Yes** | Simple UI moment |
| Hash-chained audit log | No — invisible | Foundational integrity guarantee, explain rather than show |
| Append-only evidence versioning | No — invisible | Same — explain the guarantee, don't try to stage it |
| Anomaly detection on trust-weight gaming | **Not built** | Documented risk only (§7) |

Label these clearly in the pitch so the invisible-but-important pieces (hash-chaining,
append-only storage) don't read as afterthoughts just because they can't be staged on
screen — they're the actual honest foundation the demoable parts sit on.

---

## 9. Summary of what's new vs. what already existed

| Idea | Status |
|---|---|
| SHA-256 hashing of audit entries | Already planned (Architecture v9) |
| Hash-**chaining** entries together | **New** — closes the deletion gap |
| Logging reads, not just writes | **New** |
| Named-entity search logging | **New** (replaces earlier provisional-case idea, dropped as unnecessary) |
| `is_sensitive` downgrade governance | **New** — ties into RBAC doc §3 |
| Vigilance Cell oversight role | **New** — grounded in KSP's real Vigilance wing |
| Mandatory (not optional) override reason | **New** — small fix to Item 6's field |
| Append-only evidence, generalized | **New** — extends the language-layer's existing preserve-original principle |
| Trust-weight gaming detection | Explicitly **not built** — documented risk only |
