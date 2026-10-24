# Follow-up: generic review prompt vs a short security (OWASP Top 10) prompt

The study's frozen prompt asks for correctness, security, reliability and
maintainability issues. It does not assign a security-specialist role, supply a
security checklist or identify the target flaw. This follow-up compares that
general review with dedicated security instructions, on older and newer models,
with the same diffs, judge and false-alarm controls as `../followup_policy_prompt/`.

This is a follow-up experiment, not part of the frozen study.

## Prompts

- **security:** a short OWASP Top 10 (2021) security-review prompt (full text in
  `run_reviews.py`): "You are a security engineer reviewing a pull request diff
  before it is merged. Review the code below for security vulnerabilities, using
  the OWASP Top 10 (2021) as a checklist: [the ten categories]. For each issue,
  give the location, the OWASP category, the problem, and the severity. If you
  find no security issues, say so."
- **security + touched code:** the same, plus the sentence tested in
  `../followup_policy_prompt/`: "Also report security flaws in code that this
  change touches or relies on, even if they existed before this change."

Compared with the two earlier arms: **generic** (`../prompt.md`, results in
`../followup_ai_assisted/final_scores.csv`) and **generic + touched code**
(`../followup_policy_prompt/final_detection.csv`).

## Runs and scoring

- Each arm: F1 and F2 (the two AI-assisted changes, 3 runs per model) and the
  10 benign diffs (1 run per model), on Sonnet 5, Haiku 4.5, Sonnet 5.5,
  Opus 5.5 and Haiku 5.5. 160 calls, API, `max_tokens=16000`.
- Judge: Claude Fable 5.1, same detection rubric, ground truth and benign
  classification as `../followup_policy_prompt/judge_reviews.py`. The recorded
  earlier judge prompt said "asked for an ordinary pre-merge review. The prompt
  never mentioned security or any vulnerability"; this arm used "asked for a
  security-focused pre-merge review. The prompt did not name this vulnerability."
  The earlier description was inaccurate: the general reviewer prompt did
  mention security as one review concern. Historical judge requests and scores
  are preserved; no rejudging has been performed to measure that wording's effect.
- Rule B applied to all 36 judge Caught labels (rulings with quotes in
  `final_detection.csv`). Security prompts ask for a severity, and many runs
  gave a conditional one ("High if `$eraname` is user-controlled, otherwise
  Low"). Applied consistently: **Caught** if the review rates the flaw High
  outright (including "High, pending confirmation" or "treat as High"), or
  blocks the merge until it is fixed ("Do not merge until Finding 1 is
  resolved", "Before merging, add validation"); **Partial** if the High is
  conditional and the review only asks someone to confirm.

## Results

### Detection on the two AI-assisted changes (30 runs per prompt)

| Prompt | Runs naming the flaw | Runs that would block (Caught) | Model/diff pairs Caught by majority |
|---|---|---|---|
| Generic (study prompt) | 15 | 2 | 0 of 10 |
| Generic + touched code | 25 | 8 | 2 of 10 |
| Security | 30 | 10 | 3 of 10 |
| Security + touched code | 29 | 16 | **7 of 10** |

| Item | Prompt | Sonnet 5 | Haiku 4.5 | Sonnet 5.5 | Opus 5.5 | Haiku 5.5 |
|---|---|---|---|---|---|---|
| F1 access control | Generic | Missed | Missed | Missed | Partial | Missed |
| | Security | Partial | Partial | Partial | Partial | Partial |
| | Security + touched | Partial | **Caught** | **Caught** | **Caught** | **Caught** |
| F2 path traversal | Generic | Missed | Missed | Partial | Partial | Partial |
| | Security | **Caught** | **Caught** | Partial | Partial | **Caught** |
| | Security + touched | **Caught** | **Caught** | Partial | **Caught** | Partial |

### False alarms on 10 benign diffs (one review per model per prompt)

| Prompt | Reviews with a false alarm | of which Medium or higher | Security findings raised |
|---|---|---|---|
| Generic | 2 of 50 | 1 | 66 |
| Generic + touched code | 8 of 50 | 6 | 105 |
| Security | 12 of 50 | 6 | 118 |
| Security + touched code | 18 of 50 | 13 | 173 |

| Model | Generic | Generic + touched | Security | Security + touched |
|---|---|---|---|---|
| Sonnet 5 | 0 | 1 | 4 | 5 |
| Haiku 4.5 | 2 | 4 | 6 | **9** |
| Sonnet 5.5 | 0 | 0 | 0 | 0 |
| Opus 5.5 | 0 | 2 | 0 | 0 |
| Haiku 5.5 | 0 | 1 | 2 | 4 |

(Reviews with at least one false alarm, out of 10.)

## Reading

- **Prompt choice changed the scores on these two cases.** With the generic
  prompt, no model caught either flaw by majority. With a security prompt plus the
  touched-code sentence, 7 of 10 model/diff pairs caught them, and F1, not caught
  by any model before, was caught by four of five.
- **The older models improved on these two cases.** Haiku 4.5
  went from missing both flaws to catching both. Sonnet 5 caught F2.
- **False alarms differed by model in these ten controls.** Sonnet 5.5 raised no
  false alarm under any prompt, and Opus 5.5 none under the security prompts.
  Haiku 4.5 under the strongest prompt raised a Medium-or-higher false alarm
  on 9 of 10 harmless changes. The newer models are also more likely to hedge
  ("High if user-controlled, please confirm"), which is why Sonnet 5.5 stays at
  Partial on F2.
- **Stronger instructions increased findings and false alarms overall.** Security
  findings on the benign diffs rose from 66 to 173 across the four prompts, mostly "please verify"
  requests.
- Routing security-sensitive changes to a stronger prompt is a hypothesis to
  evaluate locally. This study did not measure whether automated routing reduces
  false alarms, review time or cost while preserving required coverage.

## Limits

- Two vulnerable diffs and ten benign diffs, one benign review per model per
  prompt. Differences of one or two reviews are within noise.
- One judge. Rule B rulings applied by Claude Opus 5.5, which is also a
  reviewer. The study author approved publication; the rulings have not had a
  line-by-line human check. Each ruling quotes the review in
  `final_detection.csv`.
- The judge knew these reviews came from a security-focused prompt (see the
  changed sentence above).
- The original Sonnet 5 and Haiku 4.5 general-control reviews came from the
  Claude Code harness; the new prompt arms used the API. General-prompt controls
  were reclassified for this follow-up, so their false-alarm totals need not equal
  the original study's control scoring. Historical request and tool-access
  provenance is incomplete; the original Sonnet alias does not establish an
  immutable snapshot across dates.
- Sonnet 5 had false security alarms in 0/10 general-prompt control reviews and
  5/10 security-plus-touched-code reviews; 2/10 of the latter were Medium or
  higher (`benign_summary.csv`). These are individual control reviews, not
  majority-of-three case scores. The separate expanded-context experiment has
  no false-alarm controls, so these counts do not estimate the false-alarm rate
  of the combined prompt-and-context setup.
- Cost at list prices: about $4.10 for 160 review calls and $8.96 for 160 judge
  calls.
