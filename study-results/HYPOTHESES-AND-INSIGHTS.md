# Hypotheses and insights log (follow-up experiments)

Running record of what we expected before each follow-up test and what we
learned after it. Rules:

- A hypothesis is written down, with its date, **before** its test produces
  results, and committed then, so git history shows the order.
- Outcomes are added afterwards. Hypotheses that turn out wrong stay here,
  marked **Refuted**.
- Observations noticed after the fact are marked **post hoc**: they suggest
  hypotheses, they do not confirm them.
- Every insight points to its evidence. Sample sizes are small throughout
  (2 to 5 vulnerable diffs per follow-up), so these are leads, not
  measurements of general rates.

Status values: **Open** (not yet tested), **Supported**, **Partly supported**,
**Refuted**.

## Hypotheses

### H1. Telling the reviewer that pre-existing flaws in touched code count will raise detection on the two AI-assisted changes
- Recorded: 2026-10-21, before `followup_policy_prompt/` ran (stated in session as "if the catch rate jumps, that is a concrete policy recommendation").
- Status: **Supported**, with a cost. Runs naming the flaw 15 to 25 of 30, runs that would block 2 to 8, model/diff pairs Caught 0 to 2 of 10. Benign reviews with a false alarm 2 to 8 of 50. Evidence: `followup_policy_prompt/README.md`.

### H2. A security-focused (OWASP Top 10) prompt changes results, on older and newer models (Eric's hypothesis)
- Recorded: 2026-10-21, before `followup_security_prompt/` ran.
- Status: **Supported**. Pairs Caught: generic 0, security 3, security plus touched-code sentence 7 of 10. Evidence: `followup_security_prompt/README.md`.

### H3. Giving the reviewer the file the flaw depends on will turn cross-file misses into catches (step 4)
- Recorded: 2026-10-21, while the step 4 reviews were running and before any step 4 output had been read.
- Expectations, per case:
  - Largest gains where the dependent file states the missing fact directly:
    C3 (`globals.inc.php` describes `gateway_api_key` as "API Secret for
    Stripe"), C2 (`FhirServiceBase.php` applies patient filtering only to
    `IPatientCompartmentResourceService`), F1 (`C_PracticeSettings.class.php`
    shows the sub-controllers reached behind the `practice_settings` check).
  - Moderate gain on C1: the reviewer must infer from `Controller.class.php`
    that URL parameters map positionally onto the new `$disable_exit` argument
    and that returned output is served as HTML.
  - Smallest gain on C4: a very large diff and file, and SSRF requires knowing
    that the PDF renderer fetches URLs. Expect escaping/XSS comments (Partial)
    more often than SSRF.
  - Context helps more under the security plus touched-code prompt than under
    the generic prompt.
- Status: **Open**. Evidence will be `followup_expanded_context/`.
- Not measured in step 4: false alarms with added context.
- Judge (decided 2026-10-21, after the six abnormal runs were rerun and before
  any step 4 review was judged): Claude Opus 5.5, the study author's choice.
  Unlike the Fable 5.1 judge of the earlier follow-ups, it is also one of the
  reviewers. The 30 reused F1 diff-only reviews are re-judged with Opus 5.5 so
  every H3 comparison uses one judge.

### H4. Static scanners do well on injection-style bugs and poorly on missing-permission bugs
- Recorded: 2026-10-21, before any scanner comparison run. (The demo's earlier Snyk run on CVE-2026-25146 is already known: same 20 findings on vulnerable and fixed versions.)
- Expectation: scanners (Snyk Code today; Semgrep with rules pinned before
  2026-01-31) flag injection-style flaws, where tainted input reaches a
  dangerous call, such as the SQL injection cases, the XSS cases and the F2
  path traversal. They miss flaws that depend on what the code was meant to do:
  F1 (missing permission checks), C2 (CareTeam cross-patient access) and C3
  (private payment key sent to the browser).
- Corollaries: a Snyk miss today implies a miss before disclosure; a Snyk catch
  today carries the caveat "current scanner, after disclosure", because Snyk
  Code analyzes uploaded code with current rules and cannot be pinned to an
  older version.
- Status: **Open**. Evidence will be the scanner-comparison folder.

## Insights

### I1. Human review let these flaws through, and the record shows it (post hoc)
11 of the 12 introducing changes that went through a GitHub PR were reviewed by
a second maintainer, 9 with a recorded sign-off. In the 4 PRs where reviewers
commented on the vulnerable file, no comment touched the flaw. These are
misses by construction (every case became a CVE); there is no catch rate.
Evidence: `pr_review/pr_reviews.csv`, README section "Human Review of the
Introducing Changes".

### I2. No OpenEMR advisory traced to code an AI tool introduced; two AI-assisted changes carried existing flaws forward (post hoc)
Blame-based tracing of 132 security fixes against 490 AI-tagged commits found
no AI-introduced vulnerability. Two AI-co-authored changes rewrote vulnerable
code and kept the flaw (GHSA-9rj4-fxmj-c4r7, GHSA-m6q6-5j87-3cmp). Evidence:
`ai_trailer_trace/findings.csv`.

### I3. AI reviewers see inherited flaws and wave them through as "pre-existing" (post hoc; led to H1)
Under the generic prompt, newer models named the flaw in 12 of 18 runs but
rated it low or deferred it, because the diff had not introduced it. One run
cleared the refactor as "a faithful, cleaner extraction of the previous
logic", accurate, and exactly why the inherited gap passed. Evidence:
`followup_ai_assisted/README.md`.

### I4. The prompt matters as much as the model generation (from H2)
Asked for a security review, older models close most of the detection gap
(Haiku 4.5 went from missing both flaws to catching both). Newer models keep
their lead on precision: Sonnet 5.5 raised no false alarm under any of the four
prompts. Haiku 4.5 under the strongest prompt raised a Medium-or-higher false
alarm on 9 of 10 harmless changes. Evidence: `followup_security_prompt/README.md`.

### I5. Every gain in detection costs triage (from H1 and H2)
Security findings on the 10 benign diffs rose from 66 (generic) to 173
(security plus touched code), mostly "please verify" requests. A routing
policy should apply the strong prompt only to changes already marked
security-sensitive.

### I6. Security prompts produce conditional severities, which the rubric must handle (post hoc)
Many security-prompt reviews rate a flaw "High if the input is user-controlled,
otherwise Low" and ask someone to confirm. Whether that counts as a catch
decides several results. Applied rule: Caught only if the review rates the flaw
High outright or blocks the merge until it is fixed. Evidence: `rule_b` column
in each `final_detection.csv`.

### I7. Scoring rules and scorer independence change headline numbers (post hoc)
The rubric's two-part Caught definition (names the flaw, and would block the
merge) split the provisional scorer and the independent judge on 2 runs, which
flipped one case-level result. Rule B (must block or rate High) was chosen to
match the deck's own scoring of the payment case. The provisional scorer was
the same model family as one reviewer, which is why an independent judge and a
human check are required before results are published.

### I8. Run records must be complete and kept in the repo (process)
An audit found background-run logs only in temporary storage and 12 early
calls without token usage. From step 4 on, every call stores its exact prompt
and full raw response.
