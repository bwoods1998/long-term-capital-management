# Research across time

Our smaller evidence notebook passed the same checks as full history, but cost
more. That is the useful surprise in this experiment: fewer input tokens can lead
to more output tokens, so context size alone is a poor cost scoreboard.

The [recorded replay](../public/trajectory-replay.json) follows three fictional
companies through four research updates each. Two models each use two memory
policies: 48 completed updates, all passing, for an estimated **$0.08635**. These
are authored development cases, not evidence of investing ability. No portfolio
trades, future returns, or real disclosures were predicted.

The controller and model have different jobs. Ordinary code admits dated evidence,
rejects duplicates, and records which document replaces another. The model reads
that evidence and supplies a typed research view. Its prior answer is carried
forward as a fallible belief, never promoted into an authoritative source.

Full history retains earlier documents and earlier model views. The notebook keeps
current documents, replacement references, and the latest model view. Each next
request is frozen only after its predecessor finishes. This tests research across
updates rather than independent answers to unrelated questions. Both policies get
the same current eligible evidence; the comparison changes historical documents
and historical beliefs together.

Run these three exercises from the repository root. They only read local files;
they require no API key and make no paid requests.

## 1. Predict a correction before checking it

Cedar Compute is fictional. Its FY2025 operating cash flow was 110 and cash
property-and-equipment spending was 70. FY2026 initially showed 160 and 135,
respectively. All amounts are USD millions. A later correction changes FY2026
spending to 105.

Before running the command, calculate the cash proxy for each version. Does its
annual direction change? Should this correction also change management's separate
forecast that reported capex will fall because of accounting classification while
planned investment commitments stay unchanged?

```sh
python3 - <<'PY'
import json
result = json.load(open('public/trajectory-replay.json'))
step = next(s for s in result['steps']
    if s['trajectory'] == 'cedar-correction' and s['step'] == 3
    and s['policy'] == 'full_history' and 'Flash' in s['model'])
print('Expected:', step['expected']['values'])
print('Observed:', {k: v['value'] for k, v in step['observed'].items()})
PY
```

The arithmetic is 40, then 25, corrected to 55. The annual comparison becomes
rising. The forecast remains unchanged/accounting: a corrected historical cash
payment and management's future commitments are different facts. Company-wide
cash flow also cannot establish AI-only investment returns.

## 2. Price the whole answer

```sh
python3 - <<'PY'
import json
from decimal import Decimal as D
result = json.load(open('public/trajectory-replay.json'))
for row in result['conditions']:
    print(row['model'], row['policy'], row['cost']['usage'],
          row['cost']['estimated_usd'])
premium = D('0.04623102') - D('0.03503610')
saving_per_cached_token = (D('.66') - D('.022')) / D(1000000)
print('Hypothetical extra cached tokens needed:',
      premium / saving_per_cached_token)
PY
```

Pro's notebook used 11,313 input tokens versus 12,927 for full history. Output rose
from 13,386 to 19,578; estimated cost rose about 32%. Flash showed the same direction,
with about 12% higher cost. Reported reasoning tokens are already part of output
usage; do not count them twice. One run does not establish why output increased.

The calculation uses the September 12 Pro Flex price snapshot: $0.66 regular and
$0.022 cached input per million tokens. Holding both observed output lengths and
the full-history bill fixed, notebook-only caching would need about 17,547 tokens
to erase its premium—more than its entire input. Actual cached usage was zero.
Caching also requires eligible reuse; you cannot simply label tokens cached.
Compare this hypothetical with the separate upfront-write break-even calculation
in [Sail products](../docs/SAIL-PRODUCTS.md#cache-economics-before-enabling-another-product)
and the [provider's pricing](https://docs.sailresearch.com/pricing).

## 3. Distinguish recovery from useful research

```sh
python3 - <<'PY'
import json
result = json.load(open('public/trajectory-replay.json'))
print('Recovery:', result['recovery'])
print('Observed gates:', result['gates']['executed_per_path_counts'])
PY
```

The first process saved an accepted response ID and exited. A fresh process
retrieved that same response against the same frozen request and reservation,
without submitting a replacement. Explain which records must survive a crash.
This demonstrates operational recovery, not recovery from a mistaken investment
belief. No model step failed here, so the latter remains untested. Likewise,
rejecting an unapproved document before inference does not test whether a model
resists instructions inside an approved document.

Useful wakeups matter too. The [source watcher](../docs/SOURCE-WATCH.md) found that
two Microsoft pages changed their request trace identifiers between downloads.
Those differences were noise, not new financial disclosures. A narrow, versioned
filter ignores only that known line while preserving raw captures and changed
financial figures. Accepted source changes still require curation. The separate
[reviewed bundle handoff](../docs/SOURCE-CURATION.md) now has an offline synthetic
integration proof; it is not a result established by this replay or a live new
financial disclosure.

Choose one harder next case: a wrong prior belief, conflicting approved sources,
or a missing correction. Write the expected behavior before asking any model.
