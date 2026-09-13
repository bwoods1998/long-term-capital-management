# A short tour of the working project

Start with the [public research page](https://blakewoods.us/portfolio/). Its research
runs are reviewed observations; the evidence replay uses fictional companies.
Neither is a portfolio return. Visitors read saved artifacts and cannot start paid
work.

## Understand one loop

The agent receives a question and checked facts, chooses permitted source queries
and calculations, saves a hypothesis, and writes a report. A second model critiques
it. Explicit review decides whether it becomes public and can seed later research.
SQLite preserves the evidence, requests, costs, and stopping point. Sail provides
inference and private workflow traces.

Read [Lesson 4](../lessons/04-research-loop.md), then inspect
[what the first investigation found](INVESTIGATION-RESULTS.md). The useful finding
was an accounting qualification: management's change to reported capex did not by
itself establish a change in underlying investment commitments.

## Try three predictions

Before opening the results, write down your answers:

1. A shorter evidence notebook saves input tokens. Must it reduce the whole bill?
   Check the [timeline replay](TRAJECTORY-REPLAY.md).
2. An identical prompt is almost entirely cached. Must its next answer cost less
   or finish faster? Check the [scheduling and cache pilot](POLICY-EXPERIMENT.md).
3. A test reports no fully passing answers. Does that prove the model failed its
   financial reasoning? Check the [source-instruction pilot](ROBUSTNESS.md), which
   exposed both an underspecified unit contract and real scale omissions.

The point is to separate an observation from the explanation we want to give it.
The raw failures remain in each experiment's record.

For a financial review exercise, [audit the net effect](REVIEW-CASE.md). The agent
and its critic highlighted two positive cash-flow contributions while overlooking
offsets in the full table. Check the arithmetic, then rewrite the summary.

## Inspect your saved work

```sh
python3 operations.py
python3 research_queue.py status
python3 source_watch.py status
```

These commands do not submit model calls. The [operations guide](OPERATIONS.md)
explains completed requests, reviewed research, unknown usage, and spending holds.
The source inbox detects changed pages; accepting a candidate still does not make
its numbers checked facts or buy another investigation.

For the next hands-on exercise, use [Lesson 5](../lessons/05-research-across-time.md).
Predict how one changed disclosure should revise the agent's prior view, then
compare its actual update. No API spending is needed to read the saved experiment.
