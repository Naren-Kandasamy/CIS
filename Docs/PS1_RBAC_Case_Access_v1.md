# PS-1: RBAC & Case Access Model v1

**Status:** Supersedes `PS1_Case_Session_Management.md` §3 (access rules) and Open Question 1.
Reconciles with `PS1_Extended_Investigative_Capabilities.md` Item 6 ("3D Access Matrix").
**Purpose:** Define exactly who can see a case, when, and why — and close the gap between
"technically has access" and "should be looking at this right now."

---

## 1. Why this doc exists

Two earlier docs disagreed with each other:

- `PS1_Case_Session_Management.md` said rank grants **zero** implicit visibility — pure
  owner + explicit-collaborator list, always. It flagged this as Open Question 1.
- `PS1_Extended_Investigative_Capabilities.md` Item 6 said supervisors **do** get implicit
  ("Pull") visibility, scoped by district and department, unless a case is marked sensitive.

This doc resolves that: **Item 6's model wins, with fixes.** It also adds the department
axis explicitly (previously conflated with crime type — see §4) and adds a governance layer
so the sensitive-case toggle can't itself be abused (see the companion doc,
`PS1_Integrity_AntiCorruption_Layer_v1.md`, for the corruption-resistance angle — this doc
is the access model; that one is what stops the access model from being misused).

---

## 2. The three visibility mechanisms

Every case is visible through exactly one or more of these paths. They stack — if any one
applies, the officer can see the case.

### 2a. Explicit collaborator list (always active, highest priority)
The Investigating Officer (owner) and anyone explicitly added as a collaborator can always
see the case, regardless of rank, department, or district. This never changes and is not
affected by anything below.

### 2b. Pull — implicit jurisdictional + departmental oversight
A supervisory rank sees a case **without being added** if:

- The case's `department` matches the officer's `department`, **and**
- The case's `district` is within the officer's `home_district` (or the officer holds a
  rank whose jurisdiction spans multiple districts — e.g., a Range DIG), **and**
- The case is **not** marked `is_sensitive`.

This is audit/dashboard visibility — a supervisor *can* find the case if they go looking
(case list, search, district dashboard). It does not push anything onto their screen.

**Real-world scenario this solves:** a DySP overseeing Stations A, B, and C sees cases
across all three, but a DySP in a neighboring sub-division sees nothing from Station A —
and neither sees the other's Cyber Cell cases, because department scoping is independent
of district scoping. Rank alone crosses neither axis.

**Named exception:** SP-level and above may Pull across departments within their own
district (a district SP plausibly needs situational awareness across verticals). This is
the only rank-based cross-department exception, and it does not cross district lines.

### 2c. Push — Elevate for Review
Independent of Pull, the Investigating Officer can click **[⬆ Elevate for Review]** at any
point. This:
- adds the officer's direct commanding officer as a collaborator (§2a — permanent, not a
  one-time peek),
- generates a Case Brief (LLM summary) so the supervisor gets up to speed without reading
  raw notes,
- creates a `ReviewQueueItem` that actually appears on the supervisor's active dashboard —
  this is the only mechanism that interrupts a supervisor rather than waiting for them to
  look.

Push is how a case reaches a supervisor who has *no* Pull access at all (different
department, different district, or the case is sensitive) — Elevate always works,
regardless of the Pull rules above, because the Investigating Officer is the one choosing
to loop someone in.

---

## 3. The sensitive-case override

A case has a boolean-equivalent field: `is_sensitive`.

- **Default:** `False`. Standard cases follow the Pull rules in §2b.
- **When `True`:** Pull is switched off entirely for that case. Only §2a (explicit
  collaborators) and §2c (Elevate, if the IO chooses to) apply. Rank provides zero implicit
  visibility, full stop — this is the "the case doesn't exist to you unless you're on the
  list" behavior from the original compartmentalization idea, but scoped to just the cases
  that need it instead of applied globally.

### Governance — who can flip this flag
This is the part that matters for corruption-resistance, so it's specified precisely:

| Action | Who can do it | Logged? |
|---|---|---|
| Mark a case `is_sensitive = True` (raise protection) | Any collaborator on the case | Yes, routine log |
| Unmark `is_sensitive = False` (lower protection) | **Only** the Vigilance Cell oversight role (see companion doc §6) | Yes, mandatory `ReviewQueueItem`, never silent |

Raising protection is always low-risk, so it's left open to anyone close to the case.
Lowering protection is the actual abuse vector (exposing a witness, an internal-affairs
case, an ATS operation to people who shouldn't see it) — so it's carved out to a role
outside the normal chain of command entirely. A district SP, however senior, cannot
unilaterally strip protection from a case in their own district.

---

## 4. Data model additions

### 4a. `department` — new explicit field, not derived
Item 6's original implementation sketch filtered on `crime_type` as a stand-in for
department:

```python
filter_clause += ", crime_type: $officer_department"
```

This is wrong and needs to be fixed before it ships. `crime_type` (via
`crime_head_id`/`crime_sub_head_id`/`crime_type_freetext`) is a crime **taxonomy** field —
it describes what the offense is. `department` is an **organizational vertical** — which
unit within KSP owns the case (Law & Order, Cyber, Narcotics, Financial Crimes, etc.). A
cyber-enabled financial fraud, for instance, could plausibly sit in either taxonomy bucket
depending on how it's coded, but must map to exactly one department for access purposes.
These are not the same axis and must not be conflated.

**Fix:** add an explicit `department` field to the Case/FIR object, set at case creation
(defaulting from the creating officer's own department, editable if a case gets
re-assigned to a specialized unit later). `OfficerProfile.department` already exists per
Item 6 and is the field this should match against.

### 4b. Fields required on `Case` / FIR
```
Case {
  case_id
  district           # existing
  unit_id            # existing — Police Station
  department         # NEW — explicit organizational vertical, not crime_type-derived
  is_sensitive        # existing concept, governance now specified (§3)
  owner_officer_id     # existing — Investigating Officer
  collaborators[]      # existing
  cross_jurisdiction_reason   # see §5 — now REQUIRED, not optional, when used
}
```

### 4c. Fields required on `OfficerProfile`
```
OfficerProfile {
  officer_id
  rank
  department
  home_district
  supervisory_scope[]   # districts/units this rank has Pull authority over, if rank > IO level
}
```

---

## 5. Cross-jurisdiction override

Item 6 already logs `cross_jurisdiction_reason` when an officer's Pull would otherwise be
denied but they invoke an override (e.g., a genuine multi-district organized crime link).
Two changes:

1. **Make the reason field mandatory**, not `str | None` — the override path should not be
   invocable without a stated reason. An empty override is the exact hole a corrupt lookup
   would use.
2. **Frequency, not just presence, gets reviewed.** A single override with a real reason is
   normal police work. A pattern of frequent overrides from one officer is the actual
   signal — see the companion anti-corruption doc §5 for how this gets surfaced (this doc
   only specifies that the data must be captured cleanly enough to make that review
   possible later).

---

## 6. Access check — reference logic

```python
def can_view_case(officer: OfficerProfile, case: Case) -> bool:
    # §2a — always wins, no exceptions
    if officer.officer_id in case.collaborators or officer.officer_id == case.owner_officer_id:
        return True

    # §3 — sensitive cases skip Pull entirely
    if case.is_sensitive:
        return False  # only collaborator list (above) or a future Elevate grants access

    # §2b — Pull: department AND district/jurisdiction must both match
    department_match = (
        officer.department == case.department
        or officer.rank >= RANK_SP  # named cross-department exception, same district only
    )
    jurisdiction_match = case.district in officer.supervisory_scope

    return department_match and jurisdiction_match
```

Note what this function does *not* do: it never grants access based on rank alone, and it
never lets a department match substitute for a jurisdiction match (or vice versa). Both
axes must clear independently, except for the single named SP exception.

---

## 7. Open questions carried forward

- **`supervisory_scope` population** — is this a static org-chart import (station → sub-division
  → district → range hierarchy), or does it need to support ad-hoc task force assignments
  (e.g., a DySP temporarily heading a joint task force spanning two districts)? The access
  check above assumes a clean hierarchy; real KSP org structure should be confirmed before
  this is treated as final.
- **What happens when a case's `department` needs to change** (e.g., a case starts as
  routine Law & Order and turns out to be Cyber-enabled fraud)? Reassigning department
  changes who has Pull access overnight — worth deciding whether this itself should require
  sign-off rather than a simple field edit.
- **Elevate's collaborator addition is permanent** — is there ever a legitimate need to
  later remove a supervisor who was added via Elevate (case resolved, no longer relevant)?
  Currently unspecified; leaving as a known gap rather than guessing at a removal
  workflow you haven't asked for.
