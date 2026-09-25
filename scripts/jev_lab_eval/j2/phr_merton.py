"""Pre-registered Jev questions over a Merton pass's REQUEST text (before the answer). Direction: +1 = high p means 'this pass will produce nothing'."""
SHARED = {"context": ("Each item is one request put to Merton, the firm's expensive frontier model, BEFORE it answered. Merton may only propose "
                      "a new or rewritten strategy file, a pure-python tool over data strategies already receive, a lesson, or a change to "
                      "permitted dials. It cannot add data feeds, venues or change the House's core code (accounting, reconciliation, order routing, replay engine).")}
Q = {
    "m1_nothing": (+1, "Is this request unlikely to be solved by anything Merton is allowed to produce (a strategy file, a tool over existing data, "
                       "a lesson or a permitted dial change), because what it needs is data the House does not have, a fix to the House's core code, "
                       "or an answer the text says was already given?"),
    "m2_missing": (+1, "Does the request say the blocker is missing data, a feed, a price history or a venue feature that the House does not supply?"),
    "m3_house": (+1, "Does the request describe a defect in the House's own machinery (accounting, cash reconciliation, order routing, the replay "
                     "engine or venue rules) rather than in one strategy's own rules?"),
    "m4_strategy": (-1, "Is the request about one strategy's own entry, exit or sizing rules, which a rewritten strategy file could change?"),
    "m5_known": (+1, "Does the request say the problem is already known, already reported, already under repair, or was already answered before?"),
}
