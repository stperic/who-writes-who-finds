"""Extract a review queue from completed Snyk Code SARIF scans.

File overlap is only a candidate signal. A person must inspect the finding and
the known flaw before assigning Caught or Missed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json

from pathlib import Path

from run import DEFAULT_OUTPUT, HERE


def locations(result: dict) -> list[tuple[str, int | None]]:
    found = []
    for entry in result.get("locations", []):
        physical = entry.get("physicalLocation", {})
        found.append((physical.get("artifactLocation", {}).get("uri", ""),
                      physical.get("region", {}).get("startLine")))
    for flow in result.get("codeFlows", []):
        for thread in flow.get("threadFlows", []):
            for entry in thread.get("locations", []):
                physical = entry.get("location", {}).get("physicalLocation", {})
                found.append((physical.get("artifactLocation", {}).get("uri", ""),
                              physical.get("region", {}).get("startLine")))
    return list(dict.fromkeys(found))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Directory with raw scan results")
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_dir():
        parser.error(f"Raw result directory is absent: {output}")
    with (HERE / "manifest.csv").open(newline="") as f:
        cases = list(csv.DictReader(f))
    findings = []
    summary = []
    for case in cases:
        folder = output / case["case_id"]
        metadata_file = folder / "metadata.json"
        if not metadata_file.exists():
            summary.append({"case_id": case["case_id"], "owasp": case["owasp"],
                            "status": "not_run", "findings": "", "file_candidates": "", "score": ""})
            continue
        metadata = json.loads(metadata_file.read_text())
        raw = (folder / "stdout.json").read_bytes()
        if hashlib.sha256(raw).hexdigest() != metadata["stdout_sha256"]:
            raise ValueError(f"Raw output hash mismatch: {case['case_id']}")
        if metadata["status"] not in ("completed_with_findings", "completed_no_findings"):
            summary.append({"case_id": case["case_id"], "owasp": case["owasp"],
                            "status": metadata["status"], "findings": "", "file_candidates": "", "score": ""})
            continue
        results = json.loads(raw)["runs"][0]["results"]
        scan_files = set(case["scan_files"].split(";"))
        candidates = 0
        for index, result in enumerate(results, 1):
            paths = locations(result)
            overlaps = sorted({path for path, _ in paths if path in scan_files})
            if overlaps:
                candidates += 1
            primary_path, primary_line = paths[0] if paths else ("", None)
            findings.append({
                "case_id": case["case_id"], "finding_index": index,
                "rule_id": result.get("ruleId", ""), "level": result.get("level", ""),
                "primary_path": primary_path, "primary_line": primary_line,
                "touches_diff_file": "yes" if overlaps else "no",
                "overlap_paths": ";".join(overlaps),
                "all_locations": ";".join(f"{path}:{line}" for path, line in paths),
                "message": result.get("message", {}).get("text", ""),
            })
        summary.append({"case_id": case["case_id"], "owasp": case["owasp"],
                        "status": metadata["status"], "findings": len(results),
                        "file_candidates": candidates, "score": ""})
    for name, rows, fields in [
        ("finding-review-queue.csv", findings,
         ["case_id", "finding_index", "rule_id", "level", "primary_path", "primary_line",
          "touches_diff_file", "overlap_paths", "all_locations", "message"]),
        ("case-summary.csv", summary,
         ["case_id", "owasp", "status", "findings", "file_candidates", "score"]),
    ]:
        with (output / name).open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    print(f"{len(summary)} cases, {len(findings)} findings; scoring remains pending human review")


if __name__ == "__main__":
    main()
