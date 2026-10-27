# OpenEMR review study scripts

This repository contains the runnable scripts and fixed inputs for the OpenEMR review experiments. Run outputs belong in a local `build/` directory.

| Script | Purpose |
|---|---|
| [`quadrant-tool/quadrant.py`](quadrant-tool/quadrant.py) | Prepare historical vulnerability diffs and review inputs. |
| [`openemr-study/next-run/study.py`](openemr-study/next-run/study.py) | Prepare the matched model and prompt run, execute reviews and judgments, verify records, and summarize scores. |
| [`openemr-study/snyk-baseline/run.py`](openemr-study/snyk-baseline/run.py) | Check out each pinned OpenEMR revision and run a whole-repository Snyk Code scan. |
| [`openemr-study/snyk-baseline/analyze.py`](openemr-study/snyk-baseline/analyze.py) | Build a review queue from saved Snyk SARIF output. |
| [`openemr-study/snyk-baseline/compare_runs.py`](openemr-study/snyk-baseline/compare_runs.py) | Compare saved Snyk scans across repetitions. |
| [`openemr-study/automated-context/run.py`](openemr-study/automated-context/run.py) | Select related source context, prepare requests, and run the context experiment. |

Start with the local, read-only plan:

```sh
python3 openemr-study/next-run/study.py plan
```

See [`openemr-study/next-run/README.md`](openemr-study/next-run/README.md) for the run sequence. Each script also provides `--help`. Reviewer calls require `ANTHROPIC_API_KEY` and an explicit `--execute` flag. Snyk scans require an authenticated Snyk CLI and an OpenEMR checkout.
