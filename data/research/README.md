# Primary-source research

`research_sources.py` contains the entire source registry: the Microsoft FY2026
earnings release and earnings call, both published July 29, 2026. Models select
source IDs and search text; they cannot provide URLs, follow redirects, execute
code, or perform network requests through a research tool.

`SourceStore(project_root).capture(source_id)` captures the first retrieved HTML
as normalized text in the private `.data/research/sources` directory. The cache
uses private directories, read-only artifact files, exclusive creation, and a
SHA-256 text digest. Existing artifacts are verified and reused, never refreshed
in place. Full source text is private runtime data and is not committed here.

The runner freezes artifacts in its own durable run state before calling
`dispatch`. Passage citations contain the first 24 digest characters and exact
Python character offsets into that frozen normalized text. Each result contains
at most three passages of 1,800 characters each. A query with no match returns an
empty list; this does not establish absence from the full document.

`published_at` is the source publication date and `fetched_at` is the actual
retrieval time. A publication cutoff excludes later publications. It does not
establish what a mutable web page contained on an earlier date.

`source-notes.json` records a manually checked research lead and the identities
of the initial captures. It is an audit aid, not an automatic addition to the
thesis evidence packet. The model must read the frozen source before relying on
the additional observation.
