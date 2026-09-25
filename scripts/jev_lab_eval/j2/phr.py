"""The candidate research-filter questions (tested on Sept 22-23 only) and the shared context."""
SHARED = {"context": ("Each item is one trading strategy's research state before a paid research session: STRATEGY (desk, family, style), "
                      "PREVIOUS SESSION (what the last session concluded) and NEW SINCE (what the ledger recorded for it since then: "
                      "its own fills, settlements, refused orders, verdicts, replays, code changes, inactivity, desk notes, lessons, "
                      "fulfilled data requests).")}
Q = {
    "p1": ("Given the strategy and its previous research conclusion in the item, does the item contain decision-relevant NEW evidence "
           "that could change what a researcher would conclude or build for this strategy?"),
    "p2": ("Does the NEW SINCE part of the item report an outcome or change that removes or answers the reason the previous session "
           "gave for not acting (for example a fill, settlement, verdict, code change, fulfilled data request or a desk lesson), so that "
           "a new research session could reasonably reach a different conclusion? Answer no when nothing new is reported or when the "
           "new rows only repeat the known blocker."),
    "p3": ("Would a researcher reading this item most likely write and replay a new or changed strategy now, rather than conclude "
           "again that nothing is worth spending on?"),
}
