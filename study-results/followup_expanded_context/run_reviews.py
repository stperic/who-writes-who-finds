"""Step 4: does giving the reviewer the dependent file fix the cross-file misses?

Usage: python3 -I run_reviews.py <path-to-.env>

Arms (prompt x input):
  frozen_diff     ../prompt.md, diff only                (C1-C4; F1 exists in ../followup_ai_assisted)
  frozen_context  ../prompt.md, diff + dependent file    (C1-C4, F1)
  secpol_diff     security + touched-code prompt, diff   (C1-C4; F1 exists in ../followup_security_prompt)
  secpol_context  security + touched-code prompt, diff + dependent file (C1-C4, F1)

Inputs: diffs/item_*.diff (neutral names; the study's blinded diffs) and
context/<item>/<path> (the dependent file as of the introducing commit, see
context/SOURCES.tsv). 3 runs per model per item, all five models.

Every call stores runs/<arm>/<name>.prompt.txt (exact prompt sent),
<name>.response.json (full raw API response) and <name>.md (review text), and
appends to review_status.json. Existing non-empty outputs are skipped.
"""
import json, pathlib, re, sys, time, urllib.error, urllib.request, datetime
from concurrent.futures import ThreadPoolExecutor

HERE = pathlib.Path(__file__).resolve().parent
STUDY = HERE.parent
KEY = next(l.split("=", 1)[1].strip().strip('"') for l in open(sys.argv[1]) if l.startswith("ANTHROPIC_API_KEY="))
FROZEN = re.search(r"```\n(You are reviewing.*?\{diff\}\n```)\n```", (STUDY / "prompt.md").read_text(), re.S).group(1)
sec_src = (STUDY / "followup_security_prompt" / "run_reviews.py").read_text()
ns = {}
exec(sec_src[sec_src.index("SECURITY = "):sec_src.index('PROMPTS = {"security"')], ns)
SECPOL = ns["SEC_POLICY"]
CONTEXT_INTRO = ("\n\nFor context, these related files from the repository at the same commit are "
                 "included below. They are not changed by this pull request.")
MODELS = {"sonnet-5": "claude-sonnet-5", "haiku-4-5": "claude-haiku-4-5-20251001",
          "sonnet-5-5": "claude-sonnet-5-5", "opus-5-5": "claude-opus-5-5", "haiku-5-5": "claude-haiku-5-5"}
MAX_TOKENS = 16000

def context_block(item):
    files = sorted(p for p in (HERE / "context" / item).rglob("*") if p.is_file())
    return CONTEXT_INTRO + "".join(
        f'\n\n<file path="{p.relative_to(HERE / "context" / item)}">\n{p.read_text(errors="replace").rstrip()}\n</file>' for p in files)

def build(arm, item):
    base = FROZEN if arm.startswith("frozen") else SECPOL
    prompt = base.replace("{diff}", (HERE / "diffs" / f"{item}.diff").read_text().rstrip("\n"))
    return prompt + context_block(item) if arm.endswith("context") else prompt

jobs = []
for item in ("item_C1", "item_C2", "item_C3", "item_C4", "item_F1"):
    for arm in ("frozen_diff", "frozen_context", "secpol_diff", "secpol_context"):
        if item == "item_F1" and arm.endswith("diff"):
            continue  # already run in the earlier follow-ups
        for slug, mid in MODELS.items():
            for run in (1, 2, 3):
                jobs.append((arm, item, slug, mid, run))

def call(job):
    arm, item, slug, mid, run = job
    d = HERE / "runs" / arm; d.mkdir(parents=True, exist_ok=True)
    name = f"{item}_{slug}_run{run}"
    out = d / f"{name}.md"
    if out.exists() and out.read_text().strip():
        return None
    prompt = build(arm, item)
    (d / f"{name}.prompt.txt").write_text(prompt)
    body = json.dumps({"model": mid, "max_tokens": MAX_TOKENS, "messages": [{"role": "user", "content": prompt}]}).encode()
    resp, err = None, None
    for attempt in range(6):
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body,
            headers={"x-api-key": KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        try:
            resp = json.load(urllib.request.urlopen(req, timeout=900)); break
        except urllib.error.HTTPError as e:
            err = f"HTTP {e.code}: {e.read()[:300].decode(errors='replace')}"
            if e.code in (429, 500, 502, 503, 529) and attempt < 5: time.sleep(min(120, 10 * 2 ** attempt)); continue
            break
        except Exception as e:
            err = str(e)[:200]
            if attempt < 5: time.sleep(15); continue
    rec = {"file": f"runs/{arm}/{name}.md", "arm": arm, "item": item, "model_slug": slug, "run": run,
           "requested_model": mid, "max_tokens": MAX_TOKENS,
           "utc": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")}
    if resp is None:
        (d / f"{name}.response.json").write_text(json.dumps({"error": err}, indent=1))
        out.write_text("")
        return {**rec, "status": f"error {err}"}
    (d / f"{name}.response.json").write_text(json.dumps(resp, indent=1))
    text = "".join(b.get("text", "") for b in resp["content"] if b.get("type") == "text")
    out.write_text(text)
    return {**rec, "status": "ok" if text.strip() else "empty", "served_model": resp.get("model"),
            "response_id": resp.get("id"), "stop_reason": resp.get("stop_reason"), "usage": resp.get("usage")}

status_path = HERE / "review_status.json"
status = json.loads(status_path.read_text()) if status_path.exists() else []
with ThreadPoolExecutor(max_workers=6) as pool:
    for res in pool.map(call, jobs):
        if res:
            status.append(res)
            print(res["file"], res["status"][:60], res.get("stop_reason"), (res.get("usage") or {}).get("input_tokens"),
                  (res.get("usage") or {}).get("output_tokens"), flush=True)
            status_path.write_text(json.dumps(status, indent=1))
print("jobs:", len(jobs))
