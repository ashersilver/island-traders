# Requirement — Per-headcount medical insurance; student coverage for training (2026-06-02)

**Status:** Spec for review. Not built. New requirement ("from this time onward").
**Area:** `models/insurance.py`, the Banker insurance actions
(`engine/turn.py` sell/buy/manage insurance), the training dispatch flow
(`models/training.py` + `engine/turn.py` training), server payload + UI.

## Today
`InsurancePolicy` is a flat contract: `policy_type` ("life"/"medical"),
`premium_paid`, an expiry tick, holder + banker ids. **It has no notion of how
many people it covers**, and price is a single premium unrelated to headcount.
Training dispatch does **not** require any insurance for travelling students.

## The change

### 1. Policies cover a specified number of workers, priced by headcount
- Add `covered_count: int` to `InsurancePolicy`.
- Premium is a function of headcount: `premium = BASE_MEDICAL_PREMIUM_PER_HEAD ×
  covered_count × term_seasons` (constant **[CONFIRM value]**). The Banker's
  sell-insurance action asks for the number of workers to cover and prices
  accordingly.
- Coverage check helpers: `covers(n) -> bool`, and an island-level
  "how many of my workers/students are currently covered" rollup.

### 2. Students travelling to the Education island must be covered — paid by Education
- When a training batch is **dispatched** (students physically leave for the
  Education island), the batch's `len(worker_ids)` students must be covered by
  a **medical** policy **held and paid for by the Education Island** (the
  Educator), for the duration of the course.
- If the Educator lacks sufficient medical coverage for the incoming students,
  the dispatch is **blocked** with a clear reason ("Education Island needs
  medical cover for N more students — buy a policy from the Banker"), mirroring
  the existing PassengerSeats / capacity gates.
- Coverage is consumed/reserved per in-flight student so two concurrent batches
  can't double-count the same policy seats (same pattern as Course slots /
  workshop seats).

## Open questions (need your call)
- **A. Price:** what is `BASE_MEDICAL_PREMIUM_PER_HEAD` per season? (Suggest a
  modest figure tuned in the calibration pass, e.g. 1–2 Dp/head/season.)
- **B. Who buys for students — Educator only, or split?** The brief says the
  Education Island pays. Confirm the requester (sending island) bears none of it.
- **C. Term:** does student coverage need to last exactly the course duration,
  or a fixed minimum term? (Suggest: at least the course's away-seasons.)
- **D. Existing worker coverage:** does an island also need medical cover for its
  *own* resident workers (a passive requirement / penalty if uncovered), or is
  coverage only *required* for travelling students for now? (Suggest: only
  students are *required*; covering own workers stays optional but now has a
  concrete per-head meaning.)
- **E. What happens on a coverage lapse mid-course** (policy expires while
  students are away)? (Suggest: block new dispatches; in-flight students finish;
  flag the Educator.)

## Tests (when built)
- A medical policy covering N workers costs `per_head × N × term`; `covers(N)`
  true, `covers(N+1)` false.
- Dispatching a training batch of N students is blocked unless the Educator
  holds ≥ N student-seasons of medical coverage; cost is borne by the Educator.
- Two concurrent batches can't share the same coverage seats.
- Buying/upgrading a policy unblocks a previously-blocked dispatch.

## Dependencies / sequencing
Independent of the equity work. Touches the same training-dispatch gate as the
Course-slot / workshop checks, so it slots in alongside those. A natural unit of
work; the per-head insurance model (item 1) is a clean leaf that could go to
Codex while Claude wires the training-dispatch coverage gate (item 2).
