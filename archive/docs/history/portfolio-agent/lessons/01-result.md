# First observed result

Run `bb3e96f7-17c8-4d67-aea1-f9b0f38691fa`, September 7, 2026.

| Measurement | Result |
|---|---|
| Model | DeepSeek V4 Flash 0731 via Sail |
| Completion window | ASAP, background transport |
| Grading | 5/5 facts passed all checks |
| Status | Completed |
| Input tokens | 684 |
| Cached input tokens | 0 |
| Output tokens | 314 |
| Reported reasoning tokens | 0 |
| Estimated model cost | $0.00011808 |
| Client-observed wall time | 7.03 seconds |
| Local budget allowance held | $0.01 |

Cost arithmetic: `(684 × 0.09 + 314 × 0.18) / 1,000,000 = $0.00011808`.

At exactly this usage and these prices, one million calls would cost $118.08 in model usage. This is simple multiplication, not a forecast: caching, varying document lengths, failures, retries, volume constraints, and infrastructure expenses can change the result. Provider charges have not yet been reconciled with this estimate.

The builder's advance prediction was 5/5 and less than one cent. No user prediction had arrived before submission. A future trial should record the learner's prediction before execution.

We learned that this small request, response parsing, and grading path work against the live API. We have not established performance on unfamiliar documents. The five facts share one response and are not five independent trials. Zero reported reasoning tokens describes this run, not a guarantee about future runs or other settings. Polling time is not GPU serving time.

Your review: open `data/msft-2025.json`, check the original annual-report link, and verify the answer key. Then explain why $193,893 million of gross margin is different from a gross margin percentage.

Detailed local evidence is in `.data/runs.sqlite` and the JSON report named after the run ID. Print it without another paid call:

```sh
python3 lab.py report bb3e96f7-17c8-4d67-aea1-f9b0f38691fa
```
