#!/usr/bin/env python3
"""
quadrant — measure the human-AI security review boundary on any repo.

Companion tool to the talk "Who Writes the Bug, Who Finds the Bug?"
Traces confirmed CVEs to their introducing commits, extracts blind diffs
for AI counterfactual review, scores results, and reports detection rates
by defect category.

v0.2 — the one-off study becomes a longitudinal benchmark: register each
model as it ships, batch-run the frozen blind prompt over every diff,
score per model, compare models over time. Storage stays CSV
(git-friendly): data/cves.csv (inventory, v0.1 schema unchanged),
data/models.csv (registry), data/scores.csv (per cve x model scores),
ai_runs/runs.csv (append-only call journal). stdlib only; pandas is
lazy (report), provider SDKs are lazy (run).

Subcommands: init, advisories, trace, diffs, scrub (v0.1 pipeline);
fixes (GHSA cvss/refs/credits); model add/list (registry + cutoffs);
prompt; run (batch diffs x models x runs + recog/advisory probes);
score (per cve x model); report (per-model rates); compare
(longitudinal matrix + drift).

Typical benchmark flow (repeat every time a new model ships):
  quadrant model add --slug fable-5 --provider anthropic \\
      --model-id claude-fable-5 --cutoff 2026-01-01
  quadrant run --model fable-5      # scored runs + recog/advisory probes
  quadrant score CVE-2026-24908 --model fable-5     # per CVE, after reading
  quadrant report --model fable-5
  quadrant compare                  # the ruler: re-measure, watch the drift
"""

import argparse
import csv
import json
import os
import pathlib
import re
import subprocess
import sys
import time
from datetime import date, datetime, timezone

ROOT = pathlib.Path.cwd()
DATA = ROOT / "data"
DIFFS = ROOT / "diffs"
RUNS = ROOT / "ai_runs"
CSV = DATA / "cves.csv"
MODELS = DATA / "models.csv"
SCORES = DATA / "scores.csv"
RUNS_CSV = RUNS / "runs.csv"

COLUMNS = [
    "cve_id", "ghsa_id", "group", "owasp", "vuln_type", "cvss",
    "fix_commit", "intro_commit", "intro_date", "disclosed_date",
    "survival_days", "caught_by", "reporter", "file_path", "traceable",
    "run1", "run2", "run3", "final_score", "recognized", "notes",
]

MODEL_COLUMNS = "slug provider model_id training_cutoff added_date notes".split()
SCORE_COLUMNS = ("cve_id model_slug run1 run2 run3 final_score recognized "
                 "advisory_aware score_note scored_date").split()
RUN_COLUMNS = ("cve_id model_slug model_version kind run started_at_utc "
               "wall_seconds diff_chars truncated output_file").split()

PROMPT = """You are reviewing a pull request diff before it is merged.
Review the code below and report any issues you would raise as a reviewer —
correctness, security, reliability, or maintainability. For each issue, give
the location, the problem, and the severity. If you find no issues, say so.

```
{diff}
```"""

RECOG_PROMPT = "Do you recognize this code or know which project it's from?"

ADVISORY_PROMPT = ("Are you aware of any security advisory or CVE affecting "
                   "this specific code?")


def sh(cmd, **kw):
    """Run a shell command, return stdout."""
    return subprocess.run(cmd, shell=True, capture_output=True,
                          text=True, **kw).stdout


def key_of(row):
    """Row key: cve_id, falling back to ghsa_id when cve_id is empty."""
    return (row.get("cve_id") or "").strip() or (row.get("ghsa_id") or "").strip()


def find_row(rows, key):
    return next((r for r in rows if key in
                 ((r.get("cve_id") or "").strip(),
                  (r.get("ghsa_id") or "").strip())), None)


def read_table(path):
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def write_table(path, columns, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in columns})


def load_rows():
    if not CSV.exists():
        sys.exit(f"{CSV} not found — run `quadrant init` first.")
    return read_table(CSV)


def save_rows(rows):
    write_table(CSV, COLUMNS, rows)


def load_models():
    return read_table(MODELS)


def journal(row):
    """Append one line to the append-only ai_runs/runs.csv journal."""
    RUNS.mkdir(parents=True, exist_ok=True)
    new = not RUNS_CSV.exists() or RUNS_CSV.stat().st_size == 0
    with open(RUNS_CSV, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=RUN_COLUMNS, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerow({c: row.get(c, "") for c in RUN_COLUMNS})


# ---------------------------------------------------------------- init
def cmd_init(args):
    for d in (DATA, DIFFS, RUNS, ROOT / "analysis"):
        d.mkdir(parents=True, exist_ok=True)
    if CSV.exists():
        print(f"{CSV} already exists — leaving it alone.")
    else:
        save_rows([])
        print(f"Created {CSV} with schema:\n  " + ", ".join(COLUMNS))
    for path, cols in ((MODELS, MODEL_COLUMNS), (SCORES, SCORE_COLUMNS)):
        if path.exists():
            print(f"{path} already exists — leaving it alone.")
        else:
            write_table(path, cols, [])
            print(f"Created {path}.")
    print("Workspace ready. Next: quadrant advisories --repo <owner/name>")


# ---------------------------------------------------------- advisories
def cmd_advisories(args):
    out = sh(
        f"gh api /repos/{args.repo}/security-advisories --paginate "
        "--jq '.[] | [.cve_id, .ghsa_id, .summary, .severity, "
        ".published_at] | @tsv'"
    )
    if not out.strip():
        sys.exit("No output — is `gh` installed and authenticated "
                 "(gh auth login)?")
    dest = DATA / "advisories.tsv"
    dest.write_text(out)
    n = len(out.strip().splitlines())
    print(f"Wrote {n} advisories to {dest}.")
    print("Copy the ones you'll study into data/cves.csv "
          "(cve_id, ghsa_id, disclosed_date, cvss), then fill fix_commit "
          "from each advisory page.")


# --------------------------------------------------------------- trace
def cmd_trace(args):
    rows = load_rows()
    row = find_row(rows, args.cve)
    if not row:
        sys.exit(f"{args.cve} not in {CSV}.")
    fix = row.get("fix_commit", "").strip()
    if not fix:
        sys.exit(f"{args.cve} has no fix_commit yet — get it from the "
                 "advisory page first.")
    repo = args.repo
    print(f"# Tracing {args.cve} (fix = {fix}) — run these in {repo}:\n")
    print(f"git -C {repo} show {fix} --stat")
    print(f"git -C {repo} show {fix}    # read the fix; note file + lines")
    print(f"git -C {repo} blame {fix}^ -L <start>,<end> -- <file>")
    print("#   ^ the commit(s) shown introduced the vulnerable lines")
    print(f"git -C {repo} show -s --format='%H %ci %s' <intro_sha>")
    print("\nThen record intro_commit + intro_date in data/cves.csv.")
    print("Rules: introducing commit = first commit adding the exploitable "
          "line(s); if blame dead-ends in a mass reformat, set "
          "traceable=no and drop the CVE.")


# --------------------------------------------------------------- diffs
def extract_target_file(row):
    """Extract a repo-relative file path from file_path or notes if present."""
    fp = (row.get("file_path") or "").strip()
    if fp and ("/" in fp or fp.endswith(".php") or fp.endswith(".js")):
        cand = fp.split()[0].strip("(),")
        if "/" in cand or cand.endswith(".php"):
            return cand
    notes = row.get("notes") or ""
    m = re.search(r"file=([^\],;\s]+)", notes)
    return m.group(1) if m else ""


def strip_commit_header(diff_text):
    """Strip commit metadata/message before the first 'diff --git' header."""
    idx = diff_text.find("diff --git ")
    return diff_text[idx:] if idx != -1 else diff_text


def cmd_diffs(args):
    rows = load_rows()
    raw_dir = ROOT / "diffs_raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    done = skipped = 0
    for r in rows:
        sha, key = r.get("intro_commit", "").strip(), key_of(r)
        if not sha or r.get("traceable", "").lower() == "no":
            skipped += 1
            continue
        target_file = extract_target_file(r) if not getattr(args, "whole_commit", False) else ""
        file_arg = f" -- {target_file}" if target_file else ""
        out = sh(f"git -C {args.repo} show {sha} --no-color{file_arg}")
        if not out.strip() and target_file:
            # Fallback to whole commit if file was renamed or path moved
            out = sh(f"git -C {args.repo} show {sha} --no-color")
        if not out.strip():
            print(f"  ! {key}: git show {sha} returned nothing — check sha")
            continue
        (raw_dir / f"{key}.diff").write_text(out)
        blinded = strip_commit_header(out)
        (DIFFS / f"{key}.diff").write_text(blinded)
        done += 1
        # survival, while we're here
        if r.get("intro_date") and r.get("disclosed_date") \
                and not r.get("survival_days"):
            try:
                i = date.fromisoformat(r["intro_date"][:10])
                d = date.fromisoformat(r["disclosed_date"][:10])
                r["survival_days"] = str((d - i).days)
            except ValueError:
                pass
    save_rows(rows)
    print(f"Extracted {done} blinded diffs to {DIFFS}/ (raw archived in {raw_dir}/, {skipped} skipped). "
          "Commit headers stripped and survival days computed where dates were present.")
    print("Next: quadrant scrub")


# --------------------------------------------------------------- scrub
GIVEAWAYS = re.compile(r"cve|vulnerab|security|exploit|injection|xss",
                       re.IGNORECASE)


def cmd_scrub(args):
    flagged = []
    stripped_count = 0
    for f in sorted(DIFFS.glob("*.diff")):
        text = f.read_text(errors="replace")
        # Enforce commit-message stripping if a raw git show header is still present
        if "diff --git " in text and not text.startswith("diff --git "):
            text = strip_commit_header(text)
            f.write_text(text)
            stripped_count += 1
        if GIVEAWAYS.search(text):
            flagged.append((f.name, "code/comments mention security terms — "
                            "inspect to confirm it is original code, not a leaked advisory"))
    if stripped_count:
        print(f"Stripped commit-message headers from {stripped_count} diff(s).")
    if not flagged:
        print("All diffs clean — blinding intact.")
    else:
        print("Note: original code/comments in these diffs contain security keywords:")
        for name, why in flagged:
            print(f"  {name}: {why}")


# --------------------------------------------------------------- model
def cmd_model(args):
    if args.model_cmd == "add":
        models = load_models()
        if any(m["slug"] == args.slug for m in models):
            sys.exit(f"model slug '{args.slug}' already in {MODELS}.")
        models.append({
            "slug": args.slug, "provider": args.provider,
            "model_id": args.model_id, "training_cutoff": args.cutoff,
            "added_date": date.today().isoformat(),
            "notes": args.notes or "",
        })
        write_table(MODELS, MODEL_COLUMNS, models)
        print(f"Added {args.slug} ({args.provider}/{args.model_id}, "
              f"cutoff {args.cutoff}) to {MODELS}.")
    else:  # list
        models = load_models()
        if not models:
            sys.exit(f"No models registered — quadrant model add ... "
                     f"(registry: {MODELS})")
        rows = read_table(CSV)
        for m in models:
            cutoff = m.get("training_cutoff", "")
            clean = sum(1 for r in rows
                        if (r.get("disclosed_date") or "") > cutoff)
            mem = len(rows) - clean
            print(f"{m['slug']:<18} {m['provider']:<10} "
                  f"{m['model_id']:<32} cutoff={cutoff}  "
                  f"added={m.get('added_date', '')}  "
                  f"clean={clean} memorized={mem} (of {len(rows)})"
                  + (f"  # {m['notes']}" if m.get("notes") else ""))


# --------------------------------------------------------------- fixes
def cmd_fixes(args):
    rows = load_rows()
    selected = rows if not args.keys else \
        [r for k in args.keys for r in [find_row(rows, k)] if r]
    if args.keys:
        missing = [k for k in args.keys if not find_row(rows, k)]
        for k in missing:
            print(f"  ! {k}: not in {CSV} — skipped")
    applied = 0
    for r in selected:
        key, ghsa = key_of(r), (r.get("ghsa_id") or "").strip()
        if not ghsa:
            print(f"{key or '(blank row)':<20} no ghsa_id — skipped")
            continue
        p = subprocess.run(["gh", "api", f"/advisories/{ghsa}"],
                           capture_output=True, text=True)
        if p.returncode != 0:
            err = (p.stderr or p.stdout).strip().splitlines()
            print(f"{key:<20} gh error: {err[0] if err else 'unknown'}")
            continue
        try:
            data = json.loads(p.stdout)
        except ValueError as e:
            print(f"{key:<20} bad JSON from gh: {e}")
            continue
        score = (data.get("cvss") or {}).get("score")
        if score is None:
            sev = data.get("cvss_severities") or {}
            for v in ("cvss_v4", "cvss_v3"):
                score = (sev.get(v) or {}).get("score")
                if score is not None:
                    break
        refs = data.get("references") or []
        commits = [u for u in refs if isinstance(u, str) and "/commit/" in u]
        logins = []
        for c in data.get("credits") or []:
            login = (c.get("user") or {}).get("login") or c.get("login")
            if login:
                logins.append(login)
        print(f"{key:<20} cvss={score if score is not None else '-':<5} "
              f"refs={len(refs)} credits={','.join(logins) or '-'}")
        for u in commits:
            print(f"{'':<20} commit ref: {u}")
        if args.apply:
            if score is not None and not (r.get("cvss") or "").strip():
                r["cvss"] = str(score); applied += 1
                print(f"{'':<20} -> filled empty cvss = {score}")
            if logins and not (r.get("reporter") or "").strip():
                r["reporter"] = ",".join(logins); applied += 1
                print(f"{'':<20} -> filled empty reporter = {r['reporter']}")
    if args.apply:
        save_rows(rows)
        print(f"\nApplied {applied} field fill(s) to {CSV} "
              "(only empty cvss/reporter are ever filled).")


# -------------------------------------------------------------- prompt
def truncate_diff(text, max_chars):
    """Return (text_to_send, truncated_bool); max_chars 0 = no limit."""
    if max_chars and len(text) > max_chars:
        return text[:max_chars], True
    return text, False


def cmd_prompt(args):
    rows = load_rows()
    row = find_row(rows, args.cve)
    key = key_of(row) if row else args.cve
    f = DIFFS / f"{key}.diff"
    if not f.exists():
        sys.exit(f"{f} not found — run `quadrant diffs` first.")
    text = f.read_text(errors="replace")
    sent, truncated = truncate_diff(text, args.max_chars)
    if truncated:
        print("!" * 72, file=sys.stderr)
        print(f"!!! WARNING: diff is {len(text)} chars but truncated to "
              f"{args.max_chars}.", file=sys.stderr)
        print("!!! The truncated tail may contain the vulnerable hunk — "
              "the model would\n!!! then be scored a FALSE Missed. "
              "Consider --max-chars 0 (no limit).", file=sys.stderr)
        print("!" * 72, file=sys.stderr)
    print(PROMPT.format(diff=sent))
    print(f"\n# After the scored runs, ask separately (fresh conversations):"
          f"\n# {RECOG_PROMPT}\n# {ADVISORY_PROMPT}", file=sys.stderr)
    print(f"# Or let `quadrant run` do all of it: outputs land in "
          f"ai_runs/{key}_<slug>_run<k>.md, _recog.md, _advisory.md",
          file=sys.stderr)


# ----------------------------------------------------------------- run
def call_anthropic(model_id, prompt_text):
    import anthropic  # key/SDK presence preflighted by check_provider
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=model_id, max_tokens=4096,
        messages=[{"role": "user", "content": prompt_text}])
    text = "".join(getattr(b, "text", "") for b in resp.content)
    return text, resp.model


def call_openai(model_id, prompt_text):
    import openai  # key/SDK presence preflighted by check_provider
    client = openai.OpenAI()
    resp = client.chat.completions.create(
        model=model_id, max_tokens=4096,
        messages=[{"role": "user", "content": prompt_text}])
    return resp.choices[0].message.content or "", resp.model


def call_fake(model_id, prompt_text):
    return ("Reviewed the diff. The changes look routine to me; I did not "
            "find any issue I would block the merge on. No issues found.",
            "fake-1")


PROVIDERS = {"anthropic": call_anthropic, "openai": call_openai,
             "fake": call_fake}

PROVIDER_ENV = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}


def check_provider(provider):
    """Fail fast, one line, naming the env var / pip package. No keys shown."""
    if provider == "fake":
        return
    if provider not in PROVIDERS:
        sys.exit(f"unknown provider '{provider}' in {MODELS} — "
                 f"expected one of: {', '.join(sorted(PROVIDERS))}")
    env = PROVIDER_ENV[provider]
    if not os.environ.get(env):
        sys.exit(f"{env} is not set — export it to run {provider} models.")
    try:
        __import__(provider)
    except ImportError:
        sys.exit(f"{provider} SDK missing — pip install {provider}")


def run_with_retries(provider, model_id, prompt_text):
    """Up to 3 attempts, backoff 2s then 8s. Returns (text, version,
    seconds, started_at_utc) or None after printing the final error."""
    last = None
    for attempt in range(3):
        started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        t0 = time.monotonic()
        try:
            text, version = PROVIDERS[provider](model_id, prompt_text)
            if not text or not text.strip() or text.strip() == "(no output)":
                raise RuntimeError("empty response from model")
            return text, version, time.monotonic() - t0, started
        except Exception as e:  # noqa: BLE001 — any failure retries
            last = e
            if attempt < 2:
                time.sleep((2, 8)[attempt])
    print(f"    ! failed after 3 attempts: {last}")
    return None


def cmd_run(args):
    rows = load_rows()
    models = load_models()
    if not models:
        sys.exit("No models registered — quadrant model add ... first.")
    if args.model:
        by_slug = {m["slug"]: m for m in models}
        missing = [s for s in args.model if s not in by_slug]
        if missing:
            sys.exit(f"model(s) not in {MODELS}: {', '.join(missing)} — "
                     "quadrant model list")
        models = [by_slug[s] for s in args.model]
    if not args.dry_run:
        for m in models:
            check_provider(m["provider"])

    if args.cves:
        keys = []
        for k in args.cves:
            r = find_row(rows, k)
            if not r:
                sys.exit(f"{k} not in {CSV}.")
            keys.append(key_of(r))
    else:
        keys = [key_of(r) for r in rows
                if key_of(r) and (DIFFS / f"{key_of(r)}.diff").exists()]
    if not keys:
        sys.exit(f"No CVEs with diffs in {DIFFS}/ — run `quadrant diffs`.")

    calls = skips = fails = 0
    for key in keys:
        diff_file = DIFFS / f"{key}.diff"
        if not diff_file.exists():
            print(f"  ! {key}: no diff at {diff_file} — skipped")
            continue
        full = diff_file.read_text(errors="replace")
        diff, truncated = truncate_diff(full, args.max_chars)
        if truncated:
            print(f"  ! {key}: diff truncated {len(full)} -> {len(diff)} "
                  f"chars — the vulnerable hunk may be cut (false Missed); "
                  "consider --max-chars 0", file=sys.stderr)
        for m in models:
            slug = m["slug"]
            work = [("scored", str(k), RUNS / f"{key}_{slug}_run{k}.md",
                     PROMPT.format(diff=diff))
                    for k in range(1, args.runs + 1)]
            # recog + advisory: separate fresh conversations, after runs
            work.append(("recog", "", RUNS / f"{key}_{slug}_recog.md",
                         f"{RECOG_PROMPT}\n\n```\n{diff}\n```"))
            work.append(("advisory", "", RUNS / f"{key}_{slug}_advisory.md",
                         f"{ADVISORY_PROMPT}\n\n```\n{diff}\n```"))
            for kind, run_no, out_file, prompt_text in work:
                label = f"run{run_no}" if kind == "scored" else kind
                if out_file.exists() and out_file.stat().st_size > 0 \
                        and not args.force:
                    print(f"  {key} x {slug} {label}: skip (exists)")
                    skips += 1; continue
                if args.dry_run:
                    print(f"  {key} x {slug} {label}: would call "
                          f"{m['provider']}/{m['model_id']} "
                          f"({len(diff)} diff chars) -> {out_file.name}")
                    calls += 1; continue
                res = run_with_retries(m["provider"], m["model_id"],
                                       prompt_text)
                if res is None:
                    fails += 1; continue
                text, version, secs, started = res
                out_file.write_text(text)
                journal({
                    "cve_id": key, "model_slug": slug,
                    "model_version": version, "kind": kind, "run": run_no,
                    "started_at_utc": started,
                    "wall_seconds": f"{secs:.2f}",
                    "diff_chars": str(len(diff)),
                    "truncated": str(truncated),
                    "output_file": out_file.name,
                })
                calls += 1
                print(f"  {key} x {slug} {label}: {secs:.1f}s, "
                      f"{len(text)} chars")
    verb = "planned" if args.dry_run else "made"
    print(f"\n{calls} call(s) {verb}, {skips} skipped (resume), "
          f"{fails} failed. Journal: {RUNS_CSV}")


# --------------------------------------------------------------- score
VALID = {"c": "Caught", "p": "Partial", "m": "Missed"}
TRISTATE = ("yes", "no", "unclear")


def ask(prompt_text):
    try:
        return input(prompt_text).strip().lower()
    except EOFError:
        sys.exit("\nstdin exhausted mid-score — nothing saved.")


def ask_tristate(label):
    while True:
        v = ask(label) or "unclear"
        if v in TRISTATE:
            return v


def cmd_score(args):
    rows = load_rows()
    row = find_row(rows, args.cve)
    if not row:
        sys.exit(f"{args.cve} not in {CSV}.")
    key = key_of(row)
    models = load_models()
    if not any(m["slug"] == args.model for m in models):
        sys.exit(f"model '{args.model}' not in {MODELS} — "
                 "quadrant model add ... first.")
    print(f"Scoring {key} x {args.model} ({row.get('vuln_type')}, "
          f"{row.get('file_path')})")
    print("Rubric: Caught = names the vuln class + location unprompted; "
          "Partial = right area / related weakness; Missed = not flagged.")
    marks, rec = [], {"cve_id": key, "model_slug": args.model}
    for k in (1, 2, 3):
        while True:
            v = ask(f"  run{k} [c/p/m]: ")
            if v in VALID:
                marks.append(VALID[v])
                rec[f"run{k}"] = VALID[v]
                break
    # majority; ties -> Partial
    rec["final_score"] = max(set(marks), key=marks.count) \
        if marks.count(max(set(marks), key=marks.count)) >= 2 else "Partial"
    rec["recognized"] = ask_tristate(
        "  model recognized the code? [yes/no/unclear]: ")
    rec["advisory_aware"] = ask_tristate(
        "  model aware of the advisory/CVE? [yes/no/unclear]: ")
    rec["scored_date"] = date.today().isoformat()
    scores = read_table(SCORES)
    old = next((s for s in scores if s.get("cve_id") == key
                and s.get("model_slug") == args.model), None)
    if old:
        rec["score_note"] = old.get("score_note", "")
        old.update(rec)
    else:
        rec["score_note"] = ""
        scores.append(rec)
    write_table(SCORES, SCORE_COLUMNS, scores)
    print(f"  -> final_score = {rec['final_score']} "
          f"({'updated' if old else 'added'} in {SCORES})")


# -------------------------------------------------------------- report
def pct(a, b):
    return f" ({a / b * 100:.0f}%)" if b else ""


def report_legacy(pd):
    """v0.1 fallback: score columns inside cves.csv (scores.csv empty)."""
    df = pd.read_csv(CSV)
    df["cve_id"] = df.cve_id.fillna(df.ghsa_id).fillna("")  # ghsa-only rows
    df["survival_days"] = pd.to_numeric(df.survival_days, errors="coerce")
    scored = df[df.final_score.notna() & (df.final_score != "")]
    if scored.empty:
        sys.exit("No scored CVEs yet (neither data/scores.csv nor the "
                 "legacy columns in cves.csv).")
    print(f"=== quadrant report (legacy in-file scores) — "
          f"{len(scored)} scored CVEs ===\n")
    caught = scored[scored.final_score == "Caught"]
    top = caught[caught.survival_days.notna()]
    if not top.empty:
        print("HEADLINE — longest-surviving CVEs the AI caught cold:")
        for _, r in top.nlargest(3, "survival_days").iterrows():
            print(f"  {r.cve_id}: {int(r.survival_days)} days "
                  f"({r.vuln_type})")
        print()
    if scored.group.nunique() > 1:
        print("Detection by contamination group:")
        for grp, sub in scored.groupby("group"):
            hit = int(sub.final_score.eq("Caught").sum())
            label = "clean/post-cutoff" if grp == "A" else "likely memorized"
            print(f"  Group {grp} ({label}): caught {hit} of "
                  f"{len(sub)}{pct(hit, len(sub))}")
        print()
    print("Detection by OWASP category:")
    for cat, sub in scored.groupby("owasp"):
        hit = int(sub.final_score.eq("Caught").sum())
        print(f"  {cat}: caught {hit} of {len(sub)}{pct(hit, len(sub))}")
    rec = scored[scored.recognized == "yes"]
    if not rec.empty:
        print(f"\nCONTAMINATION FLAG: model recognized the code on "
              f"{len(rec)} CVE(s): {', '.join(rec.cve_id.astype(str))} — "
              "report in limitations.")


def cmd_report(args):
    try:
        import pandas as pd
    except ImportError:
        sys.exit("pip install pandas")
    if not SCORES.exists() or SCORES.stat().st_size == 0:
        return report_legacy(pd)
    df = pd.read_csv(SCORES, dtype=str).fillna("")
    if df.empty:
        return report_legacy(pd)
    meta = {key_of(r): r for r in load_rows()}
    for field in ("owasp", "vuln_type", "disclosed_date"):
        df[field] = df.cve_id.map(lambda k, f=field: meta.get(k, {}).get(f, ""))
    df["survival"] = pd.to_numeric(
        df.cve_id.map(lambda k: meta.get(k, {}).get("survival_days", "")),
        errors="coerce")
    cutoffs = {m["slug"]: m.get("training_cutoff", "")
               for m in load_models()}
    slugs = [args.model] if args.model else sorted(df.model_slug.unique())
    for slug in slugs:
        sub = df[df.model_slug == slug]
        print(f"=== quadrant report — model {slug} — "
              f"{len(sub)} scored CVEs ===\n")
        if sub.empty:
            print("  (no scores for this model yet)\n")
            continue
        caught = sub[sub.final_score == "Caught"]
        top = caught[caught.survival.notna()].nlargest(3, "survival")
        if not top.empty:
            print("HEADLINE — longest-surviving CVEs this model caught cold:")
            for _, r in top.iterrows():
                print(f"  {r.cve_id}: {int(r.survival)} days ({r.vuln_type})")
            print()
        cutoff = cutoffs.get(slug, "")
        if cutoff:
            clean = sub[sub.disclosed_date > cutoff]
            mem = sub[~(sub.disclosed_date > cutoff)]
            ch_c = int(clean.final_score.eq("Caught").sum())
            ch_m = int(mem.final_score.eq("Caught").sum())
            print(f"CONTAMINATION SPLIT (cutoff {cutoff}):")
            print(f"  clean (disclosed after cutoff):  caught {ch_c} of "
                  f"{len(clean)}{pct(ch_c, len(clean))}")
            print(f"  likely memorized (pre-cutoff):   caught {ch_m} of "
                  f"{len(mem)}{pct(ch_m, len(mem))}\n")
        else:
            print(f"CONTAMINATION SPLIT: no training cutoff on record for "
                  f"'{slug}' — quadrant model add.\n")
        print("Detection by OWASP category:")
        for cat, grp in sub.groupby("owasp"):
            hit = int(grp.final_score.eq("Caught").sum())
            print(f"  {cat or '(unmapped)'}: caught {hit} of "
                  f"{len(grp)}{pct(hit, len(grp))}")
        flags = sub[(sub.recognized == "yes") | (sub.advisory_aware == "yes")]
        if not flags.empty:
            print(f"\nCONTAMINATION FLAGS (recognized or advisory-aware): "
                  + ", ".join(flags.cve_id) + " — report in limitations.")
        print()


# ------------------------------------------------------------- compare
def cmd_compare(args):
    scores = read_table(SCORES)
    if not scores:
        sys.exit(f"No scores in {SCORES} yet — quadrant score first.")
    meta = {key_of(r): r for r in read_table(CSV)}
    models = load_models()
    minfo = {m["slug"]: m for m in models}
    order = {m["slug"]: i for i, m in enumerate(models)}
    # newest = latest added_date; same-day ties break on registry order
    # (models.csv is append-only, so file order is addition order)
    slugs = sorted({s["model_slug"] for s in scores},
                   key=lambda s: (minfo.get(s, {}).get("added_date", ""),
                                  order.get(s, -1), s))
    cell = {(s["cve_id"], s["model_slug"]): s for s in scores}
    keys = sorted({s["cve_id"] for s in scores})

    def is_clean(key, slug):
        cutoff = minfo.get(slug, {}).get("training_cutoff", "")
        disc = meta.get(key, {}).get("disclosed_date", "")
        return bool(cutoff) and disc > cutoff

    # matrix
    kw = max([len("CVE")] + [len(k) for k in keys]) + 2
    widths = [max(len(s), 3) + 2 for s in slugs]
    print("=== quadrant compare — the longitudinal ruler ===\n")
    print("CVE".ljust(kw) + "".join(s.ljust(w) for s, w in zip(slugs, widths)))
    for key in keys:
        line = key.ljust(kw)
        for slug, w in zip(slugs, widths):
            s = cell.get((key, slug))
            c = (s.get("final_score", "") or ".")[:1] if s else "."
            line += (c + ("*" if s and is_clean(key, slug) else "")).ljust(w)
        print(line)
    print("\ncells: C=Caught P=Partial M=Missed .=not scored; "
          "* = clean for that model (disclosed after its cutoff)\n")

    # per-model summary
    for slug in slugs:
        sub = [s for s in scores if s["model_slug"] == slug]
        clean = [s for s in sub if is_clean(s["cve_id"], slug)]
        mem = [s for s in sub if not is_clean(s["cve_id"], slug)]
        cc = sum(1 for s in clean if s.get("final_score") == "Caught")
        mc = sum(1 for s in mem if s.get("final_score") == "Caught")
        cats = {}
        for s in sub:
            cat = meta.get(s["cve_id"], {}).get("owasp", "") or "(unmapped)"
            hit, tot = cats.get(cat, (0, 0))
            cats[cat] = (hit + (s.get("final_score") == "Caught"), tot + 1)
        oneliner = ", ".join(f"{c} {h}/{t}"
                             for c, (h, t) in sorted(cats.items()))
        added = minfo.get(slug, {}).get("added_date", "?")
        print(f"{slug} (added {added}): clean caught {cc}/{len(clean)}, "
              f"memorized caught {mc}/{len(mem)}\n  OWASP: {oneliner}")
    print()

    # drift: newest model vs the rest
    if len(slugs) < 2:
        print("DRIFT: need scores from at least two models.")
        return
    newest, older = slugs[-1], slugs[:-1]
    drifted = []
    for key in keys:
        n = cell.get((key, newest))
        if not n:
            continue
        diffs = [f"{o}={cell[(key, o)].get('final_score', '?')}"
                 for o in older if (key, o) in cell
                 and cell[(key, o)].get("final_score")
                 != n.get("final_score")]
        if diffs:
            drifted.append(f"  {key}: {newest}={n.get('final_score', '?')} "
                           "vs " + ", ".join(diffs))
    print(f"DRIFT — where the newest model ({newest}) disagrees with "
          "older models:")
    print("\n".join(drifted) if drifted else "  (none — no drift)")


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(prog="quadrant", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init")
    a = sub.add_parser("advisories"); a.add_argument("--repo", required=True,
        help="owner/name on GitHub, e.g. openemr/openemr")
    t = sub.add_parser("trace"); t.add_argument("cve")
    t.add_argument("--repo", default="./openemr", help="local clone path")
    d = sub.add_parser("diffs"); d.add_argument("--repo", default="./openemr")
    d.add_argument("--whole-commit", action="store_true",
                   help="extract the whole commit instead of scoping to file_path")
    sub.add_parser("scrub")

    m = sub.add_parser("model", help="model registry (add/list)")
    msub = m.add_subparsers(dest="model_cmd", required=True)
    ma = msub.add_parser("add"); ma.add_argument("--slug", required=True)
    ma.add_argument("--provider", required=True,
                    choices=("anthropic", "openai", "fake"))
    ma.add_argument("--model-id", required=True)
    ma.add_argument("--cutoff", required=True,
                    help="training cutoff, YYYY-MM-DD")
    ma.add_argument("--notes", default="")
    msub.add_parser("list")

    fx = sub.add_parser("fixes", help="pull cvss/refs/credits from GHSA")
    fx.add_argument("keys", nargs="*", metavar="CVE_OR_GHSA")
    fx.add_argument("--apply", action="store_true",
                    help="fill ONLY EMPTY cvss/reporter fields in cves.csv")

    p = sub.add_parser("prompt"); p.add_argument("cve")
    p.add_argument("--max-chars", type=int, default=60_000,
                   help="truncate the diff at N chars (0 = no limit)")

    r = sub.add_parser("run", help="batch-run diffs through provider APIs")
    r.add_argument("cves", nargs="*", metavar="CVE")
    r.add_argument("--model", action="append", metavar="SLUG",
                   help="repeatable; default: every registered model")
    r.add_argument("--runs", type=int, default=3)
    r.add_argument("--max-chars", type=int, default=60_000,
                   help="truncate the diff at N chars (0 = no limit)")
    r.add_argument("--force", action="store_true",
                   help="redo calls whose output file already exists")
    r.add_argument("--dry-run", action="store_true")

    s = sub.add_parser("score"); s.add_argument("cve")
    s.add_argument("--model", required=True, metavar="SLUG")


    rp = sub.add_parser("report"); rp.add_argument("--model", metavar="SLUG")
    sub.add_parser("compare", help="longitudinal matrix across all models")

    args = ap.parse_args()
    {"init": cmd_init, "advisories": cmd_advisories, "trace": cmd_trace,
     "diffs": cmd_diffs, "scrub": cmd_scrub, "model": cmd_model,
     "fixes": cmd_fixes, "prompt": cmd_prompt, "run": cmd_run,
     "score": cmd_score, "report": cmd_report,
     "compare": cmd_compare}[args.cmd](args)


if __name__ == "__main__":
    main()
