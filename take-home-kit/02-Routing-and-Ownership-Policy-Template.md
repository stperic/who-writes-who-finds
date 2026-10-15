# Worksheet 2: Risk- and Context-Calibrated Routing & Governance Policy
**Companion to:** *Who Writes the Bug, Who Finds the Bug?* (Eric St-Pierre, Medoya Consulting LLC)

Use this template to fulfill **Learning Objective 2**: route each change by its observable impact and required context (not by a vulnerability class you do not know before review), define explicit human authority, and set revalidation triggers.

---

## 1. Core Operating Rule

> **"No findings" from an AI reviewer is never authorization to merge a high-impact change.**
> Even when a frontier model catches 20 of 20 single-file flaws in a retrospective test, diff-only review cannot see cross-file contracts (`CVE-2025-31121`, `CVE-2026-24487`, `CVE-2026-25146`, `CVE-2026-33321`), and a model cannot hold regulatory or operational accountability.

---

## 2. Change-Routing Matrix (Customize for Your Repository)

Route pull requests based on **what the change touches** (observable before review):

| The Pull Request Touches... | Context Supplied to AI Reviewer | AI Reviewer Authority | Human Role & Named Owner | Escalation Trigger |
|---|---|---|---|---|
| **1. Authorization, Tenant, or Patient Boundary** (e.g., ACL gates, FHIR compartments, session/token handling, front-controller routing) | Diff + full touched files + caller/base-class interfaces + short architecture invariant note | **Advisory comment only.** Never sole approver. | **Named Boundary Owner** must sign off and record what was checked (`__________________`). | Any new access path, removed guard, or AI silence on a boundary change. |
| **2. Sensitive Data Flows** (PHI, PII, secrets, payment credentials, outbound fax/email/webhook staging) | Diff + full touched files + data-classification config (`globals` / secret schema) | **Advisory first pass.** Flags unencrypted staging or client-side exposure. | **Data/Privacy Owner** approves (`__________________`). | Data crosses a trust boundary, is written to webroot/logs, or is echoed to client JS. |
| **3. Query, Parser, Command, or Template Construction** (SQL, shell commands, XML/CCDA parsers, HTML/JS output, redirects) | Diff + touched file + project sanitizer/query-binding helpers | **First pass; may block merge** on a high-confidence injection finding until triaged. | **PR Reviewer** verifies the AI finding or confirms parameterized/escaped helper usage. | Disputed finding or custom escaping helper used instead of standard bindings. |
| **4. Security Configuration, Cryptography, or Dependencies** | Diff + `composer.json` / `package.json` + SAST and secret-scanner outputs | **Advisory alongside deterministic SAST / secret scanning.** | **Platform / Security Owner** approves (`__________________`). | AI reviewer and deterministic SAST/secret scanner disagree. |
| **5. Local, Low-Impact Application Code** | Diff + touched file | **First pass.** | **Standard peer review.** | AI execution error, timeout, or empty response falls back to standard peer review. |

---

## 3. Four Non-Negotiable Pipeline Controls

1. **Approved Data Handling:** Route code only through an approved enterprise model endpoint with a signed data-protection/no-training agreement (and BAA where PHI may appear in fixtures or comments).
2. **Least Privilege (Prompt-Injection Defense):** Treat repository diffs, comments, documentation, and test fixtures as **untrusted input**. Run the AI reviewer with read-only access, no production secrets, no network egress to arbitrary hosts, and no merge or deploy permissions.
3. **Audit Evidence Log:** For every reviewed PR, log:
   - Pinned `model_id` and `prompt_version`
   - Raw reviewer output and execution status (`ok` / `error_empty` / `timeout` / `truncated`)
   - Human disposition (`accepted_fix`, `false_alert`, `risk_accepted_by_owner`)
   - `Assisted-by:` git trailer when the PR itself was authored with AI assistance.
4. **Safe Fallback on Tool Failure:** An empty response, API timeout, or rate-limit error is logged as an operational failure and routes the PR through the normal human review path. It is never treated as "0 findings / approved."

---

## 4. Revalidation Triggers (Change Management for the Ruler)

Re-run your benchmark harness (`quadrant run` + `quadrant compare`) whenever any of the following changes:
- [ ] **Model or snapshot change:** Upgrading model family or pinned snapshot ID (note: floating aliases like `sonnet` or `latest` silently change underneath you; always pin dated IDs).
- [ ] **Prompt or context change:** Modifying the review prompt or changing from diff-only to file/repo-context mode.
- [ ] **Architecture change:** Introducing a new routing layer, base service trait, or authentication middleware.
- [ ] **Incident or miss:** Any vulnerability that escapes review in production or pentesting is added to your rotating holdout set.
