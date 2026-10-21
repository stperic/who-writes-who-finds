"""Judge the policy-prompt follow-up with Claude Fable 5.1.

Usage: python3 -I judge_reviews.py <path-to-.env>

- F1/F2 reviews (policy arm): the same judge prompt, rubric and ground truth
  as ../followup_ai_assisted/judge.py (read from that file, not copied).
- Benign reviews (both arms, all five models; the frozen arm for Sonnet 5 and
  Haiku 4.5 is the study's own reviews in ../benign_controls): the judge sees
  the diff and the review and classifies every security finding.
Reviewer identity and arm are never shown to the judge. Outputs go to
judge/, results to judge_detection.csv and judge_benign.csv. Existing judge
outputs are skipped on re-run.
"""
import ast, csv, json, pathlib, re, sys, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = pathlib.Path(__file__).resolve().parent
STUDY = HERE.parent
KEY = next(l.split("=", 1)[1].strip().strip('"') for l in open(sys.argv[1]) if l.startswith("ANTHROPIC_API_KEY="))
JUDGE = "claude-fable-5-1"

src = (STUDY / "followup_ai_assisted" / "judge.py").read_text()
consts = {n.targets[0].id: ast.literal_eval(n.value) for n in ast.parse(src).body
          if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and n.targets[0].id in ("RUBRIC", "TRUTH", "PROMPT")}
RUBRIC, TRUTH, DETECT_PROMPT = consts["RUBRIC"], consts["TRUTH"], consts["PROMPT"]

BENIGN_PROMPT = """You are checking a code review for false security alarms, for a research study.

A reviewer was shown the pull-request diff below and asked for a pre-merge review. The change
is not known to introduce any vulnerability. Some of these changes are security fixes.

List every security-related finding the review makes (ignore pure correctness, style or
maintainability points). Classify each one using only what the diff shows or what the finding
itself explains:
- FALSE: the claim is wrong, or asserts a vulnerability the code shown does not support.
- SPECULATIVE: a request to verify something that cannot be judged from the diff (for example
  a helper defined elsewhere), without asserting a vulnerability.
- PLAUSIBLE: a specific, credible security weakness in code this change touches or relies on.

<diff>
{diff}
</diff>

<review>
{review}
</review>

Write one line per finding in exactly this form:
FINDING | <ten words or fewer> | severity=<the review's severity, or none> | class=<FALSE|SPECULATIVE|PLAUSIBLE> | <one-sentence reason>
If there are no security findings, write: FINDING | none
End with exactly one line:
SUMMARY: findings=<n> false=<n> speculative=<n> plausible=<n>"""

def ask(prompt):
    body = json.dumps({"model": JUDGE, "max_tokens": 16000, "messages": [{"role": "user", "content": prompt}]}).encode()
    for attempt in range(6):
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body,
            headers={"x-api-key": KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        try:
            resp = json.load(urllib.request.urlopen(req, timeout=900))
            return "".join(b.get("text", "") for b in resp["content"] if b.get("type") == "text"), resp.get("stop_reason"), resp.get("usage")
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 529) and attempt < 5: time.sleep(min(120, 10 * 2 ** attempt)); continue
            return "", f"error HTTP {e.code}", None
        except Exception as e:
            if attempt < 5: time.sleep(15); continue
            return "", f"error {str(e)[:80]}", None

jobs = []
for f in sorted((HERE / "reviews" / "policy").glob("item_F*_run*.md")):
    item = "_".join(f.stem.split("_")[:2])
    jobs.append(("detect", "policy", f, DETECT_PROMPT.format(rubric=RUBRIC, truth=TRUTH[item], review=f.read_text().strip())))
benign_reviews = [("policy", f) for f in sorted((HERE / "reviews" / "policy").glob("BENIGN-*.md"))]
benign_reviews += [("frozen", f) for f in sorted((HERE / "reviews" / "frozen").glob("BENIGN-*.md"))]
benign_reviews += [("frozen", f) for f in sorted((STUDY / "benign_controls").glob("BENIGN-*_*.md"))]
for arm, f in benign_reviews:
    diff = (STUDY / "benign_controls" / (f.stem.split("_")[0] + ".diff")).read_text()
    jobs.append(("benign", arm, f, BENIGN_PROMPT.format(diff=diff.rstrip(), review=f.read_text().strip())))

def run(job):
    kind, arm, f, prompt = job
    out = HERE / "judge" / f"{arm}__{f.stem}.md"
    if out.exists() and out.read_text().strip():
        return kind, arm, f, out.read_text(), "cached", None
    text, stop, usage = ask(prompt)
    out.parent.mkdir(exist_ok=True); out.write_text(text)
    return kind, arm, f, text, stop, usage

detect_rows, benign_rows, usage_log = [], [], []
with ThreadPoolExecutor(max_workers=4) as pool:
    for kind, arm, f, text, stop, usage in pool.map(run, jobs):
        stem = f.stem
        if f.parent.name == "benign_controls":
            bid, slug = stem.split("_", 1); run_no = "1"
        else:
            parts = stem.rsplit("_run", 1); run_no = parts[1]
            bid, slug = (parts[0].split("_", 2)[0] + "_" + parts[0].split("_", 2)[1], parts[0].split("_", 2)[2]) if stem.startswith("item_") else parts[0].split("_", 1)
        if usage: usage_log.append(usage)
        if kind == "detect":
            m = re.findall(r"LABEL:\s*\**\s*(Caught|Partial|Missed)", text)
            detect_rows.append({"item": bid, "model_slug": slug, "run": run_no, "judge_label": m[-1] if m else "", "stop": stop})
        else:
            s = re.search(r"SUMMARY:\s*findings=(\d+)\s+false=(\d+)\s+speculative=(\d+)\s+plausible=(\d+)", text)
            false_med = sum(1 for l in text.splitlines() if l.startswith("FINDING") and "class=FALSE" in l
                            and re.search(r"severity=\s*(medium|high|critical)", l, re.I))
            benign_rows.append({"benign_id": bid, "model_slug": slug, "arm": arm,
                                "findings": s.group(1) if s else "", "false": s.group(2) if s else "",
                                "speculative": s.group(3) if s else "", "plausible": s.group(4) if s else "",
                                "false_medium_plus": false_med, "stop": stop})
        print(kind, arm, f.name, (detect_rows[-1]["judge_label"] if kind == "detect" else benign_rows[-1]["false"]), stop, flush=True)

for name, rows, key in (("judge_detection.csv", detect_rows, ("item", "model_slug", "run")),
                        ("judge_benign.csv", benign_rows, ("benign_id", "arm", "model_slug"))):
    rows.sort(key=lambda r: tuple(r[k] for k in key))
    with open(HERE / name, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
tot = {k: sum((u or {}).get(k, 0) for u in usage_log) for k in ("input_tokens", "output_tokens")}
print("judge calls:", len(usage_log), "tokens:", tot)
