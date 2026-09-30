"""The harness loop's FIXED judges, one per lane (`league/swarm/harness_lanes.py`, `Lane.judge`).

Each judge is a script the loop copies out of the reviewed release and runs, read-only, against a candidate tree and
its baseline in the credential-free sandbox (`improvement.sandbox`): `/judge/<lane>.py --split dev|heldout --seed S`.
It imports the tree under test from `/work` and prints one JSON line of counts. `dev` is the fixed set the brief
describes (the motivating failure shapes); `heldout` is generated from the seed, which exists only once the candidate
is committed (`harness_lanes.heldout_seed`). All inputs are synthetic: no quotes, programs, parameters or account data.
A candidate can never edit a judge (`harness_lanes.PROTECTED`). No provider call, network or file write outside /tmp.
"""
