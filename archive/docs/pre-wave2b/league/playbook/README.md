# The playbook

Lessons Merton, as teacher, distils from the graveyard and the league table, one file a lesson,
added by pull request. The House loads them into the ledger's playbook, where every agent's
research pass can read them next to the post-mortems of the dead. It loads each lesson once, and
again whenever its text changes (Sept 23, 2026), so a corrected lesson reaches the agents. A
lesson that cites a threshold dates it, because the constitution moves; the rules in force are
in each agent's `qualification_policy`.

A lesson may also carry a **lab prior** (Sept 23, 2026): one fenced ```lab-prior``` block holding a JSON
object with a `rule` (`pause-param-forks`: the Alpha Lab breeds no parameter-only mutant of the named
lineages; their Luna and Sol rewrites, which change the mechanism, still come), what it names (`family`,
a substring of the House family the lab lineage grew from; `lineage`, a lab lineage such as
`agent:huang-h6d3302`; `niche`, a desk; `cell`, a cell prefix) and `until` (`forward-positive`: lifted
once the lineage's own forward window is positive; a `YYYY-MM-DD` day; or nothing: for good). The lab
reads the latest text of every lesson in the ledger's playbook every ten minutes, so a merged lesson is
a prior within an epoch of `House.learn`; `lab.stats` `forward.priors` shows the priors in force and what
they paused. The first is `2026-09-23-pause-prior-window-fade-forks.md`.
