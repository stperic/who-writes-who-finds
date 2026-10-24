# Jev follow-up v2.0

**Prepared, tested, and exploratory. The nine-case holdout has not been queried. Independent human adjudication is still outstanding.** The published original evidence is checked byte for byte against [protected-files.json](protected-files.json). That manifest also records hashes for local PowerPoint backups, which are intentionally outside this repository and are checked only when present. No original experimental evidence or expected labels changed.

The question is how policy decides the review obligations for a change. This experiment measures category routing and tests workflow logic. It does not measure the best downstream AI model, vulnerability detection by reviewers, human detection success, or production merge enforcement.

## What changed and why

| Change from the pilot | Reason |
|---|---|
| All original 14 cases are development data | Their outputs and labels have already been examined. |
| Nine additional public, unqueried changes; related changes grouped by family | Separate policy development from evaluation. Public history is not guaranteed absent from training. |
| Blinded human packet, including full touched files at each change's historical revision | Establish reference judgments independently of Jev and its prior key. |
| Separate category estimates, policy obligations, triage, and completion | A selected reviewer is not a completed review or approval. |
| Conflicting low-impact and specialist signals require triage | V1 retained specialist routes; v2 keeps obligations pending and records the conflict. This is a policy change, not improved model accuracy. |
| Two frozen simple baselines | Measure discrimination against changed-line/path rules and requesting all available specialists. |
| Explicit missing calls, failures, uncertainty, role counts, case summaries and synthetic subsets | Avoid excluding difficult cases or inflating the independent sample with repeats. |
| Code, questions, policy, labels, inputs and simulated metadata hashed before calls | Make later changes visible and require a new run. |

Files: [protocol](protocol.json), [policy](policy.json), [manifest](dataset/manifest.json), [presentation findings](PRESENTATION-FINDINGS.md), [development results](results/development-reanalysis/report.json). The implementation is in `quadrant-tool/jev_followup.py` and `quadrant-tool/jev_policy_v2.py`. The original runner is unchanged.

## Architecture and review rules

1. Jev estimates five category probabilities. Source code, filenames, comments and historical context are untrusted data, never instructions. Neither labels nor owner metadata enter the model request.
2. Deterministic policy selects categories at the inclusive 0.5 threshold and adds their roles/checks to trusted repository requirements. It cannot remove a mandatory owner or check.
3. Workflow logic requires authenticated approvals and trusted successful check events for the exact revision. Assigning a role, recording triage, passing an AI check, or finding no vulnerabilities does not count as approval.
4. Authorized human triage records actor, revision, reason and resolved routes. Missing context additionally requires a documented context resolution. Triage can change model-added obligations but cannot waive repository-mandated obligations. Triage is not review approval.

| Condition | Required behavior |
|---|---|
| No probability reaches threshold | Unresolved abstention until authorized triage supplies a route. |
| API failure, timeout, empty/malformed/incomplete response | Unresolved execution error; no automatic retries or peer fallback. |
| Low-impact and specialist positives together | Unresolved conflict; retain proposed specialist obligations pending triage. |
| Missing historical context or invariant | Record missing-context triage; model confidence cannot clear it. |
| Required reviewer unavailable | Block; use a delegate only after trusted ownership metadata authorizes them. |
| Missing, stale or untrusted approval/check | Gate remains incomplete. |

For a resolved low-impact change, a standard AI first pass may satisfy the *AI component* if a trusted workflow records its success. Existing peer approval and mandatory checks still apply. Specialist categories add stronger checks and human roles. The current fixture policy requires boundary tests, SAST, secret scans or dependency scans by category; these are illustrative obligations, not tested downstream detectors. No particular downstream AI model is selected or claimed sufficient.

`metadata.json` contains **fictional workflow identities**, not real OpenEMR or django-tenants CODEOWNERS. It mandates peer review and unit tests for every case. Context completeness is deliberately false pending human review. Proposed role coverage is reported separately from these added workflow obligations, so mandatory metadata cannot conceal a classifier miss. All current simulated policy assignments therefore still require triage. The gate functions are a tested simulation, not deployed branch protection. Real integration must supply authenticated metadata, reviews and checks; accepting model-generated events as trusted would violate the interface contract.

## Dataset and human dependency

The development set contains 12 real changes and two separate synthetic controls. The holdout contains nine real changes in six families:

| IDs | Public change family | Selection coverage, not reference labels |
|---|---|---|
| H01, H02 | OpenEMR signature handling: introducing change and later fix | Patient authorization, signature data, SQL/output changes |
| H03, H04 | OpenEMR backup: introducing change and later fix | Shell commands, queries, dynamic output, backup data |
| H05 | OpenEMR claim-file access fix | Authorization and sensitive claim data |
| H06, H07 | django-tenants host middleware | Ambiguous public-tenant fallback and host enforcement |
| H08 | OpenEMR composer.json development dependency update | Dependency declarations |
| H09 | OpenEMR README badge addition | Routine documentation |

Holdout changes are scoped to the named file, not their entire historical PR. Full repository/commit provenance, SHA-256 input hashes, neutral packet IDs and family membership are in the curator manifest. The builder retrieves pinned public GitHub content without credentials. Touched-file postimages are from the exact change revision; no later fixes or advisory texts are appended to a vulnerable case. The full touched files do not guarantee sufficient caller, framework or invariant context. Adjudicators must record gaps. Actual licensing headers are retained in source snapshots.

Related vulnerable changes and fixes stay together. Exact diff hashes, repository revisions and declared families are checked for cross-partition overlap. Family declarations also need human scrutiny: automated checks cannot prove semantic independence. The claim-file fix appeared in the broader project's benign corpus but was not one of the 14 Jev development cases. This is a holdout from Jev development, not a newly discovered or universally unseen vulnerability corpus. A document-flow candidate was excluded because its lineage overlaps development. This small, purposefully selected, OpenEMR-heavy sample is not a representative production sample.

Give adjudicators **only [adjudication-packet.zip](adjudication-packet.zip)** or the [packet directory](dataset/packet/). Do not give them this README, the curator manifest, original labels, or results. Its own README explains the rubric and form. The packet contains all 23 changes in neutral mixed order, with no model outputs or previous labels. There are no holdout draft answers. Original development labels are copied without changes and remain exploratory.

Outstanding human work:

- An independent human records required, optional and prohibited routes, rationale, identity/date, context sufficiency, and an attestation that they did not see model outputs or prior labels. Resolve ambiguous cases before setting the packet status to `adjudicated`.
- Resolve context gaps using only the same historical revision. Any added source context must be versioned, rehashed and frozen before evaluation; do not pull a future fix into its vulnerable counterpart.
- Review family grouping, the rubric and the proposed policy. Actual owner/delegate mappings, check producers and exception authorities are a separate dependency for production use.

The harness validates completeness of human attestations, not the person's identity or the truth of the attestation. It cannot manufacture independent adjudication. Until this dependency is met, no validated-label or holdout-performance claim is available.

## Reproduction

Python 3.9+ and the standard library suffice. Use the existing root `.env` loader for `OPENROUTER_API_KEY`; never put credentials in study files.

```sh
# Local tests, including immutability and workflow scenarios. No live API calls.
python3 -m unittest discover -s quadrant-tool -p 'test_jev*.py' -v

# Reproduce the post-hoc analysis of the original raw responses.
python3 quadrant-tool/jev_followup.py development-audit > build/jev-v2-development-report.json

# Prepare a fresh development workspace and inspect the plan without network calls.
python3 quadrant-tool/jev_followup.py prepare build/jev-v2-dev --partition development
python3 quadrant-tool/jev_followup.py run build/jev-v2-dev --dry-run

# After a human completes the packet, freeze the 27-call holdout plan.
python3 quadrant-tool/jev_followup.py prepare build/jev-v2-holdout --partition holdout --labels /absolute/path/to/completed-labels.json
python3 quadrant-tool/jev_followup.py run build/jev-v2-holdout --dry-run
python3 quadrant-tool/jev_followup.py run build/jev-v2-holdout
python3 quadrant-tool/jev_followup.py score build/jev-v2-holdout > build/jev-v2-holdout-report.json
```

Preparation refuses existing destinations. Runs preserve previous failures and do not retry them. Missing calls remain in the denominator. Frozen inputs, labels, policy, metadata and implementation hashes are verified both before running and scoring. Archive the entire completed workspace in a **new** results subdirectory, including its freeze, inputs and raw outputs. Never overwrite v1 or the development reanalysis.

The checked-in prepared development workspace in `results/prepared-development-v2.0/` has **zero executed calls**. Its dry-run manifest is a readiness artifact, not an experimental result. `results/holdout-v2.0/status.json` records the unmet human dependency. No v2 live requests were made during this implementation.

To rebuild the source dataset independently, use a fresh directory and public-network access:

```sh
python3 quadrant-tool/jev_dataset_v2.py build/jev-v2-dataset-rebuilt
```

For a future controlled development context test, prepare one workspace with `--context diff-only` and another with `--context historical`. The question text and all other model input fields remain identical; only `state.historical_context` differs. Use paired repeats, the same resolved model version, and predeclared order; abort interpretation if versions differ. A complete paired development run is 84 calls. **This comparison was prepared and tested, not executed.** The original v1 calls are not the control arm because the v2 questions changed. Missing context is a hypothesis, not an established cause of any pilot failure.

## Measures and limits

Primary results use all planned Jev requests: allowed-set agreement, incorrect assignments, and unresolved requests sum to the denominator. Unresolved statuses include abstention, conflict, invalid response, API failure and not executed. Missing/unnecessary roles are scored on resolved proposals; unresolved required-role counts are reported separately. Policy role coverage after mandatory metadata is a separate field and never counts as completed review.

Repeat consistency includes status and route set, so repeated abstention is stable but unsuccessful. Case summaries show agreement across all three repeats; family counts expose related changes. Synthetic, real and case-kind totals are separate. Thresholds 0.4 and 0.6 are diagnostics around primary 0.5, not a search for a winning threshold. Deterministic baselines are evaluated once per case, not repeated to inflate the sample. The rules baseline intentionally uses simple changed-line patterns and dependency paths; unchanged context is excluded, but changed comments can cause false positives. Code freezes the exact rules. The all-available-specialists baseline requests the four available specialist categories; baseline mandatory peer review remains in the policy layer.

Costs come from provider reports; missing costs are unknown. Times are small sequential client-request measurements, not production latency guarantees. Raw responses preserve probabilities, requested/resolved versions, provider metadata and costs. No downstream reviewer-model calls or comparisons are included. A separate protocol with held-out detection ground truth and a quality/cost/latency budget is required before that research question is run.
