# E4 patches authored by package J

Package J (the forward twin: `league/ops/forward_xs.py`) authors patch 17, the dispatches release E3's forward
modules gain. They are APPLIED in this tree (branch `feat/equity-e4-j`, on `feat/equity-e4` at 4700fa1d), so this
file is a record: each change, its anchor (a statement, never a line number) and the test that holds it. The exact
diff is the branch's own (`git diff 4700fa1d -- league/ops/`).

(This file lies under league/swarm, where release E3's seal lets no text name the forward store, its files or
one of its tables: they are named by their role here, and by name in `league/ops/E3_INTERFACES.md` section 14
(13 until the merge with main's release E3.1, whose own section keeps that number).)

Package J's design note, where it departs from the spec's patch 17: `league/xs/E4_INTERFACES.md` section 13. In one
line: the panel's runs are NOT dispatched inside E3's night; the panel has its own night (E3's `Shadow.night` on a
subclass, the job `forward_xs` after `equity_panel`), so E3's shadow needs three small hooks and no dispatch in
`slice`, `run_program` or `run_from`.

| file | anchor | the change | held by |
|---|---|---|---|
| `league/ops/forward_db.py` | after `CONTROL_ALPHA_F` | `XS_ROUTE = "XS1"`, `PANEL_UGROUP = "panel:"` | `test_forward_xs.TheRegistry` |
| | `append_registry`, the route pair's check | (`XS_ROUTE`, `E3_ALPHA_F`) is admitted; a row carries `XS_ROUTE` if and only if its `ugroup` begins `PANEL_UGROUP` (a ValueError before anything is written) | `...test_what_the_registry_refuses_it_still_refuses` |
| `league/ops/forward_register.py` | `sync`, after `rows, refused = _scored(...)` | the panel's own reader beside it (`forward_xs.scored_rows`), the two lists merged in the registry's order (`forward_xs.oldest_first`) | `TheRegistry` (three tests) |
| | `_register`, the `append_registry` call | `route` and `alpha_f` are the row's own (E3's when it names none) | the same |
| | `sync`, the live instances' loop | `forward_xs.live_row(...) or _live_row(...)` (a panel instance's NEEDS are the panel's) | `...test_a_live_panel_instance_the_registry_does_not_hold_and_its_tags` |
| | `_tags`, `looked = ...` | a panel family's look is read under `forward_xs.look_key(fam)` | the same |
| | `_stops`, the `nights` query and the registry loop | nights by job (the night row's `job`): a panel program reads the panel night's, every other program E3's own | `test_forward_xs.TheStopRulesReadEachLanesOwnNights` |
| `league/ops/forward_shadow.py` | class `Shadow`, before `__init__` | `JOB = JOB` (the job named in the night's row); `night` writes `self.JOB` | `ThePanelNight.test_each_night_runs_its_own_lane` |
| | before `due` | `_mine(program)`: not a panel program; `due` skips what is not its own | the same |
| | `_label`, its first statement (the engine label) | `forward_xs.engine_label(self.db, ...)`: "+xs." and 12 hex once a panel row is registered | `...test_the_engine_label_names_the_xs_evidence_once_a_panel_row_exists` |
| `league/ops/forward_twins.py` | `on_run`, its first test | no live-like row of a panel run | `ThePanelNight` (the first test) |
| | `_one_instance`, after the run sha's check | a panel instance, or any instance on the panel night, goes to `forward_xs.twin` (each night twins its own lane) | `test_forward_xs_twin` (thirteen tests) |
| `league/ops/forward_audit.py` | `run`, after `marked = mark(...)` | `forward_xs.audit_marks` (with the book read) | `test_forward_xs.TheMorningMarks` |
| `league/ops/forward_report.py` | `raised` | the FX alarms follow `forward_xs.raised` | `TheAlarms` |
| | `sim_program_years`, the structures | "panel" beside "etf" and "stock" | `TheReportReadsAPanelProgramInItsOwnGroups` |
| | `_group_rows` | the panel's own groups (`forward_xs.GROUPS`, `group`), from the first registered panel row | the same |
| | `_nights`; `funnel_rows`' `stale` | every job's nights but the panel's (`forward_xs.JOB`) | `TheAlarms.test_panel_programs_left_stale_two_panel_nights_running` |
| | `section`, after the FW alarms | `forward_xs.alarms(...)` appended | `TheAlarms` |

Beside patch 17, in files that are not E3's:

| file | the change | held by |
|---|---|---|
| `league/ops/registry.py` | ONE row, `forward_xs`, after `contam_probe` and before `equity_universe`: `after("equity_panel")`, the forward shadow's own limits, in a pause too | `test_forward_xs.TheJob`, `test_ops_int_ops`, `test_e3_identities`, `test_e4_integration` (E3's six still follow `dlane`, E4's six are still last) |
| `league/ops/dlane_report.py` | `panel_forward` (the twin's residual and the rebalance sessions agreed beside a live panel program, after the forward record's section is read); `PANEL_OWED` reworded, `PANEL_SHADOWED` added | `test_forward_xs_twin.TheLinesBesideAPanelProgram`, `test_dlane_report_panel` |
| `league/tests/test_e3_seal_imports.py` | `league/ops/forward_xs.py` is admitted to what E3's ops modules may import AND brought under the seal (no sealed tree imports or names it; its own imports are listed; no writable swarm store) | itself, and `TheCheckCatchesWhatItShould` |
| `league/tests/test_forward_report.py` | the same module is one of the forward record's (it may name the others; no other ops module but the dlane report may name it) | itself |
| `league/tests/test_ops_int_ops.py` | `forward_xs` runs in a pause | itself |
| `league/tests/test_e4_e2e.py` | the scored panel version is ONE registry row (it read none while the module was a stub); the marker is written by the module's own writer | itself |

NOT PATCHED, stated: `league/ops/fill_minutes.py` (the spec's seventh file: the day's traded panel symbols). A panel
lot's fill gap has no timing part until it is.
