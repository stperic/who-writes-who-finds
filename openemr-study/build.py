"""Build the compact, GitHub-readable OpenEMR study from the archived study tree.

Run from the repository root:
    python3 openemr-study/build.py

The source is study-results/ when present; otherwise it is extracted from the
bundled evidence/study-results.zip. This script never edits its source files.
"""
import csv
import hashlib
import json
import pathlib
import re
import shutil
import tempfile
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
HERE = ROOT / "openemr-study"
SOURCE = ROOT / "study-results"
TEMP = None
if not SOURCE.is_dir():
    TEMP = tempfile.TemporaryDirectory(prefix="openemr-study-")
    with zipfile.ZipFile(HERE / "evidence" / "study-results.zip") as saved:
        saved.extractall(TEMP.name)
    SOURCE = pathlib.Path(TEMP.name) / "study-results"
FOLLOW = SOURCE / "followup_haiku_prompt_fullset"
assert SOURCE.is_dir() and FOLLOW.is_dir()


def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def read_csv(path):
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def fenced(value):
    longest = max((len(m.group(0)) for m in re.finditer(r"`+", value)), default=0)
    fence = "`" * max(4, longest + 1)
    return f"{fence}text\n{value.rstrip()}\n{fence}"


def sha(data):
    return hashlib.sha256(data).hexdigest()


ORIGINAL_FILES = [
    "README.md", "METHODS.md", "prompt.md", "rubric.md", "scores.csv", "numbers.md",
    "compare.txt", "cves.csv", "models.csv", "validity.csv", "run_status.csv",
    "fix_dates.csv", "scoring_key.json", "recompute.py", "HYPOTHESES-AND-INSIGHTS.md",
    "benign_controls/benign_scores.csv", "pr_review/pr_reviews.csv",
    "ai_trailer_trace/findings.csv",
]
for rel in ORIGINAL_FILES:
    copy(SOURCE / rel, HERE / "data" / "original" / rel)
for path in sorted((SOURCE / "diffs").glob("*.diff")):
    copy(path, HERE / "data" / "original" / "diffs" / path.name)
for path in sorted((SOURCE / "benign_controls").glob("BENIGN-*.diff")):
    copy(path, HERE / "data" / "original" / "benign_controls" / path.name)
for folder in ("followup_ai_assisted", "followup_policy_prompt", "followup_security_prompt", "followup_expanded_context"):
    base = SOURCE / folder
    copy(base / "README.md", HERE / "data" / "prior-followups" / folder / "README.md")
    for name in ("final_scores.csv", "final_detection.csv", "benign_summary.csv"):
        path = base / name
        if path.exists(): copy(path, HERE / "data" / "prior-followups" / folder / name)

for name in ("case_scores.csv", "benign_scores.csv", "summary.json", "manifest.json",
             "controls_manifest.json", "truth.json", "audit_notes.md"):
    copy(FOLLOW / name, HERE / "data" / "prompt-followup" / name)
for path in sorted((FOLLOW / "prompts").glob("*.txt")):
    copy(path, HERE / "prompts" / path.name)
for path in sorted((FOLLOW / "inputs").glob("*.diff")):
    copy(path, HERE / "inputs" / path.name)

original_scores = {(r["cve_id"], r["model_slug"]): r for r in read_csv(SOURCE / "scores.csv")}
case_rows = read_csv(FOLLOW / "case_scores.csv")
cves = {r["cve_id"]: r for r in read_csv(SOURCE / "cves.csv")}
matrix = []
for row in case_rows:
    cve = row["cve_id"]
    matrix.append({
        "case_id": cve, "item": row["item"], "group": cves[cve]["group"],
        "owasp": cves[cve]["owasp"], "vulnerability": cves[cve]["vuln_type"],
        "historical_haiku": original_scores[(cve, "haiku-4-5")]["final_score"],
        "historical_sonnet": original_scores[(cve, "sonnet-5")]["final_score"],
        "new_haiku_generic": row["generic_final"],
        "new_haiku_security_touched": row["security_policy_final"],
        "change": row["change"],
        "generic_runs": row["generic_runs"], "security_touched_runs": row["security_policy_runs"],
    })
write_csv(HERE / "data" / "case-matrix.csv", matrix)
audit_path = HERE / "data" / "prompt-followup" / "audit_notes.md"
audit = audit_path.read_text().replace("(human_packet/README.md)", "(../../evidence/study-results.zip)")
item_to_cve = {r["item"]: r["cve_id"] for r in case_rows}
audit = re.sub(r"\]\((?:runs|judge)/[^)]*/(item_\d+)_run\d+\.md\)",
               lambda match: f"](../../cases/{item_to_cve[match.group(1)]}.md)", audit)
audit_path.write_text(audit)


def case_page(row):
    item, cve = row["item"], row["cve_id"]
    hist_h = original_scores[(cve, "haiku-4-5")]
    hist_s = original_scores[(cve, "sonnet-5")]
    lines = [f"# {cve}", "", "**Status:** New scores are model-judged and await independent human verification.", "",
             f"**Class:** {cves[cve]['vuln_type']} ({cves[cve]['owasp']}); **cohort:** {cves[cve]['group']}.", "",
             f"**Input:** [{item}.diff](../inputs/{item}.diff). The same bytes were supplied in both new prompt arms.", "",
             "| Setup | Run labels | Case score |", "|---|---|---|",
             f"| Historical Haiku, generic | {hist_h['run1']}/{hist_h['run2']}/{hist_h['run3']} | {hist_h['final_score']} |",
             f"| Historical Sonnet, generic | {hist_s['run1']}/{hist_s['run2']}/{hist_s['run3']} | {hist_s['final_score']} |",
             f"| New Haiku, generic | {row['generic_runs']} | {row['generic_final']} |",
             f"| New Haiku, security plus touched code | {row['security_policy_runs']} | {row['security_policy_final']} |", "",
             "The historical review text is in the full archive. The six new raw reviews and judge rationales follow. "
             "The archive also contains each exact API request and response.", ""]
    for arm, label in (("generic", "Generic"), ("security_policy", "Security plus touched code")):
        lines += [f"## {label}", ""]
        for run in (1, 2, 3):
            stem = f"{item}_run{run}"
            review = (FOLLOW / "runs" / arm / f"{stem}.md").read_text()
            judge = (FOLLOW / "judge" / "detect" / arm / f"{stem}.md").read_text()
            meta = json.loads((FOLLOW / "runs" / arm / f"{stem}.meta.json").read_text())
            score = json.loads((FOLLOW / "judge" / "detect" / arm / f"{stem}.meta.json").read_text())
            lines += [f"### Run {run}: {score['label']}", "",
                      f"Reviewer response `{meta['response_id']}`; latency {meta['latency_seconds']} s; "
                      f"tokens {meta['usage']['input_tokens']} input / {meta['usage']['output_tokens']} output.", "",
                      "**Raw review**", "", fenced(review), "", "**Judge rationale**", "", fenced(judge), ""]
    return "\n".join(lines)


(HERE / "cases").mkdir(exist_ok=True)
for row in case_rows:
    (HERE / "cases" / f"{row['cve_id']}.md").write_text(case_page(row))

controls = read_csv(FOLLOW / "benign_scores.csv")
def control_page(item):
    rows = [r for r in controls if r["item"] == item]
    lines = [f"# {item}: benign control", "", "**Status:** Model-judged; independent human verification pending.", "",
             f"**Input:** [{item}.diff](../inputs/{item}.diff). Each arm has three fresh reviews.", "",
             "| Prompt | Reviews with false security alarm | Security findings | Speculative questions | Correctness warnings |", "|---|---:|---:|---:|---:|"]
    for arm, label in (("generic", "Generic"), ("security_policy", "Security plus touched code")):
        group = [r for r in rows if r["arm"] == arm]
        lines.append(f"| {label} | {sum(int(r['false']) > 0 for r in group)}/3 | {sum(int(r['findings']) for r in group)} | "
                     f"{sum(int(r['speculative']) for r in group)} | {sum(int(r['correctness']) for r in group)} |")
    lines += ["", "The raw reviews and judge classifications follow. Exact requests and responses are in the full archive.", ""]
    for arm, label in (("generic", "Generic"), ("security_policy", "Security plus touched code")):
        lines += [f"## {label}", ""]
        for run in (1, 2, 3):
            stem = f"{item}_run{run}"
            review = (FOLLOW / "runs" / arm / f"{stem}.md").read_text()
            judge = (FOLLOW / "judge" / "benign" / arm / f"{stem}.md").read_text()
            score = json.loads((FOLLOW / "judge" / "benign" / arm / f"{stem}.meta.json").read_text())
            lines += [f"### Run {run}: {score['false']} false findings", "", "**Raw review**", "", fenced(review), "",
                      "**Judge classifications**", "", fenced(judge), ""]
    return "\n".join(lines)


(HERE / "controls").mkdir(exist_ok=True)
for number in range(1, 11):
    item = f"BENIGN-{number:02d}"
    (HERE / "controls" / f"{item}.md").write_text(control_page(item))

summary = json.loads((FOLLOW / "summary.json").read_text())
generic = summary["generic"]
strong = summary["security_policy"]
report = ["# Results", "", "All new scores are model-judged and await independent human verification. Historical scores and new direct API scores are distinct experiments.", "",
          "## Caught, Partial and Missed", "",
          "| Reviewer setup | Caught | Partial | Missed |", "|---|---:|---:|---:|",
          "| Historical Haiku 4.5, generic | 8/24 | 7/24 | 9/24 |",
          "| New Haiku 4.5, generic | 11/24 | 11/24 | 2/24 |",
          "| New Haiku 4.5, security plus touched code | **19/24** | 4/24 | 1/24 |",
          "| Historical Sonnet 5, generic | 20/24 | 3/24 | 1/24 |", "",
          "Against the new generic baseline, the stronger prompt gained eight Caught cases, retained eleven and lost none. It approached Sonnet's historical Caught total by one case. No current Sonnet comparison was run. The 19 stronger-prompt catches were Caught in all three runs each.", "",
          "## Case-by-case comparison", "",
          "| Case | Historical Haiku | Historical Sonnet | New generic Haiku | New stronger-prompt Haiku | Caught change | Evidence |",
          "|---|---|---|---|---|---|---|"]
for row in matrix:
    report.append(f"| {row['case_id']} | {row['historical_haiku']} | {row['historical_sonnet']} | "
                  f"{row['new_haiku_generic']} | {row['new_haiku_security_touched']} | {row['change']} | "
                  f"[six reviews and judge reasons](cases/{row['case_id']}.md) |")
report += ["", "Run-level labels are in [case-matrix.csv](data/case-matrix.csv). Each case page contains the full text of all six new reviews and judge rationales. The complete archive holds exact request and response JSON.", "",
           "## Ten benign controls", "",
           "Each cell below uses three independent reviews of that control. A false-alarm review has at least one unsupported security claim; speculative questions and ordinary correctness warnings are not counted as false security alarms.", "",
           "| Control | Generic false-alarm reviews | Stronger-prompt false-alarm reviews | Generic security findings | Stronger-prompt security findings | Evidence |",
           "|---|---:|---:|---:|---:|---|"]
for number in range(1, 11):
    item = f"BENIGN-{number:02d}"
    a = [r for r in controls if r["item"] == item and r["arm"] == "generic"]
    b = [r for r in controls if r["item"] == item and r["arm"] == "security_policy"]
    report.append(f"| {item} | {sum(int(r['false']) > 0 for r in a)}/3 | {sum(int(r['false']) > 0 for r in b)}/3 | "
                  f"{sum(int(r['findings']) for r in a)} | {sum(int(r['findings']) for r in b)} | [six reviews](controls/{item}.md) |")
report += ["", "| Measure across ten controls | Generic | Stronger prompt |", "|---|---:|---:|",
           "| Reviews with a false security alarm | 8/30 | 24/30 |",
           "| Reviews with a Medium-or-higher false alarm | 8/30 | 24/30 |",
           "| Unsupported security findings | 8 | 56 |",
           "| Speculative security questions | 4 | 26 |",
           "| Plausible security observations | 0 | 9 |",
           "| Correctness or reliability warnings | 34 | 1 |",
           "| Maintainability or style warnings | 27 | 2 |",
           "| All security findings | 12 | 91 |", "",
           "**Asserted severity of unsupported findings:** generic: 3 High and 5 Medium. Stronger prompt: 3 Critical, 13 High, 29 Medium, 10 Low and 1 without a substantive severity. These classifications await human review. Individual findings and severity are in [benign_scores.csv](data/prompt-followup/benign_scores.csv) and the control pages.", "",
           "## Run variability, latency and cost", "",
           "| Prompt | Cases Caught in 0/1/2/3 runs | Mixed-label cases | Caught/Partial/Missed reviews | Median CVE latency | P95 CVE latency | Median control latency | Reviewer cost | Judge cost |",
           "|---|---|---:|---|---:|---:|---:|---:|---:|"]
for arm, label in (("generic", "Generic"), ("security_policy", "Security plus touched code")):
    value = summary[arm]
    freq = value["catch_frequencies"]
    runs = value["run_labels"]
    usage = value["review_usage"]
    judge = value["judge_usage"]
    report.append(f"| {label} | {freq['0']}/{freq['1']}/{freq['2']}/{freq['3']} of 24 | {value['split_cases']}/24 | "
                  f"{runs['Caught']}/{runs['Partial']}/{runs['Missed']} of 72 | "
                  f"{usage['case_latency_median_seconds']} s | {usage['case_latency_p95_seconds']} s | "
                  f"{usage['control_latency_median_seconds']} s | ${usage['cost_usd']:.4f} | ${judge['cost_usd']:.4f} |")
report += ["", "Costs use actual input and output token counts for 72 case reviews plus 30 control reviews per arm, and separate Fable 5.1 judging. Estimates use [Anthropic standard list prices](https://platform.claude.com/docs/en/about-claude/pricing) on 2026-10-23. No call failed or required a retry. Human review cost is excluded.", "",
           "## Interpretation and limits", "",
           "- Better instructions substantially improved Haiku detection on this fixed set, and greatly increased false alarms and review volume on benign changes.",
           "- The new generic arm scored 11/24, rather than the original Haiku 8/24. The original Claude Code request and tool history is incomplete, so the new direct API arm is a fresh baseline, not an exact reconstruction.",
           "- The historical Sonnet 20/24 was not rerun with the new prompts and settings. A one-case difference in totals does not establish equivalence; a current model comparison would need matched Sonnet runs and a prespecified equivalence criterion.",
           "- The 24 CVEs were selected retrospectively and mostly use vulnerable-file diffs. Several flaws depend on other files that were deliberately not supplied in this prompt-only test. The ten controls are a small, selected set.",
           "- The new case and control labels come from one separate model judge. The judge did not receive explicit arm identity, but review wording could reveal it. Independent human verification of changed, split and false-alarm decisions is pending. See [audit notes](data/prompt-followup/audit_notes.md) and the blinded packet in the archive.", ""]
(HERE / "RESULTS.md").write_text("\n".join(report))

# Preserve the complete source tree in one downloadable file. Archive members use
# their historical paths so an extracted copy can replay the old documentation.
archive = HERE / "evidence" / "study-results.zip"
archive.parent.mkdir(exist_ok=True)
archive_tmp = archive.with_suffix(".zip.tmp")
archive_rows = []
with zipfile.ZipFile(archive_tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
    for path in sorted(p for p in SOURCE.rglob("*") if p.is_file()):
        if path.name == ".DS_Store" or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        data = path.read_bytes()
        rel = "study-results/" + path.relative_to(SOURCE).as_posix()
        bundle.writestr(rel, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        archive_rows.append({"path": rel, "bytes": len(data), "sha256": sha(data)})
archive_tmp.replace(archive)
write_csv(HERE / "evidence" / "archive-manifest.csv", archive_rows)
(HERE / "evidence" / "SHA256.txt").write_text(f"{sha(archive.read_bytes())}  study-results.zip\n")
print(f"Built {len(case_rows)} case pages, 10 control pages and archive of {len(archive_rows)} source files")
if TEMP: TEMP.cleanup()
