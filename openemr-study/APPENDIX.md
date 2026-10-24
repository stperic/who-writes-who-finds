# Presentation appendix

## Suggested slide

**Can better prompting close the Haiku gap?**

| Same 24 blinded OpenEMR diffs | Caught | Partial | Missed |
|---|---:|---:|---:|
| Haiku 4.5, new generic-prompt baseline | 11/24 | 11/24 | 2/24 |
| Haiku 4.5, OWASP plus touched-code prompt | **19/24** | 4/24 | 1/24 |
| Sonnet 5, historical generic-prompt result | 20/24 | 3/24 | 1/24 |

**Review burden:** false security alarms occurred in 8/30 generic-prompt benign reviews and 24/30 stronger-prompt benign reviews. Stronger-prompt controls contained 91 security findings, including 56 judged unsupported and 26 speculative questions.

*Three independent reviews per case and prompt. New runs used the exact Haiku 4.5 model ID and matched direct API settings. The Sonnet result used the earlier Claude Code setup. New scores are model-judged and await independent human verification. Matching historical totals alone would not establish model equivalence.*

## Short spoken answer

“Yes. On the same 24 cases, better instructions raised Haiku's catches from 11 to 19 in our new controlled runs. That is close to Sonnet's earlier 20, but the older Sonnet setup was different, so I would not call the models equivalent. The stronger prompt also produced false security alarms in 24 of 30 benign reviews, up from 8. Prompting improved detection and increased review work. These new scores still need human verification.”

## If asked about the original five catches

The first study reported five Haiku catches among the 16 post-cutoff cases and eight across all 24. In the new direct API experiment, all five post-cutoff catches reappeared under the original generic prompt before the stronger prompt was run. The new generic full-set total was 11/24, so the new prompt effect is measured against 11/24 rather than assuming the historical eight would persist.

## If asked whether a linked requirement could recover the PDF SSRF

**Slide-sized comparison:** same historical diff and Sonnet 5 review prompt;
functional PDF requirement, **0/3** explicit SSRF findings; proposed PDF
resource-control requirement, **3/3** explicit findings.

**Spoken answer:** “A requirement saying only that the report exports to PDF did
not change the result. A proposed security rule saying that clinical narrative
must not choose resources for the PDF renderer did. Sonnet then connected the
unescaped HPI to a server-side request in all three reviews. This is a
retrospective one-case probe. ZZ-Trace did not select the rule, and an accepted
requirement link would still need an executed test on the reviewed revision.”

The full proposed rule permits application-controlled, authorized clinical
media. It is in the [PDF follow-up](data/pdf-requirement-followup/README.md).
It was written after the flaw was known and should not be presented as an
upstream OpenEMR requirement or as a new 24/24 result.
