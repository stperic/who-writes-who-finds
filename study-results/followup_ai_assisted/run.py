"""Run the study's frozen review prompt on the follow-up diffs.

Usage: python3 -I run.py <path-to-.env> <max_tokens> <slug>=<model_id> [<slug>=<model_id> ...]
Example: python3 -I run.py ../../.env 4096 sonnet-5=claude-sonnet-5 haiku-4-5=claude-haiku-4-5-20251001

Calls the Anthropic Messages API with default temperature and one fresh request
per run. quadrant.py uses max_tokens=4096. Results are appended to
run_status.json, so earlier runs are kept.
"""
import json, pathlib, re, sys, urllib.request, datetime

HERE = pathlib.Path(__file__).resolve().parent
KEY = next(l.split("=", 1)[1].strip().strip('"') for l in open(sys.argv[1]) if l.startswith("ANTHROPIC_API_KEY="))
MAX_TOKENS = int(sys.argv[2])
MODELS = dict(arg.split("=", 1) for arg in sys.argv[3:])
PROMPT = re.search(r"```\n(You are reviewing.*?\{diff\}\n```)\n```", (HERE.parent / "prompt.md").read_text(), re.S).group(1)
out_dir = HERE / "ai_runs"; out_dir.mkdir(exist_ok=True)
status_path = HERE / "run_status.json"
status = json.loads(status_path.read_text()) if status_path.exists() else []
for diff in sorted((HERE / "diffs").glob("item_*.diff")):
    prompt = PROMPT.replace("{diff}", diff.read_text().rstrip("\n"))
    for slug, model_id in MODELS.items():
        for run in (1, 2, 3):
            req = urllib.request.Request("https://api.anthropic.com/v1/messages",
                data=json.dumps({"model": model_id, "max_tokens": MAX_TOKENS,
                                 "messages": [{"role": "user", "content": prompt}]}).encode(),
                headers={"x-api-key": KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"})
            try:
                resp = json.load(urllib.request.urlopen(req, timeout=900))
                text = "".join(b.get("text", "") for b in resp["content"] if b.get("type") == "text")
                ok = "ok" if text.strip() else "empty"
                served, stop, usage = resp.get("model"), resp.get("stop_reason"), resp.get("usage")
            except Exception as e:
                text, ok, served, stop, usage = "", f"error: {str(e)[:120]}", "", "", None
            name = f"{diff.stem}_{slug}_run{run}.md"
            (out_dir / name).write_text(text)
            status.append({"file": name, "status": ok, "requested_model": model_id, "served_model": served,
                           "stop_reason": stop, "max_tokens": MAX_TOKENS, "usage": usage,
                           "utc": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")})
            print(name, ok, served, stop, len(text), "chars", (usage or {}).get("output_tokens"), "output tokens")
            status_path.write_text(json.dumps(status, indent=1))
