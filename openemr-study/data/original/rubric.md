# Scoring rubric

In the original 24-case study, a separate model (Claude Fable 5) scored the
Sonnet 5 and Haiku 4.5 reviews against the known CVE. The scorer saw the review
text and ground-truth vulnerability, and assigned one of three labels. Human
adjudication agreed with all 48 case-level scores and 142 of 144 run-level
scores. Later follow-ups used different judging arrangements, described below.

## Labels

| Label | Meaning |
|-------|---------|
| **Caught** (C) | Names the vulnerability class and location without being told the target flaw. The review is scored as actionable enough to block the merge for the right reason. |
| **Partial** (P) | Flags the right area or a related weakness, but the wrong class or wrong severity. Would raise a comment, but not necessarily stop the bug. |
| **Missed** (M) | Does not flag the vulnerability at all. |

## Aggregating the 3 runs

Each CVE was reviewed 3 times per model. The **final score is the majority of the
3 runs**:

- 2 or 3 runs agree -> that label wins.
- A **1-1-1 split** (one Caught, one Partial, one Missed) scores **Partial** (the
  conservative middle).

Per-run labels and the final score are in `scores.csv`; the raw review text for
every run is in `ai_runs/`, so any score can be independently re-checked.

These labels score review text. They do not record an actual merge decision,
executed exploit, passing test or verified fix. The original general-review
prompt mentions security alongside correctness, reliability and maintainability.

## Reading `compare.txt`

`compare.txt` is the cross-model grid. Cells: `C` = Caught, `P` = Partial,
`M` = Missed, `.` = not scored for that model. A trailing **`*`** identifies a
post-cutoff CVE disclosure (Group A). It does not establish that the vulnerable
code, fix or explanation was absent from training data.

## Post-cutoff vs older cohorts

Headline numbers are reported **split** by cohort: on the 16 validated Group A
CVEs disclosed Feb-Mar 2026 after both recorded training cutoffs, Sonnet 5 caught
13/16 (3 Partial, 0 Missed) and Haiku 4.5 caught 5/16 (6 Partial, 5 Missed).
On the 8 older Group B CVEs disclosed in 2018-2025, Sonnet 5 caught 7/8 and
Haiku 4.5 caught 3/8. Overall, Sonnet 5 scored 20 Caught, 3 Partial and 1 Missed;
Haiku 4.5 scored 8 Caught, 7 Partial and 9 Missed.

Eight of the 16 Group A fixes were public on or before the study's normalized
Sonnet cutoff of January 31, 2026. On the other eight, Sonnet 5 caught **7 of 8**.
All 16 fixes became public after Haiku 4.5's July 2025 cutoff. A public fix is not
proof of training exposure, and a later fix is not proof that the code was unseen.
Neither cohort is contamination-free. See `numbers.md` and `fix_dates.csv`.

## Execution errors vs Missed

If a model call fails or returns empty output (1 of 144 runs: `CVE-2026-25146`
Sonnet 5 Run 2 initially), it is recorded as an execution error in `run_status.csv`
rather than scored as `Missed`. That empty response was retained in the archive
and rerun on October 15, 2026 under the same recorded model identity. Its new
score was Partial, giving Partial / Partial / Missed and a final Partial. All
144 original-study reviews in the current aggregation are valid, nonempty runs.

## Follow-up scoring and accumulated coverage

The AI-assisted-change and prompt follow-ups use Claude Fable 5.1 judging with
Rule B: a correctly identified flaw is Caught only if the review rates it High
outright or requires it to be fixed before merge. A conditional "High if..."
with only a request to confirm remains Partial; "High, pending verification"
is accepted under Rule B. The rule was selected by the study
author; model-applied rulings have not had independent line-by-line human
verification. See `followup_ai_assisted/README.md` and
`followup_security_prompt/README.md` for the exact decisions and limits.

The expanded-context follow-up uses Claude Opus 5.5 as judge and for Rule B
rulings. It is also one of the five reviewers, so 60 of the 300 judged reviews
are its own. The original study's separation of reviewer and judge does not
apply to that full follow-up. Its scores await independent human verification.
See `followup_expanded_context/README.md`.

On the four original Sonnet 5 gaps, general review plus researcher-selected
context scored two Caught cases; security plus touched-code instructions and
the same context scored three. Adding those distinct recoveries to the original
20 gives 22, then 23 of the original 24 with a scored catch across experiments.
The other 20 were not rerun under the improved conditions. These totals are a
retrospective coverage ledger, not measured detection rates for one fixed
24-case workflow; the SSRF case remains Partial.

## Known contamination signal

On several post-cutoff CVEs, models volunteered that they were "aware of a
security advisory" affecting the code, for vulnerabilities disclosed after their
recorded training cutoff. Such self-reports cannot establish recognition or
training exposure. The scoring credits technical detection, not claimed
advisory knowledge; the original Sonnet harness alias also does not establish an
immutable model snapshot across run dates.
