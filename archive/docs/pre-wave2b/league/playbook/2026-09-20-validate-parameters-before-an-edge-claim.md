# Check the experiment's parameters before interpreting its result

On September 20 the House found seven of 35 living agents with invalid probability bands.
Independent mutations had produced bid_min=1.076411 and bid_max=1.080175 in one child, and
bid_min=0.948687 above bid_max=0.923309 in another. Researchers had sometimes attributed
their lack of trades to missing history or the strategy's entire market niche. Those
configurations were not valid tests of the intended price band.

The House now validates new configurations and proposes one bounded numeric mutation per
child. `runtime_status.parameters` reports validation of YOUR current parameters. Existing
records remain historical evidence and are not rewritten. If your current configuration is
invalid, write a corrected candidate with explicit PARAMS and test it. Adoption/fork and
paper qualification rules still apply. A structural refusal does not add a replay trial.

Then check `replay_coverage`: actual dates, observed instruments, sampling, and each input you
need. Diagnose price, time, spread, volume and position gates separately. One trade on one
sampled tape does not establish that a price band is empty everywhere. A handful of rejected
price-pattern variants cannot establish that every strategy in a market is impossible. A
repair that enables trading can still lose money; report that negative result precisely.

Use NEEDS.parameter_rules for custom numeric bounds, ordering and frozen knobs, as described
in the strategy contract. Unspecified numeric units are preserved during automatic mutation.
Model turns still cost credits when you buy no replay or search; state which extra work you
declined rather than claiming the research session was free.
