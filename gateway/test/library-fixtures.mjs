// SYNTHETIC arXiv material for the research library's tests (lib/library.mjs). Every feed and page here is shaped
// exactly like the live ones (the Atom API, arxiv.org/html, ar5iv), as captured on Sept 29, 2026, but written by hand:
// never a raw capture, because a live comment held a personal email address. The ids, titles and people are invented.

//: A paper is its versions, oldest first: the API's `published` is v1's date, a version's `updated` its own.
export const PAPERS = {
  // Posted 2016, never revised: served as it is.
  '1602.00865': {
    categories: ['q-fin.PM', 'q-fin.RM'],
    authors: ['Ada Quill', 'Ben Harrow'],
    versions: [{ date: '2016-02-02T10:27:14Z', title: 'Tail Risk Premia for Long-Term Equity Investors',
      summary: 'We measure the variance risk premium in index options and the returns of selling tail insurance.' }],
  },
  // Posted 2022, revised in 2024 and again in 2026: an unversioned read serves v1; a read of v2 serves v2.
  '2212.06888': {
    categories: ['q-fin.PR', 'q-fin.TR'],
    authors: ['Cora Vance', 'Dev Okafor', 'Eli Brandt'],
    versions: [
      { date: '2022-12-13T20:19:14Z', title: 'Fundamentals of Perpetual Futures',
        summary: 'Perpetual futures track the index through a funding rate; we derive no-arbitrage bounds on the variance risk premium.' },
      { date: '2024-07-01T09:00:00Z', title: 'Fundamentals of Perpetual Futures',
        summary: 'Perpetual futures and funding: bounds, estimation and the variance risk premium, with new data.' },
      { date: '2026-09-17T17:23:23Z', title: 'Fundamentals of Perpetual Futures (revised)',
        summary: 'Revised with the market data of 2025 and early 2026: zero days to expiration options explain the funding.' },
    ],
  },
  // Posted 2022, its only revision dated 2025-01-22: searchable as v1 only.
  '2207.00949': {
    categories: ['q-fin.PM'],
    authors: ['Fay Ionescu'],
    versions: [
      { date: '2022-07-03T04:06:04Z', title: 'Stochastic arbitrage with market index options',
        summary: 'Stochastic arbitrage opportunities in market index options, and the variance risk premium they imply.' },
      { date: '2025-01-22T14:21:13Z', title: 'Stochastic arbitrage with market index options',
        summary: 'Stochastic arbitrage in index options: an out-of-sample test on 2025 data and the variance risk premium.' },
    ],
  },
  // A revised paper whose v1 does not hold the query's words: arXiv matched its LATER abstract.
  '2101.00002': {
    categories: ['q-fin.ST'],
    authors: ['Gus Lindqvist'],
    versions: [
      { date: '2021-01-05T08:00:00Z', title: 'Seasonality in commodity futures', summary: 'Calendar effects in commodity futures curves.' },
      { date: '2025-06-01T08:00:00Z', title: 'Seasonality in commodity futures',
        summary: 'Calendar effects in commodity futures, now with the variance risk premium of index options.' },
    ],
  },
  // Posted in 2025: never served.
  '2502.00001': {
    categories: ['q-fin.PR'],
    authors: ['Hal Mercer'],
    versions: [{ date: '2025-02-01T12:00:00Z', title: 'A variance risk premium in 2025', summary: 'The variance risk premium after 2024.' }],
  },
  // An id of 2501 whose dates claim 2024: metadata that disagrees with itself is refused.
  '2501.00001': {
    categories: ['q-fin.PR'],
    authors: ['Ivy Stone'],
    versions: [{ date: '2024-12-30T12:00:00Z', title: 'A variance risk premium study', summary: 'The variance risk premium in index options.' }],
  },
  // The last second before the cutoff: served.
  '2412.09999': {
    categories: ['q-fin.TR'],
    authors: ['Jon Pike'],
    versions: [{ date: '2024-12-31T23:59:59Z', title: 'Year-end order flow in index options',
      summary: 'Order flow and the variance risk premium around the turn of the year; forecasts to December 2025 are given.' }],
  },
  // A forecast inside a pinned abstract: the date is replaced, the item served.
  '2311.04444': {
    categories: ['q-fin.RM'],
    authors: ['Kim Ode'],
    versions: [{ date: '2023-11-08T10:00:00Z', title: 'Bond maturities and the variance risk premium',
      summary: 'Notes maturing on 2026-12-14 carry a variance risk premium by December 2025, by our estimate.' }],
  },
  // Off topic: a physics paper that matches the words.
  '2001.00003': {
    categories: ['physics.flu-dyn'],
    authors: ['Lu Chen'],
    versions: [{ date: '2020-01-02T10:00:00Z', title: 'Variance of turbulent premium flows', summary: 'The variance risk premium of eddies.' }],
  },
  // cs.LG about markets (kept) and cs.LG about images (off topic).
  '2305.18991': {
    categories: ['cs.LG'],
    authors: ['Mo Adeyemi'],
    versions: [{ date: '2023-05-30T12:41:52Z', title: 'Learning volatility surfaces',
      summary: 'A network learns the implied volatility surface of index options and the variance risk premium.' }],
  },
  '2305.00004': {
    categories: ['cs.LG'],
    authors: ['Nia Park'],
    versions: [{ date: '2023-05-01T12:00:00Z', title: 'Variance reduction for image models', summary: 'Risk and variance in image classifiers; a premium architecture.' }],
  },
  // Native HTML exists (a version from December 2023 on).
  '2409.06496': {
    categories: ['q-fin.PR'],
    authors: ['Oto Rahman', 'Pia Kerr'],
    versions: [{ date: '2024-09-10T13:24:42Z', title: 'Valuation of convertible bonds by simulation',
      summary: 'A least-squares Monte Carlo valuation of convertible bonds and a trading rule; the variance risk premium appears.' }],
  },
  // Old enough for ar5iv only; every version before the cutoff.
  '1805.01234': {
    categories: ['q-fin.ST'],
    authors: ['Quin Morrow'],
    versions: [
      { date: '2018-05-03T09:00:00Z', title: 'Overnight returns of index options', summary: 'Overnight and intraday returns of index options.' },
      { date: '2019-02-11T09:00:00Z', title: 'Overnight returns of index options', summary: 'Overnight and intraday returns of index options, revised.' },
    ],
  },
  // Old, every version pre-cutoff, but its ar5iv rendering names a later draft date: the text is withheld.
  '1901.05555': {
    categories: ['q-fin.PM'],
    authors: ['Rue Salas'],
    versions: [{ date: '2019-01-15T09:00:00Z', title: 'Momentum in option returns', summary: 'Momentum in delta-hedged option returns.' }],
  },
  // A paper whose v1 is itself in 2025 (only the API's search pre-filter could miss that it was never pre-2025).
  '2411.07777': {
    categories: ['q-fin.PR'],
    authors: ['Sol Achebe'],
    versions: [{ date: '2025-01-03T09:00:00Z', title: 'A late paper', summary: 'Posted after the cutoff.' }],
  },
  // An old-style id.
  'cond-mat/0601001': {
    categories: ['q-fin.ST', 'cond-mat.stat-mech'],
    authors: ['Tay Brooks'],
    versions: [{ date: '2006-01-01T09:00:00Z', title: 'Fat tails in option prices', summary: 'Heavy tails of option returns & their pricing.' }],
  },
};

const esc = text => String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

/** One `<entry>` for version `n` of paper `base` (the whole of it: the comment and the links included). */
export function entryXml(base, n, paper = PAPERS[base], { published, updated, id } = {}) {
  const version = paper.versions[n - 1];
  return `  <entry>
    <id>${id ?? `http://arxiv.org/abs/${base}v${n}`}</id>
    <title>${esc(version.title)}</title>
    <updated>${updated ?? version.date}</updated>
    <link href="https://arxiv.org/abs/${base}v${n}" rel="alternate" type="text/html"/>
    <link href="https://arxiv.org/pdf/${base}v${n}" rel="related" type="application/pdf" title="pdf"/>
    <summary>${esc(version.summary)}</summary>
${paper.categories.map(c => `    <category term="${c}" scheme="http://arxiv.org/schemas/atom"/>`).join('\n')}
    <published>${published ?? paper.versions[0].date}</published>
    <arxiv:comment>12 pages; revised 2026; contact synthetic.person@example.invalid</arxiv:comment>
    <arxiv:journal_ref>Journal of Invented Results 99 (2026)</arxiv:journal_ref>
    <arxiv:primary_category term="${paper.categories[0]}"/>
${paper.authors.map(name => `    <author>\n      <name>${esc(name)}</name>\n    </author>`).join('\n')}
  </entry>`;
}

/** An Atom feed as the API answers one (its own header carries today's date: it is never read into an answer). */
export const feed = entries => `<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/" xmlns:arxiv="http://arxiv.org/schemas/atom" xmlns="http://www.w3.org/2005/Atom">
  <id>https://arxiv.org/api/SyntheticFeedId</id>
  <title>arXiv Query: synthetic</title>
  <updated>2026-09-29T13:35:21Z</updated>
  <link href="https://arxiv.org/api/query?synthetic" type="application/atom+xml"/>
  <opensearch:itemsPerPage>${entries.length}</opensearch:itemsPerPage>
  <opensearch:totalResults>${entries.length}</opensearch:totalResults>
  <opensearch:startIndex>0</opensearch:startIndex>
${entries.join('\n')}
</feed>
`;

/** The API's error answer (verified live Sept 29, 2026: HTTP 400, an entry whose id is under /api/errors). */
export const errorFeed = (message, anchor = '') => `<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/" xmlns:arxiv="http://arxiv.org/schemas/atom" xmlns="http://www.w3.org/2005/Atom">
  <id>https://arxiv.org/</id>
  <title>arXiv Search Results</title>
  <updated>2026-09-29T13:53:06Z</updated>
  <opensearch:itemsPerPage>1</opensearch:itemsPerPage>
  <opensearch:totalResults>1</opensearch:totalResults>
  <opensearch:startIndex>0</opensearch:startIndex>
  <entry>
    <id>https://arxiv.org/api/errors${anchor}</id>
    <title>Error</title>
    <updated>2026-09-29T13:53:06Z</updated>
    <link href="https://arxiv.org/api/errors${anchor}" rel="alternate" type="text/html"/>
    <summary>${esc(message)}</summary>
    <author>
      <name>arXiv api core</name>
    </author>
  </entry>
</feed>
`;

/** A LaTeXML article: sections with numbered headings, a formula and a table. */
export function article({ lead = 'We study option returns.', extra = '' } = {}) {
  return `<article class="ltx_document ltx_authors_1line">
<h1 class="ltx_title ltx_title_document">A synthetic paper</h1>
<div class="ltx_abstract"><h6 class="ltx_title ltx_title_abstract">Abstract</h6><p class="ltx_p">${lead}</p></div>
<section id="S1" class="ltx_section">
<h2 class="ltx_title ltx_title_section"><span class="ltx_tag ltx_tag_section">1 </span>Introduction</h2>
<div class="ltx_para"><p class="ltx_p">The premium is <math id="m1" class="ltx_Math" alttext="\\sigma^{2}_{t}-\\mathbb{E}[RV]" display="inline"><semantics><msubsup><mi>σ</mi><mi>t</mi><mn>2</mn></msubsup><annotation encoding="application/x-tex">\\sigma^{2}_{t}</annotation></semantics></math> on average.</p></div>
<section id="S1.SS1" class="ltx_subsection">
<h3 class="ltx_title ltx_title_subsection"><span class="ltx_tag ltx_tag_subsection">1.1 </span>Data</h3>
<div class="ltx_para"><p class="ltx_p">One-minute quotes &amp; trades. Contact: first.author@univ.example.edu. ${extra}</p></div>
</section>
</section>
<section id="S2" class="ltx_section">
<h2 class="ltx_title ltx_title_section"><span class="ltx_tag ltx_tag_section">2 </span>Results</h2>
<div class="ltx_para"><p class="ltx_p">Selling puts earns the premium; pp. 2037–2053 of the survey agree.</p></div>
</section>
</article>`;
}

/** A page around an article, its chrome carrying later years (arxiv.org's does: "Copyright 2026 Fonticons"). */
export const page = body => `<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/><title>[synthetic] A synthetic paper</title>
<link rel="stylesheet" href="/static/browse/0.3.4/css/arxiv-html-papers-20260823.css"/>
<!-- Font Awesome Free 6.5.1 by @fontawesome - https://fontawesome.com Copyright 2026 Fonticons, Inc.-->
<script>window.built = '2026-08-23';</script>
</head><body><header class="desktop_header">arXiv, September 2026</header>
<div class="ltx_page_main">${body}</div>
<footer>Generated on Tue Sep 29 2026 by LaTeXML. Copyright 2026.</footer></body></html>`;

/** A synthetic comment's address: it must never appear in any answer. */
export const COMMENT_EMAIL = 'synthetic.person@example.invalid';
