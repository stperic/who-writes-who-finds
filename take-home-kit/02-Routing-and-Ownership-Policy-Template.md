# Worksheet 2: Risk- and Context-Calibrated Routing & Governance Policy
**Companion to:** *Who Writes the Bug, Who Finds the Bug?* (Eric St-Pierre, Medoya Consulting LLC)

Use this template to fulfill **Learning Objective 2**: route each change by its observable impact and required context (not by a vulnerability class you do not know before review), define explicit human authority, and set revalidation triggers.

---

## 1. Core Operating Rule

> **"No findings" from an AI reviewer is never authorization to merge a high-impact change.**
> This is a proposed starting policy to validate locally. Human approval assigns accountability and required verification. AI can assist with domain-specific and cross-file analysis when supplied relevant evidence. Our four cross-file cases motivate testing richer context; they do not establish a permanent AI limitation or a guaranteed benefit from adding context.

---

## 2. Policy Gates

Treat this as a proposed policy to validate locally. Keep the policy version, eligible configurations and exception authority under controlled change management. The reviewer and router cannot alter mandatory requirements or authorize a merge.

| Gate | Policy decision | If requirements are unmet |
|---|---|---|
| Change scope | Identify affected boundaries, data, authorized change request, applicable approved requirements and required context using the change and trusted ownership/risk metadata. | Manual assessment. |
| Review route | Choose approved models, tools and required human reviewers. | An approved fallback that preserves required verification and ownership. |
| Evidence | Require requirement-to-file-to-test links, completed checks with per-case results and retained log artifacts, inspectable AI execution records, an OpenTelemetry execution trace for this sensitive route, and disposition of findings. | Gather evidence, remediate or escalate. |
| Merge | Require an app-owned evidence check for the current PR head and tested integration revision, plus current owner approvals. The check verifies the underlying records; it does not merely repeat an AI verdict. | Hold, or record an exception granted by an authorized role. |

Retain applicable source-code analysis, dependency checks, secret scanning and tests across every route. A model recommendation cannot waive a mandatory check or owner approval. Local evaluation determines the model, prompt, context and tools eligible for each route. The OpenEMR study establishes no production routing thresholds.

Policy version: `__________________`  Policy owner: `__________________`

Approved configuration per route: `__________________`

Required checks and approvals: `__________________`

Failure fallback and exception authority: `__________________`

## 3. Change-Routing Matrix (Customize for Your Repository)

Route pull requests based on **what the change touches** (observable before review):

| The Pull Request Touches... | Context Supplied to AI Reviewer | AI Reviewer Authority | Human Role & Named Owner | Escalation Trigger |
|---|---|---|---|---|
| **1. Authorization, Tenant, or Patient Boundary** (e.g., ACL gates, FHIR compartments, session/token handling, front-controller routing) | Diff + full touched files + caller/base-class interfaces + short architecture invariant note | **Advisory comment only.** Never sole approver. | **Named Boundary Owner** must sign off and record what was checked (`__________________`). | New access path, removed guard or unresolved boundary evidence. Owner approval is required regardless of AI findings. |
| **2. Sensitive Data Flows** (PHI, PII, secrets, payment credentials, outbound fax/email/webhook staging) | Diff + full touched files + data-classification config (`globals` / secret schema) | **Advisory first pass.** Flags unencrypted staging or client-side exposure. | **Data/Privacy Owner** approves (`__________________`). | Data crosses a trust boundary, is written to webroot/logs, or is echoed to client JS. |
| **3. Query, Parser, Command, or Template Construction** (SQL, shell commands, XML/CCDA parsers, HTML/JS output, redirects) | Diff + touched file + project sanitizer/query-binding helpers | **Advisory during the pilot.** After validation, policy may block on findings that meet specified evidence criteria until triaged. | **PR Reviewer** verifies the AI finding or confirms parameterized/escaped helper usage. | Disputed finding or custom escaping helper used instead of standard bindings. |
| **4. Security Configuration, Cryptography, or Dependencies** | Diff + `composer.json` / `package.json` + SAST and secret-scanner outputs | **Advisory alongside deterministic SAST / secret scanning.** | **Platform / Security Owner** approves (`__________________`). | AI reviewer and deterministic SAST/secret scanner disagree. |
| **5. Local, Low-Impact Application Code** | Diff + touched file | **First pass.** | **Standard peer review.** | Unexpected scope, disputed findings or incomplete required evidence. The failure policy below applies to every route. |

---

## 4. Four Non-Negotiable Pipeline Controls

1. **Approved Data Handling:** Route code only through an approved enterprise model endpoint with a signed data-protection/no-training agreement (and BAA where PHI may appear in fixtures or comments).
2. **Least Privilege (Prompt-Injection Defense):** Treat repository diffs, comments, documentation, test fixtures and model output as **untrusted input**. Run PR code and the AI reviewer in an isolated worker with no signing key, check-publishing token, production secrets, arbitrary network egress, or merge/deploy permission. Validate model output against a bounded schema and checked-out file references before publishing it; the model cannot choose commands, required checks, requirement IDs, pass/fail conclusions or exceptions.
3. **Audit Evidence Log:** For every reviewed PR, log:
   - Approved change request and scope; requirement/control ID, version, source and owner; accepted links to affected files and verification tests
   - Reviewed revision, policy version, required checks, applied route and approval or exception
   - For each required test: test ID, expected and observed result, objective pass/fail decision, command, runner/tool version, environment, actor, time, source head, and any failure/deviation disposition
   - A digest and durable access-controlled link for redacted test logs and reports, retained for the project's evidence period rather than relying only on GitHub's configurable log expiration
   - For each sensitive-route execution: OpenTelemetry trace ID, root span, policy-defined pre-decision spans and their statuses, span links for asynchronous work/retries, backend export acknowledgement, log correlation IDs, trace-viewer link, and any missing-span or exporter error; audit the check-publication span afterward
   - For a one-shot review: prompt template ID/version, SHA-256 digest of the exact request sent by the runner, and a retrievable access-controlled copy of that request and supplied context. For a multi-step agent: record each model request/response, tool definition/call/result, retrieved artifact revision and relevant runtime configuration
   - Requested `model_id`, resolved version if available, model settings, execution date and any alias or provider-internal prompt uncertainty
   - If a router is used: its version, option definitions, probabilities, selected route and policy overrides or fallback
   - Raw reviewer output and execution status (`ok` / `error_empty` / `timeout` / `truncated`)
   - Human disposition (`accepted_fix`, `false_alert`, `risk_accepted_by_owner`)
   - A canonical manifest accepted and signed by a separate trusted verifier, binding the model inputs and context digests, configuration, current PR head and tested integration revision, run attempt and trace identities, status, output digest, and test/scan artifact digests; verify the approved signer and workflow identities before accepting the check as evidence. The signature authenticates the record and producer, not the correctness of its conclusions
   - `Assisted-by:` git trailer when the PR itself was authored with AI assistance.
4. **Fallback on Tool Failure:** Log empty responses, API timeouts, rate-limit errors and missing trace export as operational failures. During an advisory pilot, retain the existing required review. Once a check is mandatory, keep its gate pending until it succeeds or policy authorizes an equivalent fallback or a recorded exception. Preserve required owner approval and verification in every fallback. A failed run never counts as a clean review.

**Trusted completion sequence:**

1. Authenticate and deduplicate the webhook, authorize its repository/event/actor, and refresh the PR state.
2. A trusted controller supplies a versioned, owner-controlled test harness, launches isolated PR execution, and captures results through a channel the PR process cannot rewrite. The PR worker has no signing key or check-publishing token. Reviewed test changes may enter the harness only through the normal approval process.
3. A separate verifier checks AI output schemas, source and artifact identity, controller provenance, required result conclusions, run attempt, current PR head and tested integration revision, plus approved signer/workflow identity and revocation status. Signing preserves provenance; the trusted harness and meaningful assertions support confidence in results.
4. Configure a unique required `security-evidence` check from the named GitHub App with strict up-to-date status checks. If using a merge queue instead, rerun required checks for each current merge-group revision. The App publishes success only after all mandatory inputs explicitly succeed; missing, skipped, neutral, cancelled, stale or timed-out inputs keep it non-successful. Configure stale-review dismissal, two approvals and CODEOWNERS where applicable. The App also verifies that the peer and boundary-owner reviews were submitted after the last reviewable push, came from authorized distinct people, and came from neither the author nor last pusher. Re-evaluate on PR changes, base updates, review events and exception changes so stale success cannot remain merge-eligible. Record any bypass or exception with actor, reason, compensating control and expiry. A new revision invalidates the prior decision.

For this proposed sensitive route, start a fresh trusted OpenTelemetry trace at authenticated webhook intake for each review run. Treat incoming trace context and baggage as untrusted. Instrument the controlled orchestrator, router, requirement lookup, AI runner, test runner, scanner wrapper, verifier and check publisher. Link queued work and retries. Put trace ID and span ID on redacted logs, and expose a trace-viewer link in the PR. External services may provide only wrapper spans and result IDs. Trusted policy defines the spans required **before** the merge decision; compare them with backend-acknowledged exports by a deadline. Record check publication afterward as a separate audit receipt. Allowlist low-sensitivity attributes, keep prompts, source content, secrets and patient data out of spans, protect Collector access and transport, and set retention. A trace is operational correlation, not authenticated proof that worker-reported tests passed. Other repositories may use different observability tools to achieve the same audit objective.

---

## 5. Revalidation Triggers (Change Management for the Ruler)

Re-run your benchmark harness (`quadrant run` + `quadrant compare`) whenever any of the following changes:
- [ ] **Model or snapshot change:** Upgrading model family or pinned snapshot ID (use an immutable snapshot when available, log the resolved version, and declare uncertainty when only an alias is available).
- [ ] **Prompt or context change:** Modifying the review prompt or changing from diff-only to file/repo-context mode. Rerun adversarial prompt-injection and output-validation cases.
- [ ] **Routing or policy change:** Changing the router, option definitions, approved model mapping, thresholds, mandatory checks or exception rules. Re-evaluate both routing and end-to-end review outcomes.
- [ ] **Architecture change:** Introducing a new routing layer, base service trait, or authentication middleware.
- [ ] **Incident or miss:** Any vulnerability that escapes review in production or pentesting is added to your rotating holdout set.

## 6. Jev Example: Selecting and Completing a Review Workflow

Jev is TypeSafe's **System One** model. The local workflow defines eight independent yes/no (`noul`) checks on the change and historical context. Each answer is a probability from 0 to 1, displayed as 0% to 100%. A percentage estimates whether a condition applies; it does not measure severity or the probability of safe merge. The original workflow examples used invented probabilities; a later, separate D05 browser demo executed one live route. That D05 result is not evidence for Demo 2.

Policy combines applicable conditions into a workflow containing specialized AI reviews, AppSec approval, other owner approvals and required checks. Several conditions can apply together, and overlapping requirements are deduplicated. Each AI configuration specifies the model/version, prompt, context, tools and expected output. Mandatory repository requirements remain required regardless of the model estimates. Candidate thresholds need local development evaluation and independent review before use.

In the illustrative payment-change example, personal-data access and authorization conditions together add AppSec approval. SQL construction adds a specialized SQL AI review and SAST. Other conditions add privacy/boundary approvals, AI analysis and checks, while standard peer review and existing tests remain mandatory. These actions follow the declared example policy; they are not universal requirements.

Determine the workflow when the PR opens or changes. During review, findings, disagreement or missing evidence may add requirements or trigger triage. At merge, verify the required reviews, checks, finding dispositions and authorized approvals for the exact revision. Assigning a reviewer, recording triage or receiving a clean AI report does not satisfy a human-approval requirement. A new revision needs matching completion evidence.

**Evidence status:** The original walkthrough uses invented probabilities and completion events with a real historical code change. Nine local gate scenarios leave eight incomplete workflows pending and make the fully satisfied fixture eligible. These tests demonstrate encoded policy behavior in simulation. The later D05 run is one separate live route, not independent multi-case validation. Neither establishes routing accuracy, model suitability, detection improvement or production enforcement for Demo 2.

Nine holdout changes still await independent human workflow adjudication and threshold review. Real integration needs authenticated owner, review and check sources. Earlier routing results remain in their original archive and cannot be reused as observations for these new questions. Keep the original 24-CVE detection study and the D05 live route separate from this unexecuted Demo 2 design.

Sources: [current workflow](../jev-study/workflow-v1/README.md), [PR walkthrough](../jev-study/workflow-v1/PR-JOURNEY.md), [local validation](../jev-study/workflow-v1/results/validation.json), [TypeSafe primitives](https://docs.typesafe.ai/primitives), and [TypeSafe Noul](https://docs.typesafe.ai/primitives/noul). Full references and the example-policy details are in the deck's speaking notes.
