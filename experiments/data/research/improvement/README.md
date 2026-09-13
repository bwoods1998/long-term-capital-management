# A bounded prompt-improvement gate

This changes an **evidence-claim critic prompt**, not the investigator's report
critic, trading policy, code, financial thesis, or publication approvals. The
initial champion is the existing `research_eval.SYSTEM_PROMPT`, without weakening
it to make a candidate look better. `build_current_claim_request()` exposes the
champion through that specific claim/verdict contract; its caller still needs an
authorized task and a reservation in the existing research ledger.

The first protocol uses 8 newly authored synthetic development cases and 8
separately authored validation cases. All companies and sources are fictional.
The validation set includes cross-layer double counting, withdrawn guidance,
mixed-currency comparability, concentration, cash-flow classification and timing.
It reuses neither the old 16-case Microsoft regression set nor the development
claims/evidence. Expected labels, support groups and rationales stay out of all
critic evaluation requests. The prompt generator receives development feedback
only. These public fixtures are not a secret, independently collected holdout.

One cycle freezes the cases, baseline, model/profile, budget envelope, deadline,
and implementation/grader hashes before paid work. It then runs:

1. Eight development responses from the baseline.
2. One candidate proposal using only those development cases and grades.
3. Eight development responses from the frozen candidate.
4. Paired baseline/candidate responses on eight validation cases, alternating
   which prompt goes first. Each request is independent of its mate's answer.

The proposal parser accepts a single JSON object or one complete JSON code
fence. Duplicate keys, extra prose/fields and malformed proposals stop the cycle;
there is no automatic redraft. Evaluation responses retain the same strict plain
JSON grading for both prompts.

The default is DeepSeek V4 Flash ASAP. Both conditions use the exact same model
and profile. The ceiling is 33 calls / $3.30 in conservative reservations, with at
most four accepted calls in flight. These are maximum allowances, not expected
charges. Pro Flex is an explicit option at $6.60 maximum. Every request, including
the proposal, uses `portfolio.reserve_task` and `portfolio.execute`; there is no
second spend path or reset of the shared budget. Creation itself makes no calls.

Promotion requires all 32 evaluations, zero full-pass regressions on **either**
set, and at least one full-pass gain on **each** set. Identity and usage must be
confirmed, no request may exceed its allowance, the global budget must still be
valid, and the champion must remain the same one the cycle began with. A tie,
regression, invalid candidate or incomplete evidence of improvement leaves the
champion unchanged. Provider failures/invalid responses remain scored failures;
unknown identity or usage blocks promotion. This rule can legitimately reject a
candidate when a strong baseline already passes every case.

A validation case is consumed at cycle creation. Another cycle cannot reuse even
one of its claim/evidence fingerprints; renaming IDs does not refresh it. Future
cycles require genuinely fresh validation. This reduces repeated test tuning but
cannot detect semantic paraphrases or establish statistical independence.

Grades check labels, format, citation membership/cutoff and authored support
groups. They do **not** grade the prose explanation or arbitrary semantic citation
entailment. Extra eligible citations are allowed, so citing every eligible item
can satisfy support coverage. A promotion therefore establishes only improvement
on these small authored checks. It does not demonstrate better investment skill,
financial forecasts, general research reasoning, or long-term autonomy. One
response per prompt/case also leaves model variability unresolved.

The immutable receipts retain failed attempts and old champions. The current
pointer is verified against an append-only hash chain. Rollback appends another
event; it never deletes a promotion, result, reservation, or response. New work
stops at the deadline; an explicit later `advance` can retrieve an already
accepted response under its original ID. Code/profile changes block new
submissions while accepted requests remain recoverable.
Recovered responses are saved, but new grades and promotion wait until the
frozen implementation matches again.

```sh
python3 self_improve.py start --key critic-cycle-001 --deadline 2026-09-13T07:00:00Z
python3 self_improve.py run CYCLE_ID --seconds 900
python3 self_improve.py status CYCLE_ID
python3 self_improve.py champion
python3 self_improve.py rollback 1 --reason 'Restore the initial critic prompt'
```

Use a future UTC deadline. An interrupted cycle resumes with the same ID;
repeating `start` with the same key and identical frozen inputs is idempotent.
`--candidate path.txt` skips proposal generation for an explicit offline-authored
candidate; the paired evaluation still uses the same gate. No actual measured
outcome is implied by the offline oracle tests.
