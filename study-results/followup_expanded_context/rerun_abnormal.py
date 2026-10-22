"""Step 4: rerun the six reviews that did not end normally (see RESUME.md).

Usage: python3 -I rerun_abnormal.py <path-to-.env>

The first attempt of each is kept, renamed with an `.attempt1` suffix after the
extension (so judge_reviews.py, which globs runs/**/*.md, does not judge it).
Truncated runs (max_tokens) are rerun with max_tokens 32000; the two cyber
refusals are rerun once with the same request (max_tokens 16000). The prompt
is the exact prompt of the first attempt. Calls stream, so each rerun stores
the raw event stream (<name>.response.sse.txt) plus the message rebuilt from
it (<name>.response.json) and the review text (<name>.md). Records are
appended to review_status.json with "attempt": 2; execution_errors.csv lists
every abnormal first attempt and what its rerun returned.
"""
import csv, json, pathlib, sys, time, urllib.error, urllib.request, datetime
from concurrent.futures import ThreadPoolExecutor

HERE = pathlib.Path(__file__).resolve().parent
KEY = next(l.split("=", 1)[1].strip().strip('"') for l in open(sys.argv[1]) if l.startswith("ANTHROPIC_API_KEY="))
RERUNS = [  # (run, first-attempt stop_reason, max_tokens for the rerun)
    ("runs/secpol_context/item_C1_opus-5-5_run2", "refusal", 16000),
    ("runs/secpol_diff/item_C4_opus-5-5_run2", "refusal", 16000),
    ("runs/frozen_context/item_F1_sonnet-5_run2", "max_tokens", 32000),
    ("runs/frozen_context/item_F1_sonnet-5_run3", "max_tokens", 32000),
    ("runs/frozen_diff/item_C4_sonnet-5_run2", "max_tokens", 32000),
    ("runs/secpol_context/item_C4_haiku-5-5_run1", "max_tokens", 32000),
]
SUFFIXES = (".md", ".prompt.txt", ".response.json")

def keep_first_attempt(base):
    for s in SUFFIXES:
        src, dst = base.with_name(base.name + s), base.with_name(base.name + s + ".attempt1")
        if src.exists() and not dst.exists():
            src.rename(dst)

def rebuild(events):
    """Rebuild the final message from streamed events."""
    msg, blocks = None, {}
    for ev in events:
        t = ev.get("type")
        if t == "message_start":
            msg = ev["message"]
        elif t == "content_block_start":
            blocks[ev["index"]] = dict(ev["content_block"])
        elif t == "content_block_delta":
            b, d = blocks[ev["index"]], ev["delta"]
            for k in ("text", "thinking", "signature", "partial_json"):
                if k in d:
                    b[k] = b.get(k, "") + d[k]
        elif t == "message_delta":
            msg.update(ev.get("delta") or {})
            msg["usage"] = {**(msg.get("usage") or {}), **(ev.get("usage") or {})}
    if msg is not None:
        msg["content"] = [blocks[i] for i in sorted(blocks)]
    return msg

def stream(body):
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body,
        headers={"x-api-key": KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    raw, events = [], []
    with urllib.request.urlopen(req, timeout=900) as r:
        for line in r:
            line = line.decode()
            raw.append(line)
            if line.startswith("data:"):
                events.append(json.loads(line[5:]))
    return "".join(raw), events

def call(spec):
    rel, first_stop, max_tokens = spec
    base = HERE / rel
    first = json.loads(base.with_name(base.name + ".response.json.attempt1").read_text())
    prompt = base.with_name(base.name + ".prompt.txt.attempt1").read_text()
    out = base.with_name(base.name + ".md")
    if out.exists() and out.read_text().strip():
        return None
    base.with_name(base.name + ".prompt.txt").write_text(prompt)
    mid = first["model"]
    body = json.dumps({"model": mid, "max_tokens": max_tokens, "stream": True,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    raw, events, err = "", [], None
    for attempt in range(6):
        try:
            raw, events = stream(body)
            errors = [e for e in events if e.get("type") == "error"]
            err = json.dumps(errors[0])[:300] if errors else None
            if errors and attempt < 5: time.sleep(30); continue
            break
        except urllib.error.HTTPError as e:
            err = f"HTTP {e.code}: {e.read()[:300].decode(errors='replace')}"
            if e.code in (429, 500, 502, 503, 529) and attempt < 5: time.sleep(min(120, 10 * 2 ** attempt)); continue
            break
        except Exception as e:
            err = str(e)[:300]
            if attempt < 5: time.sleep(15); continue
    parts = base.name.split("_", 2)
    slug, run = parts[2].rsplit("_run", 1)
    rec = {"file": f"{rel}.md", "arm": base.parent.name, "item": "_".join(parts[:2]), "model_slug": slug, "run": int(run),
           "requested_model": mid, "max_tokens": max_tokens, "attempt": 2, "rerun_of": first.get("id"),
           "utc": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")}
    base.with_name(base.name + ".response.sse.txt").write_text(raw)
    resp = rebuild(events) if err is None else None
    if resp is None:
        base.with_name(base.name + ".response.json").write_text(json.dumps({"error": err or "no message in stream"}, indent=1))
        out.write_text("")
        return {**rec, "status": f"error {err}"}, first, first_stop
    base.with_name(base.name + ".response.json").write_text(json.dumps(resp, indent=1))
    text = "".join(b.get("text", "") for b in resp["content"] if b.get("type") == "text")
    out.write_text(text)
    return ({**rec, "status": "ok" if text.strip() else "empty", "served_model": resp.get("model"),
             "response_id": resp.get("id"), "stop_reason": resp.get("stop_reason"), "usage": resp.get("usage")},
            first, first_stop)

for rel, _, _ in RERUNS:
    keep_first_attempt(HERE / rel)
status_path = HERE / "review_status.json"
status = json.loads(status_path.read_text())
errors_path = HERE / "execution_errors.csv"
rows = list(csv.DictReader(open(errors_path))) if errors_path.exists() else []
with ThreadPoolExecutor(max_workers=6) as pool:
    for res in pool.map(call, RERUNS):
        if not res:
            continue
        rec, first, first_stop = res
        status.append(rec)
        status_path.write_text(json.dumps(status, indent=1))
        fu = first.get("usage") or {}
        ru = rec.get("usage") or {}
        rows.append({"file": rec["file"], "attempt1_response_id": first.get("id"), "attempt1_stop_reason": first_stop,
                     "attempt1_max_tokens": 16000, "attempt1_output_tokens": fu.get("output_tokens"),
                     "attempt1_thinking_tokens": (fu.get("output_tokens_details") or {}).get("thinking_tokens"),
                     "attempt1_refusal_category": (first.get("stop_details") or {}).get("category", ""),
                     "attempt2_response_id": rec.get("response_id"), "attempt2_status": rec["status"][:80],
                     "attempt2_stop_reason": rec.get("stop_reason"), "attempt2_max_tokens": rec["max_tokens"],
                     "attempt2_output_tokens": ru.get("output_tokens"),
                     "attempt2_thinking_tokens": (ru.get("output_tokens_details") or {}).get("thinking_tokens"),
                     "attempt2_utc": rec["utc"]})
        print(rec["file"], rec["status"][:60], rec.get("stop_reason"), ru.get("input_tokens"), ru.get("output_tokens"), flush=True)
rows.sort(key=lambda r: r["file"])
with open(errors_path, "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
print("reruns:", len(RERUNS))
