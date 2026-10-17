# Worksheet 1: Four-Quadrant Security Review Baseline Assessment
**Companion to:** *Who Writes the Bug, Who Finds the Bug?* (Eric St-Pierre, Medoya Consulting LLC)

Use this worksheet to fulfill **Learning Objective 1**: assess your review process against the 4-quadrant framework, separate measured facts from unmeasured blind spots, and establish your local baseline.

---

## Part A: Worked Example (OpenEMR Case Study, October 2026)

| Quadrant | Question | Observed Evidence (OpenEMR) | What Remains Unknown / Next Step |
|---|---|---|---|
| **Q1: What Humans Introduce** | Which vulnerability classes appear in our historical commits, and how long do they survive before disclosure? | **24 validated CVEs** traced to introducing commits: **11 Injection (A03)**, **8 Broken Access Control (A01)**, **3 Auth/Session (A07)**, **1 Secrets (A05)**, **1 SSRF (A10)**. Commit-to-disclosure across the 21 single-commit traces among the 24 scored cases: **median 5.6 years (2,043 days)**, max **15.7 years**. | Public advisories record disclosure date, not internal discovery date or production exploitability window. |
| **Q2: What AI Introduces** | Which defects arrive via AI-assisted commits, and can we audit which PRs used AI? | **External field data:** 312 AI-contributed CVEs in Georgia Tech's Vibe Security Radar (`vibesecradar.com`, Sept 2026); **61% are Injection (116) and Auth/Access Control (75)**.<br>**Local repo data:** in March 2026 OpenEMR added an AI-disclosure question to its PR template and asked for `Assisted-by:` trailers; **about 150 commits** carried the trailer by our August 2026 clone, and several hundred more carry other AI co-author markers. | Defect rate per 1,000 AI-assisted commits vs. human-only commits requires tracking `Assisted-by:` trailers over a fixed release cycle. |
| **Q3: What Humans / External Audits Catch** | Who actually finds our vulnerabilities today, and at what stage (PR review vs. years later)? | All 24 studied CVEs escaped merge-time review. Post-merge reporters: **9 external security researchers**, **7 autonomous AI analyzer vendor (AISLE)**, **8 unspecified in advisory credits**. | Merge-time human catch rate on prevented bugs is not logged unless PR review comments blocking security flaws are tagged. |
| **Q4: What AI Catches (and Misses)** | Reviewing the introducing diff blind at merge time, what does our pinned AI reviewer catch, and what does it miss? | **Sonnet 5 (diff-only):** Caught **13 / 16** post-cutoff 2026 CVEs (**3 Partial, 0 Missed**) and **20 / 24** overall. Caught **20 / 20** single-file flaws; scored **0 / 4 Caught (3 Partial, 1 Missed)** when the security contract lived in a second file outside the diff.<br>**Haiku 4.5 (diff-only):** Caught **5 / 16** post-cutoff (**8 / 24** overall).<br>**Benign controls (10 diffs):** **0 / 10** false security alerts (Sonnet 5), but **4 / 10** High "verify caller/context outside diff" warnings. | Diff-only review under-measures what an AI reviewer catches when given the full touched files and architecture notes. |

---

## Part B: Your Team's Blank Worksheet

**Repository / Service Name:** `___________________________`
**Assessment Date:** `____-__-__`
**Assessment Owner:** `___________________________`
**Pinned AI Reviewer Model & Version:** `___________________________` (Training cutoff: `____-__-__`)

| Quadrant | Your Local Data Source (20-30 items) | Measured Counts (Use Counts, Not %) | Key Blind Spots / Unmeasured Gaps | Action Required |
|---|---|---|---|---|
| **Q1: Humans Introduce** | Internal bug tracker, pentest findings, or dependency CVEs | Top classes:<br>1. `________` (`__ / __`)<br>2. `________` (`__ / __`)<br>Median age at detection: `____ days` | Are introducing commits traceable? `__ / __` | |
| **Q2: AI Introduces** | PR template checkbox or `Assisted-by:` git trailer | PRs with AI provenance tag: `__ / __`<br>Post-merge security defects in AI-tagged PRs: `__` | If you do not tag AI-assisted PRs, mark **UNMEASURED** and add the PR template control first. | |
| **Q3: Humans Catch** | PR review logs vs. post-merge scanner/pentest/bounty reports | Caught at PR review: `__`<br>Caught post-merge (SAST/pentest/external): `__` | Do reviewers record what they checked on high-impact boundaries? | |
| **Q4: AI Catches** | Blind shadow run on 20-30 historical introducing diffs + 10 benign diffs | **Valid Catches:** `__ / __`<br>**Partials:** `__ / __`<br>**Misses:** `__ / __`<br>**False security alerts on 10 benign diffs:** `__ / 10`<br>**Missing-context warnings on 10 benign diffs:** `__ / 10` | Compare single-file flaws (`__ / __`) vs. cross-file flaws (`__ / __`). | |
