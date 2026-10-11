# Release E4: the patches to existing files, one file an author

Release E4's packages own NEW files outright. A change to a file that EXISTED before E4 is never made in a package's
worktree: its E4 author writes it here, in that author's own file `<key>.md`, as an exact unified diff against the
integration head (anchored by statement, never by line number: E1 and E2 are still receiving review fixes), with the
test that holds it. The integrator applies the diffs in the order of the table below and re-checks every anchor first.
One author a file, so no two worktrees ever touch the same one. The whole contract is `league/xs/E4_INTERFACES.md`.

| # | existing file | author | the change |
|---|---|---|---|
| 1 | `league/swarm/store.py` | G | `EQUITY_STRUCTURES` gains "panel"; `OPTIONS_ONLY_SQL` and the `families(lanes=...)` scope are built from it; `add_family` admits "panel" only with lane "equity" |
| 2 | `league/swarm/bands.py` | G | the two SQL scopes read `EQUITY_STRUCTURES`; band currency from the running code (`_xs_sha`, `current_xs_evaluator`, `equity_proof_current` by the proof's engine); `equity_seating(..., seatable=)` |
| 3 | `league/swarm/evaluator.py` | E | `adopt_equity` skips structure "panel"; `adopt_xs(store, expected)` under `XS_KEY`; `XS_SELECTION_KEYS`; the lineage records are never cleared |
| 4 | `league/swarm/elane.py` | G | `STRUCTURES` gains "panel"; `_members` reads `store.EQUITY_STRUCTURES`; `card_errors`, `validate`, `look` and `view` forward a panel card or family to `elane_xs`; `cfg` passes the `panel` block and `screens.equity_xs` through |
| 5 | `league/swarm/cards.py`, `league/swarm/dlane.py` | G | a card may declare `structure: "panel"`; `declared_lane`'s structure literal reads `store.EQUITY_STRUCTURES` |
| 6 | `league/swarm/elane_births.py` | G | the PANEL block of `EquityPass.request`; `admit` and `birth` take structure "panel" and stamp `hidden_year` through `elane_xs.assign`; `EquityQuota` splits by `elane_xs.quota`; `researching` skips panel families |
| 7 | `league/swarm/elane_train.py` | G | `EquityResearcher.score`, `brief`, `restart` and `step` forward a panel family to `elane_xs`; `train_map`, `closed_cells` and `refuted_rows` skip panel families; `train_map_text` appends `elane_xs.train_map`; `may_validate` reads the panel record; the equity review of a panel program carries `elane_xs.REVIEW_XS` (the captain's A22 (3): no embedded return table, no calendar recognition) |
| 8 | `league/swarm/elane_seal.py`, `league/swarm/elane_yield.py` | G | `SEALED_KEYS` gains `elane_xs.SEALED` (eight keys); `train_counts` also counts `elane_xs` passes |
| 9 | `league/swarm/settings.py`, `league/swarm/policy.json`, `league/swarm/loop.py` | G | the `elane.panel` block and `screens.equity_xs` (nulls, in `league.xs.screen.PIN_KEYS`' order: the INTEGRATOR fills the pin from the receipt, `screen.PIN_SOURCES`, in the commit that lands `docs/benchmarks/equity_screen_xs_1.json`); `adopt_xs` at the start beside `adopt_equity` |
| 10 | `league/ops/registry.py` | A | the six job rows (`equity_universe`, `equity_panel`, `equity_spreads`, `equity_neff`, `french`, `xs_zero_edge`) |
| 11 | `league/ops/funnel.py`, `league/ops/twins.py` | B | independent asset-years beside simulated program-years; a panel lot's half-spread |
| 12 | `league/equity/kinds.py`, `league/equity/live.py` | H | `BOOKS`, `book_for`, `kind_of`; B1-B15 less B7 and B12, ONE patch |
| 13 | `league/ops/dlane_report.py` | H | a panel close's lines, XS1's sentence beside EVERY live panel trade among them; every recorded style-open passer and why it holds no seat (`elane_xs.style_of`, `league.xs.style.seat_refusal`: the captain's A22 (1)) |
| 14 | `league/tests/test_equity_decider.py` | D | the panel kind now serves five ops (the slot test becomes the ops test) |
| 15 | `league/constitution.py`, `gateway/lib/caps.mjs`, `gateway/test/stock-buys.test.mjs`, `league/tests/test_equity_money.py`, `league/ops/preopen.py` | I | THE UNIVERSE (moves the money digest; deployed separately): ONE commit, made LAST by the integrator; the gateway's half is the patch file the captain named, never an edit of gateway/ |
| 16 | `league/ci.py`, `league/tests/test_ci.py`, `docs/operations.md`, `CHANGELOG.md` | I | the protected paths; `stock_agreement` names at most 10 tickers a side; the live rules by close date, word for word; the lane's switches and rollback; the captain's A22 as the House holds it (a style-open passer takes no seat on an XS1 pass alone; 2 looks an agenda cell; the review and the contamination probe before a look) |
| 17 | E3's seven forward modules | J | OWED: after release E3 |
| 18 | E3's `league/ops/contam_probe.py` | B | OWED: after release E3 |

Merge order on green CI: C0, A, B, C, D, E, G, H, then I (J after E3).
