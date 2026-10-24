# Jev review-workflow experiment

**Implemented and tested; independent human workflow adjudication remains pending. No live requests have been made with these questions.** The 14 development cases and nine unqueried holdout cases reuse the existing dataset and family grouping. Original results, prior follow-up artifacts and presentation snapshots remain unchanged. The PowerPoint was not edited.

The subsequent authorized presentation revision on October 18 uses this workflow example. `preserved-files.json` retains the hash of the local deck snapshot from before that revision. PowerPoint backups are outside this repository, so the public check verifies the published evidence and checks a deck backup only when it is present. Experimental inputs, labels, raw results and prepared freezes remain unchanged.

Start with [the PR journey and diagram](PR-JOURNEY.md). The scientific claim is limited: the implementation can turn typed category probabilities into review requirements and simulate checking their completion. Workflow-routing accuracy, downstream detection and production enforcement are not yet established.

## Questions and probabilities

The actual [eight question definitions](questions.json) are sent together using the existing OpenRouter Decisions adapter and `.env` loader. Requests have `model`, `state.change` and `questions`; `change` holds the complete extracted diff and historical touched-file context. Questions refer to those exact fields. They do not include labels, prior predictions, trusted owner mappings or approval records.

Noul returns an estimated probability of the specified condition. The runner stores the original 0-to-1 number and derives a percentage only for display. Thus `0.94` displays as `94%`; it is neither severity nor probability of safety. Optional true/false criteria clarify the condition without changing the output type. No chat model invents scores, and neither Choice nor Score is needed here. This follows [TypeSafe Noul](https://docs.typesafe.ai/primitives/noul) and [independent shared-state questions](https://docs.typesafe.ai/primitives).

The transport uses the documented [OpenRouter Decisions request](https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-request), not Chat Completions. Validation rejects missing questions, unexpected questions, wrong types, booleans, strings, nonfinite values and values outside 0–1. Raw responses, probabilities, requested/resolved models, failures, provider cost and request times are retained. The [illustrative response](examples/typed-response.json) is schema-validated test data, not a provider observation.

## Probability-to-action policy

The following **development-candidate** thresholds encode different operational treatment by condition. They have not been calibrated against independent workflow labels. They were developed as policy design choices using the existing development case shapes and earlier uncertainty lessons, not by treating the earlier five-question probabilities as observations of these eight questions. Their operating characteristics remain to be tested on development. Human review and a new freeze are required before the holdout can execute.

For each condition: at or below the low bound is negative; at or above the high bound is positive; strictly between them requires human routing triage. Any positive rules still add their actions when another signal is uncertain. Percentages are not combined into a synthetic risk score.

| Condition | Low bound | Positive threshold | Additional actions when positive |
|---|---:|---:|---|
| Personal-data access | 25% | 65% | Privacy approval, data-flow AI review, secret scan |
| Authorization boundary | 25% | 60% | Boundary-owner approval, boundary AI review, boundary tests |
| Patient/tenant scoping | 25% | 60% | Boundary-owner approval, boundary AI review, boundary tests |
| Personal-data access **and** authorization positive | As above | Both positive | AppSec approval in addition to both individual workflows |
| SQL construction | 30% | 70% | SQL security AI review and SAST |
| Command/parser/dynamic output | 30% | 70% | Construction security AI review and SAST |
| Sensitive-data flow | 25% | 65% | Privacy approval, data-flow AI review, secret scan |
| Security configuration/dependencies | 30% | 70% | AppSec approval, configuration AI review, dependency and secret scans |
| Insufficient context | 20% | 55% | Human triage; trusted context incompleteness also requires triage regardless of this probability |

Peer approval, existing tests and any trusted repository requirements always remain mandatory. Multiple signals produce a deduplicated union. Low probabilities cannot waive owners or checks. Request failures and malformed answers produce explicit unresolved routing, not a low-impact fallback.

The [policy file](policy.json) defines five AI configurations. Each has an explicit provider/model snapshot (`openai`, `gpt-4.1-2025-04-14`), prompt text, required context, tools and output contract. SQL review, for example, needs historical files, database schema and query helpers. Configuration IDs and full configuration hashes bind review-completion events to the intended model, prompt and context. These configurations are **approved only within the simulation**; availability and production approval have not been established. No downstream AI model was called or compared. Choosing a configuration by policy does not establish that it is best.

## Workflow and gate

On PR creation or update, calculate the model-selected additions separately from mandatory requirements. The resulting workflow records required actions, pending reasons and the exact revision. A proposed or assigned action has no completion authority.

During review, blocking findings or disagreement add AppSec review and triage; missing evidence requires triage. Trusted findings and resolutions bind to the revision and finding fingerprint. A stale or unauthorized resolution cannot clear a blocking finding. Authorized routing triage may resolve uncertainty or document an exception to model-added actions, but cannot remove mandatory actions or count as human approval. Unavailable owners require a trusted delegate mapping before the gate can complete.

At the merge gate, obligations are recomputed from the inputs. Every required human approval, check and AI review must have a trusted completion event for the current revision. AI reviews must match the selected configuration/model, required context revisions and structured output contract. Later failures and approval revocations supersede earlier success. Blocking findings remain pending until an authorized human resolution exists. All requirements can pass in the local simulation; no merge is performed.

These functions require an authenticated event adapter in a real workflow. Metadata and chronological approval/check/review event streams in this study are **fixtures**, not real CODEOWNERS or CI records. The simulator is not a production security boundary. There is no isolated CI/CD integration demonstration and no branch-protection change.

## Human packet and pending dependency

Give an independent human security reviewer only [workflow-adjudication-packet.zip](workflow-adjudication-packet.zip). It includes all 23 neutral cases, historical context, declared policy and blank workflow forms. It omits previous labels and Jev outputs. The reviewer labels required/optional/prohibited **additional actions** separately from the **full workflow** and reviews the thresholds before evaluation. See [adjudication instructions](ADJUDICATION.md).

The [existing case manifest](../v2/dataset/manifest.json) remains authoritative for selection, source revisions and family grouping. Holdout related changes and fixes remain together. Synthetic controls remain development-only and are reported separately. This is a holdout from Jev development, not evidence of absence from model training. Snapshot context can lack callers or invariants; human context decisions are retained in frozen metadata.

Pending labels are not copied from the older route key or inferred from Jev. Without adjudication, the runner permits preparation and dry runs but refuses live evaluation, including the holdout. **There are no new measured workflow-agreement, missed-owner or latency results.** In preparation reports, planned requests are `not_executed`; agreement is `null`, not zero accuracy. These outcomes are distinct from observed API failures or actual model abstentions.

## Commands and results

Python 3.9+ and the standard library suffice. Run from the repository root:

```sh
python3 -m unittest discover -s quadrant-tool -p 'test_jev*.py' -v

# Fresh preparation directories; these commands make no model requests.
python3 quadrant-tool/jev_workflow.py prepare build/workflow-development --partition development
python3 quadrant-tool/jev_workflow.py run build/workflow-development --dry-run
python3 quadrant-tool/jev_workflow.py prepare build/workflow-holdout --partition holdout
python3 quadrant-tool/jev_workflow.py run build/workflow-holdout --dry-run
python3 quadrant-tool/jev_workflow.py score build/workflow-development > build/workflow-development-report.json

# Only after independent human adjudication of this exact policy and thresholds:
python3 quadrant-tool/jev_workflow.py prepare build/workflow-holdout-adjudicated --partition holdout --labels /absolute/path/to/completed-workflow-labels.json
python3 quadrant-tool/jev_workflow.py run build/workflow-holdout-adjudicated --dry-run
python3 quadrant-tool/jev_workflow.py run build/workflow-holdout-adjudicated
python3 quadrant-tool/jev_workflow.py score build/workflow-holdout-adjudicated > build/workflow-holdout-report.json
```

For development evaluation after labels are ready, use the same sequence with `--partition development`. Review threshold behavior there, document any changes, re-adjudicate the changed policy and prepare a fresh held-out freeze before evaluation. Do not use holdout responses to tune. Every new question, context or policy configuration has a distinct freeze hash; historical probabilities are not relabeled as its observations.

The [protocol](protocol.json) specifies three requests per case, no retries, a maximum of 42 calls, a $3 local spending budget and a $0.05 reservation per attempted request. Development reserves $2.10; the holdout reserves $1.35. Unknown cost or a response exceeding its reservation stops subsequent calls for reconciliation. Each attempt is recorded before dispatch, so a crash cannot silently retry a possibly billed request. A client cannot cap an in-flight provider charge; use a provider-side restricted key for a hard billing cap. No credits were spent by this implementation.

The existing key loader reads `.env` without executing it and never stores credentials in results. Frozen workspaces include inputs, questions, policy, thresholds, labels, metadata and implementation hashes. Scoring verifies the freeze and raw typed answers. Existing attempts, including errors, are preserved. Use a new results directory for a changed configuration; archive the entire workspace after a real evaluation.

Executed local evidence is in [validation.json](results/validation.json), the [development dry run](results/development-dry-run.json), the [holdout dry run](results/holdout-dry-run.json), and the [gate scenarios](examples/gate-scenarios.json). No simulated response is placed in an experimental `outputs/` directory.

## Evaluation once labels exist

All planned requests remain in headline denominators. Reports separate allowed-workflow agreement, incorrect resolved assignments, unresolved routing, execution failures and missing calls. Missing required actions, missing AppSec/owner approvals and additional actions are explicit. Per-request model-selected additions are scored separately from mandatory policy requirements; metadata cannot hide a classifier miss. Case summaries and repeat consistency accompany call counts; three repeated requests are not three independent cases. Real/synthetic subsets remain separate.

The existing changed-line/path baseline is reused with a documented adapter: broad authorization and sensitive-data matches imply personal-data access; focused patterns distinguish SQL and other construction. Its 0/1 flags are deterministic rule outputs, not model probabilities. It uses the same workflow policy and trusted metadata. Baseline results on the holdout are withheld until human adjudication. Pending labels mean baseline accuracy is also unknown. Provider-reported cost and client-request latency are preserved for actual calls; dry-run zero calls imply no latency observation, not instant inference.

Measured routing from earlier experiments remains in its original archive and is not claimed for this configuration. The new evidence is software validation and dry-run readiness. Best-model choice, downstream vulnerability detection, human effectiveness and real CI/CD enforcement remain untested.
