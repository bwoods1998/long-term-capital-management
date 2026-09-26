# Lesson 2: A thesis that remembers its evidence

V1 maintains one research view across separate runs. You supply checked evidence, Sail drafts an interpretation, and explicit review decides what becomes memory and what can be published. It does not retrieve new filings, schedule its next review, or trade.

## Predict before reading the draft

Open the evidence packet notes (`experiments/data/thesis/README.md`). Microsoft's operating cash flow increased from FY2025 to FY2026. Predict whether cash remaining after cash PP&E spending increased too, and whether these figures can establish the return on AI investment. Write one sentence and identify what additional evidence you would want.

These commands make no API calls:

```sh
python3 portfolio.py preview
python3 portfolio.py status
```

`preview` shows the complete request. On the first run, previous memory is empty. After a reviewed revision exists, its thesis and original evidence appear in the next request. `status` lists local runs, including unsuccessful ones; use `status RUN_ID` to inspect an individual draft.

## Check the financial argument

All amounts below are USD millions, for the full company:

| Calculation | FY2025 | FY2026 |
|---|---:|---:|
| Operating cash flow | 136,162 | 182,935 |
| Cash PP&E spending | 64,551 | 115,948 |
| Cash after PP&E | 71,611 | 66,987 |

Operating cash flow rose, but cash PP&E spending rose by more. The remainder declined by 4,624. Check the subtraction yourself against the [cash flow statements](https://www.microsoft.com/en-us/investor/earnings/fy-2026-q4/press-release-webcast).

That is a useful observation, not proof that the investments were good or bad. The figures are company-wide, do not isolate AI cash flows, and do not include every finance-lease commitment in cash PP&E. Future investment returns remain unknown. Management commentary is attributed evidence, not an independently verified causal explanation.

Choose one claim in the draft. Follow its evidence ID to the packet and original source. Does the evidence support the claim, or merely discuss the same subject? Valid citation IDs and valid JSON do not answer that question.

## Follow memory through the code

Read these functions in portfolio.py (`experiments/portfolio.py`):

1. `build_request` sends the checked packet and last reviewed thesis. A long context window is not a substitute for a saved record.
2. `reserve` and `execute` save a logical run before calling Sail, then retrieve accepted work by its response ID.
3. `finalize` validates a completed draft and creates an immutable revision. A draft alone does not advance memory.
4. `review` advances the current thesis after substantive checking. `public_snapshot` exports only the reviewed chain and selected public fields.

Two drafts can start from the same parent. Once one is reviewed, the other cannot replace it as though nothing changed. A new investigation must use the updated memory.

Write one concrete event that would make you reconsider the current view. The `next_review` text records such a trigger; V1 will not wake itself when that event occurs.

## An unsuccessful attempt still has economics

The first September 12 attempt, configured with a 4,096 output-token limit, ended `incomplete` and reported usage. Another attempt completed but failed local draft checks. Neither produced an accepted thesis; both had estimated token costs. The output limit is a ceiling, not a promise of a finished answer. The current model and request envelope are visible in `preview`.

Explain why cost per accepted thesis must include unsuccessful attempts. If there are no accepted results, the metric is undefined. If usage is unknown, it is not zero. Budget reservations, list-price estimates, and provider-billed charges are three different quantities.

Use the saved run ID to inspect or resume work; starting another `research` command creates another paid investigation. See the [V1 guide](../pre-portfolio-2026-09-13/V1.md) before submitting, reviewing, or publishing a new revision. Predictions attached to the initial builder runs are the builder's expectations, not a substitute for your own answer to this exercise.

## Connect the lesson to account data

```sh
python3 brokerage.py demo
```

This is an entirely synthetic accounting exercise. Explain why an order for three shares adds only two purchased shares, and why the net external funding is excluded from the reported investment P&L. Then explain why that P&L amount alone is not a time-weighted return.

Finish by writing what you would verify before replacing any synthetic field with a real brokerage observation. That is the next stage.
