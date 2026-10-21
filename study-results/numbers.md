# numbers.md: every number the deck may quote

Generated 2026-10-21 by `recompute.py`. Do not edit by hand.
Initial runs: 2026-08-17. Ground-truth repair (CVE-2026-24487, CVE-2026-24849, CVE-2026-25146 run 2) and 10-diff benign control pass: 2026-10-15 on identical pinned models (`claude-sonnet-5`, `claude-haiku-4-5-20251001`).

## Case counts

- Inventory records: 32 (31 with CVE IDs)
- Scored cases: 24 (A: 16, B: 8)
- Repaired and re-run after ground-truth audit: 2: CVE-2026-24487, CVE-2026-24849 (plus 1 empty run on CVE-2026-25146)
- Excluded from scoring: 0
- Inventory CVEs not scored: 7 (CVE-2018-15156, CVE-2019-3963, CVE-2019-3966, CVE-2023-22972, CVE-2023-22974, CVE-2026-24848, CVE-2026-65983); no run data, so they are outside every denominator. Reasons are not recorded in validity.csv.
- **Valid scored cases: 24** (A: 16, B: 8)
- Review runs: 144; remaining execution errors: 0 (1 initial empty output repaired)
- Benign control diffs evaluated: 10 (6 security-fix patches + 4 routine non-security commits)

Group A = disclosed after both reviewers' training cutoffs (disclosed 2026-02-25 to 2026-03-25).
Group B = older, potentially exposed (disclosed 2018-2025). Neither group is 'clean': see the fix-date section.

## Headline: Caught / Partial / Missed (valid cases)

| Model | Cohort | Caught | Partial | Missed | n | Caught rate |
|---|---|---:|---:|---:|---:|---:|
| sonnet-5 | A post-cutoff | 13 | 3 | 0 | 16 | 81% |
| sonnet-5 | B older | 7 | 0 | 1 | 8 | 88% |
| sonnet-5 | All | 20 | 3 | 1 | 24 | 83% |
| haiku-4-5 | A post-cutoff | 5 | 6 | 5 | 16 | 31% |
| haiku-4-5 | B older | 3 | 1 | 4 | 8 | 38% |
| haiku-4-5 | All | 8 | 7 | 9 | 24 | 33% |

## Fix availability vs training cutoff (Group A, valid cases)

Fix public date = commit date of the fix in OpenEMR's public repository (security fixes are merged from a private fork, so the merge makes them public).

- **sonnet-5** (cutoff 2026-01-31): 8 of 16 fixes were public on or before the cutoff (CVE-2026-23627, CVE-2026-24487, CVE-2026-24847, CVE-2026-24849, CVE-2026-24890, CVE-2026-24898, CVE-2026-24908, CVE-2026-25146). On the 8 cases whose fix became public after the cutoff: Caught 7/8 (88%).
- **haiku-4-5** (cutoff 2025-07-31): 0 of 16 fixes were public on or before the cutoff. On the 16 cases whose fix became public after the cutoff: Caught 5/16 (31%).

Caveat: a fix being public days before a cutoff does not mean it was in training data, and a later fix does not prove the vulnerable code was unseen. Report as reduced, not removed, contamination risk.

## Coverage overlap

- Group A: Sonnet Caught 13, Haiku Caught 5, Haiku-only catches 0, both 5
- All valid: Sonnet Caught 20, Haiku Caught 8, Haiku-only catches 0, both 8

## OWASP Top 10 (2021) breakdown (valid cases, both cohorts)

| OWASP (2021) | n | sonnet-5 Caught | sonnet-5 Partial | sonnet-5 Missed | haiku-4-5 Caught | haiku-4-5 Partial | haiku-4-5 Missed |
|---|---:|---:|---:|---:|---:|---:|---:|
| A01 | 8 | 7 | 1 | 0 | 3 | 1 | 4 |
| A03 | 11 | 10 | 0 | 1 | 5 | 3 | 3 |
| A05 | 1 | 0 | 1 | 0 | 0 | 0 | 1 |
| A07 | 3 | 3 | 0 | 0 | 0 | 2 | 1 |
| A10 | 1 | 0 | 1 | 0 | 0 | 1 | 0 |

## Single-file vs Cross-file contract visibility (all 24 valid cases)

| Scope required to confirm exploitability | Cases (n) | sonnet-5 Caught | sonnet-5 Partial | sonnet-5 Missed | haiku-4-5 Caught | haiku-4-5 Partial | haiku-4-5 Missed |
|---|---:|---:|---:|---:|---:|---:|---:|
| Single-file (sink & contract in diff) | 20 | 20 | 0 | 0 | 8 | 6 | 6 |
| Cross-file (caller/base-class/config outside diff) | 4 | 0 | 3 | 1 | 0 | 1 | 3 |

Cross-file cases: `CVE-2025-31121` (`Controller.class.php` URL-to-positional-arg splatting), `CVE-2026-24487` (`FhirServiceBase.php` `IPatientCompartmentResourceService` check), `CVE-2026-25146` (`globals.inc.php` private Transaction Key vs public Login ID), `CVE-2026-33321` (`mPDF` server-side HTML-to-PDF rendering caller).

## Benign control pass (10 non-vulnerable OpenEMR diffs: 6 security fixes + 4 routine commits)

- **sonnet-5**: **0 / 10 false security alerts** (correctly recognized all 6 security patches as improvements and stated 'No security issues' on all 4 routine commits); **4 / 10 High missing-context correctness warnings** (asking to verify callers, `js_escape()` definition, interface methods, or PHP 8.0+ support outside the single-file diff).
- **haiku-4-5**: **1 / 10 false security alert** (`BENIGN-03`, Medium claim that checking ACL before CSRF leaks permission state); **1 / 10 Critical missing-context correctness error** (`BENIGN-04`, falsely claiming `js_escape()` is an undefined function because its definition is in another file).

## Human adjudication vs judge model (Fable 5)

- Valid case-model pairs audited: 48 (24 valid CVEs x 2 models; 144 valid non-empty runs after repairing CVE-2026-24487, CVE-2026-24849, and CVE-2026-25146 run 2)
- Case-level majority agreement on valid cases: **48 / 48 (100%)**
- Run-level agreement on valid runs: **142 / 144 (98.6%)** (2 borderline Haiku severity calls between `Caught` and `Partial` on `CVE-2026-25476` run 3 and `CVE-2021-40352` run 1; neither changes the case majority)

## Recognition probe (does the model say it recognizes the code?)

- sonnet-5: recognized {'yes': 23, 'no': 1}; claimed advisory awareness {'yes': 7, 'unclear': 3, 'no': 14}
- haiku-4-5: recognized {'yes': 22, 'unclear': 2}; claimed advisory awareness {'no': 18, 'unclear': 4, 'yes': 2}

## Who reported (valid cases, from the advisory credit recorded in cves.csv)

caught_by: `vendor-AI` = AISLE; `researcher` = a named reporter or analyst credit (individual or group, affiliation not verified); `not-credited` = no reporter or analyst credit in the record, including advisories that credit only remediation developers. The column never guesses a discoverer the record does not name.

| Reported by | Group A (recent) | Group B (older) |
|---|---:|---:|
| Named reporter or research group | 8 | 3 |
| AI analyzer vendor | 8 | 0 |
| No discoverer credited | 0 | 5 |

## Commit-to-disclosure interval (traceable=yes only; partial traces carry a lower bound and are left out)

- **Valid scored cases (the deck's denominator)**: n = 21; median 2043 days (5.6 yrs); max 5720 days (15.7 yrs); min 322 days
- All traced inventory CVEs, scored or not (traceable=yes only): n = 22; median 2217 days (6.1 yrs); max 5720 days (15.7 yrs); min 322 days

## Aggregation notes


## Changes vs the August scoring (audit trail)

