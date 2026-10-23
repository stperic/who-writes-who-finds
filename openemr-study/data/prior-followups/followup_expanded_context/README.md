# Follow-up: does the reviewer catch cross-file flaws when given the file the flaw depends on?

In the main study, several misses had the same explanation in the scoring
notes: the fact that made the change dangerous lived in a file outside the
diff. For CVE-2025-31121, "Without Controller.class.php in the diff, all 3 runs
treated $disable_exit as an internal PHP flag and missed the XSS." For
CVE-2026-25146, reviewers "hedged it as Low/Medium ... because
globals.inc.php is outside the diff." The deck lists "No rerun with expanded
context" as a limit. This follow-up is that rerun: the same diffs, with and
without the one file each flaw depends on.

This is a follow-up experiment, not part of the frozen study. The expectation
was recorded as H3 in `../HYPOTHESES-AND-INSIGHTS.md` before any output was read.

## Cases

| Item | Advisory | Flaw | File added as context |
|---|---|---|---|
| C1 | CVE-2025-31121 | Stored XSS: a new `$disable_exit` parameter, settable from the URL, returns raw document bytes that the controller echoes as HTML | `library/classes/Controller.class.php` |
| C2 | CVE-2026-24487 | Cross-patient access: the FHIR CareTeam service no longer filters by patient, because the base class filters only services that implement `IPatientCompartmentResourceService` | `src/Services/FHIR/FhirServiceBase.php` |
| C3 | CVE-2026-25146 | Secret exposure: the payment page writes `gateway_api_key` (the Stripe secret key) into the browser | `library/globals.inc.php` |
| C4 | CVE-2026-33321 | SSRF: unescaped stored fields in the eye exam report are rendered server-side into a PDF, and the renderer fetches URLs in them | `interface/patient_file/report/custom_report.php` |
| F1 | GHSA-9rj4-fxmj-c4r7 | Missing permission checks: Practice Settings sub-controllers can be called directly, skipping the `admin/practice` check | `controllers/C_PracticeSettings.class.php` |

Each context file is taken as of the introducing commit (`context/SOURCES.tsv`).
The diffs are the study's blinded diffs (`diffs/`). C1 to C4 come from the main
study; F1 is the AI-assisted change from `../followup_ai_assisted/`.

## Arms

Two prompts, each with and without the context file:

- **Generic:** the study's frozen prompt (`../prompt.md`).
- **Security + touched code:** the OWASP Top 10 prompt plus the touched-code
  sentence, from `../followup_security_prompt/` (its strongest arm).
- **+ context:** the dependent file is appended after the diff, introduced by:
  "For context, these related files from the repository at the same commit are
  included below. They are not changed by this pull request."

The F1 diff-only reviews were not rerun: they are the existing reviews in
`../followup_ai_assisted/ai_runs/` (generic) and
`../followup_security_prompt/reviews/security_policy/` (security + touched code).

## Runs and scoring

- Five models (Sonnet 5, Haiku 4.5, Sonnet 5.5, Opus 5.5, Haiku 5.5), 3 runs
  per model per arm, called through the API with `max_tokens=16000` and default
  settings (no `effort` set, so Opus 5.5 and Haiku 5.5 ran at their default
  `medium`, the others at `high`). 270 new reviews, plus the 30 reused F1 reviews.
- Six first attempts did not end normally and were rerun (`rerun_abnormal.py`,
  `execution_errors.csv`). Two Opus 5.5 security-prompt reviews were stopped by
  the API's cyber safety classifier mid-review; the identical request went
  through on retry. Four reviews hit the 16,000-token output limit (thinking counts toward it);
  all four finished under 16,000 tokens on the rerun (budget raised to 32,000).
  The first attempts are kept with an `.attempt1` suffix and are not scored.
- Judge: **Claude Opus 5.5**, chosen by the study author. The earlier
  follow-ups were judged by Claude Fable 5.1. Same rubric and judge prompt as
  `../followup_ai_assisted/judge.py`, with the one-sentence change for the
  security prompt used in `../followup_security_prompt/`. Ground truth for
  C1 to C4 is written from the study's verified trace notes (`judge_reviews.py`).
  The judge never sees which model or arm wrote a review. All 300 judge calls
  ended normally.
- All 30 reused F1 reviews were judged again by Opus 5.5, so every
  comparison uses one judge. This also gives a check against the earlier
  judge: Opus 5.5 and Fable 5.1 gave the same label on 29 of 30. The one
  disagreement is on a review Opus 5.5 itself wrote (Opus: Caught, Fable:
  Partial). After Rule B, all 30 final labels are identical to the earlier
  folders' final labels.
- Rule B, as in the earlier follow-ups: a judge Caught stays **Caught** only if
  the review rates the flaw High outright (including "High, pending
  verification", or a High section heading) or blocks the merge until it is
  fixed. Otherwise it becomes **Partial**. Applied to all 112 Caught labels; 9
  became Partial. Each ruling quotes the review (`rule_b_rulings.tsv`);
  `apply_rule_b.py` builds `final_detection.csv`. Case score = majority of 3
  runs; a 1-1-1 split scores Partial (`../rubric.md`).

## Results

### Model/case pairs caught by majority (5 models per case)

| Case | Generic, diff only | Generic + context | Security + touched, diff only | Security + touched + context |
|---|---|---|---|---|
| C1 XSS via `disable_exit` | 0 | 2 | 1 | 4 |
| C2 CareTeam cross-patient | 0 | 4 | 0 | 4 |
| C3 Stripe secret in page | 2 | 4 | 2 | 4 |
| C4 SSRF via PDF renderer | 0 | 0 | 0 | 1 |
| F1 missing permission checks | 0 | 0 | 4 | 3 |
| **All pairs (of 25)** | **2** | **10** | **7** | **16** |
| Runs Caught (of 75) | 7 | 27 | 22 | 47 |
| Runs naming the flaw, Caught or Partial (of 75) | 59 | 58 | 71 | 74 |

### By model (cases caught by majority, of 5)

| Model | Generic, diff only | Generic + context | Security + touched, diff only | Security + touched + context |
|---|---|---|---|---|
| Sonnet 5 | 0 | 2 | 0 | 4 |
| Haiku 4.5 | 0 | 0 | 1 | 1 |
| Sonnet 5.5 | 1 | 3 | 3 | 3 |
| Opus 5.5 | 1 | 2 | 2 | 4 |
| Haiku 5.5 | 0 | 3 | 1 | 4 |

Per-run labels for every model, case and arm are in `final_detection.csv`.

## H3, case by case

Expectations were recorded before any output was read.

| Case | Expected | Result | Verdict |
|---|---|---|---|
| C2 | Large gain: the base class states the missing fact | 0 to 4 under both prompts | Supported |
| C3 | Large gain: `globals.inc.php` calls the value "API Secret for Stripe" | 2 to 4 under both prompts | Supported |
| F1 | Large gain: the file shows the sub-controllers behind the parent check | 0 to 0 (generic), 4 to 3 (security) | **Refuted** |
| C1 | Moderate gain: positional URL mapping must be inferred | 0 to 2 (generic), 1 to 4 (security) | Supported (larger than expected under the security prompt) |
| C4 | Smallest gain, mostly escaping comments (Partial) | 0 to 0, 0 to 1 | Supported |
| All | Context helps more under the security prompt | +8 pairs (generic), +9 pairs (security) | Not supported: the gains are about equal |

Overall: **Partly supported.**

## Reading

- **Context turns hedges into blocks.** Without the file, reviewers usually
  found the right line and asked someone to check it: "Removal of `getOne()`
  override (Low, verify)", "Medium (verify)". With the file, they named the
  mechanism and blocked the merge. Runs naming the flaw barely moved under the
  generic prompt (59 to 58 of 75); runs that would block went from 7 to 27.
- **Context and the security prompt add up.** Generic, diff only: 2 of 25
  pairs. Both together: 16 of 25.
- **Context does not fix a judgment problem.** On F1 the reviewer is not
  missing a fact; it treats a pre-existing gap as out of scope. The added file
  even reassured reviewers: its constructor shows the parent `admin/practice`
  check, and reviews concluded "`C_PracticeSettings` still performs its own ACL
  check in its constructor, so this is not a bypass." What fixed F1 was adding
  the touched-code sentence to the security prompt (0 to 4 of 5, in
  `../followup_security_prompt/`).
- **The oldest small model barely uses the context.** Haiku 4.5 caught no case
  by majority with context under the generic prompt, and one (F1) under the
  security prompt. Sonnet 5 gained the most: 0 to 4 cases under the security
  prompt.
- **The C4 SSRF stays hard.** The reviewers flag the unescaped fields (the root
  cause) in every run but rarely connect them to the server-side PDF
  fetch, even with the report page that runs the renderer in front of them.
- **A security review pipeline must plan for refusals.** The cyber classifier
  stopped 2 of the 27 Opus 5.5 security-prompt reviews on the first attempt
  (none of its 27 generic-prompt reviews). Both went through on an identical
  retry, so the refusal says nothing about the code. A pipeline that treats an
  empty or cut-off review as "no findings" would silently pass those changes.
- For a routing policy: send security-sensitive changes with the files they
  depend on (interfaces, base classes, configuration that defines what a
  value means), use the security prompt with the touched-code sentence, retry
  and log refusals, and do not expect context to replace the instruction that
  pre-existing flaws in touched code count.

## Limits

- Five cases, three runs per model per arm. Differences of one pair are noise.
- One context file per case, chosen by the study author from the trace notes
  before the runs. A different file could change a result, F1 in particular.
- The judge, Claude Opus 5.5, is also one of the reviewers: 60 of the 300
  judged reviews are its own. The 30-review check against Fable 5.1 above is
  the only measure of that effect. Rule B rulings were also applied by Claude
  Opus 5.5. No line-by-line human check has been done; each ruling quotes the
  review in `rule_b_rulings.tsv`.
- False alarms with added context were not measured (no benign controls in
  this step).
- The generic diff-only arm reruns the main study's prompt on C1 to C4. Where
  it overlaps the main study (Sonnet 5 and Haiku 4.5, 8 pairs), the final
  score matches on 6. The 2 differences are Haiku 4.5 on C1 and C2 (main
  study Missed, here Partial), from new runs through the API scored by a
  different scorer.
- Cost at list prices: about $25.47 for 276 review calls (including the 6
  first attempts) and $5.87 for 300 judge calls.

## Files

- `run_reviews.py`, `rerun_abnormal.py`, `judge_reviews.py`, `apply_rule_b.py`: the scripts, in run order.
- `diffs/`, `context/` (with `SOURCES.tsv`): the inputs.
- `runs/<arm>/`: for every review, the exact prompt (`.prompt.txt`), the full API response (`.response.json`) and the review text (`.md`). Reruns also keep the raw event stream (`.response.sse.txt`); first attempts keep an `.attempt1` suffix.
- `review_status.json`, `execution_errors.csv`, `logs/`: call records, usage and console logs.
- `judge/`, `judge_detection.csv`: judge prompts, responses and labels with usage.
- `rule_b_rulings.tsv`, `final_detection.csv`: Rule B rulings and final scores.
