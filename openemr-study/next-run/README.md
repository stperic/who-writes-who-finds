# Matched review runner

`study.py` uses 24 fixed vulnerability diffs, 10 benign-control diffs, two models, two prompts, and three independent reviews per combination. The case and control manifests bind each input to a SHA-256 hash. `protocol.json` defines the model IDs, prompts, settings, and job order. `truth.json` and the rubric are used by the separate judge, not sent to the reviewer.

The runner schedules the first five Haiku generic cases as a checkpoint, then interleaves the remaining jobs. `prepare` writes the input snapshot and exact request JSON before any model call. Each API call starts a fresh conversation; the runner stores requests, responses, usage, timing, and judgments under the chosen output directory.

```sh
python3 openemr-study/next-run/study.py plan
python3 openemr-study/next-run/study.py prepare --out build/openemr-run
```

Complete `build/openemr-run/ground_truth_signoff.json` from the generated template before execution. Set `ANTHROPIC_API_KEY`, then run:

```sh
python3 openemr-study/next-run/study.py run --out build/openemr-run --phase checkpoint --execute
python3 openemr-study/next-run/study.py judge --out build/openemr-run --phase checkpoint --execute
python3 openemr-study/next-run/study.py run --out build/openemr-run --phase rest --execute
python3 openemr-study/next-run/study.py judge --out build/openemr-run --phase rest --execute
python3 openemr-study/next-run/study.py verify --out build/openemr-run --complete
python3 openemr-study/next-run/study.py packet --out build/openemr-run
python3 openemr-study/next-run/study.py summarize --out build/openemr-run
```

The `packet` command writes a blind review packet and a separate private key. `summarize --human-csv PATH` incorporates completed human scoring rows. Run `study.py --help` for command options.
