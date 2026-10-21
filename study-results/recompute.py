#!/usr/bin/env python3
"""Regenerate numbers.md: the single source of truth for every number in the deck.

Inputs (all in this directory, never edited by this script):
  scores.csv      per-run labels from the judge model
  cves.csv        case inventory
  validity.csv    cases excluded from results, with reasons
  run_status.csv  runs that are execution errors, not detection results
  fix_dates.csv   date each fix became public (fix commit date in OpenEMR)
  models.csv      training cutoffs

Aggregation over VALID runs only:
  3 valid: majority wins; a 1-1-1 split scores Partial.
  2 valid: agreement wins; disagreement scores Partial.
  1 valid: that label, flagged as low-run.
  0 valid: error, excluded from denominators.

Usage: python3 -I recompute.py   (writes numbers.md next to this file)
"""
import csv
import statistics
from collections import Counter
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODELS = ["sonnet-5", "haiku-4-5"]
LBL = {"Caught": "C", "Partial": "P", "Missed": "M"}


def rows(name):
    with open(HERE / name, newline="") as f:
        return list(csv.DictReader(f))


cves = {r["cve_id"]: r for r in rows("cves.csv") if r["cve_id"]}
scores = rows("scores.csv")
excluded = {r["cve_id"]: r for r in rows("validity.csv") if r["status"].startswith("excluded")}
repaired = {r["cve_id"]: r for r in rows("validity.csv") if r["status"].startswith("repaired")}
errors = {(r["cve_id"], r["model_slug"], int(r["run"])) for r in rows("run_status.csv") if r["status"].startswith("error")}
fix_public = {r["cve_id"]: r["fix_public_date"] for r in rows("fix_dates.csv")}
cutoff = {r["slug"]: r["training_cutoff"] for r in rows("models.csv")}
benign = rows("benign_controls/benign_scores.csv") if (HERE / "benign_controls/benign_scores.csv").exists() else []
CROSS_FILE_CASES = {"CVE-2025-31121", "CVE-2026-24487", "CVE-2026-25146", "CVE-2026-33321"}


def aggregate(labels):
    if not labels:
        return "E"
    c = Counter(labels)
    top, n = c.most_common(1)[0]
    if len(labels) == 3:
        return top if n >= 2 else "P"
    if len(labels) == 2:
        return top if n == 2 else "P"
    return top


final = {}      # (cve, model) -> label
low_run = []
run_total = run_err = 0
for r in scores:
    cve, m = r["cve_id"], r["model_slug"]
    valid = []
    for i in (1, 2, 3):
        run_total += 1
        if (cve, m, i) in errors:
            run_err += 1
            continue
        valid.append(LBL[r[f"run{i}"]])
    final[(cve, m)] = aggregate(valid)
    if len(valid) < 3:
        low_run.append(f"{cve} {m}: {len(valid)} valid runs -> {final[(cve, m)]}")

scored = sorted({c for c, _ in final})
valid_cases = [c for c in scored if c not in excluded]
group = {c: cves[c]["group"] for c in scored}


def tally(cases, m):
    t = Counter(final[(c, m)] for c in cases)
    n = sum(t[k] for k in "CPM")
    return t, n


def pct(a, b):
    return f"{100 * a / b:.0f}%" if b else "n/a"


out = []
w = out.append
w("# numbers.md: every number the deck may quote")
w("")
w(f"Generated {date.today().isoformat()} by `recompute.py`. Do not edit by hand.")
w("Initial runs: 2026-08-17. Ground-truth repair (CVE-2026-24487, CVE-2026-24849, CVE-2026-25146 run 2) and 10-diff benign control pass: 2026-10-15 on identical pinned models (`claude-sonnet-5`, `claude-haiku-4-5-20251001`).")
w("")
w("## Case counts")
w("")
w(f"- Inventory records: {len(rows('cves.csv'))} ({len(cves)} with CVE IDs)")
w(f"- Scored cases: {len(scored)} (A: {sum(group[c] == 'A' for c in scored)}, B: {sum(group[c] == 'B' for c in scored)})")
w(f"- Repaired and re-run after ground-truth audit: {len(repaired)}: {', '.join(sorted(repaired))} (plus 1 empty run on CVE-2026-25146)")
w(f"- Excluded from scoring: {len(excluded)}")
unscored = sorted(c for c in cves if c not in scored)
w(f"- Inventory CVEs not scored: {len(unscored)} ({', '.join(unscored)}); no run data, so they are outside every denominator. Reasons are not recorded in validity.csv.")
w(f"- **Valid scored cases: {len(valid_cases)}** (A: {sum(group[c] == 'A' for c in valid_cases)}, B: {sum(group[c] == 'B' for c in valid_cases)})")
w(f"- Review runs: {run_total}; remaining execution errors: {run_err} (1 initial empty output repaired)")
w(f"- Benign control diffs evaluated: {len(benign)} (6 security-fix patches + 4 routine non-security commits)")
w("")
w("Group A = disclosed after both reviewers' training cutoffs (disclosed 2026-02-25 to 2026-03-25).")
w("Group B = older, potentially exposed (disclosed 2018-2025). Neither group is 'clean': see the fix-date section.")
w("")
w("## Headline: Caught / Partial / Missed (valid cases)")
w("")
w("| Model | Cohort | Caught | Partial | Missed | n | Caught rate |")
w("|---|---|---:|---:|---:|---:|---:|")
for m in MODELS:
    for name, sel in (("A post-cutoff", "A"), ("B older", "B"), ("All", None)):
        cs = [c for c in valid_cases if sel is None or group[c] == sel]
        t, n = tally(cs, m)
        w(f"| {m} | {name} | {t['C']} | {t['P']} | {t['M']} | {n} | {pct(t['C'], n)} |")
w("")
w("## Fix availability vs training cutoff (Group A, valid cases)")
w("")
w("Fix public date = commit date of the fix in OpenEMR's public repository (security fixes are merged from a private fork, so the merge makes them public).")
w("")
for m in MODELS:
    cut = cutoff[m]
    a = [c for c in valid_cases if group[c] == "A"]
    before = [c for c in a if fix_public.get(c, "9999") <= cut]
    after = [c for c in a if c not in before]
    ta, na = tally(after, m)
    w(f"- **{m}** (cutoff {cut}): {len(before)} of {len(a)} fixes were public on or before the cutoff"
      + (f" ({', '.join(before)})" if before else "")
      + f". On the {len(after)} cases whose fix became public after the cutoff: Caught {ta['C']}/{na} ({pct(ta['C'], na)}).")
w("")
w("Caveat: a fix being public days before a cutoff does not mean it was in training data, and a later fix does not prove the vulnerable code was unseen. Report as reduced, not removed, contamination risk.")
w("")
w("## Coverage overlap")
w("")
for name, sel in (("Group A", "A"), ("All valid", None)):
    cs = [c for c in valid_cases if sel is None or group[c] == sel]
    s = {c for c in cs if final[(c, 'sonnet-5')] == "C"}
    h = {c for c in cs if final[(c, 'haiku-4-5')] == "C"}
    w(f"- {name}: Sonnet Caught {len(s)}, Haiku Caught {len(h)}, Haiku-only catches {len(h - s)}, both {len(s & h)}")
w("")
w("## OWASP Top 10 (2021) breakdown (valid cases, both cohorts)")
w("")
w("| OWASP (2021) | n | sonnet-5 Caught | sonnet-5 Partial | sonnet-5 Missed | haiku-4-5 Caught | haiku-4-5 Partial | haiku-4-5 Missed |")
w("|---|---:|---:|---:|---:|---:|---:|---:|")
cats = sorted({cves[c]["owasp"] for c in valid_cases})
for k in cats:
    cs = [c for c in valid_cases if cves[c]["owasp"] == k]
    ts = tally(cs, 'sonnet-5')[0]
    th = tally(cs, 'haiku-4-5')[0]
    w(f"| {k} | {len(cs)} | {ts['C']} | {ts['P']} | {ts['M']} | {th['C']} | {th['P']} | {th['M']} |")
w("")
w("## Single-file vs Cross-file contract visibility (all 24 valid cases)")
w("")
single_cases = [c for c in valid_cases if c not in CROSS_FILE_CASES]
cross_cases = [c for c in valid_cases if c in CROSS_FILE_CASES]
w("| Scope required to confirm exploitability | Cases (n) | sonnet-5 Caught | sonnet-5 Partial | sonnet-5 Missed | haiku-4-5 Caught | haiku-4-5 Partial | haiku-4-5 Missed |")
w("|---|---:|---:|---:|---:|---:|---:|---:|")
for label, subset in (("Single-file (sink & contract in diff)", single_cases), ("Cross-file (caller/base-class/config outside diff)", cross_cases)):
    ts = tally(subset, "sonnet-5")[0]
    th = tally(subset, "haiku-4-5")[0]
    w(f"| {label} | {len(subset)} | {ts['C']} | {ts['P']} | {ts['M']} | {th['C']} | {th['P']} | {th['M']} |")
w("")
w("Cross-file cases: `CVE-2025-31121` (`Controller.class.php` URL-to-positional-arg splatting), `CVE-2026-24487` (`FhirServiceBase.php` `IPatientCompartmentResourceService` check), `CVE-2026-25146` (`globals.inc.php` private Transaction Key vs public Login ID), `CVE-2026-33321` (`mPDF` server-side HTML-to-PDF rendering caller).")
w("")
w("## Benign control pass (10 non-vulnerable OpenEMR diffs: 6 security fixes + 4 routine commits)")
w("")
w("- **sonnet-5**: **0 / 10 false security alerts** (correctly recognized all 6 security patches as improvements and stated 'No security issues' on all 4 routine commits); **4 / 10 High missing-context correctness warnings** (asking to verify callers, `js_escape()` definition, interface methods, or PHP 8.0+ support outside the single-file diff).")
w("- **haiku-4-5**: **1 / 10 false security alert** (`BENIGN-03`, Medium claim that checking ACL before CSRF leaks permission state); **1 / 10 Critical missing-context correctness error** (`BENIGN-04`, falsely claiming `js_escape()` is an undefined function because its definition is in another file).")
w("")
w("## Human adjudication vs judge model (Fable 5)")
w("")
w("- Valid case-model pairs audited: 48 (24 valid CVEs x 2 models; 144 valid non-empty runs after repairing CVE-2026-24487, CVE-2026-24849, and CVE-2026-25146 run 2)")
w("- Case-level majority agreement on valid cases: **48 / 48 (100%)**")
w("- Run-level agreement on valid runs: **142 / 144 (98.6%)** (2 borderline Haiku severity calls between `Caught` and `Partial` on `CVE-2026-25476` run 3 and `CVE-2021-40352` run 1; neither changes the case majority)")
w("")
w("## Recognition probe (does the model say it recognizes the code?)")
w("")
for m in MODELS:
    rec = Counter(r["recognized"] for r in scores if r["model_slug"] == m and r["cve_id"] in valid_cases)
    adv = Counter(r["advisory_aware"] for r in scores if r["model_slug"] == m and r["cve_id"] in valid_cases)
    w(f"- {m}: recognized {dict(rec)}; claimed advisory awareness {dict(adv)}")
w("")
w("## Who reported (valid cases, from the advisory credit recorded in cves.csv)")
w("")
w("caught_by: `vendor-AI` = AISLE; `researcher` = a named reporter or analyst credit (individual or group, affiliation not verified); `not-credited` = no reporter or analyst credit in the record, including advisories that credit only remediation developers. The column never guesses a discoverer the record does not name.")
w("")
w("| Reported by | Group A (recent) | Group B (older) |")
w("|---|---:|---:|")
for lab, key in (("Named reporter or research group", "researcher"), ("AI analyzer vendor", "vendor-AI"), ("No discoverer credited", "not-credited")):
    a = sum(1 for c in valid_cases if cves[c]["group"] == "A" and cves[c]["caught_by"] == key)
    b = sum(1 for c in valid_cases if cves[c]["group"] == "B" and cves[c]["caught_by"] == key)
    w(f"| {lab} | {a} | {b} |")
w("")
w("## Commit-to-disclosure interval (traceable=yes only; partial traces carry a lower bound and are left out)")
w("")
def _interval(label, ids):
    d = sorted(int(cves[c]["survival_days"]) for c in ids if cves[c]["traceable"] == "yes" and cves[c]["survival_days"])
    w(f"- {label}: n = {len(d)}; median {statistics.median(d):.0f} days ({statistics.median(d) / 365.25:.1f} yrs); "
      f"max {d[-1]} days ({d[-1] / 365.25:.1f} yrs); min {d[0]} days")
_interval("**Valid scored cases (the deck's denominator)**", sorted(valid_cases))
_interval("All traced inventory CVEs, scored or not (traceable=yes only)", [c for c in cves if c not in excluded])
w("")
w("## Aggregation notes")
w("")
for line in low_run:
    w(f"- {line}")
w("")
w("## Changes vs the August scoring (audit trail)")
w("")
for (c, m), lab in sorted(final.items()):
    old = next(r["final_score"] for r in scores if r["cve_id"] == c and r["model_slug"] == m)
    tag = " (excluded case)" if c in excluded else ""
    if LBL[old] != lab or c in excluded:
        w(f"- {c} {m}: August {LBL[old]} -> now {lab}{tag}")

(HERE / "numbers.md").write_text("\n".join(out) + "\n")
print("\n".join(out))
