# Planned validation run

**Status: prepared, not executed.** This folder contains the protocol and one
standard-library script for a later matched OpenEMR review experiment. No new
model result or score is claimed here. The original study, its follow-ups and
their evidence remain unchanged.

## Decision after the methods review

The presentation currently combines several experiments. They answer different
questions and cannot form one five-row, 24-case comparison:

| Condition | Existing scope | Treatment in the next report |
|---|---|---|
| Generic prompt, diff only | Original 24-case Claude Code study; new 24-case Haiku API arm | Core matched run |
| Generic prompt plus related file | Four selected original CVEs and one other advisory | Separate context result |
| Security prompt, diff only | New 24-case Haiku API arm | Core matched run |
| Generic prompt plus requirements | No run | Future eligible subset only |
| Security prompt plus requirements | One Sonnet PDF case, with two different cards | Separate feasibility result |
| Security prompt plus related file | Same selected context follow-up | Report with the context result |

The existing [context follow-up](../data/prior-followups/followup_expanded_context/README.md)
selected related files using known flaw traces. The existing
[PDF requirement](../data/pdf-requirement-followup/README.md) was proposed after
the flaw was known and was tested under the security prompt only. Both remain
valuable examples, with their own denominators. Neither is a measured X/24
workflow. The targeted follow-ups also used some different judging rules,
judges, model sets and output limits, so their scores will not be pooled with
the core run.

## Core matched experiment: frozen before calls

**Question:** On the same 24 historical CVE diffs and 10 original benign
controls, what changes when the review instructions change, and how do Haiku
4.5 and Sonnet 5 compare under the same current setup?

- Inputs: the 24 `item_XX.diff` files and 10 `BENIGN-XX.diff` files in
  [`../inputs/`](../inputs/). The existing case and control manifests supply
  SHA-256 checksums. The introducing diffs remain selected historical file
  diffs, not whole pull requests.
- Prompts: exact [`generic.txt`](../prompts/generic.txt) and exact
  [`security_policy.txt`](../prompts/security_policy.txt). The latter contains
  the OWASP checklist and the touched-or-relied-on-code sentence. Prompt and
  diff are the only reviewer inputs. No CVE ID, advisory, ground truth,
  previous review, related file, requirement card or repository tool is sent.
- Models: request `claude-haiku-4-5-20251001` and `claude-sonnet-5`. The Haiku
  identity is dated; Sonnet is an alias and may not be an immutable snapshot.
  Save and report both requested and returned model IDs and the run date.
- API: Anthropic Messages API version `2023-06-01`, one user message, no
  conversation history or tools, `max_tokens=16000`, no explicit sampling or
  effort parameter, no `cache_control`. Every response must report `end_turn`,
  nonempty text, the requested model ID and zero cache creation/read tokens.
  There is no manual server-cache flush. Each call starts a fresh session.
- Design: 24 cases + 10 controls, 2 models, 2 prompts, 3 independent reviews
  each: **408 reviewer calls**. The separate model judge would make another
  **408 calls**. Keep the same frozen settings across all four arms.

The [protocol](protocol.json) freezes the settings and shuffle seed. The runner
first schedules three Haiku generic reviews for each of the five post-cutoff
findings caught in the original study: `item_02`, `item_04`, `item_06`,
`item_08` and `item_15`. These are the first **15** calls and count in the
final 408. The separate judge provisionally scores those 15 reviews and saves
the five case results in `checkpoint_summary.json` **before** any
security-prompt call. Continue even if a
finding is not reproduced; the checkpoint must not be used to revise a prompt,
item, scoring rule or stopping decision. Then the remaining arms for those
five items run next. The other
29 items follow in shuffled item blocks, with model and prompt arms interleaved
within each block. No security-prompt call precedes the five-case generic
checkpoint.

## Scoring and signoff

The separate Fable 5.1 judge receives one review and the case ground truth,
or one benign diff and review. It receives no explicit reviewer model or arm
label. Review wording may still reveal the arm. Its prompts are frozen in
[`study.py`](study.py). Judge outputs are **provisional**.

Use the [original Caught / Partial / Missed rubric](../data/original/rubric.md)
and original majority-of-three rule. A 1-1-1 split is Partial. Do not add the
later follow-ups' Rule B. Count only Caught as fully caught, and publish
Partial and Missed separately. Report all three run labels for every case.

For controls, separate asserted unsupported security claims, speculative
questions, plausible security observations and non-security warnings. Report
false-alarm-bearing reviews out of 30, affected controls out of 10, severity,
finding volume and review length. A benign change is only **not known to
introduce** a vulnerability. A real flaw in touched or relied-on code may be
valid under the security prompt. Do not automatically score it as false.

**Before any paid reviewer call**, have an independent application-security
reviewer check the 24 mechanisms and supplied historical revisions. `prepare`
creates `snapshot/ground_truth_signoff_template.json`; copy it to
`ground_truth_signoff.json`, then record the reviewer's name, UTC date, both
confirmations and an evidence note for each case. The runner requires all 24
entries and freezes the signed file's hash before the first call. An AI role
review is not a substitute for this human check.

Before publication, also obtain independent application-security review of:

1. Changed and borderline Caught / Partial / Missed judgments, all cases with
   mixed run labels, and any case that decides a headline comparison.
2. Every asserted false security alarm on a control, checked against enough
   historical surrounding code to distinguish a false claim from an inherited
   flaw. The blind packet includes each control's historical OpenEMR commit and
   changed-file link for this check. Keep written reasons and any score changes.
3. The recorded reasons for excluding seven other inventoried CVEs. Do not
   change the frozen 24-case denominator.

The runner creates a blinded review packet and a separate private mapping key.
It does not declare human signoff. The summary stays marked provisional until
the verification record is complete. State the number of human-checked runs
and unresolved calls in the final report.

## What to retain and report

Keep the frozen protocol, source hashes, shuffled job order, exact request JSON,
every attempt including errors, raw API response, response ID, returned model,
UTC time, stop reason, cache counters, usage and latency. Keep the judge's exact
request, response, rationale and parsed label. An invalid or empty attempt is
an execution error, never a Missed. Retry only the same frozen request and
preserve the earlier attempt. Do not silently replace a model or item.
The runner retains a content-addressed copy of any filled human scoring CSV,
including reviewer names, dates and reasons, and records its hash in the summary.

For each arm report Caught / Partial / Missed out of 24, individual run labels,
mixed-label cases out of 24, and false-alarm reviews out of **30 reviews of 10
controls**. Report
finding volume and severity, reviewer and judge token use, latency and a cost
estimate tied to a dated price source. Compare gained, retained and lost cases
between prompts. The script records token usage; the dated cost estimate is
calculated when the results are published. Report the first five checkpoint
cases separately from the remaining 19 as a check on run-order effects. A
matching total alone does not establish model equivalence.
The historical 8/24 and 20/24 remain references, not rows in the matched
current comparison. Keep the whole-repository [Snyk baseline](../snyk-baseline/README.md)
separate because its input and execution conditions differ.

## Run later

The script requires Python 3.11 or later and only its standard library. These
first commands make **no API calls**. The recommended output path is ignored by
Git until the evidence is reviewed and deliberately curated.

```sh
python3 openemr-study/next-run/study.py plan
python3 openemr-study/next-run/study.py prepare --out build/openemr-next-run
python3 openemr-study/next-run/study.py verify --out build/openemr-next-run
```

Before running, copy and complete the ground-truth signoff template:

```sh
cp build/openemr-next-run/snapshot/ground_truth_signoff_template.json build/openemr-next-run/ground_truth_signoff.json
```

When it has been independently checked, set `ANTHROPIC_API_KEY` in the
environment and run each stage. The
`--execute` flag is required for paid model calls. An interrupted stage resumes
completed calls and preserves attempts. The `rest` stage refuses to start until
all 15 checkpoint calls completed validly.

```sh
python3 openemr-study/next-run/study.py run --out build/openemr-next-run --phase checkpoint --execute
python3 openemr-study/next-run/study.py judge --out build/openemr-next-run --phase checkpoint --execute
python3 openemr-study/next-run/study.py run --out build/openemr-next-run --phase rest --execute
python3 openemr-study/next-run/study.py judge --out build/openemr-next-run --phase rest --execute
python3 openemr-study/next-run/study.py verify --out build/openemr-next-run --complete
python3 openemr-study/next-run/study.py packet --out build/openemr-next-run
python3 openemr-study/next-run/study.py summarize --out build/openemr-next-run
```

The packet is at `build/openemr-next-run/packet/blind/`; keep
`packet/private/key.csv` and `packet/private/model_judgments.jsonl` away from
the first-pass reviewer. A filled copy of
`human_scores_template.csv` can be supplied to `summarize` with `--human-csv`.
Only rows with a written reason count as human-checked. For a control row,
provide all three security-class counts and one semicolon-separated severity
per false claim. Identify the human reviewer and review date on every completed
row; the script rejects incomplete overrides.
The generated `summary.json` is provisional even when overrides are present;
publication requires documented human signoff. The filled CSV is copied under
`human_adjudication/` with its SHA-256 in the summary. The API key is never
written to the run directory.

## Separate future context and requirements studies

**Context:** If we want a full-set context rate later, define and freeze a
related-file selection rule before looking at model outputs or the known flaw.
Snapshot each file at the vulnerable revision and apply the same selected file
to generic and security prompts, plus matching benign controls. The complete
prompt-by-context design has four cells: generic diff, generic plus context,
security diff, security plus context. The existing five-case probe already has
these cells but used hindsight-selected files. Keep its current denominator.

**Requirements:** Build an eligible set only from requirements that demonstrably
existed at the historical revision, with provenance, owner and timestamp. Use
the **same** requirement in generic-plus-requirements and
security-plus-requirements arms and suitable benign controls. Functional and
security cards are different treatments and need separate rows. If only `K`
cases qualify, report results out of `K`, not out of 24. The proposed PDF
security card remains a retrospective one-case demonstration and cannot be
included as an authentic historical requirement.

These studies are intentionally not activated by the core runner. Their input
selection and eligibility rules must be signed off before additional scripts
or model calls are justified.
