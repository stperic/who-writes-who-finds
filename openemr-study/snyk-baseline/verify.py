"""Verify the published Snyk Code evidence without calling Snyk."""

from __future__ import annotations

import csv
import hashlib
import json
import statistics
import zipfile
from collections import Counter
from pathlib import Path


HERE = Path(__file__).resolve().parent
ARCHIVE = HERE / "evidence" / "snyk-code-raw.zip"


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def indexed(path: Path) -> dict[str, dict[str, str]]:
    items = rows(path)
    result = {r["case_id"]: r for r in items}
    if len(result) != len(items):
        raise ValueError(f"Duplicate case ID in {path}")
    return result


def main() -> None:
    expected_archive_hash = (HERE / "evidence" / "SHA256.txt").read_text().split()[0]
    if hashlib.sha256(ARCHIVE.read_bytes()).hexdigest() != expected_archive_hash:
        raise ValueError("Snyk raw archive SHA-256 mismatch")

    cases = indexed(HERE / "manifest.csv")
    metrics = indexed(HERE / "case-metrics.csv")
    rulings = indexed(HERE / "adjudication.csv")
    if len(cases) != 24 or set(cases) != set(metrics) or set(cases) != set(rulings):
        raise ValueError("The three public CSVs must contain the same 24 distinct cases")
    scores = Counter(r["score"] for r in rulings.values())
    if scores != {"Caught": 6, "Borderline": 1, "Missed": 17}:
        raise ValueError(f"Published case scores changed: {scores}")
    for case_id, ruling in rulings.items():
        if ruling["score"] in ("Caught", "Borderline") and not (ruling["rule_id"] and ruling["location"]):
            raise ValueError(f"Missing finding identity for {case_id}")
        if ruling["score"] == "Missed" and (ruling["rule_id"] or ruling["location"]):
            raise ValueError(f"Missed case has a claimed matching finding: {case_id}")
        if not ruling["reason"] or not ruling["review_status"]:
            raise ValueError(f"Missing adjudication explanation: {case_id}")

    displayed = {}
    displayed_count = 0
    for line in (HERE / "RESULTS.md").read_text().splitlines():
        if line.startswith("| CVE-"):
            cells = [cell.strip() for cell in line.split("|")[1:-1]]
            displayed_count += 1
            displayed[cells[0]] = (cells[1], cells[2])
    if displayed_count != 24 or len(displayed) != 24 or set(displayed) != set(cases):
        raise ValueError("Results table must show every case exactly once")
    for case_id, (owasp, score) in displayed.items():
        if owasp != cases[case_id]["owasp"] or score != rulings[case_id]["score"]:
            raise ValueError(f"Displayed result differs from source CSV: {case_id}")
    category_counts: dict[str, Counter[str]] = {}
    for case_id, case in cases.items():
        category_counts.setdefault(case["owasp"], Counter())[rulings[case_id]["score"]] += 1
    category_rows = {}
    for line in (HERE / "RESULTS.md").read_text().splitlines():
        if line.startswith("| A") and line.split("|")[1].strip() in category_counts:
            cells = [cell.strip() for cell in line.split("|")[1:-1]]
            category_rows[cells[0]] = cells[1:4]
    if set(category_rows) != set(category_counts):
        raise ValueError("Results category table is incomplete")
    for category, counts in category_counts.items():
        total = sum(counts.values())
        expected = [f"{counts[label]}/{total}" for label in ("Caught", "Borderline", "Missed")]
        if category_rows[category] != expected:
            raise ValueError(f"Displayed OWASP totals differ from source CSV: {category}")

    entry_manifest = rows(HERE / "evidence" / "archive-manifest.csv")
    expected_entries = {r["path"]: r for r in entry_manifest}
    if len(expected_entries) != 72 or len(entry_manifest) != 72:
        raise ValueError("Archive manifest must list metadata, SARIF and stderr for 24 cases")

    findings = []
    latencies = []
    versions = set()
    with zipfile.ZipFile(ARCHIVE) as archive:
        if set(archive.namelist()) != set(expected_entries):
            raise ValueError("Raw archive contents differ from archive manifest")
        for path, entry in expected_entries.items():
            raw = archive.read(path)
            if len(raw) != int(entry["bytes"]) or hashlib.sha256(raw).hexdigest() != entry["sha256"]:
                raise ValueError(f"Archive entry changed: {path}")
        for case_id, case in cases.items():
            metadata = json.loads(archive.read(f"{case_id}/metadata.json"))
            raw = archive.read(f"{case_id}/stdout.json")
            sarif = json.loads(raw)
            runs = sarif.get("runs", [])
            if len(runs) != 1 or not isinstance(runs[0].get("results"), list):
                raise ValueError(f"Invalid Snyk SARIF: {case_id}")
            count = len(runs[0]["results"])
            if metadata["case_id"] != case_id or metadata["commit"] != case["intro_commit"]:
                raise ValueError(f"Incorrect scan identity: {case_id}")
            if metadata["status"] not in ("completed_with_findings", "completed_no_findings"):
                raise ValueError(f"Incomplete scan: {case_id}")
            if metadata["exit_code"] not in (0, 1) or metadata["finding_count"] != count:
                raise ValueError(f"Scan exit or finding count mismatch: {case_id}")
            if hashlib.sha256(raw).hexdigest() != metadata["stdout_sha256"]:
                raise ValueError(f"SARIF hash mismatch: {case_id}")
            if archive.read(f"{case_id}/stderr.txt"):
                raise ValueError(f"Unexpected nonempty stderr for {case_id}")
            for key, value in metrics[case_id].items():
                if str(metadata[key]) != value:
                    raise ValueError(f"Case metric {key} differs from raw metadata: {case_id}")
            findings.append(count)
            latencies.append(float(metadata["latency_seconds"]))
            versions.add(metadata["snyk_cli_version"])
    if versions != {"1.1308.2"} or sum(findings) != 26927:
        raise ValueError("CLI version or total finding volume changed")
    print(
        f"Verified 24 scans, {sum(findings):,} findings, "
        f"{scores['Caught']} clear Caught, {scores['Borderline']} Borderline, "
        f"{scores['Missed']} Missed; median {statistics.median(latencies):.1f}s"
    )


if __name__ == "__main__":
    main()
