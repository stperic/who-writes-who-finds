# Worksheet 3: Shadow Pilot and Adoption Scorecard

**Companion to:** *Who Writes the Bug, Who Finds the Bug?* (Eric St-Pierre, Medoya Consulting LLC)

Use this worksheet to evaluate the review workflow you intend to deploy. The four-week schedule is a planning example, not a validated minimum or a deadline for adoption. Keep existing required controls active while the proposed workflow runs in shadow mode.

## 1. Define the decision before running the pilot

Pilot owner: ____________________

Adoption decision owner: ____________________

Repository and permitted deployment scope: ____________________

Existing review workflow: ____________________

Proposed added or changed workflow: ____________________

Evaluation window and minimum evidence required: ____________________

Write the acceptance and rollback criteria below before looking at evaluation results. The decision owner may adopt within a defined scope, revise, extend the pilot, or stop. A passed test or a model finding does not authorize adoption by itself.

## 2. Four-week execution schedule

### Week one: cases, controls and a frozen configuration

- [ ] Record the existing human review, automated checks and security tools, including product, available version, settings, rules and language support. Distinguish source-code analysis from dependency scanning.
- [ ] Separate **development cases** used to refine prompts, routing and context selection from **held-out full pull requests** reserved for the final comparison. Choose the held-out set before inspecting its outcomes. Do not tune against it and then report the same set as independent validation.
- [ ] Include verified historical defects and validated benign changes. Use the full PR change and its historical repository state, rather than only a handpicked vulnerable-file diff. If the team starts with 20 to 30 defects and 10 benign changes, treat those counts as examples and justify the actual sample against the intended scope.
- [ ] Manually verify each known mechanism and the relevant vulnerable revision. Keep the advisory, answer key and later correction out of reviewer inputs. Historical code may already have been public or present in model training; held-out selection does not remove that exposure risk.
- [ ] Freeze the model identity and resolved version where available, prompts, tools, routing rules, review budget, context-selection procedure and failure behavior. Record alias or version uncertainty.
- [ ] **Freeze context selection before evaluation.** Specify which callers, access rules, configuration, tests and requirement links may be retrieved from the PR's available state, the selection method and its limits. Use the same procedure on every held-out PR. Do not choose a file from the known answer after seeing a miss and count that as an untouched test.
- [ ] Preserve the selected input packets, file revisions and tool-read records. Report missing or unavailable context explicitly. A later, answer-informed rescue experiment is useful, but belongs in a separate exploratory result.

### Week two: run beside the existing workflow

- [ ] Run the complete frozen workflow on each held-out PR, including its normal context-selection and routing steps. Keep all current merge requirements in force. The proposed reviewer has no authority to waive them.
- [ ] Run the recorded baseline on the same PR revisions where supported. Supply each workflow the input it normally requires and preserve it. Explain any differences in input, tools or review budget; a workflow comparison does not isolate model capability.
- [ ] Predeclare repeat counts and aggregation. Three independent reviews per known defect can reproduce the study's method, but the deployment evaluation must also report the behavior and cost of the actual proposed workflow.
- [ ] Log all attempted runs, unsupported cases, execution errors, empty or refused outputs and fallbacks. Report completion rates alongside detection results so failed runs do not disappear from the evaluation.
- [ ] Record human review and triage minutes, automated cost, elapsed time and required work that routing selected or omitted.

### Week three: verify findings and behavior

- [ ] Score known target defects using [Caught / Partial / Missed](../openemr-study/data/original/rubric.md). Keep the scorer's answer key separate from reviewer inputs. Use independent human verification of the final pilot judgments, with reviewer identity hidden where practical.
- [ ] Verify and deduplicate findings from both workflows. Record target defects caught by both, by the baseline alone, by the proposed workflow alone, and by neither. Report additional verified discoveries separately without silently changing the original denominator.
- [ ] Adjudicate every security alert on the benign set. Count both changes with at least one false alarm and the resulting triage effort. Separate unsupported security claims from requests for missing context.
- [ ] Check whether any baseline catches were lost through replacement, routing, filtering or ignored output. An additional tool's standalone score does not establish the combined workflow's coverage.
- [ ] Exercise missing checks, stale evidence, a new revision after approval, empty model output and unavailable context. Record whether the workflow retained required controls and routed unresolved decisions to the named owner. Simulated policy checks are separate from observed deployment outcomes.

### Week four: make and record the decision

- [ ] Compare the completed scorecard with the criteria declared in week one. Identify unmet criteria and uncertainty, including the amount of held-out evidence.
- [ ] The adoption owner records the decision, allowed scope, remaining limitations, required controls and next review date. Extend the pilot when evidence is insufficient; elapsed time does not establish reliability.
- [ ] Re-evaluate when the model, prompt, context selector, tool configuration, routing policy or relevant application behavior changes. A newly tuned configuration needs fresh held-out evaluation.

## 3. What the OpenEMR results establish

The original study used selected historical diffs with a generic prompt and three reviews per case. It found **8 of 24 Caught for Haiku 4.5** and **20 of 24 for Sonnet 5**. Original scores were human-validated. The post hoc group of four Sonnet gaps comprised three Partial cases and one Missed case.

A later targeted Sonnet experiment supplied one related file selected by the study author from trace notes. With the general prompt, two of those four gaps became Caught. With the same files and stronger security plus existing-flaw instructions, three became Caught. That gives **22 and then 23 distinct original cases with a scored catch across experiments**. The other twenty were not rerun under the improved setup. The PDF-rendering SSRF case remains Partial, and follow-up scores await independent human verification.

A separate [PDF requirement probe](../openemr-study/data/pdf-requirement-followup/README.md) revisited that SSRF case with the same diff and review prompt. A functional PDF requirement yielded zero of three explicit SSRF findings; a proposed security requirement governing PDF resource loading yielded three of three. The security requirement was written with hindsight and supplied manually. This result does not establish a 24-of-24 workflow or replace a held-out pilot.

Those targeted recoveries support testing context and instructions. They are not held-out validation of an automatic context selector, a full-PR workflow, Jev routing or ZZ-Trace. Added-context false alarms were not measured. In a separate ten-change Sonnet control set, false-alarm reviews increased from **0 of 10 with the general prompt to 5 of 10 with security plus existing-flaw instructions**. These separate observations do not supply production precision or a cost-benefit threshold.

The historical Sonnet registry entry records a harness alias, so the records do not establish an immutable snapshot across dates. The original harness and direct-API follow-ups also differed. The D05 component replay supplies separate test and gate evidence, not a comparative benchmark against Snyk or a new detection score. The separate public CSRF PR's proposed workflow has not run.

Sources: [original numbers](../openemr-study/data/original/numbers.md), [expanded-context follow-up](../openemr-study/data/prior-followups/followup_expanded_context/README.md), [security-prompt controls](../openemr-study/data/prior-followups/followup_security_prompt/README.md), [D05 readiness](../docs/demo/READINESS.md), [separate CSRF case](../docs/demo2/README.md).

## 4. Fill in your adoption scorecard

Configuration record: ____________________

Development set: ____________________

Held-out PR set and revision list: ____________________

Frozen context-selection procedure: ____________________

| Decision metric | Baseline | Proposed workflow | Predeclared acceptance criterion |
|---|---|---|---|
| Verified target-defect catches | ____ / ____ | ____ / ____ | ____ |
| Additional verified target catches beyond baseline | Reference | ____ | ____ |
| Baseline target catches lost | Reference | ____ | ____ |
| Benign PRs with at least one false security alarm | ____ / ____ | ____ / ____ | ____ |
| Human review and triage minutes per PR | ____ | ____ | ____ |
| Completed / attempted evaluations | ____ / ____ | ____ / ____ | ____ |
| Missed required review or check assignments | ____ / ____ | ____ / ____ | ____ |
| Cost and elapsed time per PR | ____ | ____ | ____ |

The OpenEMR study did not perform this full-PR baseline comparison. Its entries for additional catches, lost baseline catches, review time and adoption thresholds are **not measured**, not zero.

### Account for overlap

Common eligible target-defect cases with completed evaluations: ____

| Outcome on known target defects | Case count |
|---|---|
| Baseline and proposed workflow both catch | ____ |
| Baseline alone catches | ____ |
| Proposed workflow alone catches | ____ |
| Neither catches | ____ |

These four counts must total the completed common eligible set. Report unsupported and failed evaluations separately, including their disposition. Use the same written detection rubric for both workflows. Report any separately verified additional discoveries outside this target-defect table.

### Record the adoption decision

Decision owner: ____________________

Decision: adopt within scope / revise / extend / stop

Evidence supporting the decision: ____________________

Permitted scope and controls that remain mandatory: ____________________

Unmet criteria and remaining uncertainty: ____________________

Review date and change triggers: ____________________

## 5. Exit and rollback criteria

Before promoting from shadow mode to advisory PR comments, require a named adoption owner, an evaluated frozen context selector, acceptable verified coverage, an explicit disposition for lost baseline catches, and false alarms and review time within the team's stated budget. Approval to publish advisory findings does not grant merge authority.

Predeclare the observation window and thresholds that trigger a return to shadow mode, such as excess missed defects or false alarms, an unapproved configuration change, missing required review, or unapproved data access. Preserve evidence, restore the recorded baseline behavior and have the owner decide what must be corrected and retested.
