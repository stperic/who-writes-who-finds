"""Build or rerun the six prompt-only PDF requirement reviews.

The historical input is read from the published study archive. API use requires
an explicit --execute flag and an ANTHROPIC_API_KEY environment variable.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import urllib.request
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
STUDY = HERE.parents[1]
ARCHIVE = STUDY / "evidence/study-results.zip"
BASELINE = (
    "study-results/followup_expanded_context/runs/secpol_diff/"
    "item_C4_sonnet-5_run1.prompt.txt"
)
MODEL = "claude-sonnet-5"
MAX_TOKENS = 32000


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def prompts() -> dict[tuple[str, int], str]:
    with ZipFile(ARCHIVE) as bundle:
        base = bundle.read(BASELINE).decode()
    result = {}
    for arm in ("functional", "security"):
        card = (HERE / "conditions" / f"{arm}.txt").read_text()
        for run in (1, 2, 3):
            result[(arm, run)] = base + card
    return result


def call(arm: str, run: int, prompt: str, key: str, output: Path) -> dict:
    run_root = output / arm
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / f"run{run}.prompt.txt").write_text(prompt)
    request = json.dumps({
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    api_request = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=request,
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )
    with urllib.request.urlopen(api_request, timeout=900) as response:
        raw = json.load(response)
    (run_root / f"run{run}.response.json").write_text(json.dumps(raw, indent=2))
    review = "".join(block.get("text", "") for block in raw.get("content", [])
                     if block.get("type") == "text")
    (run_root / f"run{run}.review.md").write_text(review)
    return {
        "arm": arm,
        "run": run,
        "model": raw.get("model"),
        "stop_reason": raw.get("stop_reason"),
        "prompt_sha256": sha(prompt.encode()),
        "review_sha256": sha(review.encode()),
        "usage": raw.get("usage"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="issue six paid API calls")
    parser.add_argument("--output", type=Path, default=Path("pdf-requirement-rerun"))
    args = parser.parse_args()
    built = prompts()
    if not args.execute:
        for (arm, run), prompt in built.items():
            print(arm, run, sha(prompt.encode()))
        return
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        parser.error("ANTHROPIC_API_KEY is required with --execute")
    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(call, arm, run, prompt, key, args.output)
                   for (arm, run), prompt in built.items()]
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            print(result["arm"], result["run"], result["stop_reason"])
    (args.output / "run-status.json").write_text(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
