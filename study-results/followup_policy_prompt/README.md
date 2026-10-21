# Follow-up: does telling the reviewer that pre-existing flaws count help?

In `../followup_ai_assisted/`, AI reviewers often named the inherited flaw in
the two AI-assisted changes, then downgraded it as "pre-existing" and did not
block. This follow-up adds one sentence to the frozen prompt and measures both
sides: detection on those two changes, and false alarms on the study's 10
benign diffs.

This is a follow-up experiment, not part of the frozen study. The frozen prompt
is the control arm.

## Prompts

- **frozen:** `../prompt.md`, unchanged.
- **policy:** the frozen prompt with one sentence inserted before "If you find
  no issues, say so.":

  > Also report security flaws in code that this change touches or relies on,
  > even if they existed before this change.

## Runs (`run_reviews.py`, outputs in `reviews/`, metadata in `review_status.json`)

| Arm | Diffs | Models | Runs |
|---|---|---|---|
| policy | F1, F2 (`../followup_ai_assisted/diffs/`) | all five | 3 each (30) |
| policy | BENIGN-01 to 10 (`../benign_controls/`) | all five | 1 each (50) |
| frozen | BENIGN-01 to 10 | Sonnet 5.5, Opus 5.5, Haiku 5.5 | 1 each (30) |

Frozen-arm results for F1/F2 come from `../followup_ai_assisted/final_scores.csv`.
The frozen benign baseline for Sonnet 5 and Haiku 4.5 is the study's own reviews
in `../benign_controls/`. All new runs: Anthropic Messages API, `max_tokens=16000`.

## Scoring (`judge_reviews.py`, outputs in `judge/`)

- **Detection (F1/F2):** Claude Fable 5.1 with the identical judge prompt,
  rubric and ground truth as `../followup_ai_assisted/judge.py` (read from that
  file). Rule B then applied to every judge Caught: Caught requires rating the
  flaw High or saying it must be fixed before merge. Rulings, with the
  review's own words, are in `final_detection.csv` (column `rule_b`).
- **False alarms (benign):** the same judge sees the diff and the review and
  classifies every security finding as FALSE (wrong or unsupported by the code
  shown), SPECULATIVE (a "please verify" about code outside the diff) or
  PLAUSIBLE (a specific, credible weakness in touched or relied-on code).
  Results in `judge_benign.csv` and `benign_summary.csv`. Both arms, including
  the study's original Sonnet 5 and Haiku 4.5 reviews, were judged the same way.
- The judge never sees the reviewer's identity or the prompt arm.

## Results

### Detection on the two AI-assisted changes

| Item | Sonnet 5 | Haiku 4.5 | Sonnet 5.5 | Opus 5.5 | Haiku 5.5 |
|---|---|---|---|---|---|
| F1 frozen | Missed | Missed | Missed | Partial | Missed |
| F1 policy | M P M: Missed | P P C: **Partial** | P P P: **Partial** | P C P: Partial | M P P: **Partial** |
| F2 frozen | Missed | Missed | Partial | Partial | Partial |
| F2 policy | P P P: **Partial** | M M P: Missed | P P C: Partial | C C C: **Caught** | C C P: **Caught** |

| Measure (30 runs per arm) | Frozen | Policy |
|---|---|---|
| Runs that name the flaw | 15 | 25 |
| Runs that would block the merge (Caught) | 2 | 8 |
| Model and diff pairs Caught by majority | 0 of 10 | 2 of 10 |

### False alarms on 10 benign diffs (one review per model per arm)

| Model | Reviews with a false alarm (frozen → policy) | of which Medium or higher | Security findings raised |
|---|---|---|---|
| Sonnet 5 | 0 → 1 | 0 → 1 | 12 → 17 |
| Haiku 4.5 | 2 → 4 | 1 → 4 | 7 → 7 |
| Sonnet 5.5 | 0 → 0 | 0 → 0 | 17 → 30 |
| Opus 5.5 | 0 → 2 | 0 → 1 | 19 → 29 |
| Haiku 5.5 | 0 → 1 | 0 → 0 | 11 → 22 |
| **All** | **2 → 8 of 50** | **1 → 6 of 50** | **66 → 105** |

Most added findings are SPECULATIVE "verify this" requests (40 → 66) or
PLAUSIBLE observations about touched code (23 → 30). The one High false alarm
is Opus 5.5 on BENIGN-03: a path traversal asserted in code the diff does not
show, based on guesses about older versions.

## Reading

- The sentence works on the failure it targets. Reviewers named the inherited
  flaw in 25 of 30 runs instead of 15, and blocked on it in 8 instead of 2.
  The 5.5 models gained most; Opus 5.5 and Haiku 5.5 caught F2 by majority.
- F1 (missing permission checks on sub-controllers) stays hard: no model
  caught it by majority under either prompt.
- It has a cost. False alarms rose from 2 to 8 of 50 benign reviews, and
  security findings per review rose by about 60%, mostly "please verify"
  requests a human must triage. Haiku 4.5 is the noisiest. Sonnet 5.5 is the
  exception: more findings, zero false alarms under both prompts.
- For a routing policy, this points to using the sentence on changes that
  touch security-sensitive code (where the routing step already sends them to
  a specialist review), rather than on every PR.

## Limits

- Two vulnerable diffs and ten benign diffs, one benign review per model per
  arm. Differences of one or two reviews are within noise.
- One judge model. Rule B rulings were applied by Claude Opus 5.5, which is
  also one of the reviewers. The study author approved publication; the
  rulings have not had a line-by-line human check, so read the Opus 5.5 rows
  with that in mind. Each ruling quotes the review in `final_detection.csv`.
- The frozen benign reviews for Sonnet 5 and Haiku 4.5 are the study's
  (Claude Code harness); every other run used the API directly.
- Cost of this experiment at list prices: about $2.62 for 110 review calls and
  about $6.75 for 130 judge calls.
