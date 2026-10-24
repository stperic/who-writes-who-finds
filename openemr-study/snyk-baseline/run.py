"""Run Snyk Code once per original case in a separate OpenEMR worktree."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / "build" / "snyk-code-24"
REMOTE_URL = "https://github.com/openemr/openemr"


def command(args: list[str], *, cwd: Path | None = None) -> str:
    return subprocess.check_output(args, cwd=cwd, text=True).strip()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def git_common_dir(repo: Path) -> Path:
    return Path(command(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=repo)).resolve()


def valid_prior_scan(folder: Path, case: dict, version: str) -> bool:
    metadata_file = folder / "metadata.json"
    if not metadata_file.exists():
        return False
    metadata = json.loads(metadata_file.read_text())
    if metadata["commit"] != case["intro_commit"] or metadata["snyk_cli_version"] != version:
        raise RuntimeError(f"Existing scan has a different commit or CLI version: {folder}")
    raw = (folder / "stdout.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != metadata["stdout_sha256"]:
        raise RuntimeError(f"Existing raw output hash does not match: {folder}")
    if metadata["status"] not in ("completed_with_findings", "completed_no_findings"):
        raise RuntimeError(f"Existing scan is incomplete: {folder}")
    runs = json.loads(raw)["runs"]
    if len(runs) != 1 or len(runs[0]["results"]) != metadata["finding_count"]:
        raise RuntimeError(f"Existing SARIF result count does not match: {folder}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Full OpenEMR git clone with all case commits")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Directory for raw results")
    parser.add_argument("--worktree", type=Path, help="Separate OpenEMR scan worktree")
    parser.add_argument("--case", help="Run only one case ID; otherwise run all 24")
    args = parser.parse_args()
    source = args.source.resolve()
    output = args.output.resolve()
    worktree = args.worktree.resolve() if args.worktree else output.parent / "openemr-snyk-worktree"
    if not source.is_dir() or command(["git", "rev-parse", "--show-toplevel"], cwd=source) != str(source):
        parser.error("--source must be the root of an OpenEMR git clone")
    if output.is_relative_to(source) or output.is_relative_to(worktree) or worktree.is_relative_to(source):
        parser.error("Output and scan worktree must be outside the source clone")

    with (HERE / "manifest.csv").open(newline="") as f:
        cases = list(csv.DictReader(f))
    if len(cases) != 24 or len({c["case_id"] for c in cases}) != 24:
        raise RuntimeError("Expected 24 distinct cases in manifest.csv")
    if args.case:
        cases = [c for c in cases if c["case_id"] == args.case]
        if not cases:
            parser.error("case ID is absent from manifest.csv")

    version = command(["snyk", "--version"])
    if not worktree.exists():
        subprocess.run(
            ["git", "-C", str(source), "worktree", "add", "--quiet", "--detach", str(worktree), cases[0]["intro_commit"]],
            check=True,
        )
    if command(["git", "rev-parse", "--show-toplevel"], cwd=worktree) != str(worktree):
        raise RuntimeError("Existing worktree path is not the expected Git checkout")
    if git_common_dir(source) != git_common_dir(worktree):
        raise RuntimeError("Scan worktree belongs to a different repository")

    output.mkdir(parents=True, exist_ok=True)
    for i, case in enumerate(cases, 1):
        case_id = case["case_id"]
        folder = output / case_id
        if valid_prior_scan(folder, case, version):
            print(f"[{i}/{len(cases)}] {case_id}: verified prior scan, skipped", flush=True)
            continue
        if folder.exists():
            raise RuntimeError(f"Refusing to overwrite existing scan directory: {folder}")
        if command(["git", "status", "--porcelain"], cwd=worktree):
            raise RuntimeError("OpenEMR scan worktree has local changes")
        subprocess.run(["git", "checkout", "--quiet", "--detach", case["intro_commit"]], cwd=worktree,
                       check=True, stdout=subprocess.DEVNULL)
        commit = command(["git", "rev-parse", "HEAD"], cwd=worktree)
        if commit != case["intro_commit"]:
            raise RuntimeError(f"Checked out wrong revision for {case_id}")
        folder.mkdir()
        started = utc_now()
        start = time.monotonic()
        print(f"[{i}/{len(cases)}] {case_id}: scanning {commit[:12]}", flush=True)
        scan = subprocess.run(
            ["snyk", "code", "test", "--json", f"--remote-repo-url={REMOTE_URL}"],
            cwd=worktree, capture_output=True, timeout=900,
        )
        raw = scan.stdout
        (folder / "stdout.json").write_bytes(raw)
        (folder / "stderr.txt").write_bytes(scan.stderr)
        try:
            data = json.loads(raw)
            runs = data["runs"]
            if len(runs) != 1 or not isinstance(runs[0]["results"], list):
                raise ValueError("Expected one SARIF run with results array")
            findings = len(runs[0]["results"])
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            findings = None
            error = str(exc)
        else:
            error = None
        status = ("completed_no_findings" if scan.returncode == 0 else
                  "completed_with_findings" if scan.returncode == 1 else "execution_error")
        if findings is None:
            status = "execution_error"
        metadata = {
            "case_id": case_id,
            "commit": commit,
            "revision_policy": "introducing commit used for original AI review diff",
            "scope": "whole OpenEMR repository, Snyk Code default rules",
            "remote_repo_url": REMOTE_URL,
            "snyk_cli_version": version,
            "command": "snyk code test --json --remote-repo-url=https://github.com/openemr/openemr",
            "organization_scope": "CLI account default; no --org was supplied",
            "started_at": started,
            "ended_at": utc_now(),
            "latency_seconds": round(time.monotonic() - start, 3),
            "exit_code": scan.returncode,
            "status": status,
            "finding_count": findings,
            "stdout_sha256": hashlib.sha256(raw).hexdigest(),
            "stderr_sha256": hashlib.sha256(scan.stderr).hexdigest(),
            "error": error,
        }
        (folder / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
        print(f"[{i}/{len(cases)}] {case_id}: {status}, {findings} findings", flush=True)
        if status == "execution_error":
            raise RuntimeError(f"Snyk execution error for {case_id}; see {folder}")


if __name__ == "__main__":
    main()
