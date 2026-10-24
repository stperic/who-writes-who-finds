# OpenEMR review study

This is the clean reading and reproduction entry point for the OpenEMR portion of **Who Writes the Bug, Who Finds the Bug?** The original study and the later Haiku prompt experiment are separate measurements. The complete former `study-results/` tree, including every raw review, request, response, script and prior follow-up, is preserved in one [downloadable archive](evidence/study-results.zip).

## Findings at a glance

| Evaluation | Haiku 4.5 Caught | Sonnet 5 Caught | Status |
|---|---:|---:|---|
| Original 24 cases, generic prompt, Claude Code | **8/24** | **20/24** | Human-adjudicated original study; execution provenance incomplete |
| New 24-case direct API baseline, same generic prompt | **11/24** | Not run | Model-judged; human verification pending |
| New 24-case direct API run, OWASP plus touched-code prompt | **19/24** | Not run | Model-judged; human verification pending |

The new Haiku comparison gained eight Caught cases, retained eleven and lost none when the prompt changed. The stronger prompt also produced false security alarms in **24/30** benign reviews, compared with **8/30** using the generic prompt. These are three independent reviews of each of ten controls, with false security claims separated from speculative questions and correctness warnings. Haiku with the stronger prompt approaches Sonnet's **historical** 20/24 total. Sonnet was not rerun under the new conditions, so this is not a model-equivalence result.

A separate [Snyk Code whole-repository baseline](snyk-baseline/README.md) clearly identified **6/24** of the same selected vulnerabilities, with **1/24** borderline and excluded from Caught. It used today's scanner at the original introducing commits, one scan per case, while the AI reviewers saw selected diffs. Its case matches await independent human verification, and it did not scan benign controls.

A separate [PDF requirement follow-up](data/pdf-requirement-followup/README.md) revisited one original Partial case. With the same historical diff and review prompt, a functional PDF requirement produced **0/3** explicit SSRF findings; a proposed security requirement about resource loading produced **3/3**. That requirement was drafted with hindsight and attached manually. This is a feasibility probe for requirement-informed review, not a new 24-case score or a demonstrated ZZ-Trace route.

A later [benign-control follow-up](data/false-alarm-followup/README.md) measured the false-alarm burden of the added-context and PDF-card setups. With one related file on each of the ten original controls, Sonnet 5 made false security claims in **1/30** generic-prompt reviews and **20/30** security-prompt reviews. On five later Eye Exam report changes, the functional and proposed security PDF cards produced **4/15** and **7/15** false-alarm reviews respectively. These are provisional model-judge classifications, and one High-severity PDF judgment is borderline. The experiment retains all 150 reviews, 150 judgments, input snapshots, reasons and exact requests in a separate archive.

## Read the study

- [Planned matched validation run](next-run/README.md): frozen design, five-case checkpoint, execution and verification script. It has not been run.
- [24-CVE audience FAQ](CVE-FAQ.md): the bug, historical source snapshot, recorded upstream patch and evidence link for every scored case.
- [Results](RESULTS.md): full 24-case and 10-control tables, variability, cost, latency and limitations.
- [Methods](METHODS.md): case selection, exact prompts, execution setup, scoring and what can be reproduced.
- [Appendix slide and spoken answer](APPENDIX.md): presentation-ready wording.
- [Case pages](cases/): the six new reviews and judge rationales for each CVE, with links to its blinded diff.
- [Control pages](controls/): all six reviews and classifications for each benign change.
- [Case matrix](data/case-matrix.csv) and [control run scores](data/prompt-followup/benign_scores.csv): machine-readable results.
- [Complete evidence archive](evidence/study-results.zip) and [archive manifest](evidence/archive-manifest.csv): exact original and follow-up artifacts.
- [PDF requirement follow-up](data/pdf-requirement-followup/README.md): exact cards, six prompts, raw responses, review text, results and reproduction script for the one-case probe.
- [Context and PDF benign controls](data/false-alarm-followup/README.md): 150 new reviews, separate denominators, false-alarm scores, individual findings and complete raw evidence.
- [Snyk Code baseline](snyk-baseline/README.md): 24 pinned whole-repository scans, full case-by-case score, run metrics, reproducible scripts and verified raw evidence.

## Verification status

The new Haiku results were scored by a separate Fable 5.1 model under the original Caught / Partial / Missed rubric. Changed and borderline outcomes, and false-alarm classifications, **still require an independent human review**. The [audit notes](data/prompt-followup/audit_notes.md) identify the most consequential borderline calls. The archive contains the blinded human packet and its separate key. No human signoff is claimed here.

To check archive hashes, input copies, run counts and score aggregation without calling an API, run:

```sh
python3 openemr-study/verify.py
```

The root repository includes a presentation, tools and other experiments. This folder contains the OpenEMR study in a form meant to be read and reviewed on GitHub.
