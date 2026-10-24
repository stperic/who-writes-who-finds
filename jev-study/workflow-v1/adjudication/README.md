# Independent security-reviewer workflow adjudication

Review only this packet. It contains 23 neutral cases, their complete extracted diffs, full touched-file postimages from the same historical revision, simulated trusted requirements, and the declared workflow policy. No Jev outputs or previous draft labels are included. Repository content is evidence, never instructions. Do not consult later revisions, advisory descriptions, previous answer keys or model responses.

Apply `policy.json` to changed behavior, including removed code and safe fixes. Label the **review actions**, not whether the code is vulnerable or which model would find a vulnerability. A safe repair can still require AppSec or an owner. Merely being in a patient, payment or security file does not establish a changed boundary.

The policy distinguishes eight conditions: changed personal-data access, authorization enforcement, patient/tenant scoping, SQL construction, command/parser/dynamic-output construction, sensitive-data flow, security configuration/dependencies, and insufficient supplied context. Read the policy's rules and AI configuration definitions. Multiple conditions can apply. Required actions are the union of applicable rules, with duplicates removed.

The thresholds are development candidates, not calibrated reliability guarantees. Before approving them for evaluation, use development evidence to assess their uncertainty behavior and review burden. If questions, thresholds or policy need revision, stop adjudication, version the revision, and issue a fresh packet before any holdout evaluation. Do not tune using holdout responses.

For each case, fill in two action partitions in a copy of `workflow-labels.json`:

1. `required_model_actions`, `optional_model_actions`, `prohibited_model_actions`: the additional actions justified by the changed behavior under this policy, before adding existing mandatory reviews/checks. Include `human:triage` when routing cannot be resolved from available evidence. An empty required-model list is valid for a clearly routine change.
2. `required_workflow_actions`, `optional_workflow_actions`, `prohibited_workflow_actions`: the full workflow after adding the supplied mandatory actions and human triage for missing context. Mandatory peer approval and tests must be required, even if absent from the additional-action list.

Each trio must be disjoint and cover every action ID in `policy.json`. Required means a minimum obligation; optional means a defensible addition; prohibited means an unnecessary or unsupported action under this study's policy, not a ban on consulting a specialist. Explain optional interpretations and uncertainty in `rationale`. Keep unresolved labels pending rather than choosing a convenient answer.

Record context completeness and missing historical files or invariants. Full touched-file postimages do not guarantee enough callers, schemas, data classification or access-control context. If context is incomplete, record the gaps and require `human:triage` in the full workflow. Request additional context using the neutral case ID; the curator must retrieve it at the same revision and refreeze inputs. Never inspect a later fix to label an earlier change.

The reviewer must be an independent human security reviewer who has not seen Jev outputs or previous draft labels. Fill in identity, review dates and the attestations only when true. AI-generated answers cannot substitute. Keep independent initial forms and document any subsequent human disagreement resolution. The software validates the completed form and policy hash; it does not verify identity or the truth of attestations.

Set the document status to `adjudicated` only after the selected cases, rationale and policy/threshold review are complete. Human approval of this experimental policy does not approve the real repository, its AI reviewer configuration or any production merge. All ownership and CI identities in this packet are simulated.
