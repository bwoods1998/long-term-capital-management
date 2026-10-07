# Unconfirmed provider requests

A POST may reach Sail even if its response is lost. The provider cleanup sweep
therefore polls only requests with a saved response ID. Requests without an ID
retain their original reservation, status, error and accounting day after the
poll deadline and across restarts. Research cost accounting retains the same
hold. A terminal response with usable usage can replace it with the actual cost.

This repair prevents future timeout cleanup from releasing uncertain charges.
It does not settle historical `abandoned` rows, restore their old counters,
change request retries, certify an all-in daily cap, or migrate live databases.
Published token rates and the legacy reservation formula remain estimates.

## Review and rollout

1. Run the provider and research caller checks on the exact release head:

   ```sh
   python -m unittest ltcm.tests.test_provider league.tests.test_swarm_researcher league.tests.test_swarm_stage3
   ```

2. Before any authorized rollout, retain a consistent backup of the provider and
   research ledgers, the installed release identity, and the count and original
   reserved amount of unknown-cost requests. Keep historical `abandoned` rows
   visible as unresolved unless original provider billing evidence settles them.
   An empty recent-task list, a missing response, a timeout, and a local
   `abandoned` status are not zero-cost evidence. In particular, the existing
   `reconcile_budget_days` repair treats abandoned rows as released; it is not a
   historical invoice reconciliation tool.

3. Verify exact-head CI, rehearse release rollback using copies, and follow the
   deployment window and runbook. The shared provider can serve live trading
   processes; deployment of that execution stack remains an owner operation.

4. After rollout, monitor reservations separately from settled charges. With
   held requests present, the spend guard may correctly stop new research.
   Recover saved response IDs with passive GETs and reconcile any remaining
   unknown requests against original billing evidence. Do not clear holds merely
   to restore throughput.

Rolling application files back does not justify rolling the ledgers back. The
prior sweep may release no-ID holds again; keep affected inference stopped
through rollback and accounting review. Never reset an allowance or discard
requests, errors, accepted IDs or costs during recovery.
