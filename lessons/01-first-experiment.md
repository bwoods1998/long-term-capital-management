# Lesson 1: What does one correct result cost?

Our first learning objective is to follow one model request all the way from source data to a financial conclusion.

## Before looking at the result

Predict whether the model will get all five facts correct, whether it will cost less than one cent, and which mistake is most likely. Write a sentence explaining why. A wrong prediction is useful: it gives us something specific to investigate.

## The source

Open `data/msft-2025.json`. It contains five factual rows from Microsoft's 2025 annual report, with both 2025 and 2024 figures. The task asks for 2025 values in USD millions. Gross margin is an amount here, not a percentage. The source link lets you check our transcription.

The `expected` values are reference answers checked by the builder against the source. You should verify them independently. Those reference-answer fields stay in the local evaluator; the model receives the passage and requested field names. This is a development example, not a held-out benchmark.

## Follow the code in four steps

1. `build_request` in `lab.py`: turns the passage and output requirements into an HTTP request. Run `python3 lab.py preview` to see it for free. `max_output_tokens` limits generation; it is not a requested answer length.
2. `reserve` and `execute`: save a trial before sending it, then submit and poll for its result. Background mode means the work can continue after our connection ends. The saved request ID lets us retrieve that work again.
3. `grade`: compares five facts with reference answers. Each fact must have the right value, currency, unit, period, and exact source row. Valid JSON does not establish financial correctness. Exact-row grading is deliberately strict and can reject harmless formatting differences.
4. `estimate_cost`: converts token counts into an estimated dollar expense using a dated price snapshot. The provider's invoice is a separate measurement.

You do not need to memorize Python syntax. Start by identifying what each function accepts, what it returns, and what can go wrong.

## Work through the arithmetic

At the current DeepSeek rate, suppose a request uses 1,000 input tokens, including 200 cached tokens, and 100 output tokens:

`(800 × $0.09 + 200 × $0.02 + 100 × $0.18) / 1,000,000 = $0.000094`

Cached tokens are already inside the input total. Reasoning-token details must not be blindly added on top of an output total that already includes them. The run saves the original usage fields for inspection.

Task success requires all five facts to pass and a completed response. For several trials:

`cost per successful task = spending across all trials / successful tasks`

If nothing passes, report the metric as undefined, not zero. Missing usage also means unknown cost, not free work.

## Inspect your actual result

`python3 lab.py report RUN_ID` prints the answer, each grading result, token usage, elapsed wall time, and the cost estimate. A JSON report also lives in `.data/`.

The timing is when our client observed the result. It includes queueing, network and polling, and any pause before resuming. It is not GPU execution time or time to first token.

## Explain the result before the next experiment

- Does 5/5 on this table tell us the model can read a full annual report? Why?
- If it used fewer tokens but made one financial mistake, would it be cheaper in a useful sense?
- What changes financially if we repeat the task a million times?

Next, change one source value locally and predict the output without changing the prompt. Update the reference answer to match and label the new case as synthetic. This checks whether the model follows supplied evidence rather than reproducing a familiar company's memorized figures. After that, introduce unfamiliar held-out passages and ambiguous units. We will record such changes as new experiments rather than rewriting an old result.
