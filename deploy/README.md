# Owner deployment

`scripts/floor_box.py` stages `league`, `scripts` and `deploy` into immutable Sail release directories, runs an isolated synthetic options canary, promotes the release and watches health with an available rollback. Runtime state and credentials stay outside those directories.

The floor bootstrap installs the pinned numpy dependency into the House interpreter; sealed Gym images have their own full data dependencies. A canary verifies the program runtime, option structure arithmetic and money table without venue access or model calls.

Use `floor_box.py status --json` to identify the actual current/previous release and pending verdict. `deploy --help` and `rollback --help` show the current owner interface. Automatic updates default off and no workflow automatically merges a change.

Wave 2b changes the money digest and upload trees. It remains a draft until after Monday's close and requires an owner release, current state-aware rollback floor and grant re-ratification. Do not deploy from 13:25 to 20:05Z on a trading day except a rollback. The complete sequence and private data-worker configuration are in [operations](../docs/operations.md).
