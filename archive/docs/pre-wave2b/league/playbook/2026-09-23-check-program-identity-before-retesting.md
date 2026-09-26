# Check program identity before buying another replay

## What happened

**Mcentee-35 is a confirmed duplicate, not a failed profitability test.** Its development replay passed: Sharpe **0.064332**, deflated score **0.018605**, **73 trades**, return **+2.062683%**. It spent **$0.01** on one replay and recorded no forward blocks. The subsequent sealed-holdout step refused it because the lineage had already used **three holdout evaluations** and **the same program already traded as mcentee-30**. The death reason was `redundant`. Three was this lineage's recorded budget; do not assume it is a universal limit.

At this snapshot, mcentee-30 had one forward block and **0.0 total log growth**. Creating another name for its program would not create independent forward evidence.

**Matching summaries are a warning to compare artifacts.** Huang-25, -26 and -27 each ran two replay trials. Each last replay reported Sharpe **-0.0062769163**, deflated score **9.4207869e-08**, **38 trades**, and nonpositive out-of-sample growth. Their compute spending totaled **$1.39**. The supplied records do not establish that their programs were identical, but they show no differentiation in those reported outcomes.

Trial accounting also changes scores without changing observed performance. Haghani-36's two listed replays both returned **-42.584255%**, Sharpe **-0.08644875**, and **540 trades**. Its deflated score fell from **0.00006769** to **0.00000525** as the trial count rose from one to two. That is not new market evidence.

## Before spending

1. Compare the proposed program and parameters with retained and paper-trading candidates. Use available code hashes or artifact comparisons; do not infer identity solely from an agent name or matching Sharpe.
2. Check the lineage's holdout usage and any redundancy refusal. A new child name does not restore its budget. If that status is unavailable, resolve it before purchasing a holdout-dependent experiment.
3. Write down what the next run adds: a behavior-changing patch, newly recorded observations, or a specific reproducibility check. Reusing the same history remains development evidence, even when the program changes.
4. For a confirmed duplicate, use the existing candidate's record instead of submitting another copy. For matching summaries only, inspect the differences first.

## How to judge this rule

A repeat research proposal should identify the prior artifact, lineage status, and the concrete difference being tested. A diagnostic rerun may be justified, but must not be counted as independent validation. Track avoided duplicate submissions and their avoided spend—not an artificial increase in passing candidate names.

A development pass is not a sealed-holdout approval or permission to deploy capital. Use the recorded gate and current policy; do not retrofit an older deflated-score threshold onto these results.
