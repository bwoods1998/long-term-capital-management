// The protected paths: what no automated merge may change (LTCM v3, release V3-A, WP8).
//
// The engineer's pull requests merge through this gateway (`POST /v1/github/merge`, lib/merge.mjs) on green CI and an
// automated review, with no human step. What decides money, judges evidence, or holds the walls themselves changes only
// by the owner's own deploy, so a pull request that touches any path below is never merged here, whatever CI and the
// reviewer said, and the engineer may not even open one (`github.pathRefusal`, role `engineer`).
//
// The list is `league/ci.py` FORBIDDEN (the updater's own wall) and `ci.MERGE_ONLY` (league/config.json, whose bounded
// dials alone the updater lets through). test/merge.test.mjs reads FORBIDDEN from the repository and fails while any
// of its entries is missing here, and league/tests/test_ci.py fails while the lists differ by anything else. A name ending in "/" is a tree. Compared without case, as `league.ci` compares.

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
  // What feeds and enforces the budget rule (V3-A integration): the Sail guard, the model router's Claude room and the
  // job context (the settings' overlay is below).
  'league/swarm/guard.py', 'league/swarm/models.py', 'league/ops/context.py',
  // The evaluator's identity and the evidence it reads: the Gym, the gate, the bands, the evaluator, the settings and
  // the store of the swarm; the data layer and its builders.
  'league/gym/', 'league/swarm/gate.py', 'league/swarm/bands.py', 'league/swarm/evaluator.py',
  'league/swarm/settings.py', 'league/swarm/store.py', 'ltcm/data/', 'scripts/data/',
  // How the House is deployed, and the House's configuration.
  'deploy/', 'league/config.json',
]);

/**
 * Why no automated merge may change `path`, or `null` when it may. A path of the wrong shape (absolute, with a way up,
 * an empty segment, a control character or a backslash) or naming git's own files (`.git*`, which change a checkout) is
 * refused as if protected: the merge route fails closed on anything it cannot read plainly.
 */
export function protectedRefusal(path) {
  if (typeof path !== 'string' || !path || path.length > 400) return 'not a plain repository path';
  if (path.startsWith('/') || path.includes('\\') || /[\x00-\x1f\x7f]/.test(path)) return 'not a plain repository path';
  const segments = path.split('/');
  if (segments.some(segment => segment === '' || segment === '.' || segment === '..')) return 'not a plain repository path';
  const lower = path.toLowerCase();
  const hit = MERGE_FORBIDDEN.find(entry => lower === entry || (entry.endsWith('/') && lower.startsWith(entry)));
  if (hit) return `protected (${hit})`;
  return segments.some(segment => /^\.git/i.test(segment)) ? 'git\'s own files' : null;
}
