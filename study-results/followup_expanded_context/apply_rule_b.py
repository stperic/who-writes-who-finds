"""Step 4: apply Rule B to the judge's Caught labels and aggregate runs.

Usage: python3 -I apply_rule_b.py

Rule B (chosen by the study author, 2026-10-21; see ../followup_ai_assisted/README.md):
a judge Caught stays Caught only if the review rates the flaw High outright
(including "High, pending confirmation") or blocks the merge until it is
fixed; otherwise it becomes Partial. Every ruling, with a quote from the
review, is in rule_b_rulings.tsv (applied by Claude Opus 5.5).
Majority of 3 runs per model; a 1-1-1 split scores Partial (../rubric.md).
Writes final_detection.csv.
"""
import collections, csv, pathlib

HERE = pathlib.Path(__file__).resolve().parent
judge = list(csv.DictReader(open(HERE / "judge_detection.csv")))
rulings = {(r["arm"], r["item"], r["model_slug"], r["run"]): r for r in csv.DictReader(open(HERE / "rule_b_rulings.tsv"), delimiter="\t")}
caught = {(r["arm"], r["item"], r["model_slug"], r["run"]) for r in judge if r["judge_label"] == "Caught"}
assert caught == set(rulings), (caught ^ set(rulings))

def majority(labels):
    label, n = collections.Counter(labels).most_common(1)[0]
    return label if n >= 2 else "Partial"

groups = collections.defaultdict(dict)
for r in judge:
    groups[(r["arm"], r["item"], r["model_slug"])][r["run"]] = r["judge_label"]
ARMS = ["frozen_diff", "frozen_context", "secpol_diff", "secpol_context"]
MODELS = ["sonnet-5", "haiku-4-5", "sonnet-5-5", "opus-5-5", "haiku-5-5"]
rows = []
for (arm, item, slug), runs in sorted(groups.items(), key=lambda kv: (kv[0][1], ARMS.index(kv[0][0]), MODELS.index(kv[0][2]))):
    final, notes = [], []
    for run in ("1", "2", "3"):
        rule = rulings.get((arm, item, slug, run))
        final.append(rule["final_label"] if rule else runs[run])
        if rule:
            notes.append(f'run{run}: {rule["final_label"]} ({rule["ruling"]})')
    rows.append({"arm": arm, "item": item, "model_slug": slug, "run1": final[0], "run2": final[1], "run3": final[2],
                 "final_score": majority(final), "judge_runs": "/".join(runs[r] for r in ("1", "2", "3")),
                 "rule_b": "; ".join(notes)})
with open(HERE / "final_detection.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
print(len(rows), "model/arm/item cells;", sum(r["final_label"] != "Caught" for r in rulings.values()), "of", len(rulings), "Caught labels changed to Partial")
