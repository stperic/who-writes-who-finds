"""Review runs for the security-prompt follow-up.

Usage: python3 -I run_reviews.py <path-to-.env>

Arms:
  security         a short OWASP Top 10 security-review prompt
  security_policy  the same plus the 'flaws in touched code count' sentence

Diffs: F1/F2 from ../followup_ai_assisted/diffs (3 runs each) and the 10
benign controls from ../benign_controls (1 run each, as in the study).
Outputs go to reviews/<arm>/, call metadata to review_status.json. Existing
non-empty outputs are skipped, so the script can be re-run after failures.
"""
import json, pathlib, re, sys, time, urllib.error, urllib.request, datetime
from concurrent.futures import ThreadPoolExecutor

HERE = pathlib.Path(__file__).resolve().parent
STUDY = HERE.parent
KEY = next(l.split("=", 1)[1].strip().strip('"') for l in open(sys.argv[1]) if l.startswith("ANTHROPIC_API_KEY="))
FROZEN = re.search(r"```\n(You are reviewing.*?\{diff\}\n```)\n```", (STUDY / "prompt.md").read_text(), re.S).group(1)
POLICY_SENTENCE = ("Also report security flaws in code that this change touches or relies on, even if\n"
                   "they existed before this change. ")
assert FROZEN.count("If you find no issues, say so.") == 1
POLICY = FROZEN.replace("If you find no issues, say so.", POLICY_SENTENCE + "If you find no issues, say so.")
SECURITY = """You are a security engineer reviewing a pull request diff before it is merged.
Review the code below for security vulnerabilities, using the OWASP Top 10 (2021) as a checklist:
broken access control, cryptographic failures, injection (including SQL injection and XSS),
insecure design, security misconfiguration, vulnerable and outdated components, identification
and authentication failures, software and data integrity failures, security logging and
monitoring failures, and server-side request forgery. For each issue, give the location, the
OWASP category, the problem, and the severity. If you find no security issues, say so.

```
{diff}
```"""
SEC_POLICY = SECURITY.replace("If you find no security issues, say so.",
    "Also report security flaws in code that this change touches or relies on, even if\nthey existed before this change. If you find no security issues, say so.")
assert SEC_POLICY != SECURITY
PROMPTS = {"security": SECURITY, "security_policy": SEC_POLICY}
ALL = {"sonnet-5": "claude-sonnet-5", "haiku-4-5": "claude-haiku-4-5-20251001",
       "sonnet-5-5": "claude-sonnet-5-5", "opus-5-5": "claude-opus-5-5", "haiku-5-5": "claude-haiku-5-5"}
NEW = {k: v for k, v in ALL.items() if k.endswith("5-5")}
MAX_TOKENS = 16000

items = sorted((STUDY / "followup_ai_assisted" / "diffs").glob("item_F*.diff"))
benign = sorted((STUDY / "benign_controls").glob("BENIGN-*.diff"))
jobs = []
for arm in ("security", "security_policy"):
    for d in items:
        for slug, mid in ALL.items():
            for run in (1, 2, 3): jobs.append((arm, d, slug, mid, run))
    for d in benign:
        for slug, mid in ALL.items(): jobs.append((arm, d, slug, mid, 1))

def call(job):
    arm, diff, slug, mid, run = job
    out = HERE / "reviews" / arm / f"{diff.stem}_{slug}_run{run}.md"
    if out.exists() and out.read_text().strip():
        return None
    prompt = PROMPTS[arm].replace("{diff}", diff.read_text().rstrip("\n"))
    body = json.dumps({"model": mid, "max_tokens": MAX_TOKENS, "messages": [{"role": "user", "content": prompt}]}).encode()
    for attempt in range(6):
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body,
            headers={"x-api-key": KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        try:
            resp = json.load(urllib.request.urlopen(req, timeout=900))
            break
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 529) and attempt < 5:
                time.sleep(min(120, 10 * 2 ** attempt)); continue
            return {"file": str(out.relative_to(HERE)), "status": f"error HTTP {e.code}", "requested_model": mid}
        except Exception as e:
            if attempt < 5: time.sleep(15); continue
            return {"file": str(out.relative_to(HERE)), "status": f"error {str(e)[:100]}", "requested_model": mid}
    text = "".join(b.get("text", "") for b in resp["content"] if b.get("type") == "text")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    return {"file": str(out.relative_to(HERE)), "status": "ok" if text.strip() else "empty",
            "requested_model": mid, "served_model": resp.get("model"), "stop_reason": resp.get("stop_reason"),
            "max_tokens": MAX_TOKENS, "usage": resp.get("usage"),
            "utc": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")}

status_path = HERE / "review_status.json"
status = json.loads(status_path.read_text()) if status_path.exists() else []
with ThreadPoolExecutor(max_workers=6) as pool:
    for res in pool.map(call, jobs):
        if res:
            status.append(res)
            print(res["file"], res["status"], res.get("stop_reason"), (res.get("usage") or {}).get("output_tokens"), flush=True)
            status_path.write_text(json.dumps(status, indent=1))
print("jobs:", len(jobs))
