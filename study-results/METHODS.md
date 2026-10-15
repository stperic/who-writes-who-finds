# Methodology: How the CVEs Were Identified, Traced, and Tested
### Reproducibility methods for "Who Writes the Bug, Who Finds the Bug?"
### Eric St-Pierre, Medoya Consulting LLC. Study run 2026-08-17.

This document records the exact process used to build the study dataset and run
the counterfactual, so the work can be audited and reproduced. It favors honesty
about what was automated, what was manual, and where the process had to make
judgment calls. No em dashes (this is a publishable artifact document).

Target platform: **OpenEMR** (github.com/openemr/openemr), a major open-source
electronic health record system (100,000+ providers, 200M+ patient records).
Chosen for a fully public CVE history, real PHI stakes, and a category mix
(injection plus broken access control) that populates both ends of the routing
model.

---

## 1. Data sources (exact)

| Source | Endpoint / access | Used for |
|---|---|---|
| GitHub Security Advisories | `gh api /repos/openemr/openemr/security-advisories --paginate` | Group A (2026) CVE list, GHSA IDs, severity, CVSS v3, reporter credits |
| GitHub per-advisory detail | `gh api /repos/openemr/openemr/security-advisories/<GHSA>` | CVSS score, credits_detailed (reporter/analyst/finder) |
| NVD 2.0 REST | `services.nvd.nist.gov/rest/json/cves/2.0?virtualMatchString=cpe:2.3:a:open-emr:openemr` | Group B (pre-2024) CVE list, CVSS 4.0 scores where GHSA had none |
| OSV.dev | `api.osv.dev/v1/vulns/<CVE>` | Fix-commit references (by CVE ID) |
| AISLE disclosure | aisle.com/cve-discoveries, aisle.com/blog | Cross-reference for the Q1 2026 AI-found batch (38 CVEs) |
| Media corroboration | SecurityWeek, HIPAA Journal | Independent confirmation of the AISLE batch and category mix |

At pull time the GitHub advisory endpoint returned **85 advisories** for OpenEMR,
**74 of them published in Q1 2026**. NVD returned **218** OpenEMR CVEs across the
full history.

---

## 2. CVE identification and selection

The dataset is split into two groups by design, because the split is itself a
control (see Section 6).

### Group A: contamination-clean (2026 disclosures)

1. Pulled the full GitHub advisory list (command above).
2. Cross-referenced against AISLE's publicly disclosed Q1 2026 batch (38 CVEs,
   more than half of that quarter's OpenEMR advisories) and the follow-on
   disclosures through August 2026.
3. Selected 19 CVEs to (a) cover multiple OWASP Top 10 categories (A01 access
   control, A03 injection, A05 secrets, A07 auth failures, A10 SSRF), (b) include
   the maximum-severity flagship bugs (the two 10.0 / 9.9 CVEs), and (c) include
   the freshest possible disclosures (CVE-2026-65983 in July, GHSA-hj9x-33vw-5g3x
   in August) so at least part of the set is post-cutoff for every model on the
   market.

### Group B: likely-memorized (pre-2024 disclosures)

1. Pulled the NVD list (command above), filtered to 2018 through 2023 disclosures.
2. Anchored specific CVEs from known public audits so the set has provenance a
   reviewer can check: the **Sonar 2023 chain** (CVE-2023-22972/22973/22974), the
   **Project Insecurity 2018 batch** (CVE-2018-15145/15152/15156), the
   **controller.php reflected-XSS pair** (CVE-2019-3963/3966), and the
   **immunization-module SQLi** (CVE-2020-29140), which is the re-introduction
   pair of a 2026 CVE in the same module.
3. Kept the category mix similar to Group A (injection- and access-control-heavy)
   so cross-group detection differences are attributable to contamination rather
   than a difference in difficulty, subject to the confound named in Section 10.

### Selection criteria, in priority order

1. **Traceability**: an identifiable fixing commit, so the introducing commit can
   be found. CVEs whose fix could not be located were dropped, not guessed.
2. **Category coverage**: spread across OWASP Top 10 to populate the routing model.
3. **Contamination status**: Group A disclosed after model cutoffs; Group B before.
4. **Severity and salience**: flagship criticals included for narrative weight, but
   not at the expense of category balance.

Final dataset: **32 candidate CVEs** (19 Group A, 13 Group B), recorded one row
per CVE in `cves.csv`.

---

## 3. Metadata enrichment (CVSS, reporter, fix commit)

Only empty fields were ever filled; existing values were never overwritten.

- **CVSS**: taken from the GitHub advisory (`cvss.score`), falling back to NVD
  CVSS 4.0 for CVEs where the GHSA carried a severity label but no numeric score
  (CVE-2026-23627 = 7.4, CVE-2026-24487 = 5.7, CVE-2026-24848 = 8.7). One early
  draft value was corrected here (CVE-2026-24908 is 9.9, not 10.0).
- **Reporter credits**: from `credits_detailed` on the GitHub advisory (login plus
  role: reporter / analyst / finder / remediation_developer). This is how the
  "who caught it" attribution is grounded rather than assumed.
- **Fix commit**: from OSV references (FIX-type GitHub commit URLs) for Group A.
  OSV returned **no** fix commits for any Group B CVE, so those required git
  archaeology (Section 4).

---

## 4. Fix-commit and introducing-commit tracing (SZZ-style)

The introducing commit is found by the SZZ approach (Sliwerski-Zimmermann-Zeller),
done by hand at this scale. For each CVE with a known fix:

1. **Read the fix** to isolate the vulnerable sink line(s):
   `git show <fix> --stat` then `git show <fix> -- <file>`. The pre-fix version of
   the changed line is the sink (the unsanitized concatenation, the missing ACL
   check, the unescaped echo).
2. **Blame the sink in the fix's parent**:
   `git blame <fix>^ -L <start>,<end> -- <file>`.
3. **Step back through noise**: when blame landed on a reformat, lint pass, or
   import move rather than the logic author, we stepped back with
   `git log -S '<distinctive vulnerable substring>' --all --reverse -- <file>` and
   re-blamed, until the first commit that introduced the actual exploitable
   expression was found.
4. **Record** the introducing commit and its author date
   (`git show -s --format='%H %ad %s' --date=short`).

### Decision rules (stated so they can be challenged)

- The introducing commit is the first commit that added the **exploitable** line,
  not merely the file.
- When two commits interact to create the vulnerability, the **later** one is
  recorded, with a note (example: CVE-2026-23627, where a 2020 refactor removed an
  existing `quoteValue` sanitizer).
- When blame dead-ends in the repository's **2005 root import** (`7080e87bbabb`,
  "Initial revision," 1,100 files), the CVE is marked `traceable=partial` and its
  survival time is treated as a **lower bound**, not a datable introduction,
  because the code predates the git history (OpenEMR forked from an earlier
  project). Two CVEs fell here.
- When the introducing commit is a **large bulk feature import** (for example a
  285-file portal drop), it is kept but flagged: `intro_date` means "feature landed
  in-repo," not "line authored." Three CVEs fell here.

### Independent verification

Automated traces were not taken on trust. Every result with an early date or a
same-commit collision was checked by hand: the 2005 root-import collisions and the
large feature-drop commits were each inspected with `git show --stat` and
`git rev-list --count` to confirm whether they were real focused commits or bulk
imports. The corrections in the two rules above came out of that check.

### Tracing outcome (updated 2026-10-15)

28 of 32 candidate advisories were traced to introducing commits: 22 `traceable=yes`
and 6 `partial` (including 4 that trace back to the 2005 root import `7080e87bbabb`,
1 composite multi-commit chain `CVE-2023-22974`, and 1 case `CVE-2021-40352` where
the introducing commit is pinpointed but the repository lacked a dedicated fix on
that file). During the October 2026 ground-truth validation audit, 2 of the 24
scored cases (`CVE-2026-24487` and `CVE-2026-24849`) were found to have been linked
to fix commits for different mechanisms (`FhirLocationService.php` and TLS
verification in `CDADocumentService.php`) and were quarantined in
`study-results/validity.csv` (with their true fix and introducing commits documented
in `cves.csv`). Across the 20 validated single-commit traces (`traceable=yes`,
excluding the 2 quarantined cases), the commit-to-disclosure interval has a median
of **2,404 days (6.6 years)** and a maximum of **5,720 days (15.7 years)**.

---

## 5. Diff extraction and blinding

The AI reviewer must see only what a reviewer would have seen at merge time, with
no post-hoc signal.

1. **File-scoped extraction**: `git show <intro> --no-color -- <vulnerable_file>`,
   not the whole commit, so a large commit does not bury the relevant hunk. (25 of
   the 26 extracted diffs are scoped to the single vulnerable file; 1 small commit,
   `CVE-2026-25476` at 3,819 chars, included all 3 touched files. When the
   vulnerable file was created in that commit, the diff is the whole new file,
   which is a legitimate "reviewer approved a big new file" scenario.)
2. **Commit messages stripped**: everything before the first `diff --git` is
   removed, so the introducing commit's own message cannot leak intent. This
   mattered: the commit that left behind the 15.7-year SQLi (CVE-2026-29187) had a
   message reading "secure the patient search scripts, prevent sql-injection." The
   full messages are archived separately as data.
3. **Neutral outer filenames**: each diff is staged as `item_01` through `item_26`
   so the CVE ID in the filename cannot leak to the reviewer. Standard unified diff
   headers (`diff --git a/<path> b/<path>`) inside the diff body are retained, just
   as a reviewer at merge time sees the file path being modified.
4. **Scrub check**: each diff is scanned for giveaway tokens
   (`cve|vulnerab|security|exploit|injection|xss`) before any run. All diffs passed
   after message stripping.

---

## 6. Contamination controls

1. **Group A/B split** by disclosure date versus each model's training cutoff.
2. **Model registry** (`models.csv`) records each reviewer's pinned model ID and
   published training cutoff; a per-CVE clean/memorized flag is computed from
   disclosure date versus that cutoff.
3. **Blind raw diff only**: no CVE IDs, no fix-commit messages (Section 5).
4. **Recognition probes**: after review, each model is asked, in a separate context,
   whether it recognizes the code and whether it is aware of any advisory or CVE
   affecting it. Finding: models recognize the project (the code is in all training
   data) and over-claim advisory awareness even for CVEs disclosed after their
   cutoff, so self-reported recognition is treated as an unreliable signal and the
   structural controls above are what the contamination claim rests on.

---

## 7. Counterfactual execution and scoring

- **Frozen prompt**: one neutral wording used verbatim for every run ("review this
  pull request diff... report any issues you would raise as a reviewer"). It never
  states that a vulnerability exists.
- **Runs**: 3 independent runs per CVE per model, each a fresh context.
- **Models**: Claude Sonnet 5 (`claude-sonnet-5`, cutoff January 2026) and Claude
  Haiku 4.5 (`claude-haiku-4-5-20251001`, cutoff July 2025). The second is
  deliberately a lightweight, earlier-cutoff model: its July 2025 cutoff predates
  every 2026 disclosure, making its clean-set run airtight, and the capability gap
  between the two is itself a finding.
- **Scoring separation and human adjudication**: reviews were initially scored by a
  third model (Claude Fable 5) against the known CVE, and all 44 valid case-model
  rows (131 valid non-empty runs) were then verified by human adjudication (100%
  agreement on valid case-model majority scores; 129 of 131 valid individual runs).
  Rubric: Caught (names the vulnerability class and location unprompted), Partial
  (right area or related weakness, wrong class or severity), Missed (does not flag
  it). Final score is the majority of valid runs; ties and 1-1-1 splits score
  Partial. Execution errors (1 empty output on `CVE-2026-25146` Sonnet Run 2) are
  logged in `study-results/run_status.csv` and excluded from valid run denominators
  rather than scored as Missed.
- **Raw outputs saved verbatim** (`study-results/ai_runs/`, 192 files across both
  models: 144 review runs plus 48 recognition/advisory probes) so any score can be
  independently re-checked.

---

## 8. Tooling and reproducibility

- **`quadrant`** CLI (published in `quadrant-tool/`): model registry, advisory
  pulls, blind-diff prompting, scoring, per-model reporting, and cross-model
  `compare`. See its README and BENCHMARK.md for the re-run cadence.
- **git** (full clone, not shallow, so blame works), **gh** CLI, and the NVD/OSV
  REST APIs.
- **Multi-agent workflows** were used to parallelize the per-CVE git-blame tracing
  and the per-CVE blind reviews; each agent's work is plain git or a single blind
  prompt, reproducible by hand.
- Every intermediate is preserved: `cves.csv` (dataset plus per-CVE trace notes),
  `models.csv`, `scores.csv`, `compare.txt`, and the raw AI outputs.

---

## 9. What a third party needs to reproduce this

1. Clone OpenEMR (full history).
2. Take `cves.csv` (CVE list plus fix and introducing commits).
3. Re-extract the introducing diffs (Section 5) and confirm the scrub.
4. Register your own reviewer models with their cutoffs.
5. Run the frozen prompt, 3 runs each, and score against the CVE column.
6. Compare your detection rates to ours; differences by model or by date are the
   point, not a defect.

---

## 10. Honest limitations and deviations from the ideal

- **Single codebase**: findings are directional, not a benchmark.
- **Model access**: the intended second reviewer (Sonnet 4.6, August 2025 cutoff)
  could not be pinned through the available tooling; the alias resolved to Sonnet 5
  (January 2026 cutoff). Haiku 4.5 was used as the airtight-cutoff model instead.
  Sonnet 5's cutoff sits close to the disclosure boundary, so its clean claim is
  strong but not airtight; the within-run category contrast (both post-cutoff)
  does not depend on it.
- **Thin memorized set**: only one Group B CVE had an OSV fix commit at first, so
  the initial clean-versus-memorized comparison was underpowered. The Group B
  tracing pass addresses this.
- **Difficulty confound**: Group A bugs escaped human researchers for years until a
  specialized AI found them, so they may be systematically subtler than Group B.
  Cross-group differences are reported as "consistent with contamination," not
  "caused by" it.
- **Selection bias**: Group A is an AI-selected sample (AISLE found them), so a
  general model's detection on that set is a specific, named question, not a claim
  about all OpenEMR bugs.
- **One dropped run**: one of the three Sonnet runs for CVE-2026-25146 was lost to a
  connection error and scored on two runs; noted rather than silently backfilled.
- **Model self-report caveat**: Haiku 4.5 reported a February 2025 cutoff versus
  Anthropic's documented July 2025. The registry uses the documented date; the
  discrepancy is itself an illustration that model self-reports are unreliable.
