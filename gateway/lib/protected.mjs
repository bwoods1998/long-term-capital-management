// The protected paths: what no automated merge may change (LTCM v3, release V3-A, WP8).
//
// The engineer's pull requests merge through this gateway (`POST /v1/github/merge`, lib/merge.mjs) on green CI and an
// automated review, with no human step. What decides money, judges evidence, or holds the walls themselves changes only
// by the owner's own deploy, so a pull request that touches any path below is never merged here, whatever CI and the
// reviewer said, and the engineer may not even open one (`github.pathRefusal`, role `engineer`). The engineer is held
// to its lanes' surfaces besides (`github.ENGINEER_SURFACE`, and within them its branch's own lane,
// `github.ENGINEER_LANES`); this list is the wall behind those.
//
// The list is `league/ci.py` FORBIDDEN (the updater's own wall) and `ci.MERGE_ONLY` (league/config.json, whose bounded
// dials alone the updater lets through): league/tests/test_ci.py fails while the two lists differ by anything else. It
// holds the judges and the money rules, the evaluator's identity, the data the evidence is computed from, every module
// outside league/live/ and league/gym/ that those trees import or seal into the decider's runtime, the swarm's spend
// limits and settings, the harness loop's own objective (`harness_lanes.PROTECTED` but the candidate tests), the
// forward ladder's benchmark, the frozen judge of its binding and the swarm's own read of its cohorts, and the House's
// job framework. test/merge.test.mjs reads each of those sources from the repository, FORBIDDEN among them, and fails
// while any entry is missing here. A name ending in "/" is a tree. Compared without case, as `league.ci` compares.

export const MERGE_FORBIDDEN = Object.freeze([
  // league/ci.py FORBIDDEN, in its order.
  'league/constitution.py', 'league/ci.py', 'league/ledger.py', 'league/book.py', 'league/evaluator.py',
  'league/stats.py', 'league/auditor.py', 'league/watchdog.py', 'league/safety.py', 'league/replay.py', 'league/updater.py',
  'gateway/', '.github/',
  'league/campaigns.json', 'league/campaigns.py', 'league/funded.py', 'league/experiments.py', 'league/recordings.py',
  'league/research_jobs.py', 'league/capabilities.py', 'league/parameters.py',
  'league/live_trading.py', 'league/live_pilot.py', 'scripts/live_trading.py', 'scripts/live_pilot.py',
  'league/live/',
  'league/sandbox.py', 'league/lab.py', 'league/history.py', 'league/deep_replay.py', 'league/allocator.py',
  'league/families.py', 'league/shards.py', 'league/labbox.py', 'league/resolution.py',
  // The House's protected jobs (V3-A, WP1's additions to ci.FORBIDDEN): the budget rule, the drills, the standing grant.
  'league/ops/budget.py', 'league/ops/drills.py', 'league/ops/grant.py',
  // What feeds and enforces the budget rule (V3-A integration): the Sail guard, the model router's Claude room, the
  // job context and the close economics (the budget's p30, the public Net; V3-A review). The settings' overlay is below.
  'league/swarm/guard.py', 'league/swarm/models.py', 'league/ops/context.py', 'league/ops/economics.py',
  // Resource commitments and their dispatch path enforce the research ceiling too.
  'league/swarm/compute.py', 'league/swarm/daily_compute.py', 'league/swarm/pool.py',
  // The owner's ordinary research fence, including alternative Python loaders of its name.
  'league/swarm/research_permission.py',
  // And the framework that schedules and runs the House's jobs, and computes the realized p30 the budget is funded
  // from: the whole tree, after its named files so that a refusal names the file.
  'league/ops/',
  // The evaluator's identity and the evidence it reads: the Gym, the gate, the bands, the evaluator, the settings and
  // the store of the swarm; the data layer and its builders.
  'league/gym/', 'league/swarm/gate.py', 'league/swarm/bands.py', 'league/swarm/evaluator.py',
  'league/swarm/settings.py', 'league/swarm/store.py', 'ltcm/data/', 'scripts/data/',
  // What league/live/ and league/gym/ import from outside their trees, and what is sealed into the Gym bundle and the
  // decider's runtime with them: the packages' own __init__ files run first in every House process and in the sandbox;
  // structure_core classifies, limits and prices every real order; ltcm.performance names the owner's flows the stops
  // net out.
  'league/__init__.py', 'league/structure_core.py', 'league/structures.py', 'league/swarm/__init__.py',
  'ltcm/__init__.py', 'ltcm/performance.py',
  // The swarm's settings as code (V3-A, WP9: the gate image, the splits, the spend fuses) and its funded spend: the
  // funding reader beside the Sail guard's daily cap and the model router above; the floor's own budget, pacer and
  // economics.
  'league/swarm/policy.json', 'league/swarm/funding.py',
  'league/budget.py', 'league/pacer.py', 'league/economy.py', 'league/project_economics.py',
  // Capital permissions outside league/live/.
  'league/grants.py', 'league/capital.py', 'league/exposure.py',
  // The harness loop's objective: the lanes, their judges, the canary and the loop that retains or reverts a change,
  // the benchmarks and the evidence lines it measures by; and what a researcher may see of Validation (D2a).
  'league/swarm/harness_lanes.py', 'league/swarm/harness_judges/', 'league/swarm/harness_runtime.py',
  'league/swarm/harness_improve.py', 'league/swarm/improvement.py', 'league/swarm/improvement_benchmark.py',
  'league/swarm/canary.py', 'league/swarm/benchmarks.py', 'league/swarm/long_single_benchmarks.py',
  'league/swarm/evidence.py', 'league/swarm/diagnostics.py', 'league/swarm/tournament.py', 'scripts/harness_improve.py',
  'playbooks/harness-improvement.md', 'docs/goals/', 'docs/benchmarks/',
  // The forward ladder's benchmark and its judge (evidence v3): the desks that measure the ladder's rule against the
  // sealed look, and the frozen script that alone says whether the ladder may bind. The rule itself is under
  // league/live/.
  'league/swarm/forward_benchmarks.py', 'scripts/ladder_judge.py',
  // The swarm's own read of the ladder's cohorts: each cohort's window (the window hold) and its own record, which
  // decide the families the cohort keep holds alive for the ladder to judge.
  'league/swarm/practice.py',
  // How the House is deployed, the House itself (its tick calls the updater), and the House's configuration.
  'deploy/', 'scripts/floor_box.py', 'league/house.py', 'league/config.json', 'CHANGELOG.md',
]);

// A protected module is shadowed by a package or a compiled module of the same name (Python's finder prefers a
// package directory, and an extension module or an unchecked .pyc, to the .py beside it), and a protected tree by a
// module of its name when it is a namespace package. So `league/constitution.py` protects `league/constitution/` and
// every `league/constitution.*`, and `scripts/data/` protects `scripts/data.*` too.
const SHADOWS = MERGE_FORBIDDEN.flatMap(entry => {
  const stem = entry.endsWith('/') ? entry.slice(0, -1) : entry.endsWith('.py') ? entry.slice(0, -3) : null;
  return stem ? [[`${stem}/`, entry], [`${stem}.`, entry]] : [];
});
// Files Python loads before, or instead of, the source in the tree: compiled modules, bytecode caches, path hooks run
// at interpreter start, and the start-up customization modules. None belongs in this repository; all are refused.
const LOADER_SUFFIX = /\.(pyc|pyo|pyd|so|pth|dylib)$/i;
const LOADER_NAMES = ['sitecustomize.py', 'usercustomize.py'];

/**
 * Why no automated merge may change `path`, or `null` when it may. A path of the wrong shape (absolute, with a way up,
 * an empty segment, a control character or a backslash) or naming git's own files (`.git*`, which change a checkout) is
 * refused as if protected: the merge route fails closed on anything it cannot read plainly. So is a file that would
 * shadow a protected module (SHADOWS) and a file Python loads instead of source (LOADER_SUFFIX, LOADER_NAMES).
 */
export function protectedRefusal(path) {
  if (typeof path !== 'string' || !path || path.length > 400) return 'not a plain repository path';
  if (path.startsWith('/') || path.includes('\\') || /[\x00-\x1f\x7f]/.test(path)) return 'not a plain repository path';
  const segments = path.split('/');
  if (segments.some(segment => segment === '' || segment === '.' || segment === '..')) return 'not a plain repository path';
  const lower = path.toLowerCase();
  const hit = MERGE_FORBIDDEN.find(entry => lower === entry.toLowerCase() || (entry.endsWith('/') && lower.startsWith(entry.toLowerCase())));
  if (hit) return `protected (${hit})`;
  const shadow = SHADOWS.find(([prefix]) => lower.startsWith(prefix.toLowerCase()));
  if (shadow) return `protected (${shadow[1]}: a file that would shadow it)`;
  if (segments.some(segment => /^\.git/i.test(segment))) return 'git\'s own files';
  const name = segments.at(-1).toLowerCase();
  if (segments.some(segment => segment.toLowerCase() === '__pycache__') || LOADER_SUFFIX.test(name) || LOADER_NAMES.includes(name)) {
    return 'a file Python loads instead of source';
  }
  return null;
}
