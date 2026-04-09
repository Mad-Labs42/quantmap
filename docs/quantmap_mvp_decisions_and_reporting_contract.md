# QuantMap MVP Decisions, Trust Contract, and Reporting Policy

## Purpose of this document

This document captures the current product, statistical, reporting, and trust-related decisions for QuantMap so that implementation does not drift and future contributors do not have to reconstruct intent from chat history, code comments, or scattered notes.

This is a working design contract for QuantMap MVP.

It exists to answer five questions clearly:

1. What QuantMap is trying to do
2. What QuantMap must never do
3. How QuantMap defines truth, validity, confidence, and reporting
4. What behavior is required for MVP
5. What is intentionally deferred until after MVP

This document should be treated as a source of product and engineering truth unless later superseded by a more specific design doc.

---

## 1. Core project philosophy

QuantMap is a local AI benchmarking and reporting system built to help users compare inference configurations in a structured, repeatable, and trustworthy way.

QuantMap is not a magic optimization engine and is not intended to hide uncertainty behind confident language.

### QuantMap priorities

For MVP, QuantMap prioritizes:

- trustworthy raw benchmarking and scoring
- strong, readable, highly traceable reports
- robust environment characterization and run context capture
- conservative confidence and uncertainty handling
- no silent failures
- no fake precision
- no speculative causality
- no hidden score manipulation

### Non-negotiable standards

QuantMap must:

1. Keep **data separate from interpretation**
2. Avoid **over-promising**
3. Avoid **speculative causality**
4. Avoid **fake precision**
5. Avoid **silent omissions**
6. Make failures visible and understandable
7. Preserve **traceability**
8. Make confidence and uncertainty match actual evidence
9. Remain robust under ugly real-world conditions
10. Never be merely plausible-looking while being semantically wrong

If the system is technically functional but practically misleading, that is a defect.

---

## 2. MVP scope vs deferred scope

### In scope for MVP

- raw benchmarking and scoring
- run/cycle execution
- campaign comparison
- report generation
- environment characterization
- capability and confidence signaling
- warning and limitation surfacing
- statistically honest handling of sparse data
- structured, readable, LLM-friendly reporting

### Explicitly out of scope for MVP

- environment-aware scoring as a primary ranking engine
- hidden adjusted scores
- automatic recommendation authority based on heuristic contamination correction
- dashboard/UI-heavy surfaces
- advanced interactive exports as a core product surface
- fully metric-specific validity logic

### Post-MVP direction

After MVP, QuantMap may move toward:

- metric-specific validity rules
- environment-aware analysis expansion
- environment-aware scoring as an optional, clearly experimental secondary analysis
- richer interactive export surfaces (for example Excel)

---

## 3. Source of truth policy

### Canonical source of benchmark truth

For MVP, the **SQLite database is the authoritative source of benchmark results**.

The `raw.jsonl` file is an **append-only trace artifact** and is **not** the authoritative source of truth.

### Meaning of each artifact

#### SQLite database

The database is the validated, structured, canonical dataset used for:

- scoring
- analysis
- aggregation
- reporting
- winner/no-winner logic
- validity checks
- confidence and warning rollups

#### `raw.jsonl`

The raw trace file is intended as:

- an append-only forensic/debug trace
- an execution-time record of request activity
- a supplementary inspection artifact

It may include:

- incomplete requests
- aborted requests
- invalidated requests
- partially recorded activity later discarded from the canonical dataset

### Required disclaimer behavior

A metadata line should appear at the top of newly created `raw.jsonl` files indicating that:

- the SQLite database is the authoritative source of benchmark truth
- `raw.jsonl` is append-only
- `raw.jsonl` may contain incomplete or invalidated requests
- validated metrics, scoring, and reporting should come from the database

The same policy should also be documented in project docs.

### Report-level treatment

For MVP, this should be surfaced lightly and clearly, not repeatedly.

Recommended behavior:

- docs must explain it clearly
- `raw.jsonl` should self-declare it in metadata
- reports may include a single compact artifact/source-of-truth note in metadata or appendix
- disclaimers should not clutter every section

---

## 4. Cycle definition

### Formal definition

A **cycle** is a single isolated execution of a configuration under one consistent runtime context.

A cycle consists of:

- one cold request
- followed by multiple warm requests
- executed under one server/process/runtime session
- with associated environment/run-context capture

### What a cycle is not

A cycle is not:

- a single request
- an arbitrary time window
- an entire campaign
- a batch without a stable runtime boundary

### Why this matters

Cycle is the canonical unit for:

- repeatability
- variance across runs
- environment characterization attachment
- contamination visibility
- failure isolation
- per-cycle reporting

---

## 5. Valid warm sample definition

### MVP decision

For MVP, QuantMap uses a **strict completion definition**.

A warm sample is valid only if it:

- completes successfully
- produces valid benchmark metrics
- is not a timeout
- is not a crash artifact
- is not an incomplete/partial execution treated as failed

### What does not count as a valid warm sample

The following are not valid warm samples for MVP:

- timed-out requests
- requests that fail mid-execution
- requests with invalid or missing required benchmark metrics
- partial outputs being used as if they were successful completions
- crash-tainted results

### Rationale

This is the safest and most statistically honest default.

QuantMap prefers:

- clean truth over larger but ambiguous data volume
- explicit invalidity over weak implicit acceptance

### Long-term note

A more nuanced, tiered validity model may be added later, but not for MVP.

---

## 6. Expected warm count definition

### MVP decision

For MVP, the **expected warm count** is derived from the planned run schedule, not from the number of observed attempts.

### Meaning

Expected warm count means:

- how many warm requests the run plan intended to execute for that config/cycle
- not how many requests survived
- not how many attempts partially occurred

### Rationale

This avoids survivorship bias and preserves a clear distinction between:

- what should have happened
- what actually completed successfully

### Consequence

Success-rate and validity calculations must use the planned warm count, not the observed/attempted count.

---

## 7. Validity policy for scoring and ranking

### MVP decision

For MVP, QuantMap uses **Option C** as the official validity model.

That means a config is considered score-valid only if it satisfies both:

1. a minimum absolute valid-sample floor
2. a minimum success-rate threshold

### Current MVP interpretation

This means:

- a config cannot be treated as valid just because it barely has a few surviving samples
- a config cannot be treated as valid just because its success ratio looks okay at tiny sample sizes

Both conditions are required.

### Why this is the correct MVP policy

The two parts answer different questions:

- **minimum valid-sample floor**: is there enough data to compute anything responsibly?
- **success-rate threshold**: did enough of the intended run succeed for the result to represent the config honestly?

### Minimum sample floor

For MVP, the minimum valid warm-sample floor is treated as a low absolute floor aligned with low-sample honesty protections.

The current intended MVP floor is:

- **3 valid warm samples**

This should be treated as a minimum floor, not the final long-term statistical endpoint.

### Long-term direction

After MVP, the long-term goal is **metric-specific validity**, because:

- CV/stability need stronger sample requirements than some other metrics
- percentiles and ranking evidence do not all deserve the same threshold
- different metrics have different statistical fragility

That metric-specific model is not required for MVP.

---

## 8. Option B / relaxed validity policy

### Purpose

Option B exists only as a possible future **exploratory / custom / non-rigorous mode**, not as the official or recommended benchmarking path.

### MVP status

For MVP:

- Option B is not the standard reporting path
- if exposed at all, it must never be the default
- if present, it should be limited to Custom/Exploratory usage

### Core principle

Option B may be useful when strict validity would otherwise block access to results that are useful for debugging, exploratory probing, or unstable early-stage system inspection.

### Required restrictions if Option B is ever enabled

If Option B is present:

- it must be clearly and repeatedly labeled as exploratory / relaxed-validity
- it must not masquerade as the official or recommended mode
- it must not use standard winner language
- it must not present results as strictly comparable in the same way as Option C
- it must carry strong report-level disclaimer language
- it must be structurally separated, not merely textually caveated

### Allowed language under Option B

Use phrases like:

- highest observed
- exploratory result
- relaxed validity
- not strictly comparable
- use caution in interpretation

Do not use:

- best
- winner
- recommended configuration
- strongest config

### Recommended UI/product posture

If exposed later:

- make it toggleable only in Custom or explicit Exploratory modes
- require clear tooltip/help text
- make the report top matter visibly different

### Long-term note

Option B is not the destination. It is a controlled escape hatch.

---

## 9. Passing config definition

### MVP decision

A config is considered **passing** only if it:

- meets required scoring/quality thresholds
- and satisfies the active validity policy

### Meaning

Passing is not just about metrics.
A config that looks numerically acceptable but lacks sufficient valid evidence is not passing.

### Consequence

Passing controls:

- ranking eligibility
- winner eligibility
- official comparison eligibility
- report language intensity

---

## 10. Zero-valid-sample configs

### MVP decision

Configs with zero valid samples must:

- remain visible
- never receive a fabricated score
- never silently disappear
- be excluded from rankings
- be clearly labeled invalid / failed / non-comparable

### Rationale

This prevents survivorship bias and silent erasure of catastrophic failures.

### Reporting requirement

These configs should still appear in diagnostics, appendices, and elimination/failure reporting with their status preserved.

---

## 11. Tie handling

### MVP decision

QuantMap allows **explicit ties**.

### Meaning

If two configs are meaningfully tied, QuantMap should not invent a difference through arbitrary hidden tie-breakers.

### Reporting requirement

If ties occur:

- they should be documented clearly
- the report should not imply false precision
- the tie should be visible in ranking/report outputs

### Documentation requirement

Tie behavior should be documented explicitly in reports or docs where relevant.

---

## 12. What if all configs fail?

### MVP decision

If all configs fail:

- QuantMap must not assign a winner
- QuantMap must say so explicitly
- QuantMap must explain why, with visible reasons/status where possible
- the report should point to logs and diagnostics for deeper inspection

### Required language posture

Use clear wording such as:

- no configurations met the required criteria
- no ranking or winner is assigned
- see elimination diagnostics / failure details / logs

Do not present a least-bad config as a winner.

---

## 13. What if only one config passes?

### MVP decision

If only one config passes:

- QuantMap may report it as the only passing configuration
- but must clearly state the limited comparison context
- and should explain why others failed where helpful

### Required posture

Do not imply the surviving config won a broad competitive field if all others were invalid or eliminated.

Use language that reflects:

- constrained comparison
- limited competition
- reason visibility for other failures

---

## 14. Confidence model

### MVP decision

QuantMap will use **three confidence levels** for user-facing interpretation and recommendation strength:

1. **High degree of certainty**
2. **Reasonable degree of certainty**
3. **Unsure / not enough information / error**

### Philosophy

Confidence should not block the user from seeing results.
Confidence exists to shape:

- interpretation strength
- caution language
- recommendation confidence
- how strongly QuantMap speaks

### Important rule

Confidence must reflect **evidence strength**, not just pass/fail validity.

That means confidence should consider things like:

- sample sufficiency
- environment cleanliness
- observation completeness
- probe failures / capability gaps
- anomalous conditions
- consistency of evidence

### Consequence

A result may be valid enough to appear and be discussed while still being only:

- reasonably certain
- or unsure

### Suggested interpretation posture

- **High degree of certainty**: strong evidence, clean conditions, sufficient sample support
- **Reasonable degree of certainty**: usable result with caveats or limitations
- **Unsure / not enough information / error**: insufficient evidence, major limitations, or severe failure conditions

### Long-term note

Confidence should eventually cap interpretation intensity, but should not suppress visibility.

---

## 15. Summary behavior and summary/detail consistency

### What is a summary?

A summary is any compressed interpretation that appears before, above, or instead of the full evidence.

This includes:

- top-level conclusions
- winner statements
- environment summaries
- confidence summaries
- condensed “what happened” language

### Summary purpose

A good summary should quickly answer:

1. What happened?
2. Can I trust it?
3. What should I pay attention to?

### What belongs in a summary

High-value summary content includes:

- what was tested (briefly)
- what passed vs failed
- whether a winner exists
- confidence level
- major limiting factors or anomalies

### What does not belong in a summary

Avoid in summaries:

- giant raw tables
- overly detailed metric enumeration
- speculative explanations
- long justifications that require cross-reference to understand
- narrative fluff

### Consistency rule

A summary may compress detail, but it must **never contradict** the underlying details.

### MVP policy

The correct summary model is effectively:

- conservative enough not to contradict the most important caution signals
- nuanced enough to say “mostly clean, with intermittent noise” instead of bluntly flattening detail

### Working interpretation

This is best thought of as:

- worst-case consistency
- plus nuanced phrasing where appropriate

### Required outcome

If the detailed sections show important warnings or caveats, the summary cannot present a falsely clean or confident story.

---

## 16. Sparse-data and low-sample honesty

### Principle

If a metric cannot be interpreted honestly at a low sample size, QuantMap must say so explicitly rather than render numeric-looking fake precision.

### MVP behavior

For sparse or low-sample conditions:

- display `N/A` or equivalent clear wording where appropriate
- do not silently coerce `None` into `0`
- do not let low-sample configs win stability-style interpretations by accident

### Reporting consequence

Low sample size should affect:

- displayed variability metrics
- confidence language
- interpretation strength
- comparative claims

---

## 17. OOM classification policy

### Problem to solve

Not every mid-cycle crash during an OOM boundary sweep should be called OOM with full certainty.

QuantMap should avoid both:

- false certainty (“every crash is OOM”)
- brittle underdetection (“only explicit exact log string counts”)

### MVP direction

Use a **tiered evidence model**.

### Recommended classification states

1. **OOM**
   - explicit strong evidence in logs or execution path
2. **Probable OOM**
   - strong circumstantial evidence during OOM sweep, but incomplete certainty
3. **Runtime failure**
   - crash/failure without sufficient OOM evidence

### Core rule

Never label an event as definite OOM without strong evidence.

### Why this is correct

This preserves:

- automation usefulness
- honest uncertainty
- accurate diagnostics
- auditability

### Reporting/documentation requirement

Reports and docs should explain that OOM boundary handling distinguishes between:

- explicit OOM
- probable OOM
- other runtime failures

and that ambiguous cases are labeled conservatively.

---

## 18. Raw reporting vs environment-aware scoring

### MVP policy

For MVP, QuantMap focuses on:

- raw scoring
- trustworthy raw reporting
- environment diagnostics
- context and confidence signaling

### Not part of MVP core truth engine

Environment-aware scoring is **deferred**.

### Approved interim direction

Plan B is the MVP path:

- preserve raw score as the source of truth
- use environment as context and diagnostics
- improve interpretation of raw results
- do not allow hidden score rewriting to drive official conclusions

### Long-term direction

Environment-aware scoring may exist later as:

- a secondary, clearly experimental feature
- contamination-aware analysis rather than hidden correction
- side-by-side with raw score, not replacing it

### Required product positioning

If environment-aware scoring is later introduced:

- market it as a secondary, work-in-progress feature
- do not oversell it
- always show raw score alongside adjusted result
- document methodology, assumptions, and limitations thoroughly

---

## 19. Reporting contract

### Reports must do the following

- keep data and interpretation separate
- label interpretation, limitations, warnings, and implications clearly
- avoid recommendation language that outruns evidence
- preserve traceability to visible data
- surface failures rather than omitting them
- remain readable to humans
- remain interpretable by downstream LLMs without leading them too strongly

### Reports must not do the following

- silently drop failed configs
- use fake precision on sparse data
- imply causality where only correlation or overlap exists
- let one unrelated problem poison all interpretation language
- flatten low-confidence results into strong conclusions
- hide source-of-truth ambiguity

---

## 20. Documentation requirements

The following topics should be documented clearly in docs/Q&A/tips/disclaimer material:

### Must document

- SQLite DB is the authoritative source of benchmark truth
- `raw.jsonl` is append-only trace data and may include incomplete/invalidated requests
- what a cycle means
- what a valid warm sample means
- expected warm count semantics
- validity policy for MVP
- what passing means
- tie behavior
- no-winner behavior when all configs fail
- limited-comparison behavior when only one config passes
- confidence levels and what they mean
- sparse-data handling and why some metrics show `N/A`
- OOM classification tiers and what they mean
- exploratory/relaxed-validity mode constraints, if exposed

### Nice to document later

- metric-specific validity roadmap
- environment-aware scoring roadmap and limitations
- advanced/custom mode caveats

---

## 21. Open items intentionally deferred until after MVP

The following are acknowledged future work, not MVP blockers:

- metric-specific validity logic
- environment-aware scoring as a secondary experimental feature
- Excel/interactable master report outputs
- more advanced custom-mode statistical semantics
- richer environment-aware recommendation logic

---

## 22. Final MVP truth statement

For MVP, QuantMap is committed to the following:

- raw benchmark results remain primary truth
- validity is strict and conservative
- sparse data is not allowed to masquerade as strong evidence
- failed and invalid configs stay visible
- confidence shapes interpretation but does not suppress visibility
- summaries may compress, but may not contradict detail
- source-of-truth boundaries are explicit
- ambiguous failures are labeled conservatively, not optimistically

If QuantMap cannot say something honestly, it must say less—not more.

