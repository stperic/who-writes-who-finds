#!/usr/bin/env python3
"""Choose one related PHP file from a PR diff and a pinned repository revision.

This is the deterministic selector for the automated-context follow-up. It never
reads a CVE, advisory, scoring key, future fix, or the current worktree. The
reviewer still receives the original diff in full. No model call is made here.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
from html import escape
import json
from pathlib import Path
import re
import subprocess
import sys


VERSION = "1"
IGNORED_PREFIXES = ("vendor/", "node_modules/", "tests/", "public/assets/")
COMMON_VARIABLES = {
    "GLOBALS", "_GET", "_POST", "_REQUEST", "_SERVER", "_SESSION", "_COOKIE",
    "this", "result", "data", "value", "name", "array", "count", "index", "item",
    "patient_id", "pid", "encounter", "formid", "id", "row", "res", "sql",
}
PHP_PATHSPEC = "*.php"


def ignored(path: str) -> bool:
    parts = path.split("/")
    return (path.startswith(IGNORED_PREFIXES) or
            any(part in {"vendor", "node_modules", "tests", ".phpstan"}
                or part.startswith(".") for part in parts[:-1]))


def git(repo: Path, *args: str, no_match_ok: bool = False) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                          text=True, errors="replace")
    if proc.returncode == 1 and no_match_ok:
        return ""
    if proc.returncode:
        raise RuntimeError(f"git {' '.join(args[:3])} failed: {proc.stderr.strip()}")
    return proc.stdout


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def paths_in_diff(diff: str) -> list[str]:
    paths = []
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            path = line[6:]
            if path not in paths:
                paths.append(path)
    if not paths:
        raise ValueError("Diff has no added or modified file paths")
    return paths


def added_lines(diff: str) -> str:
    return "\n".join(line[1:] for line in diff.splitlines()
                     if line.startswith("+") and not line.startswith("+++"))


def read_at(repo: Path, ref: str, path: str) -> str:
    return git(repo, "show", f"{ref}:{path}")


def grep_files(repo: Path, ref: str, literal: str) -> list[str]:
    output = git(repo, "grep", "-l", "-F", "-e", literal, ref, "--", PHP_PATHSPEC,
                 no_match_ok=True)
    prefix = ref + ":"
    return [line[len(prefix):] for line in output.splitlines()
            if line.startswith(prefix) and not ignored(line[len(prefix):])]


def php_paths(repo: Path, ref: str) -> list[str]:
    return [p for p in git(repo, "ls-tree", "-r", "--name-only", ref).splitlines()
            if p.endswith(".php") and not ignored(p)]


def anchors_from_diff(repo: Path, ref: str, diff: str, changed: list[str]) -> list[dict]:
    added = added_lines(diff)
    anchors = []
    seen = set()

    def add(kind: str, literal: str, weight: int, count: int = 1) -> None:
        key = (kind, literal)
        if key not in seen:
            seen.add(key)
            anchors.append({"kind": kind, "literal": literal, "weight": weight,
                            "diff_occurrences": count})

    for path in changed:
        if not path.endswith(".php"):
            continue
        source = read_at(repo, ref, path)
        for match in re.finditer(r"\bclass\s+\w+\s+extends\s+([A-Za-z_\\][\w\\]*)", source):
            add("parent_class", match.group(1).split("\\")[-1], 100)

    for key in re.findall(r"\$GLOBALS\s*\[\s*['\"]([A-Za-z_][\w]{5,})['\"]\s*\]", added):
        add("global_key", key, 40)

    # Local variables produce many unrelated matches. Only explicit PHP globals
    # and constant-style variables are reliable cross-file search keys.
    declared_globals = set(re.findall(r"\bglobal\s+\$([A-Za-z_][A-Za-z_0-9]*)", added))
    variables = Counter(re.findall(r"\$([A-Za-z_][A-Za-z_0-9]*)", added))
    useful = [(name, count) for name, count in variables.items()
              if name not in COMMON_VARIABLES and len(name) >= 7
              and (name in declared_globals or (name.isupper() and count >= 2))]
    for name, count in sorted(useful, key=lambda row: (-row[1], row[0]))[:12]:
        add("variable", "$" + name, 8, count)

    # Controller maps and similar PHP arrays often name classes as strings.
    quoted = Counter(re.findall(r"=>\s*['\"]([A-Z][A-Za-z0-9]{8,})['\"]", added))
    for name, count in sorted(quoted.items(), key=lambda row: (-row[1], row[0]))[:12]:
        add("class_string", name, 20, count)
    return anchors


def find_candidates(repo: Path, ref: str, changed: list[str], anchors: list[dict]) -> list[dict]:
    changed_set = set(changed)
    path_index = php_paths(repo, ref)
    evidence: dict[str, list[dict]] = defaultdict(list)
    cache: dict[str, str] = {}

    def source(path: str) -> str:
        if path not in cache:
            cache[path] = read_at(repo, ref, path)
        return cache[path]

    for anchor in anchors:
        kind, literal = anchor["kind"], anchor["literal"]
        if kind == "parent_class":
            candidates = grep_files(repo, ref, "class " + literal)
        elif kind == "class_string":
            names = {literal.casefold(), ("C_" + literal).casefold()}
            candidates = [p for p in path_index
                          if Path(p).name.split(".")[0].casefold() in names]
        else:
            candidates = grep_files(repo, ref, literal)
            if len(candidates) > 12:
                continue
        for path in candidates:
            if path in changed_set:
                continue
            body = source(path)
            points = anchor["weight"]
            if kind == "parent_class":
                if not re.search(r"\bclass\s+" + re.escape(literal) + r"\b", body):
                    continue
            elif kind == "global_key":
                if re.search(r"['\"]" + re.escape(literal) + r"['\"]\s*=>", body):
                    points += 25  # definition or configuration entry
            elif kind == "variable":
                points += 4 * min(body.count(literal), 6)
                points += min(anchor["diff_occurrences"], 10)
                if re.search(re.escape(literal) + r"\s*=", body):
                    points += 6
            elif kind == "class_string":
                points += min(anchor["diff_occurrences"], 3)
            evidence[path].append({"kind": kind, "literal": literal, "points": points})

    changed_basenames = {Path(p).name for p in changed}
    ranked = []
    for path, signals in evidence.items():
        body = source(path)
        basename_bonus = 12 if any(name in body for name in changed_basenames) else 0
        # Many same-form field names in a neighboring file are one relationship,
        # not independent evidence that the file is the best security context.
        ranked.append({"path": path, "score": max(x["points"] for x in signals)
                       + min(3, len(signals) - 1) + basename_bonus, "signals": signals,
                       "changed_basename_bonus": basename_bonus})
    return sorted(ranked, key=lambda row: (-row["score"], row["path"]))


def fallback_candidates(repo: Path, ref: str, changed: list[str], diff: str) -> list[dict]:
    """Find direct uses of a changed class, function, or distinctive filename."""
    found: dict[str, list[dict]] = defaultdict(list)
    for path in changed:
        if not path.endswith(".php"):
            continue
        body = read_at(repo, ref, path)
        classes = re.findall(r"\bclass\s+([A-Za-z_]\w*)\b", body)
        methods = re.findall(r"^\+[^+].*?\bfunction\s+([A-Za-z_]\w*)\s*\(", diff, re.M)
        keys = [("class_reference", x, 25) for x in classes]
        keys += [("function_reference", x, 18) for x in methods if len(x) >= 9]
        if len(Path(path).name) >= 14:
            keys.append(("filename_reference", Path(path).name, 20))
        for kind, literal, points in keys[:12]:
            matches = grep_files(repo, ref, literal)
            if len(matches) > 20:
                continue
            for candidate in matches:
                if candidate in changed:
                    continue
                source = read_at(repo, ref, candidate)
                bonus = 0
                if kind == "filename_reference" and re.search(
                        r"(?:include|require)[^\n]*" + re.escape(literal), source):
                    bonus = 10
                elif kind == "class_reference" and re.search(
                        r"\b(?:new\s+|::)" + re.escape(literal) + r"\b", source):
                    bonus = 10
                found[candidate].append({"kind": kind, "literal": literal,
                                         "points": points + bonus})
    ranked = [{"path": path, "score": max(s["points"] for s in signals),
               "signals": signals, "changed_basename_bonus": 0}
              for path, signals in found.items()]
    return sorted(ranked, key=lambda row: (-row["score"], row["path"]))


def numbered(lines: list[str], start: int, end: int) -> str:
    return "\n".join(f"{n:5d}| {lines[n - 1]}" for n in range(start, end + 1))


def context_excerpt(body: str, signals: list[dict], available: int) -> tuple[str, list[list[int]]]:
    lines = body.splitlines()
    whole = numbered(lines, 1, len(lines))
    if len(whole) <= available:
        return whole, [[1, len(lines)]]
    literals = [s["literal"] for s in signals]
    centers = [n for n, line in enumerate(lines, 1) if any(x in line for x in literals)]
    if not centers:
        centers = [1]
    windows = []
    for center in centers:
        start, end = max(1, center - 18), min(len(lines), center + 18)
        if windows and start <= windows[-1][1] + 1:
            windows[-1][1] = max(windows[-1][1], end)
        else:
            windows.append([start, end])
    chunks, included = [], []
    for start, end in windows:
        chunk = numbered(lines, start, end)
        if sum(map(len, chunks)) + len(chunk) + 8 * len(chunks) > available:
            break
        chunks.append(chunk)
        included.append([start, end])
    if not chunks:
        raise ValueError("No context excerpt fits the remaining input budget")
    return "\n...\n".join(chunks), included


def select_context(repo: Path, head: str, diff: str,
                   max_input_chars: int = 160_000) -> dict:
    repo = repo.resolve()
    ref = git(repo, "rev-parse", f"{head}^{{commit}}").strip()
    changed = paths_in_diff(diff)
    # The prompt template and context labels also consume input. Never drop the diff.
    reserve = 3_000
    if len(diff) + reserve >= max_input_chars:
        raise ValueError(f"Diff is {len(diff)} characters and exceeds the "
                         f"{max_input_chars}-character input ceiling")
    anchors = anchors_from_diff(repo, ref, diff, changed)
    ranked = find_candidates(repo, ref, changed, anchors)
    if not ranked:
        ranked = fallback_candidates(repo, ref, changed, diff)
    selected = ranked[0] if ranked else None
    context, spans, blob_hash = "", [], None
    if selected:
        body = read_at(repo, ref, selected["path"])
        available = max_input_chars - len(diff) - reserve - 300
        context, spans = context_excerpt(body, selected["signals"], available)
        blob_hash = sha(body)
    return {"selector_version": VERSION, "head": ref, "changed_paths": changed,
            "diff_sha256": sha(diff), "diff_chars": len(diff), "anchors": anchors,
            "ranked_candidates": ranked[:20], "selected_path": selected["path"] if selected else None,
            "selected_score": selected["score"] if selected else None,
            "selected_signals": selected["signals"] if selected else [],
            "selected_blob_sha256": blob_hash, "included_lines": spans,
            "context": context, "estimated_packet_chars": len(diff) + len(context) + reserve}


def context_block(result: dict) -> str:
    if not result["selected_path"]:
        return ""
    path = escape(result["selected_path"], quote=True)
    lines = ",".join(f"{start}-{end}" for start, end in result["included_lines"])
    return (f'<context_file path="{path}" lines="{lines}" role="related_code">\n'
            f'{result["context"]}\n</context_file>')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--head", required=True)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--diff-file", type=Path)
    choice.add_argument("--base")
    parser.add_argument("--max-input-chars", type=int, default=160_000)
    parser.add_argument("--metadata-out", type=Path)
    args = parser.parse_args()
    diff = (args.diff_file.read_text() if args.diff_file else
            git(args.repo, "diff", f"{args.base}...{args.head}"))
    result = select_context(args.repo, args.head, diff, args.max_input_chars)
    if args.metadata_out:
        args.metadata_out.parent.mkdir(parents=True, exist_ok=True)
        args.metadata_out.write_text(json.dumps({k: v for k, v in result.items() if k != "context"},
                                                indent=2) + "\n")
    print(f"<pr_diff>\n{diff.rstrip()}\n</pr_diff>")
    if result["selected_path"]:
        print(context_block(result))
    else:
        print("<context_file selected=\"none\" />")
    print(f"selected={result['selected_path']} candidates={len(result['ranked_candidates'])} "
          f"packet_chars~{result['estimated_packet_chars']}", file=sys.stderr)


if __name__ == "__main__":
    main()
