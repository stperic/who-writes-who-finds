# Worksheet 1: Four-Quadrant Security Review Assessment
**Companion to:** *Who Writes the Bug, Who Finds the Bug?* (Eric St-Pierre, Medoya Consulting LLC)

Use the four questions from slide 6 to record evidence, identify gaps and plan a local evaluation. Revisit the assessment when the model, context, tools or workflow changes. This supports Learning Objective 1.

## Part A: Worked OpenEMR Example

| Quadrant and question | Evidence available | Limits and next measurement |
|---|---|---|
| **People introduce:** What defects enter human-written code? | Historical tracing of 24 scored cases, with 21 fully traced histories and three partial traces. The fully traced cases have a median selected-commit-to-disclosure interval of 2,043 days (5.6 years). | AI assistance is unverified for five introductions. Keep unknown provenance separate. Disclosure dates do not establish discovery dates or prove what happened during merge-time review. |
| **AI introduces:** What defects enter AI-assisted code? | External studies and catalogs provide evidence of AI-linked vulnerabilities. Appendix slide 31 summarizes those sources. OpenEMR's assistance tags illustrate how a team can record provenance. | This study does not measure an AI-authored defect rate in OpenEMR. A missing assistance tag does not prove human-only authorship. Count changes in each documented provenance group before comparing rates. |
| **People find:** What does human review catch? | Public credits describe who reported the historical cases: recent cases include eight AI analyzer vendor credits and eight named reporters or research groups. Older cases include three named reporters or groups and five cases with no discoverer credited. | Credits do not prove who discovered a bug, which tools they used, or whether a human reviewed the introducing change. A matched human-review baseline remains unmeasured. |
| **AI finds:** What does your AI reviewer catch? | Our diff-only evaluation measured Sonnet 5 and Haiku 4.5 on 24 vulnerabilities and 10 benign changes. Sonnet caught 20 of 24 cases, Haiku eight of 24. False security alerts: Sonnet zero of ten benign changes, Haiku one of ten. | These counts describe selected historical cases under the recorded configurations. They do not establish production reliability, human-versus-AI superiority, or performance with richer context. |

The finding about missing context is a hypothesis to test: Sonnet caught 20 of 20 cases classified after scoring as having the needed evidence inside the diff and zero of four requiring outside context. A later targeted follow-up supplied one researcher-selected related file for each of the four gaps; three became Caught with stronger instructions, while PDF-rendering SSRF remained Partial. A separate, post hoc [PDF requirement probe](../openemr-study/data/pdf-requirement-followup/README.md) produced explicit SSRF findings in three of three reviews with a proposed security requirement, versus zero of three with a functional requirement. Neither follow-up is a full-set rerun. Separate false security alerts from other warnings: four benign diffs produced High correctness/context warnings for Sonnet, and one produced a Critical correctness error for Haiku.

Sources: `openemr-study/data/original/numbers.md`, `openemr-study/data/original/METHODS.md`, `openemr-study/data/original/scores.csv`, `openemr-study/data/original/models.csv`, `cves.csv` and `references.md`. Sonnet's registry entry records access through a harness alias. The inspected records do not establish an immutable Sonnet snapshot across August and October.

## Part B: Your Team's Assessment

**Repository or service:** `___________________________`<br>
**Assessment date:** `____-__-__`<br>
**Owner:** `___________________________`<br>
**Reviewer configuration:** requested model ID, resolved version if available, prompt, input scope and allowed tools: `___________________________`

| Question | Evidence to collect | Counts or observations | Gaps | Next test or action |
|---|---|---|---|---|
| What defects enter human-written code? | Confirmed defects, change history and documented authorship | Defects: `__`; changes examined: `__`; unknown provenance: `__` | `________` | `________` |
| What defects enter AI-assisted code? | Assistance tags or equivalent provenance, confirmed defects and change history | Defects: `__`; AI-assisted changes examined: `__` | `________` | `________` |
| What does human review catch? | A declared review exercise or review logs that record findings and tools used | Caught: `__ / __`; false alerts: `__ / __`; reviewer minutes: `__` | `________` | `________` |
| What does your AI reviewer catch? | Blind review of confirmed defects and benign changes, with saved inputs and outputs | Caught: `__ / __`; Partial: `__ / __`; Missed: `__ / __`; false alerts: `__ / __`; errors: `__` | `________` | `________` |

Document how authorship is classified. AI-assisted work can involve human authors and reviewers. Preserve unknown provenance instead of assigning it to the human-only group. For discovery, record which people and tools contributed.

For a comparative review exercise, use comparable cases and a declared rubric. Record input context, allowed tools and time budgets. Avoid exposing reviewers to the answer through earlier runs. Human verification of an AI score is a scoring check, not a human-review detection baseline.

## Part C: Workflow Decision

- Which finding changes the role of your AI reviewer? `________________`
- Who owns approval for the affected boundary? `________________`
- What evidence is still required before changing that authority? `________________`
- Which change will trigger re-evaluation? `________________`
