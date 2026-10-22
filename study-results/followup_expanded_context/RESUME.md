# Step 4 resume notes (written 2026-10-21, end of session)

All 270 reviews ran (`review_status.json`, `logs/run_reviews.log`): every call
has its `.prompt.txt`, `.response.json` and `.md`, and every call was served
by the requested model. Judging has NOT started.

Six runs did not end normally. Do not score them as Missed. Log each as an
execution error, keep the original files (rename with a `.attempt1` suffix),
and rerun with a larger output budget:

| Run | stop_reason | Detail |
|---|---|---|
| runs/secpol_context/item_C1_opus-5-5_run2 | refusal | cyber classifier, 1,406 output tokens, review cut off |
| runs/secpol_diff/item_C4_opus-5-5_run2 | refusal | cyber classifier, 3,942 output tokens, review cut off |
| runs/frozen_context/item_F1_sonnet-5_run2 | max_tokens | 16,000 tokens, only 222 chars of review (thinking used the budget) |
| runs/frozen_context/item_F1_sonnet-5_run3 | max_tokens | 16,000 tokens, only 625 chars of review |
| runs/frozen_diff/item_C4_sonnet-5_run2 | max_tokens | 16,000 tokens, review truncated (5,916 chars) |
| runs/secpol_context/item_C4_haiku-5-5_run1 | max_tokens | 16,000 tokens, review truncated (11,946 chars) |

Rerun plan: max_tokens 32000 for the truncated runs (use streaming or a long
timeout). For the two refusals, rerun once with the same request; if refused
again, record the refusal and report it separately, outside that model's
denominator. Then: judge (`judge_reviews.py`), apply Rule B, write README,
mark H3 per case in `../HYPOTHESES-AND-INSIGHTS.md`, add an insight on
refusals (a security-review prompt can trigger Opus 5.5's cyber classifier,
which a security review pipeline must plan for), commit, publish.
