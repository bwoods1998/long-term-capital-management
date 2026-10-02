# The desk's daily scoreboard

From release V3-A (LTCM v3; [the run record](../2026-10-02-unattended-desk.md)), the House commits one file here a day,
by itself: `<YYYY-MM-DD>.md`, written by its `scoreboard` job (`league/ops/scoreboard.py`, daily at 23:30 UTC) and
committed to `main` through the gateway's `POST /v1/github/docs` route (commit messages start with `desk:`). Nobody
edits these files by hand.

Each page is built from an allowlist of the House's own figures and checked by a public filter before it is posted: no
account equity or balance, no quote, contract symbol, strike, box id, parameter or program text, and no Validation or
holdout figure. A page that fails the filter is not posted, and the job's receipt says so.

The gateway accepts only paths matching `docs/runs/desk/<YYYY-MM-DD>[-<slug>].md`, at most 64 KB each and at most six
commits a New York day. Until V3-A is deployed this directory holds only this note.
