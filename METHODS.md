# Methodology: How the CVEs Were Identified, Traced, and Tested
### Reproducibility methods for "Who Writes the Bug, Who Finds the Bug?"
### Eric St-Pierre, Medoya Consulting LLC. Study run 2026-08-17; ground-truth repair and benign controls 2026-10-15.

This document records dataset construction, the documented review procedure and
scoring, so the work can be audited and the method repeated. Historical model
identity, request and tool-access provenance is incomplete; repeating the method
does not reconstruct an identical original execution. It distinguishes what was
automated, what was manual and where judgment calls were required.

Target platform: **OpenEMR** (github.com/openemr/openemr), a major open-source
electronic health record system (100,000+ providers, 200M+ patients served; project estimates).
Chosen for public advisories and fixes, real PHI stakes, and a category mix
including injection and broken access control. The results inform routing
hypotheses; they do not establish a validated human-versus-AI division of work.

---

## 1. Data sources (exact)

| Source | Endpoint / access | Used for |
|---|---|---|
| GitHub Security Advisories | `gh api /repos/openemr/openemr/security-advisories --paginate` | Group A (2026) CVE list, GHSA IDs, severity, CVSS v3, reporter credits |
| GitHub per-advisory detail | `gh api /repos/openemr/openemr/security-advisories/<GHSA>` | CVSS score, credits_detailed (reporter/analyst/finder) |
| NVD 2.0 REST | `services.nvd.nist.gov/rest/json/cves/2.0?virtualMatchString=cpe:2.3:a:open-emr:openemr` | Group B (2018-2025 disclosures) CVE list, CVSS 4.0 scores where GHSA had none |
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

### Group A: post-cutoff disclosures (2026)

1. Pulled the full GitHub advisory list (command above).
2. Cross-referenced against AISLE's publicly disclosed Q1 2026 batch (38 CVEs,
   more than half of that quarter's OpenEMR advisories) and the follow-on
   disclosures through August 2026.
3. Selected 19 advisory candidates to (a) cover multiple OWASP Top 10 categories (A01 access
   control, A03 injection, A05 secrets, A07 auth failures, A10 SSRF), (b) include
   the maximum-severity flagship bugs (the two 10.0 / 9.9 CVEs), and (c) include
   the freshest possible disclosures (CVE-2026-65983 in July, GHSA-hj9x-33vw-5g3x
   in August) to include candidates with later disclosure dates. The final scored
   Group A subset has 16 CVEs disclosed Feb-Mar 2026; the July CVE and August
   advisory are not part of that scored subset.

### Group B: older, potentially exposed (2018 to 2025 disclosures)

1. Pulled the NVD list (command above), filtered to 2018 through 2025 disclosures.
2. Anchored specific CVEs from known public audits so the set has provenance a
   reviewer can check: the **Sonar 2023 chain** (CVE-2023-22972/22973/22974), the
   **Project Insecurity 2018 batch** (CVE-2018-15145/15152/15156), the
   **controller.php reflected-XSS pair** (CVE-2019-3963/3966), and the
   **immunization-module SQLi** (CVE-2020-29140), which is the re-introduction
   pair of a 2026 CVE in the same module.
3. Sought a category mix similar to Group A (injection- and access-control-heavy).
   This does not control difficulty or isolate contamination as the cause of
   cross-group differences; see Section 10.

### Selection criteria, in priority order

1. **Traceability**: an identifiable fixing commit, so the introducing commit can
   be found. CVEs whose fix could not be located were not scored, not guessed.
   Partial traces were kept as scored cases and carry lower-bound intervals.
2. **Category coverage**: spread across OWASP Top 10 to populate the routing model.
3. **Contamination status**: Group A disclosed after model cutoffs; Group B before.
4. **Severity and salience**: flagship criticals included for narrative weight, but
   not at the expense of category balance.

Final inventory: **32 advisory candidates** (19 Group A, 13 Group B), recorded
in `cves.csv`. One row has no CVE ID, so 31 records carry an ID.

**Scored set: 24 of the 31 CVEs with IDs.** Scored: 16 Group A, 8 Group B. Of the
scored cases, 21 are fully traced and 3 are partially traced.

**Not scored: 7 records.** The traceability rule above does not explain this split
on its own:

| CVE | Group | Trace status in `cves.csv` |
|---|---|---|
| CVE-2026-24848 | A | No introducing commit recorded |
| CVE-2026-65983 | A | No introducing commit recorded |
| CVE-2018-15156 | B | No introducing commit recorded |
| CVE-2023-22972 | B | Fully traced, not scored |
| CVE-2023-22974 | B | Partial trace, not scored |
| CVE-2019-3963 | B | Partial trace, not scored |
| CVE-2019-3966 | B | Partial trace, not scored |

The reason the seven were not scored is not recorded in this repository.
`openemr-study/data/original/validity.csv` records the two quarantined and repaired traces,
not the reasons these seven lack runs. Until the reason is recorded, these seven should be described as "not scored"
and not as "excluded for traceability."

---

## 3. Metadata enrichment (CVSS, reporter, fix commit)

Only empty fields were ever filled; existing values were never overwritten.

- **CVSS**: taken from the GitHub advisory (`cvss.score`), falling back to NVD
  CVSS 4.0 for CVEs where the GHSA carried a severity label but no numeric score
  (CVE-2026-23627 = 7.4, CVE-2026-24487 = 5.7, CVE-2026-24848 = 8.7). One early
  draft value was corrected here (CVE-2026-24908 is 9.9, not 10.0).
- **Reporter credits**: from `credits_detailed` on the GitHub advisory (login plus
  role: reporter / analyst / finder / remediation_developer). This is how the
  "who caught it" attribution is grounded rather than assumed. The `caught_by`
  column classifies that credit: `vendor-AI` (AISLE), `researcher` (a named reporter
  or analyst credit, individual or group, affiliation not verified), or
  `not-credited` (no reporter or analyst credit in the record, including advisories
  that credit only remediation developers). It never guesses a discoverer the record
  does not name. AISLE credits appear under the GitHub logins `simecek`,
  `pavelkohout396` and `stanislavfortaisle`: the 39 Q1 2026 OpenEMR advisories
  credited to them (all with CVE IDs; `stanislavfortaisle` never appears without the
  other two) are the credit-based attribution record. That count is not identical
  to AISLE's published 38-CVE batch. A reporter or analyst credit to any of them
  is classified `vendor-AI`. Audit of 2026-10-17 against the
  advisory API: `CVE-2026-25476` and `CVE-2026-33918` moved to `vendor-AI`,
  `CVE-2026-25746` (credited to `ChrisSub08`) moved to `researcher`, and eight
  Group A cases with a named reporter but no classification became `researcher`.
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
  project). Four inventory CVEs fell here.
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
verification in `CDADocumentService.php`). Both were
re-traced to their true fix and introducing commits (documented in `cves.csv`),
re-extracted, and re-run under the same recorded model identities on 2026-10-15; the August runs
are quarantined in `openemr-study/evidence/study-results.zip` and the repair is
recorded in `openemr-study/data/original/validity.csv`. All 24 scored cases are valid. Across the
22 single-commit traces (`traceable=yes`), the commit-to-disclosure interval has a
median of **2,217 days (6.1 years)**, a minimum of 322 days, and a maximum of
**5,720 days (15.7 years)**. Restricted to the 24 scored cases, 21 are single-commit
traces: median **2,043 days (5.6 years)**, same minimum and maximum. The deck quotes
this scored-set figure.

---

## 5. Diff extraction and blinding

The supplied code comes from the introducing revision, with advisory IDs and
commit-message hints removed. Selection still uses hindsight: the researcher
identified the vulnerable file before extraction. This tests review of selected
historical files, not autonomous discovery in an unrestricted full PR. Original
repository reads were not fully recorded, so supplied input must not be equated
with a verified record of everything the model inspected.

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
2. **Model registry** (`openemr-study/data/original/models.csv`) records requested or reported
   model identities and training cutoffs. Legacy clean/memorized flags in tooling
   reflect disclosure timing only, not measured training exposure. The original
   Sonnet harness alias does not establish an immutable snapshot across dates.
3. **Blind raw diff only**: no CVE IDs, no fix-commit messages (Section 5).
4. **Recognition probes**: after review, each model is asked, in a separate context,
   whether it recognizes the code and whether it is aware of any advisory or CVE
   affecting it. Models often reported recognizing OpenEMR and sometimes claimed
   awareness of advisories disclosed after their recorded cutoff. These statements
   cannot establish actual training exposure. The disclosure and fix-date checks
   reduce particular exposure concerns without making either cohort clean.

---

## 7. Counterfactual execution and scoring

- **Frozen prompt**: one neutral wording used verbatim for every run ("review this
  pull request diff... report any issues you would raise as a reviewer"). It asks
  about correctness, security, reliability and maintainability, without naming
  the target flaw or asserting that a vulnerability exists.
- **Runs**: 3 independent runs per CVE per model, each a fresh context.
- **Models**: Claude Sonnet 5 (`claude-sonnet-5`, cutoff January 2026) and Claude
  Haiku 4.5 (`claude-haiku-4-5-20251001`, cutoff July 2025). The second is
  deliberately a lightweight, earlier-cutoff model: its July 2025 cutoff predates
  every Group A fix-public date and disclosure. This reduces one exposure concern
  without proving the code was unseen. The original study ran through Claude Code;
  Sonnet's alias does not establish a fixed snapshot across August and October.
  The matched case scores compare the recorded configurations, not isolated model
  architecture or production performance. Sonnet scored 20 Caught, 3 Partial and
  1 Missed; Haiku scored 8 Caught, 7 Partial and 9 Missed across the same 24 cases.
- **Scoring separation and human adjudication**: reviews were initially scored by a
  third model (Claude Fable 5) against the known CVE, and all 48 case-model rows
  (144 valid runs) were then verified by human adjudication (48 of 48 case-model
  majority scores; 142 of 144 individual runs).
  Rubric: Caught (names the vulnerability class and location unprompted), Partial
  (right area or related weakness, wrong class or severity), Missed (does not flag
  it). Final score is the majority of valid runs; ties and 1-1-1 splits score
  Partial. The one execution error (an empty output on `CVE-2026-25146` Sonnet run 2) is
  logged in `openemr-study/data/original/run_status.csv`; it was re-run under the same recorded model identity
  on 2026-10-15 rather than scored as Missed, leaving 0 execution errors in the
  valid run set.
- **Single-file versus cross-file label**: each scored case was labeled, after
  scoring, by whether confirming exploitability needs a file outside the extracted
  diff (a caller, base class, or configuration file). With four cross-file cases the
  contrast is a hypothesis for a pilot to test, not a measured boundary.
- **Raw outputs saved verbatim** (`openemr-study/evidence/study-results.zip`, 192 files across both
  models: 144 review runs plus 48 recognition/advisory probes) so any score can be
  independently re-checked.

### Targeted follow-ups and accumulated coverage

The later AI-assisted-change, prompt and expanded-context follow-ups are separate
experiments using the direct API, not the original Claude Code execution setup.
Their READMEs record prompts, run settings, model judging and Rule B rulings.
The follow-up labels await independent line-by-line human verification. In the
expanded-context experiment, Claude Opus 5.5 also judges its own reviewer outputs;
the original study's separation of reviewer and scorer does not apply throughout.

For Sonnet 5 on the four original incomplete cases, the general prompt plus a
researcher-selected historical context file scored two Caught cases (patient
access and payment-secret exposure). Security plus touched-code instructions
with the same files scored three Caught cases, adding stored XSS. SSRF remained
Partial. The context files were chosen from known vulnerability trace notes.

The original 20 Caught cases plus these distinct recoveries yields 22, then 23
of the original 24 with a scored catch across experiments. The other 20 were not
rerun under those improved conditions; these are retrospective coverage totals,
not detection rates for one fixed 24-case workflow. Jev and ZZ-Trace did not
select the study prompts or context. See
`openemr-study/data/prior-followups/followup_expanded_context/README.md` and its `final_detection.csv`.

Separate Sonnet prompt controls scored false security alarms in 0/10 general
reviews and 5/10 security-plus-touched-code reviews, including 2/10 Medium-or-higher
alerts. These count individual comparison reviews, not majority-of-three case
scores. False alarms with added context were not measured. See
`openemr-study/data/prior-followups/followup_security_prompt/README.md` and its `benign_summary.csv`.

---

## 8. Tooling and reproducibility

- **`quadrant`** CLI (published in `quadrant-tool/`): model registry, advisory
  pulls, blind-diff prompting, scoring, per-model reporting, and cross-model
  `compare`. See its README and BENCHMARK.md for the re-run cadence.
- **git** (full clone, not shallow, so blame works), **gh** CLI, and the NVD/OSV
  REST APIs.
- **Multi-agent workflows** were used to parallelize the per-CVE git-blame tracing
  and the per-CVE reviews. The retained user prompt and selected diff describe the
  intended review input, not a complete captured tool-access history.
- Preserved artifacts include `cves.csv` (dataset and trace notes), the model
  registry, scores, comparison output and raw review text. The inspected D05
  baseline lacks exact original request bytes, repository-read records, latency,
  usage and cost. New API calls cannot reconstruct those historical measurements;
  see `demo/baseline.py` and `docs/demo/READINESS.md`.

---

## 9. What a third party needs to reproduce this

1. Clone OpenEMR (full history).
2. Take `cves.csv` (CVE list plus fix and introducing commits).
3. Re-extract the introducing diffs (Section 5) and confirm the scrub.
4. Register the resolved model configuration and cutoff; record the complete
   request, harness, actual tool/file access, revisions, timing and usage.
5. Run the frozen prompt, 3 runs each, record execution errors, and score against
   the CVE column using a declared judging and independent-verification procedure.
6. Compare the resulting configurations while retaining their execution and
   judging differences. A new run repeats the method, not necessarily the original
   model snapshot or complete environment.

---

## 10. Honest limitations and deviations from the ideal

- **Single codebase**: findings are directional, not a benchmark.
- **Model access**: the intended second reviewer (Sonnet 4.6, August 2025 cutoff)
  could not be pinned through the available tooling; the alias resolved to Sonnet 5
  (January 2026 cutoff). Haiku 4.5 was used as the earlier-cutoff model instead.
  8 of the 16 Group A fixes were public before Sonnet 5's 2026-01-31 cutoff; on the
  8 whose fix became public after the cutoff it caught 7 of 8. Contamination risk
  is reduced, not removed. The observed visibility grouping does not isolate
  context from possible prior exposure or other case differences.
- **Limited older cohort**: eight older cases cannot isolate the effect of training
  exposure. Tracing improves provenance but does not make this a randomized or
  difficulty-matched comparison.
- **Difficulty confound**: the cohorts differ in vulnerability mix, diff size and
  disclosure history. Cross-group differences do not identify whether difficulty,
  training exposure or another factor caused them.
- **Selection bias**: these are selected known vulnerabilities, not representative
  PR traffic. Eight of the 16 scored Group A cases credit an AI-analyzer vendor;
  eight credit named researchers or groups. The sample does not establish a
  human-versus-AI detection rate or a universal routing boundary.
- **Follow-up validation**: the targeted recovery scores are model-judged and await
  independent human verification. Context selection used the known flaws. A fixed
  workflow should be evaluated on held-out full PRs and comparison changes; a
  rerun of these known 24 cases alone is a regression check, not generalization.
- **One empty run**: one of the three Sonnet runs for CVE-2026-25146 returned empty
  output in August; it was logged as an execution error, preserved, and re-run on
  the same recorded model identity in October 2026 (scored Partial), rather than scored as
  Missed or silently backfilled.
- **Model self-report caveat**: Haiku 4.5 reported a February 2025 cutoff versus
  Anthropic's documented July 2025. The registry uses the documented date; the
  discrepancy is itself an illustration that model self-reports are unreliable.
