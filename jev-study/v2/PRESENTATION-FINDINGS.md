# Presentation-ready findings

**Suggested slide title: Category estimates can inform review policy; uncertainty still needs an owner.**

The original exploratory Jev pilot used 14 changes, including two synthetic controls, with three calls each. Against unchanged draft labels, 32 of 42 calls agreed, six disagreed and four abstained. All eight CVE cases included their draft-required roles on all 24 calls. These are reviewer-routing observations, not vulnerability-detection results.

V2 separates category estimates from deterministic policy obligations, recorded triage and completed review. Reinterpreting the **same archived probabilities** under a rule that sends conflicting low-impact/specialist signals to triage gives **32 agreements, three incorrect assignments and seven unresolved assignments out of 42 planned calls**. The seven are four abstentions and three conflicts. This policy change does not improve the underlying model or establish safety.

| Development method | Allowed-set agreement | Incorrect | Unresolved | Cases agreeing on every evaluated repeat |
|---|---:|---:|---:|---:|
| Jev probabilities, v2 handling, threshold 0.5 | 32/42 calls | 3 | 7 | 10/14 |
| Changed-line/path rules | 6/14 cases | 8 | 0 | 6/14 |
| Request every available specialist | 1/14 cases | 13 | 0 | 1/14 |

Jev repeats are correlated observations; they are not 42 independent cases. Baselines run once per case. These results include the two synthetics. On real changes only, Jev agrees on 26/36 calls; rules on 4/12 cases; all-specialists on 1/12. The machine-readable report retains each subset and case. Labels are unadjudicated and the baselines were created after inspecting development results, so this is exploratory evidence of possible discrimination, not a held-out superiority claim.

Among resolved proposals, Jev omitted no draft-required specialist role and added an unnecessary role on three calls. Rules omitted one specialist assignment and added roles on seven cases. The all-specialists baseline omitted no specialist and added roles on 13 cases. There were zero peer-only assignments on specialist-required cases for these methods. Both baselines also fail to select the low-impact category on some routine cases; their policy layer still retains mandatory peer review. Unresolved Jev cases are not counted as successful role assignments or silently dropped.

Development diagnoses:

- **Patient-boundary fix:** boundary probabilities were 0.35, 0.43 and 0.34, producing three abstentions at 0.5. Lowering to 0.4 resolves only one repeat. Missing context has not been established as the cause.
- **Calendar change:** low-impact probabilities were 0.48, 0.52 and 0.54. At threshold 0.5, one repeat abstains; at 0.4 all select low impact; at 0.6 all abstain. This is sensitivity around a decision threshold, not a calibrated risk estimate.
- **Payment-secret change:** platform/security is added outside the draft allowed set on all three repeats at 0.5. Independent humans must decide whether that label boundary is defensible; the expected labels have not been changed.
- **Payment arithmetic change:** construction is 0.63 on every repeat while low impact is 0.73, 0.68 and 0.64. V1 retained construction; v2 records a conflict and requires triage. It is not a completed review.

Across thresholds 0.4 / 0.5 / 0.6, agreement is 31 / 32 / 31 of 42; unresolved assignments are 5 / 7 / 9. Primary threshold remains 0.5. Thirteen of 14 cases have stable status and route sets across repeats at 0.5, including stable failures. Stability does not establish correctness.

Original reported cost was **$0.008253378 for 42 calls**. Recorded request times sum to 7.26 seconds, with median about 0.169 seconds and maximum 0.300 seconds. These measurements describe this small sequential pilot, not production throughput, worst-case latency, or the cost of stronger downstream review. The follow-up made no new live model calls.

**What is ready:** a separate versioned harness, nine unqueried public holdout changes in six families, a blinded 23-case human packet, frozen preparation inputs, two baselines and deterministic workflow tests. Tests exercise missing/stale approvals, missing/stale checks, abstention, failure, conflict, missing context and reviewer unavailability. They are software tests, not evidence that humans caught vulnerabilities.

**What remains unproven:** independently validated labels, held-out routing accuracy, actual human reviewer availability, named-person selection, choice of the best AI reviewer, downstream vulnerability detection, review effort, and production merge enforcement. Independent human adjudication is the remaining prerequisite for the held-out routing run. Real repository owner/check integration is a separate prerequisite for production use.

**Practical policy lesson:** use model estimates to propose additional review obligations. Preserve mandatory owners and checks, keep uncertain assignments open until authorized triage resolves them, and require evidence that the specified reviews actually completed. “No findings” and “reviewer assigned” are both insufficient evidence of approval.
