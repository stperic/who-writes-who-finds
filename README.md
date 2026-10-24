# Who Writes the Bug, Who Finds the Bug?
### Human-AI Security Lessons from Open Source: Reproducibility Artifact & Take-Home Kit

**Speaker:** Eric St-Pierre, CISSP, CCSP, HCISPP · Founder & Fractional CTO, Medoya Consulting LLC  
**Conference:** ISC2 Security Congress 2026 (Denver, October 2026)

This repository contains the study dataset, raw model review outputs, practitioner worksheets, and `quadrant` CLI harness for the ISC2 Security Congress 2026 session *"Who Writes the Bug, Who Finds the Bug? Human-AI Security Lessons from Open Source."* Historical execution provenance is incomplete; the limits below distinguish reproducible scoring from a new model run.

---

## Repository Contents

| Path | Description |
|---|---|
| [`presentation/`](presentation/README.md) | **Current slide deck and evidence guide:** the supported PowerPoint, a run ledger with slide numbers and denominators, direct links to raw records, and a clear boundary between measured results and proposed workflows. |
| [`take-home-kit/`](take-home-kit/) | **Start here on Monday:**<br>1. [`01-Four-Quadrant-Assessment-Worksheet.md`](take-home-kit/01-Four-Quadrant-Assessment-Worksheet.md) (with worked OpenEMR baseline + blank worksheet)<br>2. [`02-Routing-and-Ownership-Policy-Template.md`](take-home-kit/02-Routing-and-Ownership-Policy-Template.md) (risk & context routing table, AI authority rules, revalidation triggers)<br>3. [`03-30-Day-Shadow-Pilot-Scorecard.md`](take-home-kit/03-30-Day-Shadow-Pilot-Scorecard.md) (4-week shadow-mode pilot plan, worked scorecard, exit/rollback criteria) |
| [`openemr-study/`](openemr-study/) | **Start here for the OpenEMR study:** original results, the complete 24-case Haiku prompt comparison, a separate [Snyk Code baseline](openemr-study/snyk-baseline/README.md), a [24-CVE bug and fix FAQ](openemr-study/CVE-FAQ.md), case and control evidence pages, exact prompts, and raw archives. |
| [`human-review-packet/`](human-review-packet/) | **6-Diff Blind Human Review Packet:**<br>Ready-to-run 30-minute blind review exercise ([`INSTRUCTIONS-AND-SCORESHEET.md`](human-review-packet/INSTRUCTIONS-AND-SCORESHEET.md)) and sealed answer key ([`ANSWER-KEY-DO-NOT-OPEN-FIRST.md`](human-review-packet/ANSWER-KEY-DO-NOT-OPEN-FIRST.md)) to benchmark human reviewers on your team against the same rubric. |
| [`quadrant-tool/`](quadrant-tool/) | **`quadrant` CLI harness:**<br>Python CLI ([`quadrant.py`](quadrant-tool/quadrant.py)) and longitudinal benchmark guide ([`BENCHMARK.md`](quadrant-tool/BENCHMARK.md)) to trace CVEs, extract blinded diffs, run pinned models, score against the rubric, and compare drift across model releases. |
| [`jev-study/`](jev-study/) | **Reviewer-routing pilot:** 14 changes, draft policy labels, and a [Jev runner](quadrant-tool/jev.py) using OpenRouter's Decisions API. The initial 42-call exploratory run and raw responses are archived separately from the detection study. |
| [`METHODS.md`](METHODS.md) | Detailed SZZ-style git-blame tracing rules, blinding protocol, contamination controls, and study limitations. |
| [`cves.csv`](cves.csv) | Master 32-row OpenEMR CVE/GHSA inventory with introducing commits, fix commits, commit-to-disclosure intervals, and forensic trace notes. |
| [`references.md`](references.md) | Verified bibliography grouped by talk section. |

---

## Headline Empirical Findings (OpenEMR Case Study)

We traced **24 validated CVEs** (16 disclosed Feb-Mar 2026 after both recorded model training cutoffs; 8 older CVEs from 2018-2025) in **OpenEMR** to their introducing changes, extracted selected blinded diffs, and reviewed each three times under two recorded model identities: **Claude Sonnet 5** (cutoff Jan 2026) and **Claude Haiku 4.5** (cutoff Jul 2025). The same general pre-merge prompt mentions correctness, security, reliability and maintainability (`144` review runs). A separate **10-change comparison set** (`20` original reviews) checks false security alerts:

The original study used Claude Code. Sonnet's harness alias does not establish an immutable snapshot across the August runs and October repairs. Inputs were curated using known flaws: 25 of 26 staged diffs were scoped to the vulnerable file. Later CVE disclosure does not prove the code was unseen; eight of the 16 recent fixes were public by Sonnet's normalized cutoff. The original case scores were human-validated; this is a selected-case study, not a production detection rate or matched human-versus-AI benchmark.

| Metric | Claude Sonnet 5 (`claude-sonnet-5`) | Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) |
|---|---|---|
| **Post-cutoff CVEs (Group A, n=16)** | **13 / 16 Caught** (3 Partial, 0 Missed) | **5 / 16 Caught** (6 Partial, 5 Missed) |
| **Fix public after the model's training cutoff** | **7 / 8 Caught (88%)** (Jan 31, 2026 cutoff; n=8) | **5 / 16 Caught** (Jul 31, 2025 cutoff; n=16) |
| **Older CVEs (Group B, n=8)** | **7 / 8 Caught** (0 Partial, 1 Missed) | **3 / 8 Caught** (1 Partial, 4 Missed) |
| **All Validated CVEs (n=24)** | **20 / 24 Caught (83%)** (3 Partial, 1 Missed) | **8 / 24 Caught (33%)** (7 Partial, 9 Missed) |
| **Single-File Contract Visibility (n=20)** | **20 / 20 Caught (100%)** | **8 / 20 Caught** (6 Partial, 6 Missed) |
| **Cross-File Contract Visibility (n=4)** | **0 / 4 Caught** (3 Partial, 1 Missed) | **0 / 4 Caught** (1 Partial, 3 Missed) |
| **False Security Alerts on Benign Controls (n=10)** | **0 / 10 false security alerts** | **1 / 10 false security alert (Medium)** |
| **High-or-higher correctness concerns on comparison changes (n=10)** | **4 / 10 High warnings** (asked to verify callers/helpers/PHP version outside diff) | **1 / 10 Critical error** (falsely called `js_escape()` undefined) |

### Key Takeaway
Sonnet 5 caught **7 of 8** Broken Access Control cases, so these results do not support assigning entire vulnerability classes to humans or AI. The original post hoc grouping found **20/20 Caught** where the sink and contract were visible in the supplied diff, versus **0/4 Caught** where confirming exploitability required a caller, base class or configuration file outside it. That association motivated a targeted context test; it is not a universal boundary or proof that missing context caused every incomplete result.

### Targeted follow-ups on the four original Sonnet gaps

The direct-API follow-up supplied one historical related file selected by the researcher from the known vulnerability trace. With the general prompt, Sonnet 5 scored Caught on **2 of the 4** original gaps: patient access and payment-secret exposure. Security plus touched-code instructions with the same files scored **3 of 4**, adding stored XSS. PDF-rendering SSRF remained Partial.

Adding those distinct recoveries to the original 20 gives **22, then 23 of the original 24 with a scored catch across experiments**. The other 20 were not rerun with the improved setup. These are retrospective coverage totals, not full rerun rates for one fixed workflow. Follow-up model judging and model-applied rulings await independent human verification; false alarms with added context were not measured. Jev and ZZ-Trace did not select the study prompts or context. Sources: [`followup_expanded_context/README.md`](openemr-study/data/prior-followups/followup_expanded_context/README.md) and [`final_detection.csv`](openemr-study/data/prior-followups/followup_expanded_context/final_detection.csv).

Separate prompt controls found false security alarms in **0/10** Sonnet general-prompt reviews and **5/10** security-plus-touched-code reviews, including **2/10** Medium-or-higher alerts. These are individual comparison reviews, not majority-of-three case scores, and do not estimate the combined prompt-and-context false-alarm rate. See [`followup_security_prompt/README.md`](openemr-study/data/prior-followups/followup_security_prompt/README.md) and [`benign_summary.csv`](openemr-study/data/prior-followups/followup_security_prompt/benign_summary.csv).

### PDF requirement follow-up: a separate post hoc probe

For the one PDF-rendering SSRF case, a new matched Sonnet 5 probe supplied the same selected diff and security-review prompt with one appended requirement. A functional requirement to include narrative and images led to **0/3 explicit PDF SSRF findings**. A proposed security requirement that narrative must not choose resources fetched by the PDF generator led to **3/3 explicit findings**. The latter permits authorized clinical media. This is a retrospective, manually selected requirement, not an OpenEMR requirement known to exist at the historical PR and not a ZZ-Trace selection result. No benign controls or other cases were run under these cards; the reviews have not been independently adjudicated. It does not turn the accumulated 23/24 observation into a measured 24/24 workflow. See the [complete prompt and response evidence](openemr-study/data/pdf-requirement-followup/README.md).

A later full-set Haiku 4.5 prompt comparison reran all 24 original diffs three times per arm under matched direct API settings. Caught cases rose from **11/24** with the generic prompt to **19/24** with the OWASP plus touched-code prompt. False security alarms on the ten benign controls rose from **8/30** to **24/30** reviews. These new scores are model-judged and await independent human verification; Sonnet's earlier 20/24 was not rerun under this setup. See the [clean study results](openemr-study/RESULTS.md).

### Snyk Code baseline: a separate scanner follow-up

Snyk Code with default CLI rules scanned the full OpenEMR repository once at each of the 24 bug-introducing revisions. It **clearly identified 6/24** selected vulnerabilities; **1/24** is borderline and excluded from Caught, and **17/24** were clear misses. These are provisional case-match judgments awaiting independent human verification. The current scanner ran after disclosure and saw the full repository, while the AI reviewers saw selected diffs, so this is an operational comparator rather than a matched model-versus-scanner experiment. The [methods and results](openemr-study/snyk-baseline/README.md), [24-case table](openemr-study/snyk-baseline/RESULTS.md), scripts, metrics and verified raw archive are in the separate follow-up folder. Confirm the applicable Snyk agreement before using the comparator in a public presentation.

---

## Quadrant Status

Each quadrant of the four-quadrant framework is labeled by what this repository measures. Only the AI-catches quadrant has results from this study.

| Quadrant | Status here | Basis |
|---|---|---|
| Humans introduce | Traced, not rated | Introducing commits for the 24 scored CVEs are recorded in [`openemr-study/data/original/cves.csv`](openemr-study/data/original/cves.csv) (intro dates 2005-2024). No rate of human-introduced defects is computed. |
| AI introduces | No AI-tagged introduction found in the inspected records | The 24 scored CVEs have introducing changes dated no later than May 2024; dates alone do not prove human-only authorship. A separate trace of OpenEMR security fixes from September 2025 to October 21, 2026 found no advisory whose vulnerable code was introduced by an AI-tagged commit. Missing trailers do not rule out AI assistance (see AI-Tagged Commits in OpenEMR). |
| Humans catch | Not measured; human misses documented | No human catch rate: every case is a vulnerability that was merged. 11 of the 24 introducing changes went through a PR reviewed by a second maintainer (see Human Review of the Introducing Changes). The [human review packet](human-review-packet/) is a separate exercise and is not part of the reported results. |
| AI catches | **Measured review scores** | 24 OpenEMR CVEs, selected blinded introducing diffs, two recorded model identities, 3 runs per diff. Targeted follow-ups have separate judging and validation limits (see Headline Findings). |

## Human Review of the Introducing Changes

For each scored CVE we looked up the GitHub pull request behind the introducing commit and read its review record. Data: [`pr_reviews.csv`](openemr-study/data/original/pr_review/pr_reviews.csv). The scripts are preserved in the [full archive](openemr-study/evidence/study-results.zip).

- **Commits:** the 24 CVEs trace to 21 distinct introducing commits.
- **No PR record (12 CVEs):** commits from 2005 to 2017 that were pushed directly or merged before a PR workflow. Whether anyone reviewed them is unknown.
- **PR found (12 CVEs):** 11 through the GitHub API and one (CVE-2026-24898) through the PR number in its commit message (#1949).
- **Reviewed by a second maintainer: 11 of 12.** CVE-2026-24849 (PR #7429) had no reviewer and was merged by its author.
- **Sign-off on those 11:** 4 recorded GitHub approvals, 5 written sign-offs in the PR conversation (for example "looks good to me"), 1 "review complete" with minor issues noted, and 1 with no written sign-off. OpenEMR's CONTRIBUTING.md says a maintainer reviews each PR. It does not require a GitHub approval, and maintainers often sign off in the conversation.
- **Comments on the vulnerable file:** reviewers commented on the vulnerable file in 4 PRs. None of the comments addressed the vulnerability:

| CVE | PR | Reviewer comments on the vulnerable file |
|---|---|---|
| CVE-2026-25146 (gateway secret exposed) | #2099 | 7 comments on output escaping and translation. None on the gateway key rendered into browser JavaScript. After signing off, the reviewer noted how the encrypted key should be decrypted, not where it was sent. |
| CVE-2018-15152 (portal authentication bypass) | #1090 | 8 comments, including a question about session handling at the top of the file. None on the portal session flag set before authentication. |
| CVE-2026-24890 (authorization) | #2614 | 2 comments on error-output escaping. None on the authorization branch. |
| CVE-2025-43860 (XSS) | #5557 | 1 comment on a delete button's role. None on the `innerHTML` sinks. |

**AI results on the same 11 reviewed cases:** Claude Sonnet 5 scored 9 Caught and 2 Partial. Claude Haiku 4.5 scored 4 Caught, 2 Partial and 5 Missed.

This is not a matched human-versus-AI comparison. These cases were selected because they became CVEs, so flaws stopped by historical development and review controls are absent from the sample. Human reviewers had the whole PR available at merge time. The models were supplied selected historical file diffs later, with possible prior exposure to the public fix and incomplete records of original repository reads.

Open item: for CVE-2026-25476, PR #4435's file list does not include the vulnerable file (`library/auth.inc.php`), so that commit-to-PR link is under review.

## AI-Tagged Commits in OpenEMR

OpenEMR's CONTRIBUTING.md asks contributors to mark AI involvement with `Assisted-By:` or `Generated-By:` commit trailers. Commits made through Claude Code and the Copilot coding agent can also carry `Co-authored-by:` trailers. These tags support tracing recorded AI assistance; they do not establish complete authorship coverage or that AI introduced a flaw.

- **AI-tagged commits:** 490 on `master` (all branches: 1,263, counting cherry-picks). Almost all date from November 2025 onward.
- **Method:** for 132 security-fix commits from September 2025 to October 21, 2026 (79 on `master`, 53 on release branches), we blamed every line each fix changed or sat next to, in the commit before the fix (SZZ, the same method as the main study). We then checked whether the blamed commit carried an AI trailer, and inspected each hit by hand.
- **Result: no advisory traced to vulnerable code introduced by an AI-tagged commit.** 15 fixes on `master` touched lines last written by AI-tagged commits. The 4 matching release-branch fixes are backports of the same changes.
  - **11 mechanical:** large AI-assisted refactors (for example `$GLOBALS` to `OEGlobalsBag`, `$_SESSION` to a session object) rewrote existing lines without changing their logic.
  - **1 unrelated change:** a Copilot commit changed error handling in a function whose vulnerability predates it.
  - **1 fix on a fix:** an AI-co-authored security fix (GHSA-xg3m-9pfq-c8r6) was adjusted the same day. The vulnerable OneTimeAuth code dates to 2023, before that AI-assisted fix.
  - **2 carried forward:** an AI-co-authored change rewrote the vulnerable code and kept the flaw.

| Advisory | AI-tagged change | What happened |
|---|---|---|
| [GHSA-9rj4-fxmj-c4r7](https://github.com/openemr/openemr/security/advisories/GHSA-9rj4-fxmj-c4r7) (high, fixed in 8.3.0): broken access control in `controller.php` | PR #11163, March 2026, `Co-authored-by: Claude` | Rewrote controller routing and kept the missing permission check for six sub-controllers. The advisory's proof of concept confirms the old route was exploitable in 8.0.x, before this change. |
| [GHSA-m6q6-5j87-3cmp](https://github.com/openemr/openemr/security/advisories/GHSA-m6q6-5j87-3cmp) (high, fixed in 8.3.0): path traversal in `sl_eob_process.php` | February 2026, `Co-authored-by: Claude` | Rewrote the vulnerable file-path line without sanitizing `eraname`, which was already unsanitized. |

In both cases the AI-assisted change was a chance to catch an existing flaw, and the flaw survived. Neither advisory has a CVE ID.

Limits: fixes were found through advisory links and OpenEMR's "Merge commit from fork" security merges, so a fix merged any other way may be missed. Commits without trailers can still be AI-written. Blame attributes a line to its last change, which is why mechanical rewrites show up and were inspected by hand. The [classification data](openemr-study/data/original/ai_trailer_trace/findings.csv) is directly viewable; the scripts are in the [full archive](openemr-study/evidence/study-results.zip) and expect a local OpenEMR clone.

## Inventory and Scope

- **Inventory:** 32 records, 31 with CVE IDs.
- **Scored:** 24 CVEs (16 Group A, 8 Group B). Each was run on both models.
- **Traceability among scored cases:** 21 fully traced, 3 partially traced.
- **Inventory not scored:** 7 CVEs have no run data: CVE-2018-15156, CVE-2019-3963, CVE-2019-3966, CVE-2023-22972, CVE-2023-22974, CVE-2026-24848, CVE-2026-65983. The reason is not recorded in [`openemr-study/data/original/validity.csv`](openemr-study/data/original/validity.csv), so none of these is in any denominator.
- **Source of truth:** [`openemr-study/data/original/cves.csv`](openemr-study/data/original/cves.csv) and [`openemr-study/data/original/numbers.md`](openemr-study/data/original/numbers.md).

## OWASP Top 10 (2021) Breakdown

Scored cases only (n=24). Cells show Caught / Partial / Missed.

| OWASP 2021 category | Cases | Claude Sonnet 5 | Claude Haiku 4.5 |
|---|---:|---:|---:|
| A01 Broken Access Control | 8 | 7 / 1 / 0 | 3 / 1 / 4 |
| A03 Injection (includes XSS) | 11 | 10 / 0 / 1 | 5 / 3 / 3 |
| A05 Security Misconfiguration (includes secrets) | 1 | 0 / 1 / 0 | 0 / 0 / 1 |
| A07 Identification and Authentication Failures | 3 | 3 / 0 / 0 | 0 / 2 / 1 |
| A10 Server-Side Request Forgery | 1 | 0 / 1 / 0 | 0 / 1 / 0 |

Source: [`openemr-study/data/original/numbers.md`](openemr-study/data/original/numbers.md), OWASP section.

---

## Reproducing the Numbers

```bash
python3 -I openemr-study/data/original/recompute.py
```

For running `quadrant` on your own repository, see [`quadrant-tool/README.md`](quadrant-tool/README.md) and [`take-home-kit/03-30-Day-Shadow-Pilot-Scorecard.md`](take-home-kit/03-30-Day-Shadow-Pilot-Scorecard.md).

Recomputing archived scores is distinct from reproducing the historical execution. Complete original request bytes and repository reads were not retained for the inspected D05 baseline, and the Sonnet alias is not an immutable snapshot across dates. New evaluations should freeze and record the resolved configuration, full request, actual tool/file access, case selection, scoring rules, timing and usage. Test a fixed workflow on held-out full PRs with comparison changes; rerunning these known 24 cases alone is a regression check.

## License

MIT License. See [`LICENSE`](LICENSE).
