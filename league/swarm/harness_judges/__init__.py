"""The harness loop's FIXED judges, one per lane (`league/swarm/harness_lanes.py`, `Lane.judge`).

Each judge is a script the loop copies out of the reviewed release and runs, read-only, against a candidate tree and
its baseline in the credential-free sandbox (`improvement.sandbox`):
`/judge/<lane>.py --split dev|heldout --seed S --nonce-stdin [--pool-stdin] [--gate open|closed --key KEY]`. It imports
the tree under test from `/work` and prints one JSON line of counts carrying the per-run nonce it read from standard
input. `dev` is the fixed set in these public files the brief describes (the motivating failure shapes); `heldout` is
PRIVATE classes the dev split never uses, from the lane's pool (outside this repo, pinned by hash in
`harness_lanes.HELDOUT_POOLS`, read from standard input after the nonce), drawn from a seed that exists only once the
candidate is committed (`harness_lanes.heldout_seed`).
An arms-lane candidate is judged with its gate forced open (the change) and forced closed (which must equal the
baseline); `_regress.py` runs the lane's fixed regressions the same two ways. All inputs are synthetic: no quotes,
programs, parameters or account data. A candidate can never edit a judge (`harness_lanes.PROTECTED`). No provider
call, network or file write outside /tmp.
"""
