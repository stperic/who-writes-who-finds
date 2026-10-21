# Follow-up: AI review of AI-assisted changes that carried a flaw forward

Two OpenEMR advisories trace to AI-co-authored commits that rewrote already
vulnerable code and kept the flaw (see `../ai_trailer_trace/findings.csv`).
This follow-up asks whether AI reviewers would have flagged the flaw if they
had reviewed those changes as pull requests.

| Item | Advisory | AI-assisted commit | Vulnerable file |
|---|---|---|---|
| F1 | GHSA-9rj4-fxmj-c4r7 (published 2026-08-18) | `0381a2dbc1` (2026-03-20, `Co-authored-by: Claude`) | `library/classes/Controller.class.php` |
| F2 | GHSA-m6q6-5j87-3cmp (published 2026-08-18) | `ac5bb730d2` (2026-02-12, `Co-authored-by: Claude`) | `interface/billing/sl_eob_process.php` |

## Reviewers and exposure

| Model | Training cutoff | Exposure to these flaws |
|---|---|---|
| Sonnet 5 (`claude-sonnet-5`) | 2026-01-31 | Before both commits and both advisories. |
| Haiku 4.5 (`claude-haiku-4-5-20251001`) | 2025-07-31 | Before both commits and both advisories. |
| Opus 5.5 (`claude-opus-5-5`) | June 2026 | After both commits (the vulnerable code may be in training data), before the fixes (2026-08-16) and advisories (2026-08-18). |
| Sonnet 5.5 (`claude-sonnet-5-5`) | Not documented | Unknown. |
| Haiku 5.5 (`claude-haiku-5-5`) | Not documented | Unknown. |

## Method

- Diffs: `git show --format= <commit> -- <vulnerable file>` (commit message
  stripped, file-scoped), in `diffs/`.
- Prompt: the frozen prompt in `../prompt.md`, unchanged.
- Runs: 3 fresh runs per model per diff via the Anthropic Messages API
  (`run.py`), default settings otherwise. Raw outputs in `ai_runs/`, call
  metadata in `run_status.json`.
- Scoring: `../rubric.md` labels and majority rule, in `scores.csv`. Applied
  consistently as: **Caught** = names the flaw at the right line and rates it
  High or says it must be fixed before merge; **Partial** = names the flaw but
  treats it as optional, "verify", or a follow-up; **Missed** = does not name it.

## Deviations from the main study

- The main study ran Sonnet 5 and Haiku 4.5 through the Claude Code harness.
  This follow-up calls the API directly.
- Sonnet 5 and Haiku 4.5 ran at `max_tokens=4096` (as in `quadrant.py`).
  Sonnet 5 returned empty output on F1 in all three runs (`stop_reason:
  max_tokens`; the budget went to extended thinking). Following the study's
  rule, these were logged as execution errors and re-run at `max_tokens=16000`.
  The 5.5 models ran at `max_tokens=16000` from the start.
- Scores are provisional: one scorer (Claude Opus 5.5), no human check yet.
  The main study used a separate judge model plus human adjudication. The
  scorer is the same model as one of the reviewers, so the Opus 5.5 rows in
  particular need an independent check.

## Result

| Item | Sonnet 5 | Haiku 4.5 | Sonnet 5.5 | Opus 5.5 | Haiku 5.5 |
|---|---|---|---|---|---|
| F1 access control | M M M: **Missed** | M P M: **Missed** | M M M: **Missed** | P P P: **Partial** | M M M: **Missed** |
| F2 path traversal | M M P: **Missed** | M M C: **Missed** | P M P: **Partial** | P P P: **Partial** | C P P: **Partial** |

No model caught either flaw by majority. The 5.5 models raised the issue far
more often: 11 of 18 runs, against 3 of 12 for Sonnet 5 and Haiku 4.5.

The pattern is the same in nearly every run that found the flaw: the reviewer
named it correctly, then rated it as pre-existing, lowered the severity, and
did not block the merge, because the diff had not introduced it. Opus 5.5
named the exact unprotected controllers (`x12_partner`, `insurance_company`,
`pharmacy` and others) in all three F1 runs, and rated the gap Low or Medium.
On F1, one Sonnet 5 run cleared the access-control code as "a faithful,
cleaner extraction of the previous logic", which is accurate and is why the
inherited gap passed: the reviewer checked that the refactor preserved
behavior, and the preserved behavior was the vulnerability.

Only 2 of 30 runs would have blocked the merge for the right reason (Haiku 4.5
F2 run 3, Haiku 5.5 F2 run 1).
