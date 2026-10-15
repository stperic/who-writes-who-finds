# Scoring rubric

A separate model (Claude Fable 5) scored every review against the known CVE, so
no model grades its own output. The scorer saw the model's review text and the
ground-truth vulnerability, and assigned one of three labels.

## Labels

| Label | Meaning |
|-------|---------|
| **Caught** (C) | Names the vulnerability class and location unprompted. A real reviewer reading this would block the merge for the right reason. |
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

## Reading `compare.txt`

`compare.txt` is the cross-model grid. Cells: `C` = Caught, `P` = Partial,
`M` = Missed, `.` = not scored for that model. A trailing **`*`** means that CVE
was **clean for that model** (disclosed after the model's training cutoff), as
opposed to potentially memorized.

## Post-cutoff vs older cohorts

Headline numbers are reported **split** by cohort: on the 14 validated post-cutoff
Group A CVEs (disclosed Feb-Mar 2026), Sonnet 5 caught 12/14 (plus 2 Partial) and
Haiku 4.5 caught 5/14 (plus 6 Partial, 3 Missed); on the 8 older Group B CVEs
(disclosed 2018-2025), Sonnet 5 caught 7/8 and Haiku 4.5 caught 3/8. Because 6 of
the 14 Group A security fixes were merged into OpenEMR's public repository in mid-
to-late January 2026 (days before Sonnet 5's January 31, 2026 cutoff), `numbers.md`
also reports the subset of 8 Group A CVEs whose fix became public *after* January
31, 2026: Sonnet 5 caught **7 of 8 (88%)**. Haiku 4.5's July 2025 cutoff predates
every Group A fix and disclosure.

## Execution errors vs Missed

If a model call fails or returns empty output (1 of 144 runs: `CVE-2026-25146`
Sonnet 5 Run 2), it is recorded as an execution error in `run_status.csv` and
excluded from the valid run aggregation rather than scored as `Missed`. With 2 valid
runs on `CVE-2026-25146` (`Partial` and `Missed`), disagreement scores `Partial`.

## Known contamination signal

On several post-cutoff CVEs, models volunteered that they were "aware of a
security advisory" affecting the code, for vulnerabilities disclosed after their
own training cutoff, which they could not have seen. That over-claiming is itself
a finding, and a reason the scoring credits only the technical detection, not any
claimed advisory knowledge.
