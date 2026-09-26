# What the first investigator found

The assignment was narrow: **Do changes in reported capital expenditures imply a change in underlying infrastructure investment commitments?** We compared an agent with primary-source tools against one using only the checked financial packet. Both used DeepSeek Pro for research and Kimi K3 for critique.

The reviewed reports (`experiments/public/investigations.json`) are also on the [public research page](https://blakewoods.us/portfolio/). The reports are research observations, not portfolio recommendations.

## The accounting distinction

The tool-assisted investigation found a passage in Microsoft's earnings call that was not summarized in the initial packet. Management announced a longer estimated life for datacenters and office buildings and said more future datacenter leases would consequently be classified as operating rather than finance leases. Its reported capex definition includes finance leases but excludes operating leases. Management said its calendar-year investment expectations were unchanged apart from this useful-life effect. That is an attributed outlook, not independent proof of unchanged construction commitments. [Microsoft call transcript](https://www.microsoft.com/en-us/investor/events/fy-2026/earnings-fy-2026-q4)

The reported annual cash figures answer a different question. Cash PP&E outlays increased from $64.551 billion to $115.948 billion, while operating cash flow increased from $136.162 billion to $182.935 billion. The calculated remainder after cash PP&E fell from $71.611 billion to $66.987 billion. These are company-wide fiscal-year measures; they do not establish AI-only profitability or total investment commitments. [Microsoft financial results](https://www.microsoft.com/en-us/investor/earnings/fy-2026-q4/press-release-webcast)

The single-pass answer correctly preserved uncertainty about total commitments. The investigator added the specific lease-accounting explanation. Its extra tool access also means it observed more evidence, so this pair does not isolate a model-quality effect.

## All research attempts

| Attempt | Model calls | Tool calls | Outcome | Estimated cost |
| --- | ---: | ---: | --- | ---: |
| Initial investigator | 10 | 20 | Rejected after repair failed the output contract | $0.125172592 |
| Investigator after retrieval fix | 7 | 8 | Reviewed after an editorial correction and fresh critique | $0.069444196 |
| Single-pass comparison | 3 | 0 | Reviewed after an editorial correction and fresh critique | $0.025267560 |
| Total | 20 | 28 | Two reviewed reports; one rejected attempt retained | $0.219884348 |

Costs include the critic and editorial rechecks, and retain the unsuccessful attempt. They use reported token usage and saved prices, not an itemized provider bill. The separate 128-call [development evaluation](EVALUATION-RESULTS.md) cost an estimated $0.263369576. The two terminated [Sailbox attempts](SAIL-PRODUCTS.md) had observed finalized charges totaling $0.010. Combined new usage at this milestone was therefore approximately $0.493254, excluding any later experiment.

## Failures that changed the implementation

The initial retrieval fallback favored early passages containing common query words. The model repeated searches, and its conversation exceeded the 96,000-byte request envelope. Retrieval now ranks distinct query coverage and term rarity. A deterministic notebook removes repeated transcript text while preserving all observed passages, citation IDs, calculations, hypotheses, and source hashes. Resuming uses the original body whenever a request has already been reserved.

The first critic caught a headline that confused a forward-looking accounting change with already reported cash spending. The revised content improved, but the model returned one required array as a string. Local validation rejected it; the run was not reset or replaced in the record. The repair instructions now make the array contract explicit.

Critique still needed review. A later critic accepted an overconfident headline and overlooked a claim about what the prior view had said. We corrected the report editorially, preserved the original, and required another critique. The critic now receives the frozen prior memory so it can assess change claims. One critique summary also incorrectly wrote an exact equality between rounded quarterly amounts that did not add up. Public critique status therefore shows the verdict and issue count; its unreviewed explanatory prose stays private.

These observations distinguish three checks: valid JSON, a model's critique, and substantive review against evidence. None substitutes for the others.

## What this demonstrates

The agent chose source queries and calculations, found a useful accounting qualification, and recovered from growing context without discarding its evidence. Sail Voyages recorded real research stages, and the request ledger preserved costs and identities across interruptions. The experiment does not yet establish reliable research over months, broad source discovery, or investment performance. The next test changes evidence across multiple episodes and measures whether the agent retains, qualifies, and retracts the right conclusions.
