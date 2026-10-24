# JEV reviewer-routing pilot

The [focused workflow experiment](workflow-v1/README.md) extends category estimates to specialized AI reviews, AppSec/owner approvals and completion gates. Its human workflow adjudication is pending; its new questions have not been queried.

The separate [v2 follow-up](v2/README.md) adds deterministic policy/gate tests, blinded human adjudication, simple baselines and an unqueried holdout. The original archived pilot below remains unchanged.

JEV tests a different question from the original `quadrant` study: **given a change and the proposed review policy, which human reviewer roles should be involved?** Detecting the target CVE and assigning the right review obligations are separate outcomes. A model can miss a vulnerability while correctly routing the change to an owner.

This is a new, exploratory component. It calls the actual **TypeSafe Jev model through OpenRouter's Decisions API**. The initial implementation was a generic chat-model harness; the OpenRouter adapter now uses Jev's typed decision protocol. The reference labels are drafts prepared from the archived diffs and must be independently adjudicated before making a validation claim. The tool measures role selection, not named-person selection, human detection success or production safety.

## Initial live run: October 18, 2026

The [archived report](results/2026-10-18-jev-1.14/report.json) and [raw responses](results/2026-10-18-jev-1.14/outputs/) record 42 calls to requested model `typesafe/jev-1.14`, resolved consistently to `typesafe/jev-1.14-20261014`. The frozen threshold was 0.5. No labels, questions or thresholds were changed after seeing these results.

- All eight CVE cases included every draft-required role on all three runs: 24 of 24 CVE runs. Seven of eight cases matched the allowed set on every run; the payment-secret case added a platform/security reviewer outside the draft key on all three runs.
- Across all 14 changes: 32 of 42 planned runs matched the draft policy, six disagreed, and four abstained. There were zero API errors and zero peer-only assignments on changes requiring a specialist. Among non-abstained runs, 32 of 38 matched; report the four abstentions alongside that denominator.
- The benign patient-compartment fix (`BENIGN-06`) abstained on all three runs. That is an unresolved routing obligation, not a correct owner assignment. The routine calendar change (`BENIGN-09`) abstained once and selected peer review twice.
- The routine payment-arithmetic change (`BENIGN-10`) selected both construction and low impact above threshold on all three runs. The declared precedence retained construction, producing an unnecessary escalation under the draft policy. The three CVE payment-case disagreements and these three control disagreements are the six total mismatches.
- All 12 cases with three non-abstained outputs returned the same route set across repeats. This excludes the two cases with abstentions and does not establish correctness.
- The API reported a total cost of **$0.008253378** across all 42 calls, with 196,509 input tokens. Recorded request wall times sum to 7.26 seconds; this is a small sequential run, not a latency benchmark.

The outcome supports another shadow-mode experiment, not autonomous approval or a production reliability claim. The controls show why abstention handling and adjudication of policy boundaries matter. The report retains synthetic results separately. For reproduction, the archive includes its answer key, policy, manifest, neutral inputs, run configuration, raw responses and public-source verification. Re-score without network calls:

```sh
python3 quadrant-tool/jev.py score jev-study/results/2026-10-18-jev-1.14
```

## Small first experiment

The pilot contains **14 changes**: eight archived CVE-introducing diffs, four existing benign controls, and two explicitly synthetic policy-coverage controls. Three independent requests per item give **42 routing calls per model**. The requests contain the policy and the complete diff, with no conversational history. Repeats are not independent CVE cases.

The eight CVEs are `CVE-2026-24908`, `CVE-2026-24487`, `CVE-2026-25146`, `CVE-2026-24898`, `CVE-2026-33913`, `CVE-2026-24849`, `CVE-2025-31121`, and `CVE-2026-25476`. The two repaired cases use the corrected diffs in `openemr-study/data/original/diffs/`. The key and its rationale are in [cases.json](cases.json).

The four real benign controls include query and patient-boundary fixes that should still receive the relevant reviewer, plus two local changes. A benign patch is not automatically a low-impact patch. The synthetic TLS configuration change covers a gap in the selected CVEs; the static help-text edit provides an unambiguous local control. Synthetic results are reported separately and cannot support a CVE performance claim.

## Policy and labels

[policy.json](policy.json) makes the slide's five rows operational. Jev answers five independent yes/no (`noul`) questions in one request, returning a probability for each route. The runner maps selected routes to the union of reviewer roles deterministically. It cannot approve a merge. Any advisory route makes the combined AI authority advisory. Jev does not generate quotations, explanations or reasoning traces; the runner does not fabricate them. See the [Jev documentation](https://openrouter.ai/docs/guides/community/jev) and [Decisions API reference](https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-request).

The exploratory selection threshold is fixed at **0.5**, recorded in every run configuration before calls. Specialist routes at or above that threshold are selected together. Peer-only routing requires a positive `low_impact` decision and no selected specialist. If no route qualifies, the runner abstains and requires human triage. Contradictory positive specialist and low-impact decisions retain the specialists and are flagged. This threshold is a declared starting point, not a calibrated safety threshold. Keep probabilities to support later calibration on separate cases.

| Route | Required role |
|---|---|
| Authorization, session, tenant or patient boundary | Boundary owner |
| Sensitive data flow | Data/privacy owner |
| Query, parser, command or dynamic output construction | PR reviewer |
| Security configuration, crypto or dependencies | Platform/security owner |
| Local low-impact change | Peer reviewer |

`cases.json` distinguishes required routes from defensible optional routes. A prediction is acceptable only if it includes every required route and no route outside that allowed set. This is agreement with a declared policy. Do not derive expected routes solely from OWASP labels or target CVE classes: the full diff can change several behaviors.

Before an evidentiary run, have an independent reviewer adjudicate these labels and policy interpretations using the full changed behavior. Record that review in the source key, then prepare a fresh workspace. An initial run against the draft labels is still useful for discovering ambiguities, but must remain labeled exploratory. Do not tune labels after reading predictions and present the rerun as an untouched holdout.

## Run it

Run from the repository root with Python 3.9 or later. The OpenRouter integration, preparation, smoke tests and scoring use only the standard library. No additional SDK installation is needed for Jev.

Put your key in the project-root `.env` file:

```dotenv
OPENROUTER_API_KEY=your-key-here
```

The runner loads that file automatically. `.env` and `.env.*` are ignored by Git; `.env.example` is the blank shareable template. Existing process environment variables take precedence. Quoted values, `export KEY=value` and comments are supported. The loader never executes the file or performs variable/command expansion. An alternative path can be supplied with `--env-file`.

```sh
python3 quadrant-tool/jev.py prepare build/jev-openrouter
python3 quadrant-tool/jev.py run build/jev-openrouter --provider openrouter --model typesafe/jev-1.14 --runs 3 --dry-run
```

Then run the pilot and score it:

```sh
python3 quadrant-tool/jev.py run build/jev-openrouter --provider openrouter --model typesafe/jev-1.14 --runs 3
python3 quadrant-tool/jev.py score build/jev-openrouter > build/jev-openrouter/report.json
```

The OpenRouter adapter posts to `https://openrouter.ai/api/alpha/decisions`, not Chat Completions. It requires an explicit Jev version and never substitutes another model. Responses preserve the actual resolved model ID, provider, request ID, raw probabilities, reported usage and cost. A changed resolved version is flagged by scoring. HTTP redirects are rejected so the bearer key is not forwarded elsewhere.

Each request has a 90-second timeout and no automatic retries. Empty, non-JSON, incomplete or invalid-probability responses are execution errors requiring human triage. The full input is sent without truncation; context rejection is also an execution error. OpenRouter documents that Jev switches to long-context processing for text requests over roughly 32 KB. The full payment and fax-controller diffs exceed this size, so report their performance separately if interpreting a size effect. See [Jev input limits](https://openrouter.ai/docs/guides/community/jev).

Optional generative baselines remain available with `--provider openai` or `--provider anthropic`, their explicit model IDs and the corresponding SDK/API key. These use the original JSON-and-quotation prompt with a 4,096-token output limit. They are different reviewer configurations; Jev does not supply their textual-evidence metric. Do not send a Jev model to those chat adapters.

Preparation refuses to overwrite an existing workspace. Policy, answer key and inputs are frozen by hash. Running resumes existing records, including errors; it never silently retries a failed attempt until it succeeds. Use a fresh workspace for another attempt or configuration. Keep earlier attempts when reporting reliability. `build/` is ignored by Git: explicitly archive a completed study elsewhere when ready to retain or publish it.

The prepared `inputs/item_XX.json` file holds the generic baseline prompt and the Jev `state`/`questions` payload. Each adapter sends only its own input format. CVE IDs, benign labels, the answer key, expected routes and earlier detection scores are withheld. Source file paths inside the diff remain visible. The archived diffs already have commit headers removed; preparation also strips any prefix before `diff --git` and rejects CVE/GHSA identifiers in the body. No network browsing, tool access or repository traversal is granted to the model. Question definitions are frozen with the inputs.

## Local smoke check

```sh
python3 -m unittest discover -s quadrant-tool -p 'test_jev.py' -v
python3 quadrant-tool/jev.py prepare build/jev-smoke
python3 quadrant-tool/jev.py run build/jev-smoke --provider smoke --model smoke-fixture --runs 3
python3 quadrant-tool/jev.py score build/jev-smoke > build/jev-smoke/report.json
```

The smoke provider always selects `low_impact`, without consulting the answer key. It deliberately misses specialist routing. Its output is marked `SMOKE_ONLY_NOT_MODEL_EVIDENCE`; its scores verify the plumbing and must never be used as model results.

## Read the results

The JSON report includes acceptable route sets, missing required roles, unnecessary roles, unsafe peer-only assignments, specialist escalation on local controls, and repeat consistency. All denominators are explicit. Missing, failed and abstained runs are kept separate from valid routing predictions. Report abstentions alongside accuracy so rejecting difficult inputs cannot look like improved routing. Counts are broken down into CVEs, benign fixes, benign routine changes and synthetic controls. Raw outputs and per-item probabilities support adjudication.

For generative baselines, textual evidence validation confirms that a quoted substring exists, not that it justifies the route. A human must check rationale quality and whether the quote concerns changed behavior. For Jev, inspect the source diff and selected probabilities directly; there is no generated rationale to judge. The runner records escalation rules; it does not simulate scanner disagreements or verify that a later human actually handled an escalation.

For a smoke-to-pilot progression, predeclare the criteria before live calls: zero observed peer-only assignments on cases requiring specialists, every mandatory owner included, and a separately agreed tolerance for unnecessary escalation and operational failures. Report the counts even when a criterion fails. Passing a handful of selected historical cases is not proof of production reliability. Previously published code may have been seen in training.

Actual named reviewers require a maintained mapping from these roles to repository/team owners. A later study can compare diff-only with historical file/caller context, then compare the routed workflow with the existing workflow on additional catches and reviewer effort. This pilot does not measure those outcomes.
