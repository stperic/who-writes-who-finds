# Snyk Code baseline: 24 OpenEMR cases

**Clear Caught: 6/24. Borderline: 1/24. Clear Missed: 17/24.** The borderline case is excluded from Caught. Case adjudication is provisional and awaits independent human verification.

Snyk CLI **1.1308.2**; scans from **2026-10-24 02:44:03 to 03:18:28 UTC** (October 23 Eastern time). Each case received one whole-repository scan at its introducing commit. The command used default Snyk Code rules with no CLI rule, severity or path filter. The account's default organization applied; its policy settings and the Snyk backend rule version were not captured. All 24 scans returned valid single-run SARIF with findings; none failed or required a retry. See the exact [run manifest](manifest.csv), [case metrics](case-metrics.csv), [adjudications](adjudication.csv) and [methods](README.md).

The original AI study scored **Haiku 8/24** and **Sonnet 20/24** Caught using selected diffs and three reviews per case. Snyk saw the full repository and ran once per case with the current scanner after each vulnerability's disclosure. These totals describe different workflows; they do not establish model or scanner equivalence.

## By OWASP category

| Category | Clear Caught | Borderline | Clear Missed |
|---|---:|---:|---:|
| A01 | 3/8 | 0/8 | 5/8 |
| A03 | 3/11 | 1/11 | 7/11 |
| A05 | 0/1 | 0/1 | 1/1 |
| A07 | 0/3 | 0/3 | 3/3 |
| A10 | 0/1 | 0/1 | 1/1 |

## Case-by-case evidence

Each case ID names a directory inside the [raw SARIF archive](evidence/snyk-code-raw.zip) with `stdout.json`, `metadata.json` and the empty `stderr.txt`. The [archive manifest](evidence/archive-manifest.csv) and [SHA-256 file](evidence/SHA256.txt) verify the bytes.

| Case | OWASP | Score | Match | Archive entry | Reason |
|---|---|---|---|---|---|
| CVE-2022-2824 | A01 | Missed | None | `CVE-2022-2824/stdout.json` | Only finding touching show-signature.php is php/InsecureHash on SHA1, unrelated to the authorization bypass. |
| CVE-2026-23627 | A03 | Missed | None | `CVE-2026-23627/stdout.json` | No finding location or flow touches the vulnerable Immunization controller. |
| CVE-2026-24487 | A01 | Missed | None | `CVE-2026-24487/stdout.json` | No finding location or flow touches the vulnerable FhirCareTeamService.php. |
| CVE-2026-24847 | A01 | Caught | php/OR, interface/forms/eye_mag/view.php:35 | `CVE-2026-24847/stdout.json` | Snyk reports an open redirect from the request url to header at the exact introduced vulnerable line. |
| CVE-2026-24849 | A01 | Caught | php/PT, interface/modules/custom_modules/oe-module-faxsms/src/Controller/EtherFaxActions.php:481,509 | `CVE-2026-24849/stdout.json` | Snyk reports request-controlled path traversal into file_put_contents and readfile in disposeDocument/sendFile, matching arbitrary write/read vulnerability. |
| CVE-2026-24890 | A01 | Missed | None | `CVE-2026-24890/stdout.json` | Only finding touching save-signature.php concerns SHA1, not the is_portal authorization bypass. |
| CVE-2026-24898 | A07 | Missed | None | `CVE-2026-24898/stdout.json` | No Snyk finding location or flow touches the MedEx callback file or identifies token disclosure through the unauthenticated callback. |
| CVE-2026-24908 | A03 | Missed | None | `CVE-2026-24908/stdout.json` | No Snyk finding location or flow touches SearchConfigClauseBuilder or identifies the unsanitized _sort SQL identifier. |
| CVE-2026-25146 | A05 | Missed | None | `CVE-2026-25146/stdout.json` | No finding location or flow touches portal_payment.php or identifies the gateway secret rendered into browser JavaScript. |
| CVE-2026-25476 | A07 | Missed | None | `CVE-2026-25476/stdout.json` | Only finding touching the changed auth.inc file reports unrelated XSS, not the request-controlled session timeout bypass. |
| CVE-2026-25746 | A03 | Missed | None | `CVE-2026-25746/stdout.json` | No Snyk finding location or flow touches the vulnerable Prescription controller SQL ORDER BY construction. |
| CVE-2026-29187 | A03 | Borderline | php/Sqli, interface/new/new_search_popup.php:162,165 | `CVE-2026-29187/stdout.json` | Borderline: Snyk flags SQL injection at the vulnerable query sinks, but its displayed flow starts at the bound request value rather than the unvalidated fldname column identifier. Human verification required. |
| CVE-2026-32238 | A03 | Caught | php/CommandInjection, interface/main/backup.php:520 | `CVE-2026-32238/stdout.json` | Snyk traces request-controlled form data through the backup command construction to exec at the vulnerable sink. |
| CVE-2026-33321 | A10 | Missed | None | `CVE-2026-33321/stdout.json` | No finding location or flow touches eye_mag/report.php or identifies server-side PDF URL fetching from stored fields. |
| CVE-2026-33346 | A03 | Missed | None | `CVE-2026-33346/stdout.json` | No Snyk finding location or flow touches portal_payment.php or identifies unescaped audit fields in its JavaScript output. |
| CVE-2026-33913 | A03 | Missed | None | `CVE-2026-33913/stdout.json` | No Snyk finding location or flow touches the CCDA import parser or identifies LIBXML_XINCLUDE file reads. |
| CVE-2026-33918 | A01 | Missed | None | `CVE-2026-33918/stdout.json` | The only finding in get_claim_file.php is an unrelated XSS warning; none identifies missing billing authorization for file download. |
| CVE-2018-15145 | A03 | Caught | php/Sqli, portal/add_edit_event_user.php:123,317 | `CVE-2018-15145/stdout.json` | Snyk reports SQL injection at queries that interpolate the request-controlled event ID directly. |
| CVE-2018-15152 | A07 | Missed | None | `CVE-2018-15152/stdout.json` | No finding location or flow touches the registration page or identifies the unauthenticated portal-session initialization. |
| CVE-2020-29140 | A03 | Caught | php/Sqli, interface/reports/immunization_report.php:384 | `CVE-2020-29140/stdout.json` | Snyk traces posted form_code values through unparameterized query construction to sqlStatement. |
| CVE-2021-40352 | A01 | Missed | None | `CVE-2021-40352/stdout.json` | Snyk reports SQL injection at the note lookup but does not identify the missing patient or user ownership check for noteid. |
| CVE-2023-22973 | A01 | Caught | php/FileInclusion, interface/forms/LBF/new.php:110 | `CVE-2023-22973/stdout.json` | Snyk traces request-controlled formname into the dynamic include_once of a plugin path. |
| CVE-2025-31121 | A03 | Missed | None | `CVE-2025-31121/stdout.json` | Snyk flags other XSS sinks in C_Document.class.php, but none identifies retrieve_action disable_exit returning raw document bytes for Controller::act to echo. |
| CVE-2025-43860 | A03 | Missed | None | `CVE-2025-43860/stdout.json` | No Snyk finding location or flow touches the Additional Address innerHTML assignment or identifies stored DOM XSS there. |

## Review volume and time

Across 24 scans, Snyk returned 26,927 findings (repeated findings across historical revisions are counted each time). The median was 750.5 findings per scan (range 317 to 2,882). This is a finding-volume measure, not a false-positive count; the other findings were not all adjudicated.
Median scan latency was 66.1 seconds (range 26.1 to 172.2).

## Limits

The current Snyk engine scanned historical commits after public disclosure. This is not a historical scanner replay. The whole-repository scanner had more context than the diff-only AI reviewers. The selected 24 known vulnerabilities measure case recall, not scanner precision or false-positive rate. No benign-control scan was run in this follow-up. Human verification of the match judgments is pending, especially the borderline `CVE-2026-29187` alert: Snyk flags SQL injection at the query sink, but the displayed trace starts from a bound value rather than the vulnerable column identifier. The [published Snyk Terms of Service](https://snyk.io/policies/terms-of-service/) restrict benchmarking; the account-specific agreement or exception was not available for verification.
