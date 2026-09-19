# The pause and the clean slate (Sept 19, 2026, 03:30-04:10 UTC)

The owner stopped the floor to rebuild the project properly. What was done, in order, and what
it left behind.

## The floor

1. `scripts/floor_box.py stop` engaged the kill switch, latched `/workspace/STOP` so the
   supervisor cannot restart the loop, and quiesced the loop (36 s).
2. Every resting order on both venues was cancelled, and every real position was closed with
   limit orders a cent through the touch. Twenty of twenty-seven closed. The refusals were
   fractional contract sizes (Kalshi trades whole contracts), the critic refusing a close-out
   rationale that read like a memo, and one venue rejection; the rerun with whole sizes and a
   plain close-out rationale cleared the rest.
3. Seven positions remain, all Sept 18 weather contracts and a 0.40 fractional Fed contract.
   Nothing rests on either venue. They settle at the venue without the floor.
4. Kalshi: $277 equity, $253 cash. Coinbase: $584, flat.

## The state

`/workspace/.data/ltcm` was archived to `/workspace/.archive/ltcm-state-20260919T034032Z.tar.gz`
(507 MB) and emptied: the event tape, the ledgers, the model-spend ledger, the research cache,
the strategy store, the Foundry lane states, the checkpoints, the publish cursor and the
service state. `ltcm/desks` and `playbooks` were archived too and cut back to the four founding
desks. Only the kill switch remains.

## The website

A token-guarded `POST /api/capital/reset?confirm=erase-everything` clears the published tape,
the balance history, the checkpoint and the desks. It cleared 20,000 events, 660 history
points, one checkpoint and 36 desks, so tracked profit, Sail spend, the self-improving clock
and the all-time performance chart all start from nothing.

The loop page (`/capital/committee/`, "The loop" and "Everything") is retired: its address
redirects to the floor, nothing links to it, and one page holds the project. `IN_DEVELOPMENT`
in `capital/capital.js` makes every live indicator read "in development" with the pulse
stopped; set it false when the loop trades again.

## Sail

All 63 LTCM boxes are paused: 62 research and desk sandboxes, then the floor box itself. The
first pause of the floor box failed with a guest-agent dial timeout and succeeded on a retry a
minute later. Only an explicit `resume` brings any of them back.

## Starting again

`scripts/floor_box.py resume` then `start` releases the kill switch and the STOP latch. The
floor will bootstrap the four founding desks and an empty tape. Nothing about the old run
carries over except the archives on the box and this repository.
