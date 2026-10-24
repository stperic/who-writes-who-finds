# False-alarm controls for the context and PDF follow-ups

This is a new, separate control experiment. It does not alter the original
OpenEMR study, the five-case expanded-context follow-up, or the one-case PDF
requirement probe. Those earlier follow-ups had no benign-control runs. This
experiment measures what the same reviewer settings say about changes not
known to introduce vulnerabilities.

## Inputs and arms

| Control set | Arms | Controls | Repetitions | Review calls |
|---|---|---:|---:|---:|
| Original benign changes with one related file | Exact generic prompt; exact OWASP plus touched-code prompt | 10 | 3 per arm | 60 |
| Original benign changes with a PDF card | Functional card; proposed security card, both appended to the OWASP plus touched-code prompt | 10 | 3 per arm | 60 |
| Later Eye Exam report changes with a PDF card | Same two PDF cards | 5 | 3 per arm | 30 |

The first two rows use the [original ten control diffs](../../inputs/) without
modification. For the context arms, one related file from each control's commit
was selected before running the reviewers, fetched at that commit, and saved
under `context/`. [The manifest](context_manifest.json) records its full commit,
path, GitHub blob ID, SHA-256 and size. The input follows the prior expanded-
context format, including the exact introductory sentence and `<file>` block.

The five PDF-specific controls are one-file diffs in
`interface/forms/eye_mag/report.php` from later OpenEMR commits. All are
descendants of both recorded March 2026 security fixes in this file. They
include resource-path migration, escaping and rendering changes, and two
smaller maintenance changes. [Their manifest](pdf_controls_manifest.json)
records commits, dates, subjects and diff hashes; `pdf_diffs/` has the exact
inputs. They are apparently benign changes, not proof that all surrounding
code is secure. The two smaller controls have little direct connection to PDF
resource loading.

The ten original controls are unrelated to the Eye Exam PDF. Their PDF-card
arms test **instruction spillover on unrelated changes**, not false-alarm
precision in a PDF export workflow. The five report-file controls are more
relevant but still cover only one component and short diffs. Keep these
denominators separate.

The reviewer was requested as `claude-sonnet-5` through the direct Anthropic
Messages API. Each call had one user message, no tools or conversation history,
default model settings and `max_tokens=16000` for context arms or `32000` for
PDF-card arms. The templates come from the frozen original archive. The PDF
cards are byte-for-byte copies of the existing requirement follow-up's cards.
Prompts contain no advisory text, CVE identifiers, past review output or
scoring keys. Arms for a control were interleaved at run time. The API's
served model, response ID, stop reason, token usage, UTC start time and elapsed
seconds are saved for every call.

## Scoring

A separate `claude-fable-5-1` judge classifies each security claim as:

- **FALSE:** the review asserts a vulnerability that the supplied code and
  requirement do not support or contradict.
- **SPECULATIVE:** a conditional question or request to check an unshown
  dependency, without asserting the vulnerability.
- **PLAUSIBLE:** a specific credible weakness in touched or relied-on code.

The judge also counts non-security correctness/reliability and maintainability
warnings separately. A false-alarm *review* has at least one FALSE finding.
Controls with any such review among their three repetitions are counted
separately. Severity is the reviewer's own label, not a judge-assigned rank.
The judge sees the code and, as applicable, the related file or requirement
card, but no reviewer model name or prompt-arm label. The review may reveal
which instructions it received, and the PDF cards themselves are distinguishable.
All scores are provisional until an independent person checks the false and
borderline classifications against the raw review and code.

## Results

These are **provisional model-judge counts**. A cell such as 20/30 means 20 of
the 30 separate reviews contained at least one asserted, unsupported security
claim. It does not mean 20 vulnerable commits were found. “High label” counts
reviews with a false finding whose original severity contains `High` or
`Critical`, including mixed labels such as `Medium-High`.

| Control set and card | False-alarm reviews | Controls with any false alarm | False security claims | High-label reviews | Speculative security questions | Correctness warnings | Mean review words |
|---|---:|---:|---:|---:|---:|---:|---:|
| Original 10 + context, generic prompt | **1/30** | **1/10** | 1 | 0/30 | 15 | 53 | 389 |
| Original 10 + context, security prompt | **20/30** | **10/10** | 33 | 7/30 | 86 | 4 | 808 |
| Original 10 + functional PDF card | **12/30** | **7/10** | 17 | 1/30 | 75 | 4 | 650 |
| Original 10 + security PDF card | **13/30** | **7/10** | 15 | 1/30 | 80 | 4 | 655 |
| Five Eye Exam report changes + functional PDF card | **4/15** | **2/5** | 5 | 0/15 | 51 | 2 | 668 |
| Five Eye Exam report changes + security PDF card | **7/15** | **4/5** | 9 | 2/15 | 47 | 0 | 835 |

The added-context generic and security rows differ in both their review
instruction and resulting workload. With the same ten diffs and related
files, the security prompt produced 33 unsupported security claims rather
than one and about twice as many review words. The median review time rose
from 28 to 49 seconds. This is evidence of a substantial false-alarm burden
under the stronger prompt **with context**. It is not an estimate of how much
the context file alone changed false alarms.

On the five report-file controls, the proposed security card produced more
false-alarm reviews (7/15 versus 4/15) and longer reviews (835 versus 668 mean
words; 64 versus 37 median seconds). This is a small, selected set. In one
High-severity review, the judge called a conditional warning FALSE; a human
could reasonably score it SPECULATIVE. If that one finding is changed, the
security-card count becomes **6/15 reviews, 3/5 controls and 8 false claims**.
The direction of the review-level difference remains, but the control-level
difference narrows. [Audit notes](AUDIT.md) identify that and other calls for
independent verification.

The ten original controls with PDF cards show 12/30 versus 13/30
false-alarm reviews. Those cards do not concern those changes. Treat this as
an instruction-spillover check, not a PDF-workflow false-alarm rate. It also
shows why the focused five-control result deserves its own denominator.

### Per-control false-alarm reviews

Each cell is a count out of **three** reviews, not a case-level majority score.

| Original control | Context generic | Context security | Functional PDF card | Security PDF card |
|---|---:|---:|---:|---:|
| BENIGN-01 | 0/3 | 1/3 | 0/3 | 0/3 |
| BENIGN-02 | 0/3 | 2/3 | 3/3 | 0/3 |
| BENIGN-03 | 1/3 | 2/3 | 0/3 | 3/3 |
| BENIGN-04 | 0/3 | 3/3 | 2/3 | 3/3 |
| BENIGN-05 | 0/3 | 1/3 | 1/3 | 1/3 |
| BENIGN-06 | 0/3 | 2/3 | 1/3 | 0/3 |
| BENIGN-07 | 0/3 | 1/3 | 1/3 | 1/3 |
| BENIGN-08 | 0/3 | 2/3 | 0/3 | 2/3 |
| BENIGN-09 | 0/3 | 3/3 | 3/3 | 1/3 |
| BENIGN-10 | 0/3 | 3/3 | 1/3 | 2/3 |

| Report-file control | Functional PDF card | Security PDF card |
|---|---:|---:|
| PDF-01, resource-path accessor migration | 3/3 | 3/3 |
| PDF-02, narrative line-break escaping | 0/3 | 1/3 |
| PDF-03, commented-out attribute encoding | 1/3 | 2/3 |
| PDF-04, note output escaping | 0/3 | 1/3 |
| PDF-05, translation echo | 0/3 | 0/3 |

Severity labels, reasons and each run's speculative and correctness counts are
in [all classified findings](findings.csv), [original-control run scores](run_scores.csv)
and [report-file run scores](pdf_run_scores.csv). [Summary CSVs](summary.csv)
and [PDF summary CSV](pdf_summary.csv) include token use and latency.

## Reproduction and evidence

The complete exact requests, prompts, full API responses, review text, judge
requests and rationale, and per-call metadata are retained in
[evidence.zip](evidence.zip) with [a SHA-256 digest](evidence.sha256).
Extract that archive into this directory to inspect or recompute results.
The readable CSVs summarize every run and finding. [The script](measure.py)
builds the inputs, runs the calls, applies the stated count rule and exports
the tables. It skips completed normal calls. Paid stages require `--execute`.

```sh
unzip openemr-study/data/false-alarm-followup/evidence.zip -d openemr-study/data/false-alarm-followup
python3 openemr-study/data/false-alarm-followup/measure.py verify
python3 openemr-study/data/false-alarm-followup/measure.py summarize
python3 openemr-study/data/false-alarm-followup/measure.py summarize-pdf
```

To make new calls, set `ANTHROPIC_API_KEY` in the environment or the
repository's untracked `.env`, then run the script's `prepare`, `run`, `judge`,
`prepare-pdf`, `run-pdf` and `judge-pdf` stages in that order for each set.
`prepare` needs GitHub CLI access. `prepare-pdf` expects an OpenEMR git clone
at `build/openemr-full`; the frozen input files are already provided here, so
neither preparation step is needed to repeat the model calls. Future provider
responses can differ even when the requested alias and input are the same.

## Interpretation limits

The added-context arms measure false alarms *with* a related file. They do not
isolate the causal effect of adding that file because this experiment did not
run contemporaneous diff-only controls. Earlier Sonnet diff-only controls had
one review per arm, different dates and execution conditions.

The PDF security card was drafted with knowledge of the original SSRF case.
These controls test whether that card also provokes unsupported findings on
selected harmless changes. They do not validate the card's real-world
precision or show that the requirement existed at the historical PR. Human
verification of the new classifications remains outstanding.
