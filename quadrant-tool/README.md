# quadrant

**Measure the human-AI security review boundary on your own codebase.**

`quadrant` traces confirmed CVEs back to the commit that introduced them,
extracts blind diffs for AI counterfactual review, runs those diffs against
every model you register, scores the results, and reports detection rates
by defect category: so you can decide, with data, which reviews to route
to AI and which to keep with humans.

Companion tool to the talk *"Who Writes the Bug, Who Finds the Bug?
Human-AI Security Lessons from Open Source"* (Eric St-Pierre, ISC2).

## Why

Most teams calibrated their AI-review trust once and never re-measured.
But the boundary moves every time models improve, in both directions.
`quadrant` is the ruler you re-run: a repeatable measurement of what AI
catches, what it misses, and how long bugs survive human review. Since
v0.2 the ruler is longitudinal: each model lives in a registry with its
pinned ID and training cutoff, its scores accumulate in their own CSV,
and `quadrant compare` shows the boundary moving release by release.

## Install

```bash
git clone <this-repo> && cd quadrant
python3 -m venv .venv && source .venv/bin/activate
pip install pandas
# optional but recommended: GitHub CLI (`gh`) for advisory pulls
# optional, only for the batch runner: pip install anthropic  (and/or openai)
```

## Quick start

```bash
mkdir mystudy && cd mystudy
python /path/to/quadrant.py init
python /path/to/quadrant.py advisories --repo openemr/openemr

# For each CVE: fill fix_commit in data/cves.csv, then
python /path/to/quadrant.py trace CVE-2026-24908 --repo ./openemr
# ...record intro_commit, then:

python /path/to/quadrant.py diffs --repo ./openemr
python /path/to/quadrant.py scrub                       # blinding check
python /path/to/quadrant.py fixes --apply               # fill empty cvss/reporter from advisories

# Register the model you are measuring: pinned dated ID + published cutoff
python /path/to/quadrant.py model add --slug sonnet-4 --provider anthropic \
    --model-id claude-sonnet-4-20250514 --cutoff 2025-03-01
python /path/to/quadrant.py model list                  # clean vs memorized per model

# Batch-run the blind reviews (resumable; try --dry-run first)
export ANTHROPIC_API_KEY=...
python /path/to/quadrant.py run --model sonnet-4 --runs 3

# Score each CVE x model pair, then read the numbers
python /path/to/quadrant.py score CVE-2026-24908 --model sonnet-4
python /path/to/quadrant.py report --model sonnet-4
python /path/to/quadrant.py compare                     # all models, side by side
```

Prefer a chat UI over the API? `quadrant prompt CVE-2026-24908` still
prints the frozen prompt for manual pasting, exactly as in v0.1.

## Method in one paragraph

For each confirmed CVE, the *fixing* commit (from the security advisory) is
blamed back to the *introducing* commit: the SZZ approach, done with
`git blame` at small scale. Survival time = disclosure date minus
introduction date. The introducing diff is then shown, blind, to an AI
reviewer with a neutral prompt (no hint a vulnerability exists), three runs
per CVE, scored **Caught / Partial / Missed** against the known CVE.
Contamination is controlled per model: each model's published training
cutoff splits the CVEs into post-cutoff (clean) and pre-cutoff (likely
memorized) groups, giveaway text is scrubbed from diffs, and after the
scored runs each model is asked, in two separate conversations, whether it
recognizes the code and whether it knows of an advisory affecting it.

## Scoring rubric

| Score | Definition |
|---|---|
| Caught | Names the vulnerability class and location, unprompted |
| Partial | Flags the right area or a related weakness; wrong class or severity |
| Missed | Does not flag the vulnerable code |

Final score = majority of 3 runs; ties -> Partial.

## Output

`quadrant report` prints, per model:
- the longest-surviving CVEs that model caught cold (your headline number)
- detection on clean vs. likely-memorized CVEs, computed from that model's
  cutoff, always as counts ("caught 4 of 9"): the honesty check
- detection per OWASP category (your routing evidence)
- contamination flags: CVEs where the model recognized the code or knew of
  the advisory (limitations section)

`quadrant compare` prints the longitudinal view across every model with
scores:
- a CVE x model matrix of final scores (C/P/M), with a marker on cells
  where that CVE is clean for that model
- a summary block per model: clean caught x of y, memorized caught x of y,
  per-OWASP one-liners
- a drift section: CVEs where the newest model disagrees with any older one

## A benchmark you re-run

v0.2 stores per-model scores in `data/scores.csv`, the model registry in
`data/models.csv`, and an append-only run journal (model version, wall
seconds, truncation) in `ai_runs/runs.csv`. All plain CSV, all
git-friendly: commit after every cycle and the history *is* the benchmark.
The cadence for each new model release, the way clean/memorized shifts as
CVEs age into training data, and the cautions that keep the numbers honest
are in [BENCHMARK.md](BENCHMARK.md).

## Honest limitations

Single-codebase runs are directional, not general benchmarks. Contamination
is mitigated, never zero. Small n is a feature (deep, reproducible case
study), not a statistical claim: report counts, not percentages alone. If
you find an *undisclosed* vulnerability while tracing, report it to the
project's security process, don't publish it.

## License

MIT. Use it, fork it, run it on your own repos: that's the point.
