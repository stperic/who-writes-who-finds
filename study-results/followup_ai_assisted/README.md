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
- Scoring: `../rubric.md` labels and majority rule. Final scores are in
  `final_scores.csv`: the independent judge's labels with the human
  adjudicator's rule for Caught applied (Rule B, chosen by the study author on
  2026-10-21): **Caught** = names the flaw at the right line and either rates it
  High or says it must be fixed before merge; **Partial** = names the flaw but
  treats it as optional, "verify", or a follow-up; **Missed** = does not name it.
  This matches the main study's treatment of the payment-credential case
  (CVE-2026-25146), scored Partial for a right-area, understated-severity review.

## Deviations from the main study

- The main study ran Sonnet 5 and Haiku 4.5 through the Claude Code harness.
  This follow-up calls the API directly.
- Sonnet 5 and Haiku 4.5 ran at `max_tokens=4096` (as in `quadrant.py`).
  Sonnet 5 returned empty output on F1 in all three runs (`stop_reason:
  max_tokens`; the budget went to extended thinking). Following the study's
  rule, these were logged as execution errors and re-run at `max_tokens=16000`.
  The 5.5 models ran at `max_tokens=16000` from the start.
- Scoring: a provisional scorer (Claude Opus 5.5, `scores.csv`) and an
  independent judge (Claude Fable 5.1, `judge.py`, `judge_scores.csv`,
  rationales in `judge/`). The judge saw the rubric labels, the ground truth
  and the review text, in shuffled order, without the reviewer's identity or
  the provisional score. The human adjudicator chose the rule for the one
  disagreement that mattered (see Result). The remaining non-Missed runs in
  `SPOT-CHECK.md`, where both scorers agree, have not yet had a line-by-line
  human check.

## Result

Final scores (judge labels, Rule B applied; `final_scores.csv`):

| Item | Sonnet 5 | Haiku 4.5 | Sonnet 5.5 | Opus 5.5 | Haiku 5.5 |
|---|---|---|---|---|---|
| F1 access control | M M M: **Missed** | M P M: **Missed** | M P M: **Missed** | P P P: **Partial** | M M M: **Missed** |
| F2 path traversal | M M P: **Missed** | M M C: **Missed** | P M P: **Partial** | P P P: **Partial** | C P P: **Partial** |

No model caught either flaw by majority. The 5.5 models raised the issue far
more often: 12 of 18 runs, against 3 of 12 for Sonnet 5 and Haiku 4.5.

Scorer agreement: the independent judge (Claude Fable 5.1) and the provisional
scorer (Claude Opus 5.5) agreed on 27 of 30 runs and 9 of 10 case-level scores.

| Run | Provisional | Judge | Final |
|---|---|---|---|
| F1 / Sonnet 5.5 / run 2 | Missed | Partial | Partial (judge label; no case-level change) |
| F2 / Opus 5.5 / run 1 | Partial | Caught | Partial (Rule B) |
| F2 / Opus 5.5 / run 2 | Partial | Caught | Partial (Rule B) |

The two Opus 5.5 runs name the traversal, the line and the fix, then decline to
block because the flaw is pre-existing (severity "Medium/High" and
"Medium-High"). Under a looser rule that credits naming plus a fix regardless
of the merge verdict (Rule A), Opus 5.5 on F2 would score **Caught** (C C P);
every other case-level score is the same under both rules.

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
