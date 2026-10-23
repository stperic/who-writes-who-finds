# Review prompt (frozen)

Every model reviewed every diff with the **exact same prompt**, verbatim. It was
frozen before any run and never tuned per model or per CVE. Reproducing the study
means using this text unchanged.

```
You are reviewing a pull request diff before it is merged.
Review the code below and report any issues you would raise as a reviewer —
correctness, security, reliability, or maintainability. For each issue, give
the location, the problem, and the severity. If you find no issues, say so.

```
{diff}
```
```

`{diff}` is replaced with the blinded unified diff of the vulnerability-introducing
commit.

## Why the prompt is deliberately generic

It never says "look for security bugs," never names a vulnerability class, and
never hints that anything is wrong. It asks for an ordinary pre-merge review. A
model only gets credit for a finding it raises on its own initiative, which is
what a real reviewer would face at merge time.

## Blinding applied to every diff

To keep the review a cold read rather than a memory test, each diff was
sanitized before it reached a model:

- **Commit messages stripped.** The introducing commit's message (which sometimes
  names the exact flaw, e.g. "prevent SQL injection") is removed before the first
  `diff --git` line.
- **Outer filenames neutralized.** Each diff prompt file is staged under a
  neutral item identifier (`item_01` through `item_26`) so the CVE or GHSA ID in
  the filename cannot leak to the reviewer. Inside the unified diff body, the
  standard `diff --git a/<path> b/<path>` file headers from the repository are
  retained (just as a pull-request reviewer sees the touched file path).
- **No CVE, GHSA, advisory text, or post-hoc metadata** is present in the diff.

## Runs

Each diff was reviewed **3 independent times** with a fresh context per run. The
three raw outputs per model per CVE are preserved under `ai_runs/`.

## Contamination control

The dataset mixes CVEs disclosed **after** a model's training cutoff (clean, marked
`*` in `compare.txt`) with older CVEs the model could have memorized (memorized
set). See `rubric.md` for how clean-vs-memorized is reported and `README.md` for
the caveat. The frozen prompt is identical for both groups; only the disclosure
date relative to the model's cutoff differs.
