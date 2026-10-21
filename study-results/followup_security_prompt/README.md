# Follow-up: generic review prompt vs a short security (OWASP Top 10) prompt

The study's frozen prompt is deliberately generic: it never asks for security.
That measures what a general AI reviewer finds unprompted. A security team
would instead route security-sensitive changes to a security review. This
follow-up measures that case, on older and newer models, with the same
diffs, judge and false-alarm controls as `../followup_policy_prompt/`.

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
  classification as `../followup_policy_prompt/judge_reviews.py`. One sentence
  of the detection judge prompt changed, because it was no longer true: "asked
  for an ordinary pre-merge review. The prompt never mentioned security or any
  vulnerability" became "asked for a security-focused pre-merge review. The
  prompt did not name this vulnerability."
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

- **The prompt matters as much as the model.** With the generic prompt, no
  model caught either flaw. With a short security prompt plus the
  touched-code sentence, 7 of 10 model/diff pairs caught them, and F1, missed
  by every model before, was caught by four of five.
- **Older models close the detection gap when asked for security.** Haiku 4.5
  went from missing both flaws to catching both. Sonnet 5 caught F2.
- **Newer models keep their advantage in precision.** Sonnet 5.5 raised no
  false alarm under any prompt, and Opus 5.5 none under the security prompts.
  Haiku 4.5 under the strongest prompt raised a Medium-or-higher false alarm
  on 9 of 10 harmless changes. The newer models are also more likely to hedge
  ("High if user-controlled, please confirm"), which is why Sonnet 5.5 stays at
  Partial on F2.
- **Every gain in detection costs triage.** Security findings on the benign
  diffs rose from 66 to 173 across the four prompts, mostly "please verify"
  requests.
- For a routing policy: route security-sensitive changes to a security review
  with the touched-code instruction, run it on a model with a low false-alarm
  rate, and keep the generic review for everything else.

## Limits

- Two vulnerable diffs and ten benign diffs, one benign review per model per
  prompt. Differences of one or two reviews are within noise.
- One judge. Rule B rulings applied by Claude Opus 5.5, which is also a
  reviewer; they need a human check before publication.
- The judge knew these reviews came from a security-focused prompt (see the
  changed sentence above).
- Cost at list prices: about $4.10 for 160 review calls and $8.96 for 160 judge
  calls.
