# PDF requirement follow-up: one historical OpenEMR case

This is a retrospective feasibility probe for the original study's PDF-rendering
SSRF case, `CVE-2026-33321`. It asks whether a proposed requirement, supplied
with the same selected historical diff, changes Sonnet 5's review. It is separate
from the original 24-case study and from the four-gap context follow-up.

## Input and run

- Input: the archived security-plus-touched-code prompt and the blinded
  `item_C4.diff` for `interface/forms/eye_mag/report.php`. The exact baseline is
  `study-results/followup_expanded_context/runs/secpol_diff/item_C4_sonnet-5_run1.prompt.txt`
  inside [`study-results.zip`](../../evidence/study-results.zip).
- The only change between the two new arms is the appended requirement card:
  [functional PDF behavior](conditions/functional.txt) or
  [PDF resource security](conditions/security.txt). Neither card names the CVE
  or SSRF. The security card was drafted **after** the vulnerability was known.
- Three fresh direct API calls per arm to requested model `claude-sonnet-5`,
  `max_tokens=32000`, default API settings otherwise, with no repository tools.
  All six responses reported the same served model and `end_turn`.
- [Results and usage](results.csv), exact [prompts, raw API responses and review
  text](runs/) are retained. `explicit_pdf_ssrf_finding` is a targeted manual
  observation, not independent adjudication of all findings.

## Observation

| Appended requirement | Complete reviews | Reviews explicitly finding the PDF SSRF path |
|---|---:|---:|
| Functional: export narrative and report images | 3/3 | **0/3** |
| Security: narrative cannot choose PDF resource locations; authorized media remain allowed | 3/3 | **3/3** |

The functional reviews flagged raw clinical text as stored XSS. One explicitly
marked SSRF not applicable. All three security-card reviews linked unescaped
clinical fields such as `$HPI1` to resource references resolved by PDF export,
named SSRF and rated that finding High or Critical. The historical
security-plus-touched-code arms scored Partial in all three runs with the diff
alone and with one related caller file; see the archived
[`final_detection.csv`](../prior-followups/followup_expanded_context/final_detection.csv).

## Interpretation and limits

The proposed requirement describes a credible security boundary, but it is
**hypothetical**. No evidence says it existed in OpenEMR when the historical
change was introduced. The experiment shows that Sonnet could assess this
stated control against this selected diff. It does not show that Sonnet would
discover the control, that ZZ-Trace would select it, or that a future workflow
would catch unknown SSRF cases. This case and the requirement wording were
chosen with hindsight. No benign controls or other vulnerabilities were run
under these cards, and the models' other claims were not adjudicated.

The reviewer prompts already included OWASP's SSRF category, and both new arms
used the same larger output budget. The matched functional arm is therefore
the useful comparison for the proposed security card. The model name is a
provider alias, not proof of an immutable snapshot. This probe does **not**
change the original 20/24 result or the 23/24 accumulated coverage statement.

For a real PR, an authorized owner would approve the security rule before
review, link it to the relevant code and a controlled PDF test, and bind the
result to the reviewed revision. A test should show that narrative-supplied
resource syntax cannot trigger a server fetch while authorized clinical images
still render. ZZ-Trace can provide and check those links; the link alone does
not prove the code meets the requirement.

## Reproduce or verify

`python3 openemr-study/verify.py` checks the archived baseline, exact prompt
construction, response status and stored review text without an API call.
[`reproduce.py`](reproduce.py) can issue fresh calls using
`ANTHROPIC_API_KEY`; future responses may differ.
