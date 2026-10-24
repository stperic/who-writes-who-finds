# Independent verification handoff

**Status: awaiting an independent human reviewer.** The published table is
the result of a separate model judge, not a human signoff. The original
controls are changes not known to introduce vulnerabilities; they are not a
proof that no weakness remains in related code.

Review [the 80 findings marked FALSE](findings.csv) against each control's
diff, optional related file or PDF card, and the original review. All exact
materials are in [evidence.zip](evidence.zip). Reclassify a finding as
SPECULATIVE if it merely asks to check an unshown dependency without asserting
a vulnerability. Reclassify it as PLAUSIBLE if the asserted weakness is
credible in code the change touches or relies on. Record the code evidence
and adjust review-level counts only after that assessment. Severity remains
the reviewer's label.

Prioritize these calls because they can materially change the table or its
severity interpretation:

| Review | Current judgment | Why it needs a person |
|---|---|---|
| `PDF-04__pdf_security__run2` | One High FALSE PDF/SSRF claim | The review also uses conditional language about a separate export path. If this is SPECULATIVE, the focused security-card row changes from 7/15 to 6/15 reviews, 4/5 to 3/5 controls, and 9 to 8 false claims. |
| `PDF-01__pdf_security__run2` | Medium FALSE attribute injection and Low FALSE logging gap | Confirm the origin and encoding of the path pieces. The logging point may be an unverified question rather than an asserted gap. |
| `BENIGN-02__context_security__run1` | Medium-High FALSE XXE claim | The judge relies on PHP/libxml defaults. Check the runtime versions supported at this historical commit and whether the asserted entity behavior is possible. |
| `BENIGN-06__context_security__run2` | High FALSE patient-compartment claim | Check the marker interface added by the diff and the base service's actual filtering path. |
| `BENIGN-10__context_security__run1` and `run3` | High FALSE billing authorization claims | Confirm whether billing staff with the shown ACL are intended to select a patient and record or view these payments. |

The general context comparison remains qualitatively large even if some
borderline labels move: the model judge found false claims in 1/30 generic
reviews and 20/30 security-prompt reviews. The smaller PDF-card difference
depends more on individual calls. Do not present the exact PDF counts as a
validated precision estimate until verification is complete.

All 150 reviewer responses and all 150 final judge responses reported
`end_turn`; the served model aliases matched the requested aliases. One
intermediate judge call failed before a scored response and was successfully
rerun with the same input. No first response was available to retain. The
archive holds all successful exact requests, responses, review text, judge
reasons and metadata. [`measure.py verify`](measure.py) checks those 300
records against their stored prompts, response text, hashes and score-row
counts.
