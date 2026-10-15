# Worksheet 3: 30-Day Shadow-Mode Pilot Plan & Exit Scorecard
**Companion to:** *Who Writes the Bug, Who Finds the Bug?* (Eric St-Pierre, Medoya Consulting LLC)

Use this template to fulfill **Learning Objective 3**: replicate the evaluation on your own codebase (or a key dependency) in 30 days and make a defensible go/no-go deployment decision.

---

## 1. Four-Week Execution Schedule

### Week 1: Ground Truth & Benign Control Selection (~4 hours)
- [ ] Assign **one Pilot Owner** and select **one repository**.
- [ ] Collect **20 to 30 confirmed historical defects** (your own resolved security bugs, pentest findings, or public CVEs in a major open-source dependency).
- [ ] Trace each fix back to its introducing commit (`git blame <fix>^ -L <start>,<end> -- <file>`) and **manually verify the vulnerable mechanism** (do not trust advisory commit links blindly; in our OpenEMR study, 2 of 24 public links pointed to the wrong fix until audited).
- [ ] Collect **10 validated benign commits** (5 security-fix commits + 5 routine feature/refactor commits that do not introduce vulnerabilities).
- [ ] Strip commit messages before `diff --git` and stage under neutral item IDs (`quadrant diffs` + `quadrant scrub`).

### Week 2: Shadow-Mode Execution (~2 hours)
- [ ] Pin exact dated model IDs in `data/models.csv` (never use floating aliases).
- [ ] Run the frozen neutral prompt 3 times per defect diff (`quadrant run --model <slug> --runs 3`) plus 1 pass on each of the 10 benign control diffs.
- [ ] Log execution errors/empty outputs separately from detection misses.

### Week 3: Rubric Scoring & Human Verification (~3 hours)
- [ ] Score each run **Caught / Partial / Missed** against the known defect using the 3-line rubric (`rubric.md`).
- [ ] Have a human reviewer verify the scores and adjudicate every alert raised on the 10 benign control diffs (separating **false security alerts** from **missing-context correctness questions**).

### Week 4: Scorecard Decision & Rollout Gate (~1 hour)
- [ ] Populate the Pilot Scorecard below and review against your pre-declared Exit Criteria.

---

## 2. Pilot Scorecard (Worked OpenEMR Example vs. Your Pilot)

| Metric | OpenEMR Study Result (`claude-sonnet-5`, Diff-Only) | OpenEMR Study Result (`claude-haiku-4-5`, Diff-Only) | Your Pilot Target / Threshold | Your Measured Pilot Result |
|---|---|---|---|---|
| **1. Post-cutoff valid catches (Group A)** | **13 / 16 Caught** (3 Partial, 0 Missed) | **5 / 16 Caught** (6 Partial, 5 Missed) | Define per boundary | `__ / __` |
| **2. All validated cases (Group A + B)** | **20 / 24 Caught** (3 Partial, 1 Missed) | **8 / 24 Caught** (7 Partial, 9 Missed) | Define per boundary | `__ / __` |
| **3. Single-file vs. Cross-file catches** | **20 / 20 single-file Caught** vs. **0 / 4 cross-file Caught** (3P, 1M) | **8 / 20 single-file Caught** vs. **0 / 4 cross-file Caught** (1P, 3M) | Supply caller/file context if cross-file catches are low | Single: `__ / __`<br>Cross: `__ / __` |
| **4. False security alerts on benign diffs** | **0 / 10 benign diffs** had false security alerts | **1 / 10 benign diffs** had a false Medium security alert | `<= 1 / 10` on benign controls | `__ / 10` |
| **5. Missing-context High alerts on benign diffs** | **4 / 10 benign diffs** asked to verify callers/helpers/PHP version outside diff | **1 / 10 benign diffs** falsely called `js_escape()` undefined | Reduce by passing full touched file + `composer.json` | `__ / 10` |
| **6. Execution errors / empty outputs** | **1 / 144 initial runs** (0 / 144 after retry) | **0 / 144 runs** | `< 2%` with automatic fallback | `__ / __` |
| **7. Human vs. judge scoring agreement** | **48 / 48 cases** (142 / 144 valid runs) after repair | **48 / 48 cases** | Human verifies 100% of pilot set | `__ / __` |
| **8. Incremental catches from 2nd model** | **0 unique catches** added by Haiku 4.5 over Sonnet 5 | Baseline | Only deploy 2nd model if unique catches > cost/triage | `__ unique` |

---

## 3. Formal Exit & Rollback Criteria

- **Go Decision (Promote from Shadow Mode to Advisory PR Comments):**
  - [ ] Named owner appointed for the reviewer configuration and each high-impact trust boundary.
  - [ ] False security alert rate on benign controls is within the team's triage budget.
  - [ ] Full touched-file context (and `composer.json` / helper definitions) is supplied so reviewers are not spammed with "verify caller outside diff" warnings.
- **Rollback Trigger (Revert to Shadow Mode Immediately If):**
  - [ ] Reviewers dismiss `> 50%` of High/Critical AI comments as false or missing-context noise over any 2-week window.
  - [ ] Any prompt-injection attempt or unapproved data egress is detected.
  - [ ] An upstream model alias changes without a completed revalidation run.
