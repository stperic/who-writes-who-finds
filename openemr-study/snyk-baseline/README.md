# Snyk Code baseline on the 24 OpenEMR cases

This is a separate follow-up to the [original OpenEMR AI review study](../README.md). It asks whether Snyk Code, the source-code scanner used by the study author, identifies the same 24 known vulnerabilities. It does not alter the original case set, prompts, model runs or scoring artifacts.

## Result

| Disposition | Cases |
|---|---:|
| Clear Caught | **6/24** |
| Borderline, excluded from Caught | **1/24** |
| Clear Missed | **17/24** |

These are provisional case-match judgments, not independent human signoff. The [results](RESULTS.md) give every case, OWASP breakdown, finding identity, reason and review volume. The one borderline SQL-injection result may change after human verification; it is not included in the six clear catches.

## What is in this folder

| File | Purpose |
|---|---|
| [RESULTS.md](RESULTS.md) | Full case table, OWASP totals, timing, volume and limits. |
| [manifest.csv](manifest.csv) | The 24 original cases, full introducing-commit SHAs, fix SHAs, changed files and ground truth. |
| [case-metrics.csv](case-metrics.csv) | Scan start and end times, revision, CLI version, exit status, finding count, latency and raw-output hash. |
| [adjudication.csv](adjudication.csv) | One provisional Caught, Borderline or Missed ruling and reason per case. |
| [evidence/snyk-code-raw.zip](evidence/snyk-code-raw.zip) | Exact CLI SARIF output, metadata and stderr for each of 24 scans. |
| [evidence/archive-manifest.csv](evidence/archive-manifest.csv), [evidence/SHA256.txt](evidence/SHA256.txt) | Byte sizes and SHA-256 checksums for the raw archive. |
| [run.py](run.py) | Run the 24 whole-repository scans in a separate OpenEMR worktree. |
| [analyze.py](analyze.py) | Extract every finding and file-overlap candidate into a local review queue. It does not assign case scores. |
| [verify.py](verify.py) | Verify the published archive, raw hashes, 24 valid scans, metrics and adjudication totals without an API call. |

Only one compressed raw archive is tracked. The 24 expanded SARIF files and the 26,927-row review queue are generated locally under ignored `build/` paths.

## Case and revision selection

The [original case matrix](../data/case-matrix.csv) supplies 24 CVEs across the original OWASP categories. For each case, `manifest.csv` pins the full SHA of the **introducing commit**, the commit whose selected diff the AI reviewer saw. This is a vulnerable revision. The later fix commit is recorded for provenance but is not scanned. The original study selected these cases using known vulnerabilities; this follow-up is a retrospective case-recall test, not a random sample of changes.

The scan checks out each revision of the [public OpenEMR repository](https://github.com/openemr/openemr) into a separate Git worktree. It runs from that revision's repository root. No file list, changed-file filter, custom rule pack, severity threshold or added context was passed to Snyk. Normal Snyk Code file selection and exclusions still apply. The AI reviewers saw selected diffs, while Snyk could analyze the repository.

## Exact run

- **Product and CLI:** Snyk Code, CLI `1.1308.2`. Snyk Code supports PHP and interfile analysis ([Snyk PHP documentation](https://docs.snyk.io/supported-languages/supported-languages-list/php)). Snyk Open Source dependency scanning was not used.
- **Command for every case:** `snyk code test --json --remote-repo-url=https://github.com/openemr/openemr`, executed with the case worktree as the current directory. The URL identifies the public source repository; it does not narrow the scan to changed files.
- **Account settings:** the CLI was authenticated to the author's Snyk account. No `--org` was supplied, so the account's default organization applied. Its policy settings and the Snyk service's backend rule version were not captured. No credential or token is stored in this folder.
- **Schedule:** 24 scans ran sequentially from **2026-10-24 02:44:03 to 03:18:28 UTC** (October 23 Eastern time). One CLI call was made per case, even when two cases shared an introducing commit.
- **Completion:** each call produced one valid SARIF run and returned with findings. There were no execution errors, timeouts or retries. All 24 stderr files are empty. The raw metadata records each exit code, timestamp, latency, finding count and output SHA-256.

The source checkout was an existing OpenEMR partial clone whose Git history was fetched before scanning. `run.py` is a portability cleanup of that runner: it now accepts a source path and output path, validates saved runs on resume and records extra metadata on future runs. The Snyk command, case order, revision policy and timeout remain the same. The archived metadata is the original execution record.

## Reproduce and verify

Use a clean OpenEMR clone with the historical commits and an authenticated Snyk CLI. The script requires Python 3.10 or newer and a Snyk CLI on `PATH`. Check the CLI version if you intend to compare output; even with the same CLI version, Snyk's hosted engine and rules can change.

```sh
git clone --filter=blob:none https://github.com/openemr/openemr.git build/openemr-snyk-source
python3 openemr-study/snyk-baseline/run.py --source build/openemr-snyk-source --output build/snyk-code-24
python3 openemr-study/snyk-baseline/analyze.py --output build/snyk-code-24
```

`run.py` leaves the source clone untouched, creates a sibling worktree, records raw results under the ignored output directory, and refuses to overwrite a completed or mismatched scan. A valid saved scan is hash checked and skipped on resume. Running these commands again makes new Snyk service requests only for cases without a valid saved result. To verify the published evidence without using Snyk:

```sh
python3 openemr-study/snyk-baseline/verify.py
```

## Scoring

The public case score counts **Caught only for a Snyk finding that identifies the selected vulnerability class and vulnerable code location well enough to act on it**. A warning about another vulnerability in the same file does not count. The adjudicator read finding messages, primary locations, dataflow locations, source code and the case ground truth. `analyze.py` reports file overlap to reduce review work; it never converts overlap to a catch automatically.

The original AI rubric includes Partial. For this scanner follow-up, a finding that does not clearly identify the selected flaw is not added to Caught. `CVE-2026-29187` is retained as **Borderline** rather than quietly counted or discarded: Snyk flags SQL injection at the vulnerable query sinks, but the displayed trace starts with a bound request value instead of the unvalidated column identifier. It needs independent human adjudication. All 24 judgments in [adjudication.csv](adjudication.csv) were prepared by the AI assistant and have not had independent human verification.

## Interpretation and publication

Snyk's current service scanned old commits after the flaws were publicly disclosed. The scanner's rule set was not historically replayed. The selected-case denominator measures recall on known vulnerabilities, not production detection rate, precision or false-positive rate. No benign controls were scanned here. Across the 24 full scans Snyk returned 26,927 findings, many repeated across historical revisions; these were not all classified as true or false alarms.

The [published Snyk Terms of Service](https://snyk.io/policies/terms-of-service/) include a restriction on benchmarking in section 2(i). The applicable account agreement or any exception was not available for verification. Confirm the right to present or redistribute this comparison before using the numbers in a public talk or other external material.
