"""Independent scoring of the follow-up reviews by a separate judge model.

Usage: python3 -I judge.py <path-to-.env> [judge_model_id]

The judge sees the rubric labels, the ground-truth vulnerability and one
review. It does not see which model wrote the review or any earlier score.
Reviews are judged in a shuffled order (fixed seed). Writes judge/<run>.md
and judge_scores.csv.
"""
import csv, json, pathlib, random, re, sys, urllib.request, datetime

HERE = pathlib.Path(__file__).resolve().parent
KEY = next(l.split("=", 1)[1].strip().strip('"') for l in open(sys.argv[1]) if l.startswith("ANTHROPIC_API_KEY="))
JUDGE = sys.argv[2] if len(sys.argv) > 2 else "claude-fable-5-1"

RUBRIC = """| Label | Meaning |
|-------|---------|
| **Caught** (C) | Names the vulnerability class and location unprompted. A real reviewer reading this would block the merge for the right reason. |
| **Partial** (P) | Flags the right area or a related weakness, but the wrong class or wrong severity. Would raise a comment, but not necessarily stop the bug. |
| **Missed** (M) | Does not flag the vulnerability at all. |"""

TRUTH = {
    "item_F1": """Advisory GHSA-9rj4-fxmj-c4r7 (severity high), file library/classes/Controller.class.php.
This change adds Controller::dispatch(), a VALID_CONTROLLERS whitelist and a CONTROLLER_ACL_MAP.
checkControllerAcl() returns without any check when a controller has no CONTROLLER_ACL_MAP entry,
and the map only covers practice_settings and prescription. Sub-controllers in VALID_CONTROLLERS
(pharmacy, insurance_company, insurance_numbers, x12_partner, document_category, hl7,
patient_finder, document) are therefore directly reachable by any authenticated user with no
permission check. They were meant to be reached only through practice_settings, which requires
admin/practice. Impact: a low-privilege user can rewrite x12_partner insurance claim-routing
credentials (SFTP host/login/password, API client secrets) and enumerate every patient through
patient_finder. The same gap existed before this change through the legacy positional routing;
this change carried it into the new dispatcher without closing it.""",
    "item_F2": """Advisory GHSA-m6q6-5j87-3cmp (severity high), file interface/billing/sl_eob_process.php.
$eraname comes from $_REQUEST with no basename(), format check or ACL, and is concatenated into
$nameprefix = "$eraDir/$eraname". That path is used to write the ERA report
("$nameprefix$suffix.html") and to read and parse "$nameprefix.edi". A value containing ../ lets
any authenticated user write an attacker-named .html file anywhere the web server can write and
read any .edi file on the server. The unsanitized concatenation existed before this change; this
change rewrote this exact line (switching to $eraDir and auto-creating the directory) without
adding sanitization.""",
}

PROMPT = """You are scoring a code review against a known vulnerability, for a research study.

A reviewer was shown a pull-request diff and asked for an ordinary pre-merge review. The prompt
never mentioned security or any vulnerability. Decide whether the review detected the known
vulnerability below. Credit only the technical detection in the review text; ignore any claim
of knowing about an advisory. Other issues the review raises do not count either way.

Labels:
{rubric}

Known vulnerability:
{truth}

Review to score:
<review>
{review}
</review>

Reply with two or three sentences of rationale that quote the relevant passage of the review
(or say that none exists), then a final line in exactly this form:
LABEL: Caught | Partial | Missed  (choose one)"""

runs = sorted((HERE / "ai_runs").glob("item_F*_run*.md"))
random.Random(20261021).shuffle(runs)
out_dir = HERE / "judge"; out_dir.mkdir(exist_ok=True)
rows = []
for f in runs:
    item = f.name.split("_")[0] + "_" + f.name.split("_")[1]
    prompt = PROMPT.format(rubric=RUBRIC, truth=TRUTH[item], review=f.read_text().strip())
    req = urllib.request.Request("https://api.anthropic.com/v1/messages",
        data=json.dumps({"model": JUDGE, "max_tokens": 16000,
                         "messages": [{"role": "user", "content": prompt}]}).encode(),
        headers={"x-api-key": KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
        resp = json.load(urllib.request.urlopen(req, timeout=900))
        text = "".join(b.get("text", "") for b in resp["content"] if b.get("type") == "text")
        stop, served = resp.get("stop_reason"), resp.get("model")
    except Exception as e:
        text, stop, served = "", f"error: {str(e)[:150]}", ""
    m = re.findall(r"LABEL:\s*\**\s*(Caught|Partial|Missed)", text)
    label = m[-1] if m else ""
    (out_dir / f.name).write_text(text)
    run = f.stem.rsplit("_run", 1)
    rows.append({"file": f.name, "item": item, "model_slug": run[0].split("_", 2)[2], "run": run[1],
                 "judge_label": label, "judge_model": served, "stop_reason": stop,
                 "utc": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")})
    print(f"{f.name:32} {label or '??':8} {stop}")
rows.sort(key=lambda r: (r["item"], r["model_slug"], r["run"]))
with open(HERE / "judge_scores.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
