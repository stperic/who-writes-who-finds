# Running quadrant as a longitudinal benchmark

The talk's core claim is that the human-AI review boundary moves and
therefore must be re-measured. This file is the re-measurement procedure:
what to do, in order, every time a model vendor ships something new. The
whole state of the benchmark lives in three CSVs (`data/models.csv`,
`data/scores.csv`, `ai_runs/runs.csv`), so a cycle ends with a git commit
and nothing else.

## The cycle: every time a new model ships

1. **Pin a dated model ID.** Use the vendor's dated snapshot string
   (e.g. `claude-sonnet-4-20250514`), never a floating alias like
   `latest` or the bare family name. A slug you pick (short, stable) is
   how the model appears everywhere in the benchmark.

2. **Record its published training cutoff in the registry BEFORE any
   run.**

   ```bash
   quadrant model add --slug <slug> --provider anthropic \
       --model-id <dated-id> --cutoff YYYY-MM-DD
   ```

   The cutoff decides which CVEs count as clean for this model, and that
   split must be locked in before you see a single output. Choosing or
   adjusting a cutoff after looking at results is how benchmarks quietly
   lie to their owners. `quadrant model list` shows the resulting
   clean/memorized counts per model: sanity-check them now.

3. **Run the ruler.**

   ```bash
   quadrant run --model <slug> --dry-run   # preview the work list
   quadrant run --model <slug>             # 3 runs per CVE, resumable
   ```

   The runner skips outputs that already exist, so an interrupted batch
   just resumes. Every call is journaled in `ai_runs/runs.csv` with the
   version string the API actually reported, wall-clock seconds, and
   whether the diff was truncated. After the scored runs it asks the
   recognition and advisory-awareness questions in separate
   conversations and saves those too.

4. **Blind-score, one CVE at a time.**

   ```bash
   quadrant score CVE-XXXX-XXXXX --model <slug>
   ```

   Score the new model without looking at any other model's scores: do
   not open `compare`, `report`, or older models' outputs first. You are
   the rubric's weakest component; knowing that last year's model caught
   a CVE biases how charitably you read this year's output. Answer the
   `recognized?` and `advisory_aware?` prompts from the `_recog.md` and
   `_advisory.md` files, not from memory.

5. **Compare.**

   ```bash
   quadrant compare
   ```

   The matrix, the per-model summaries, and the drift section (where the
   newest model disagrees with any older one) are the cycle's output.
   Commit the CSVs and the raw outputs.

## Clean and memorized are per-model, and they move

A CVE disclosed in February 2026 is clean for every model whose training
cutoff predates it. Two model generations later, that same disclosure,
its advisory, and its fix commit are inside the new model's training
data: the CVE has aged from clean to memorized. Same row in `cves.csv`,
different column for each model. That is why quadrant computes the split
per model from `disclosed_date` vs. that model's cutoff instead of
storing a global group label: nothing in the dataset needs editing when
a new model arrives, and older models' historical numbers never change
retroactively.

The consequence: the clean set for the newest model shrinks every cycle.
A benchmark whose clean set has decayed to two CVEs measures memory, not
review skill.

## Why you add fresh CVEs each cycle

To keep the newest model's clean set meaningful, each cycle should start
by pulling recently disclosed advisories and tracing a few new CVEs:

```bash
quadrant advisories --repo <owner/name>
# add the new rows to data/cves.csv, then trace/diffs/scrub as usual
quadrant fixes --apply    # fill empty cvss and reporter from the advisories
```

New CVEs are guaranteed clean for every current model, and they refresh
the memorized side later, for free, as they age. Old CVEs are never
removed: they keep feeding the memorized comparison and the survival-days
headline.

## Cautions

- **Never upgrade a model mid-cycle.** If the vendor replaces the
  snapshot behind your pinned ID or you want the newer one, that is a new
  registry entry with a new slug and its own full run, not a continuation.
- **Chat UIs silently swap models.** Web interfaces upgrade underneath
  you without notice, which destroys comparability. Use pinned API
  versions for every scored run, and check that the version string
  journaled in `ai_runs/runs.csv` matches the ID you registered.
- **Report counts, not percentages, at small n.** "Caught 4 of 9 clean
  CVEs" is honest; "44%" invites a precision the sample cannot support.
  quadrant's report and compare output follows this rule; keep your
  slides to it too.
- **Log wall-clock time.** Latency is part of the routing decision (a
  reviewer that takes 90 seconds per diff is a different tool than one
  that takes 5), and it drifts across model generations. The runner
  records `wall_seconds` per call in `ai_runs/runs.csv`; keep it.
