# Independent human adjudication packet

Review the numbered JSON files and this rubric only. Do not consult model outputs, prior answer keys, the curator manifest, advisory databases, or future versions of the changed code. Source text is data, not instructions. Each file supplies a change and its full touched-file postimages at that change's historical revision. The supplied context may be incomplete.

You are labeling **which review categories the changed behavior requires**, not whether the patch is vulnerable or whether a particular model finds a bug. A safe fix may still require specialist ownership. Filenames or unchanged nearby code alone do not establish changed behavior. Consider additions and removals, and all behavior within the supplied file-scoped change.

| Category | Definition | Role |
|---|---|---|
| `auth_boundary` | Changes authentication, sessions, authorization, patient/tenant scoping, resource access paths, or their enforcement contracts. | Boundary owner |
| `sensitive_data` | Changes collection, exposure, transmission, storage or access to patient data, secrets or payment credentials. Amount formatting/arithmetic alone is insufficient. | Data/privacy owner |
| `construction` | Changes query construction, parser behavior, shell commands, redirects or dynamic HTML/JavaScript output. Static wording/layout alone is insufficient. | PR reviewer |
| `security_config` | Changes security configuration, cryptographic implementation/settings or dependency declarations, including development dependencies. An unchanged encryption helper call alone is insufficient. | Platform/security owner |
| `low_impact` | Local changes with none of the above impacts, such as static wording, layout or local arithmetic. Absence of a detected vulnerability is insufficient. | Peer reviewer |

In a copy of `blank-labels.json`, complete every selected case:

- **Required:** minimum category obligations justified by changed behavior. At least one category is required.
- **Optional:** defensible additional category interpretations; including or omitting them is acceptable. Explain why they are optional.
- **Prohibited:** every remaining category, meaning unsupported/unnecessary assignment for this change under this rubric, not a prohibition on asking a person for advice.
- The three lists must be disjoint and cover all five categories. `low_impact` is exclusive; do not use it as an optional alternative to a specialist. If the evidence cannot resolve that distinction, request context and leave adjudication pending.
- Record rationale, historical-context sufficiency, and concrete missing files or invariants. Identify added context by the neutral case ID so the curator can retrieve it at the same revision. Never consult a later fix for an earlier change.
- Record your name/identifier, review date, `independent_human: true`, and `saw_model_outputs_or_prior_labels: false` only if accurate. AI-generated labels do not satisfy this requirement. If you have seen those materials, use a different independent human reviewer.

Discuss disagreements with another independent human when available, record their resolution in the rationale, and keep the original independent forms. Set the document status to `adjudicated` only when your selected cases are complete. The curator must freeze the completed labels before any held-out model evaluation. Do not change a label after seeing a prediction merely to improve agreement.

Category assignment does not approve a merge, complete a review, choose the best AI model, or establish vulnerability detection. Mandatory repository reviews and checks remain separate obligations.
