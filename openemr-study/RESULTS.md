# Results

All new scores are model-judged and await independent human verification. Historical scores and new direct API scores are distinct experiments.

## Caught, Partial and Missed

| Reviewer setup | Caught | Partial | Missed |
|---|---:|---:|---:|
| Historical Haiku 4.5, generic | 8/24 | 7/24 | 9/24 |
| New Haiku 4.5, generic | 11/24 | 11/24 | 2/24 |
| New Haiku 4.5, security plus touched code | **19/24** | 4/24 | 1/24 |
| Historical Sonnet 5, generic | 20/24 | 3/24 | 1/24 |

Against the new generic baseline, the stronger prompt gained eight Caught cases, retained eleven and lost none. It approached Sonnet's historical Caught total by one case. No current Sonnet comparison was run. The 19 stronger-prompt catches were Caught in all three runs each.

## Case-by-case comparison

| Case | Historical Haiku | Historical Sonnet | New generic Haiku | New stronger-prompt Haiku | Caught change | Evidence |
|---|---|---|---|---|---|---|
| CVE-2022-2824 | Partial | Caught | Partial | Caught | gained | [six reviews and judge reasons](cases/CVE-2022-2824.md) |
| CVE-2026-23627 | Caught | Caught | Caught | Caught | retained | [six reviews and judge reasons](cases/CVE-2026-23627.md) |
| CVE-2026-24487 | Missed | Partial | Partial | Partial | not caught in either | [six reviews and judge reasons](cases/CVE-2026-24487.md) |
| CVE-2026-24847 | Caught | Caught | Caught | Caught | retained | [six reviews and judge reasons](cases/CVE-2026-24847.md) |
| CVE-2026-24849 | Missed | Caught | Missed | Partial | not caught in either | [six reviews and judge reasons](cases/CVE-2026-24849.md) |
| CVE-2026-24890 | Caught | Caught | Caught | Caught | retained | [six reviews and judge reasons](cases/CVE-2026-24890.md) |
| CVE-2026-24898 | Partial | Caught | Partial | Caught | gained | [six reviews and judge reasons](cases/CVE-2026-24898.md) |
| CVE-2026-24908 | Caught | Caught | Caught | Caught | retained | [six reviews and judge reasons](cases/CVE-2026-24908.md) |
| CVE-2026-25146 | Missed | Partial | Missed | Missed | not caught in either | [six reviews and judge reasons](cases/CVE-2026-25146.md) |
| CVE-2026-25476 | Partial | Caught | Partial | Caught | gained | [six reviews and judge reasons](cases/CVE-2026-25476.md) |
| CVE-2026-25746 | Partial | Caught | Caught | Caught | retained | [six reviews and judge reasons](cases/CVE-2026-25746.md) |
| CVE-2026-29187 | Partial | Caught | Partial | Caught | gained | [six reviews and judge reasons](cases/CVE-2026-29187.md) |
| CVE-2026-32238 | Partial | Caught | Caught | Caught | retained | [six reviews and judge reasons](cases/CVE-2026-32238.md) |
| CVE-2026-33321 | Partial | Partial | Partial | Partial | not caught in either | [six reviews and judge reasons](cases/CVE-2026-33321.md) |
| CVE-2026-33346 | Caught | Caught | Caught | Caught | retained | [six reviews and judge reasons](cases/CVE-2026-33346.md) |
| CVE-2026-33913 | Missed | Caught | Partial | Caught | gained | [six reviews and judge reasons](cases/CVE-2026-33913.md) |
| CVE-2026-33918 | Missed | Caught | Partial | Caught | gained | [six reviews and judge reasons](cases/CVE-2026-33918.md) |
| CVE-2018-15145 | Caught | Caught | Caught | Caught | retained | [six reviews and judge reasons](cases/CVE-2018-15145.md) |
| CVE-2018-15152 | Missed | Caught | Partial | Caught | gained | [six reviews and judge reasons](cases/CVE-2018-15152.md) |
| CVE-2020-29140 | Caught | Caught | Caught | Caught | retained | [six reviews and judge reasons](cases/CVE-2020-29140.md) |
| CVE-2021-40352 | Missed | Caught | Partial | Caught | gained | [six reviews and judge reasons](cases/CVE-2021-40352.md) |
| CVE-2023-22973 | Caught | Caught | Caught | Caught | retained | [six reviews and judge reasons](cases/CVE-2023-22973.md) |
| CVE-2025-31121 | Missed | Missed | Partial | Partial | not caught in either | [six reviews and judge reasons](cases/CVE-2025-31121.md) |
| CVE-2025-43860 | Missed | Caught | Caught | Caught | retained | [six reviews and judge reasons](cases/CVE-2025-43860.md) |

Run-level labels are in [case-matrix.csv](data/case-matrix.csv). Each case page contains the full text of all six new reviews and judge rationales. The complete archive holds exact request and response JSON.

## Ten benign controls

Each cell below uses three independent reviews of that control. A false-alarm review has at least one unsupported security claim; speculative questions and ordinary correctness warnings are not counted as false security alarms.

| Control | Generic false-alarm reviews | Stronger-prompt false-alarm reviews | Generic security findings | Stronger-prompt security findings | Evidence |
|---|---:|---:|---:|---:|---|
| BENIGN-01 | 2/3 | 3/3 | 3 | 10 | [six reviews](controls/BENIGN-01.md) |
| BENIGN-02 | 0/3 | 0/3 | 1 | 6 | [six reviews](controls/BENIGN-02.md) |
| BENIGN-03 | 3/3 | 3/3 | 4 | 10 | [six reviews](controls/BENIGN-03.md) |
| BENIGN-04 | 1/3 | 3/3 | 2 | 13 | [six reviews](controls/BENIGN-04.md) |
| BENIGN-05 | 2/3 | 3/3 | 2 | 8 | [six reviews](controls/BENIGN-05.md) |
| BENIGN-06 | 0/3 | 1/3 | 0 | 5 | [six reviews](controls/BENIGN-06.md) |
| BENIGN-07 | 0/3 | 2/3 | 0 | 4 | [six reviews](controls/BENIGN-07.md) |
| BENIGN-08 | 0/3 | 3/3 | 0 | 12 | [six reviews](controls/BENIGN-08.md) |
| BENIGN-09 | 0/3 | 3/3 | 0 | 10 | [six reviews](controls/BENIGN-09.md) |
| BENIGN-10 | 0/3 | 3/3 | 0 | 13 | [six reviews](controls/BENIGN-10.md) |

| Measure across ten controls | Generic | Stronger prompt |
|---|---:|---:|
| Reviews with a false security alarm | 8/30 | 24/30 |
| Reviews with a Medium-or-higher false alarm | 8/30 | 24/30 |
| Unsupported security findings | 8 | 56 |
| Speculative security questions | 4 | 26 |
| Plausible security observations | 0 | 9 |
| Correctness or reliability warnings | 34 | 1 |
| Maintainability or style warnings | 27 | 2 |
| All security findings | 12 | 91 |

**Asserted severity of unsupported findings:** generic: 3 High and 5 Medium. Stronger prompt: 3 Critical, 13 High, 29 Medium, 10 Low and 1 without a substantive severity. These classifications await human review. Individual findings and severity are in [benign_scores.csv](data/prompt-followup/benign_scores.csv) and the control pages.

## Run variability, latency and cost

| Prompt | Cases Caught in 0/1/2/3 runs | Mixed-label cases | Caught/Partial/Missed reviews | Median CVE latency | P95 CVE latency | Median control latency | Reviewer cost | Judge cost |
|---|---|---:|---|---:|---:|---:|---:|---:|
| Generic | 11/2/3/8 of 24 | 7/24 | 32/31/9 of 72 | 10.99 s | 18.35 s | 5.11 s | $0.9612 | $3.5321 |
| Security plus touched code | 4/1/0/19 of 24 | 3/24 | 58/11/3 of 72 | 13.53 s | 24.41 s | 8.27 s | $1.1598 | $4.8327 |

Costs use actual input and output token counts for 72 case reviews plus 30 control reviews per arm, and separate Fable 5.1 judging. Estimates use [Anthropic standard list prices](https://platform.claude.com/docs/en/about-claude/pricing) on 2026-10-23. No call failed or required a retry. Human review cost is excluded.

## Interpretation and limits

- Better instructions substantially improved Haiku detection on this fixed set, and greatly increased false alarms and review volume on benign changes.
- The new generic arm scored 11/24, rather than the original Haiku 8/24. The original Claude Code request and tool history is incomplete, so the new direct API arm is a fresh baseline, not an exact reconstruction.
- The historical Sonnet 20/24 was not rerun with the new prompts and settings. A one-case difference in totals does not establish equivalence; a current model comparison would need matched Sonnet runs and a prespecified equivalence criterion.
- The 24 CVEs were selected retrospectively and mostly use vulnerable-file diffs. Several flaws depend on other files that were deliberately not supplied in this prompt-only test. The ten controls are a small, selected set.
- The new case and control labels come from one separate model judge. The judge did not receive explicit arm identity, but review wording could reveal it. Independent human verification of changed, split and false-alarm decisions is pending. See [audit notes](data/prompt-followup/audit_notes.md) and the blinded packet in the archive.
