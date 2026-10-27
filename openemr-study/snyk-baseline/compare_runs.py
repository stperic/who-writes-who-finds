"""Compare Snyk Code findings across repeat runs of the 24 case scans.

Each run is a directory written by run.py or a zip archive with the same
layout. Findings are compared on the key recorded in hypothesis H5: rule,
level, primary location, message, data-flow trace, fingerprints 0 and 1, and
priority score. Snyk's identity UUIDs, run ID, timestamps and latency are
ignored because they label or time findings rather than describe them.
"""

from __future__ import annotations

import argparse
import csv
import json
import zipfile
from collections import Counter
from pathlib import Path

from run import HERE


def reader(source: Path):
    if source.suffix == ".zip":
        archive = zipfile.ZipFile(source)
        return lambda case_id: archive.read(f"{case_id}/stdout.json")
    return lambda case_id: (source / case_id / "stdout.json").read_bytes()


def finding_key(result: dict) -> str:
    physical = result["locations"][0]["physicalLocation"]
    return json.dumps([
        result["ruleId"], result["level"],
        physical["artifactLocation"]["uri"], physical["region"],
        result["message"]["text"], result.get("codeFlows"),
        result["fingerprints"].get("0"), result["fingerprints"].get("1"),
        result.get("properties", {}).get("priorityScore"),
    ], sort_keys=True)


def load(read, case_id: str) -> tuple[list[str], str]:
    run = json.loads(read(case_id))["runs"][0]
    coverage = json.dumps(run["properties"].get("coverage"), sort_keys=True)
    return [finding_key(r) for r in run["results"]], coverage


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", type=Path, nargs="+", help="Run directories or zip archives; the first is the baseline")
    args = parser.parse_args()
    if len(args.runs) < 2:
        parser.error("Give at least two runs to compare")
    with (HERE / "scan_manifest.csv").open(newline="") as f:
        cases = list(csv.DictReader(f))
    readers = [reader(path.resolve()) for path in args.runs]
    changed = []
    for case in cases:
        case_id = case["case_id"]
        loaded = [load(read, case_id) for read in readers]
        base, base_coverage = loaded[0]
        cells = []
        for n, (keys, coverage) in enumerate(loaded[1:], 2):
            only_base = sum((Counter(base) - Counter(keys)).values())
            only_other = sum((Counter(keys) - Counter(base)).values())
            if only_base or only_other:
                cells.append(f"run {n}: {only_base} only in run 1, {only_other} only in run {n}")
            else:
                cells.append(f"run {n}: identical{'' if keys == base else ' (order differs)'}")
            if coverage != base_coverage:
                cells[-1] += ", coverage differs"
        if any("only in" in cell for cell in cells):
            changed.append(case_id)
        print(f"{case_id:15} {len(base):5} findings | " + " | ".join(cells))
    print(f"{len(cases) - len(changed)} of {len(cases)} cases identical to run 1 across all runs"
          + (f"; changed: {', '.join(changed)}" if changed else ""))


if __name__ == "__main__":
    main()
