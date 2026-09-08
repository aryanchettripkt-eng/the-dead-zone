# SETU-DRR — Remaining Problem Analysis & AI-Agent Execution Handoff

**Project:** SETU-DRR / SIH 4  
**Purpose:** Finalize the post-P0 execution strategy by analyzing the remaining P1–P3 problems, identifying safe task pairings, and defining the iteration protocol for AI-agent implementation and review.

---

## 1. Current Status

All planned **P0 correctness work is complete**:

- P0.1 — B3: explicit-zero semantics
- P0.2 — B2: remove hardcoded name-driven logic
- P0.3 — H9: four-tier triage
- P0.4 — H10: MHI monotonicity / weighted contribution correctness
- P0.5 — H7: hard candidate eligibility
- P0.6 — deterministic DB test environment

P0 is now **closed**.

The next phase is **P1 API / dynamic-alert correctness**, followed by P2 ML/planning integration and P3 production hardening.

> **Important:** Do not reopen completed P0 fixes unless a later change demonstrably regresses a P0 invariant.

---

# 2. Why We Are Changing the Execution Strategy

The remaining problem list contains many individual IDs, but they are not all independent.

Some problems share:

- the same API surface,
- the same DTOs,
- the same database tables,
- the same temporal/dynamic data path,
- the same test fixtures,
- or the same architectural boundary.

Giving every problem its own AI prompt would create unnecessary context switching and repeated investigation.

Conversely, combining too many problems into one prompt creates large diffs, unclear causality, and difficult review.

Therefore the execution strategy is:

> **Pair only problems that are genuinely coupled. Keep architectural or high-risk behavioral changes isolated.**

The AI agent should investigate broadly but change narrowly.

---

# 3. Proposed Execution Batches

## Batch 1 — API Contract Foundation

### Problems

- **B4** — Stabilize OpenAPI + generated TypeScript types
- **B5** — Shared API error envelope / contract documentation

### Pairing: **YES**

These should be handled together because both affect the canonical API contract and OpenAPI representation.

Expected dependency:

```text
B4 + B5
   ↓
canonical OpenAPI contract
   ↓
canonical error schema
   ↓
generated TypeScript types
   ↓
contract verification
```

### Scope

The agent should investigate:

- current OpenAPI generation,
- committed/generated frontend types,
- current error response models,
- exception handlers,
- endpoint response declarations,
- contract tests,
- generation scripts and CI assumptions.

### Must not do

- unrelated frontend refactoring,
- API redesign,
- opportunistic endpoint changes,
- application-domain behavior changes unrelated to B4/B5.

---

# 4. Batch 2 — Temporal / Dynamic API Reads

### Problems

- **H1** — `valid_at` must actually work
- **H2** — live/forecast MHI must actually work
- **H3** — forecast horizon must actually filter
- **H6** — tier filtering must be correct

### Pairing: **YES**

These are all read-side API correctness issues involving temporal/dynamic state or filtering.

The P0.6 deterministic DB environment has already exposed a concrete H6 defect:

- specific tier filtering currently allows rows with `NULL` tier to pass through.

This is now an observed application bug rather than a hypothetical backlog item.

### Expected investigation

Trace:

```text
request
  ↓
API endpoint
  ↓
repository/service
  ↓
DB query
  ↓
temporal/dynamic fields
  ↓
response DTO
```

For each problem, verify actual behavior rather than merely checking that a parameter exists.

### Must not do

- build the entire dynamic-trigger pipeline here,
- redesign zone architecture,
- invent temporal semantics not supported by the PRD/handoff,
- modify unrelated allocation behavior.

---

# 5. Batch 3 — Dynamic Trigger → Live MHI Pipeline

### Problem

- **B7** — Connect trigger → hazard amplification → MHI_live → zone/alert → snapshot

### Pairing: **NO — SOLO**

This is an architectural/data-flow connection rather than a simple API bug.

Target conceptual flow:

```text
dynamic trigger
      ↓
hazard amplification
      ↓
MHI_live
      ↓
zone / alert state
      ↓
snapshot / persisted result
```

### Why isolated

B7 can affect several layers simultaneously. Keeping it alone makes it possible to verify:

- source trigger selection,
- amplification logic,
- live MHI calculation,
- downstream propagation,
- persistence,
- temporal behavior,
- and regression safety.

### Must not do

Do not bundle B6, provenance, staleness, or unrelated API cleanup into the implementation.

---

# 6. Batch 4 — Deterministic Alert Fixtures + State Separation

### Problems

- **B6** — deterministic AAZ/FAZ fixtures
- **M18** — separate static classification from alert state

### Pairing: **YES**

These work naturally together after B7 exists.

The fixtures should prove that dynamic alert state is independent from permanent/static classification.

Desired conceptual test:

```text
same static classification
        +
different dynamic trigger
        ↓
different alert_state
```

while permanent relocation classification remains unchanged.

### Must not do

- convert AAZ/FAZ into permanent relocation tiers,
- fabricate live data,
- redesign the entire zone model.

---

# 7. Batch 5 — Provenance + Staleness

### Problems

- **H4** — no fabricated alert provenance
- **H5** — explicit staleness semantics

### Pairing: **YES**

These are two sides of the same trust boundary.

Conceptual model:

```text
dynamic observation
      ↓
source / cycle
      ↓
observation age
      ↓
current / stale / unavailable
```

The implementation must not manufacture:

- source,
- cycle,
- model version,
- timestamps,
- or freshness information.

Missing information should remain explicit.

### Must not do

- invent provenance values to satisfy tests,
- silently treat stale data as live,
- introduce fake model outputs.

---

# 8. Batch 6 — ModelRegistry Production Wiring

### Problem

- **B1**

### Pairing: **NO — SOLO**

B1 establishes the production inference boundary:

```text
ModelRegistry
      ↓
provider
      ↓
TerrainHazardEvaluator
```

The key validation is behavioral, not merely structural.

A useful proof is:

1. register a deterministic stub provider,
2. have it return a clearly distinguishable value,
3. invoke the production evaluator,
4. verify the registered provider's value actually affects production behavior.

### Must not do

- implement a real ML model,
- fabricate model outputs,
- change unrelated hazard formulas,
- refactor the entire model architecture.

---

# 9. Batch 7 — Dependency / Pipeline Packaging Boundary

### Problems

- **H8** — dependency correctness
- **M4** — Sentinel-1 pipeline boundary

### Pairing: **CONDITIONAL**

These may be combined only if repository investigation demonstrates that they share the same packaging/dependency boundary.

The agent must first determine whether:

```text
H8
  ↕
package / import boundary
  ↕
M4
```

is a genuine relationship.

If they are independent, keep M4 separate.

### Must not do

- blindly restructure the repository,
- remove modules without tracing imports and runtime use,
- add dependencies merely because they are convenient.

---

# 10. Batch 8 — Explanation DTO Consolidation

### Problems

- **M11**
- **M12**

### Pairing: **YES**

These should be handled together because they concern the same conceptual contract:

- canonical `FeatureContributionDTO`,
- consistent habitation/zone payloads,
- documentation and schema consistency.

Desired outcome:

```text
one canonical explanation representation
          ↓
habitation responses
zone responses
documentation / OpenAPI
```

### Must not do

- redesign unrelated response DTOs,
- change explanation semantics without evidence.

---

# 11. Batch 9 — Allocation Group-Split Semantics

### Problem

- **H12** — `allow_group_splits` must actually work

### Pairing: **NO — SOLO**

This is solver/business-behavior correctness.

The important distinction is:

```text
allow_group_splits = false
        ↓
group must remain intact
```

It must not merely be accepted as an input parameter and ignored.

### Must not do

- rewrite unrelated allocation policy,
- alter candidate eligibility rules from H7,
- weaken capacity or safety constraints.

---

# 12. Batch 10 — Scenario Output Honesty

### Problems

- **M10** — no silent scenario truncation
- **M13** — no fabricated site suitability

### Pairing: **YES**

Both concern honesty at the scenario/planning boundary:

- do not silently hide scenario results,
- do not claim suitability without actual evidence.

### Must not do

- fabricate suitability scores,
- silently discard scenarios to make an API response convenient,
- redesign the planner.

---

# 13. Batch 11 — Serving Version Gate

### Problem

- **H13**

### Pairing: **NO — SOLO**

This is a production data-serving boundary.

Desired behavior:

```text
valid active serving version
        ↓
serve compatible data

no valid serving version
        ↓
PipelineNotReady / 503
```

The implementation should make the failure explicit rather than silently serving stale or incompatible data.

---

# 14. P3 Hardening Strategy

Do **not** hand all P3 items to the AI in one prompt.

P3 should be split into focused batches after P1/P2.

## P3.1 — Database failure semantics

DB failures should produce an explicit service-unavailable response rather than an ambiguous application failure.

Potentially related to H13 later, but should be evaluated after H13 is implemented.

---

## P3.2 — Authentication / CORS / Rate Limiting

### Pairing: SOLO

Security work deserves an isolated implementation/review pass.

---

## P3.3 + P3.4 + P3.5 — Configuration / Governance

Potentially pair:

- DataQuality vocabulary canonicalization,
- duplicate capacity-policy knobs,
- authoritative governance configuration.

Only combine them if code investigation confirms they share a centralized configuration boundary.

---

## P3.6 — Transaction Ownership / False Success

### Pairing: SOLO

High-value correctness issue.

Must verify:

```text
transaction ownership
      ↓
commit / rollback
      ↓
actual persisted result
      ↓
API response
```

No successful response should be returned when the allocation was not actually committed.

---

## P3.7 — Pagination / Ordering

Potentially pair with later scenario-output work if code boundaries overlap, but do not assume that upfront.

---

## P3.8 — Migration Runner

### Pairing: SOLO

Migration correctness is infrastructure-level and should be independently validated.

---

## P3.9 — Dependency Lock / Python Version Drift

Potentially revisit together with H8 after H8's actual dependency analysis.

---

## P3.10 — Remaining Low-Severity Contract / Data-Quality Issues

Leave until the higher-value correctness work is complete.

---

# 15. Final Recommended Execution Order

```text
PASS 1   B4 + B5
           ↓
PASS 2   H1 + H2 + H3 + H6
           ↓
PASS 3   B7
           ↓
PASS 4   B6 + M18
           ↓
PASS 5   H4 + H5
           ↓
PASS 6   B1
           ↓
PASS 7   H8 + M4  [conditional]
           ↓
PASS 8   M11 + M12
           ↓
PASS 9   H12
           ↓
PASS 10  M10 + M13
           ↓
PASS 11  H13
           ↓
P3       selective hardening batches
```

This reduces the remaining work from a flat list of individual prompts into a manageable sequence of **focused engineering passes**.

---

# 16. AI-Agent Operating Rules

Every implementation prompt should follow these rules.

### 16.1 Investigate first

The agent should:

1. locate the relevant code,
2. trace callers and dependencies,
3. inspect schemas/migrations,
4. inspect existing tests,
5. understand current behavior,
6. identify the smallest correct change.

Do not prescribe an implementation before the investigation.

---

### 16.2 Change narrowly

The agent may inspect broadly, but implementation must remain within the named batch.

No opportunistic refactoring.

---

### 16.3 Preserve completed invariants

Especially:

- explicit zero semantics,
- no hardcoded habitation-name logic,
- four-tier triage semantics,
- MHI monotonicity,
- hard candidate eligibility,
- deterministic DB testing.

---

### 16.4 Never fabricate uncertainty-sensitive data

Never invent:

- ML predictions,
- alert provenance,
- timestamps,
- suitability,
- tenure,
- cost,
- live/forecast status,
- model versions,
- freshness,
- confidence,
- source metadata.

Unknown must remain explicit.

---

### 16.5 Test proportionally

Use:

1. focused unit tests,
2. focused integration tests,
3. relevant regression tests,
4. broader suites only when justified.

Do **not** automatically run the entire backend test suite for every batch.

---

### 16.6 Finish every pass with an audit

The AI must report:

- files changed,
- tests run,
- test results,
- remaining failures,
- whether failures are pre-existing,
- `git diff` summary,
- `git status`,
- any concerns or follow-up recommendations.

---

# 17. Our Iteration Protocol

We are deliberately using an iterative review loop.

```text
Human selects batch
        ↓
AI investigates + implements
        ↓
AI reports evidence
        ↓
Human reviews implementation
        ↓
YAY
  └── move to next batch

NAY / CONDITIONAL
  └── send corrective prompt
        ↓
      AI fixes
        ↓
      re-test
        ↓
      review again
```

A failed or incomplete AI report does **not** mean the entire approach is discarded.

If the architecture is sound but implementation has a flaw, issue a narrow corrective prompt.

---

# 18. Special Lesson From P0.6

The deterministic DB environment exposed an important existing H6 behavior:

> Specific tier filtering currently allows `NULL` tier rows through.

This demonstrates why future work must distinguish:

```text
planned problem
        vs.
observed defect
```

The remaining priority list should therefore be treated as the roadmap, while actual repository behavior and focused tests remain the final authority for implementation decisions.

---

# 19. Current Starting Point

We are now at:

```text
P0  ████████████████████ COMPLETE

P1  ░░░░░░░░░░░░░░░░░░░░ NEXT
P2  ░░░░░░░░░░░░░░░░░░░░
P3  ░░░░░░░░░░░░░░░░░░░░
```

**Next implementation pass: B4 + B5.**

Before issuing that implementation prompt, perform the repository-level dependency investigation described by this handoff and verify that the proposed pairing still matches the actual codebase.

---

## 20. Definition of Done for a Batch

A batch is complete only when:

- the intended behavior is implemented,
- relevant tests prove it,
- no known requirement is silently weakened,
- no fabricated data has been introduced,
- completed P0 invariants remain intact,
- no unrelated refactoring has slipped into the diff,
- the AI's final report clearly identifies any unresolved issue,
- and the human review says **YAY**.

**Do not mark a problem complete merely because tests pass.**

The implementation must be correct relative to the PRD, handoff, problem definition, and actual system behavior.
