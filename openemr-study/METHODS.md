# Methods and reproducibility

## Original study

The original study selected 24 known OpenEMR CVEs: 16 disclosed in 2026 after the recorded model training cutoffs and 8 older disclosures. The researcher traced each flaw to an introducing commit and supplied the selected vulnerable file's introducing diff, stripped of commit-message hints. Twenty-one scored cases have a full trace and three are partial. Selection was retrospective; this is not an unrestricted full pull-request benchmark.

Claude Code ran the [generic review prompt](prompts/generic.txt) three times per case with the recorded Haiku 4.5 and Sonnet 5 identities. Reviews were scored Caught, Partial or Missed against the known vulnerability. The case score is the majority of three; a one-of-each split is Partial. Human adjudication verified the original case-level scores. The original result was Haiku 8/24 and Sonnet 20/24 Caught. The original Sonnet alias, complete request bytes, repository reads, token use and latency were not retained, so this historical execution cannot be reconstructed exactly. The full original [methods](data/original/METHODS.md), [rubric](data/original/rubric.md), [scores](data/original/scores.csv), [case inventory](data/original/cves.csv) and raw reviews in the [archive](evidence/study-results.zip) remain available.

## Full-set Haiku prompt experiment

The new experiment ran the exact original [generic prompt](prompts/generic.txt) against the exact existing [security prompt with OWASP Top 10 and touched-code instruction](prompts/security_policy.txt). The original 24 blinded diffs and ten benign controls were copied byte for byte into [inputs](inputs/). The [case manifest](data/prompt-followup/manifest.json) and [control manifest](data/prompt-followup/controls_manifest.json) record source paths and SHA-256 hashes. No related file, advisory, CVE identifier, scoring key, previous review or review tool was supplied to the reviewer. The same input bytes and request settings were used in both prompt arms.

Each case and control received three fresh, independent Anthropic Messages API calls per arm. Every call requested exactly `claude-haiku-4-5-20251001`, `max_tokens=16000`, one user message and no explicit sampling or effort setting. The returned model ID and normal `end_turn` were checked. The 204 review calls and 204 separate judge calls all completed without an execution error or retry. The five post-cutoff CVEs caught by Haiku in the original study were reproduced with the generic prompt before the security prompt was run. The other arms were run close together. Exact requests, full responses, raw reviews, usage, timestamps and latency are in the archive.

Claude Fable 5.1 judged each new review against a [ground-truth description](data/prompt-followup/truth.json) using the original Caught / Partial / Missed rubric and majority rule. It received one review at a time without an explicit model or prompt-arm label, although the review's wording could reveal its instructions. No stricter or looser case aggregation threshold was introduced. On controls, the judge separated unsupported security claims (`FALSE`), speculative requests to verify unseen code (`SPECULATIVE`), plausible security observations (`PLAUSIBLE`) and non-security warnings. These are model judgments awaiting independent human verification. See [audit notes](data/prompt-followup/audit_notes.md).

The new generic arm is a contemporaneous control for the prompt change. It scored 11/24, versus the historical Haiku 8/24, which illustrates why the old 8 catches cannot be carried forward without rerunning all cases. The direct API had no review tools; the original Claude Code tool and context provenance is incomplete. Thus neither the new generic arm nor the stronger arm is an exact replay of the old configuration. Sonnet was not rerun in the new setup; the historical 20/24 is a reference, not a matched current comparator.

## Benign controls and cost

The ten controls are the original six security-fix patches and four routine changes. Each arm has 30 independent reviews. False-alarm counts are reviews with at least one judge-labeled unsupported security claim. Severity uses the reviewer's asserted level. Speculative security questions and correctness warnings are tabulated separately. Review volume is reported as the number of security findings, not just alarm-bearing reviews.

Costs use recorded API input and output tokens for all 102 review calls per arm (72 CVE calls plus 30 controls), and 102 judge calls per arm. The estimate uses [Anthropic's standard list prices](https://platform.claude.com/docs/en/about-claude/pricing) on 2026-10-23: Haiku 4.5 at $1 input and $5 output per million tokens, Fable 5.1 at $10 input and $50 output. Human review and taxes are excluded.

## Source preservation

The [full archive](evidence/study-results.zip) preserves the complete old `study-results/` tree, including the original study, four earlier targeted follow-ups, and the full-set prompt experiment. The [archive manifest](evidence/archive-manifest.csv) contains every member path, length and SHA-256. [verify.py](verify.py) checks the archive and the curated copies without an API key.
