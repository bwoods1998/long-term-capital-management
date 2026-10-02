"""THE MECHANISM LIBRARY (LTCM v3, Oct 2026): the documented, risk-defined option premia every new family is born from.

WHY. Through Oct 2 the architect bore families from the leaderboard, the graveyard and the gaps, and most were new anomalies
mined on the Gym's own data: families self-refuted in a median of under an hour, Train rank-predicted Validation weakly, and
every Validation pass was the market's drift. The premia the literature documents for a small account are few, risk-defined
and known before the Gym's data: the index variance premium (through debit butterflies real money can trade now, and through
defined-risk credit structures for practice), post-event volatility crush, term-structure roll-down, expiry-week pinning and
dispersion, plus two documented entry filters for bought premium. The library is that list, curated by hand with its
pre-2025 literature; a birth names one entry (`library_class` on its card) and is held to it.

AN ENTRY (`LIBRARY`): its title, the premium (who pays and why it persists), the expressions (how a program trades it), the
structures it may use, the root groups it may trade (`strategist.root_group`: index, etf, names), the card classes its card
may declare (`cards.MECHANISM_CLASSES`), the holding buckets (`cards.HOLDING`) and its citations. Single-name anomaly mining
is not an entry: a name may be a root only where the documented premium lives on names (pinning, post-event crush,
dispersion's constituents, a lead-lag leader). `long_single`, `long_call` and `long_put` belong only to the timing-filter
entry. Every citation is posted before 2025 (`Citation.year`, checked by a test); the model reads authors, title and venue,
never a year.

ADMISSION (`check`, `architect.library` on; league/swarm/architect.py `admit`): a card must name an entry, and its
structure, every root's group, its declared class and its holding must be the entry's; its expected activity
(`sessions_per_year` traded sessions a year, `structures_per_session` opened on a traded session) must reach the validation
line's frequency (`evidence.MIN_DAYS` days and `evidence.MIN_TRADES` trades a year), since a family that expects fewer can
never be judged. Each refusal names the field.

THE LEAD-LAG QUOTA (`LeadLagQuota`). Cross-root lead-lag (a leader root's move predicting a lagging root's) is the one
mined class kept, at most `LEAD_LAG_SHARE` (a quarter) of the births of the trailing `LEAD_LAG_WINDOW_DAYS`: a lead-lag
birth is admitted only when, counting it, lead-lag births are at most that share of the window's architect births (the
pass's own births included). No model call.

MODEL-SAFE. `library_text` is what the architect and the strategist read: plain ASCII, no year or date, no Validation or
holdout figure, no family name, no account figure. A test holds it so.

Standard library only.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

#: The lead-lag quota: at most this share of the trailing window's births (GOAL 2.2: "cross-root lead-lag stays at most a
#: quarter of births").
LEAD_LAG = "cross_root_lead_lag"
LEAD_LAG_SHARE = 0.25
LEAD_LAG_WINDOW_DAYS = 7
#: A card's expected activity: traded sessions a year (a year holds about 252) and structures opened on a traded session.
SESSIONS_MAX = 252
STRUCTURES_MAX = 20


@dataclass(frozen=True)
class Citation:
    authors: str
    title: str
    venue: str
    year: int  # the code's check that it predates 2025; never rendered for a model

    def text(self) -> str:
        return f"{self.authors}, {self.title} ({self.venue})"


@dataclass(frozen=True)
class Entry:
    name: str
    title: str
    premium: str
    expressions: str
    structures: tuple[str, ...]
    root_groups: tuple[str, ...]
    card_classes: tuple[str, ...]
    holding: tuple[str, ...]
    citations: tuple[Citation, ...]
    practice_first: bool = False


_C = Citation
#: THE LIBRARY, in the order the request lists it. Hand-curated: a change here is a change to what may be born.
ENTRIES: tuple[Entry, ...] = (
    Entry(
        "index_variance_fly",
        "Index variance premium, bought as a debit butterfly",
        "Index options are priced above the variance that follows: investors pay for protection against market variance, "
        "so implied volatility on index options exceeds subsequent realized volatility on average, most of all at short "
        "tenors. A long butterfly centered near the money is the risk-defined debit expression of that short-variance view: "
        "it gains when the index moves less than the options priced.",
        "XSP (cash-settled, European) or SPY long call or long put butterflies centered at the money, one to two sessions "
        "to expiry, held to XSP's cash settlement or closed before SPY's expiry; a broken-wing butterfly (one wing wider) "
        "tilts the risk toward the side the skew overprices. Condition entries on the level of implied volatility against "
        "recent realized volatility, never on a market direction.",
        ("long_butterfly",), ("index", "etf"), ("volatility_risk_premium", "pinning_gamma"), ("intraday", "days_1_3"),
        (_C("Carr and Wu", "Variance Risk Premiums", "Review of Financial Studies", 2009),
         _C("Bakshi and Kapadia", "Delta-Hedged Gains and the Negative Market Volatility Risk Premium",
            "Review of Financial Studies", 2003),
         _C("Andersen, Fusari and Todorov", "Short-Term Market Risks Implied by Weekly Options", "Journal of Finance", 2017))),
    Entry(
        "index_variance_credit",
        "Index variance premium, sold through defined-risk credit structures",
        "The same premium sold directly: short index and broad ETF options earn the gap between implied and realized "
        "volatility, and the put side is the most overpriced because hedgers buy it and dealers must be paid to warehouse it.",
        "Credit verticals, iron condors and iron butterflies on SPY, QQQ, IWM or XSP, every short leg covered by a long wing, "
        "a few sessions to a few weeks to expiry, entered when implied volatility is rich against realized and closed at a "
        "profit target or before expiry. Practice first: real money opens these types only above the House's equity line.",
        ("credit_vertical", "iron_condor", "iron_butterfly"), ("index", "etf"), ("volatility_risk_premium", "skew"),
        ("days_1_3", "days_4_10", "days_11_plus"),
        (_C("Coval and Shumway", "Expected Option Returns", "Journal of Finance", 2001),
         _C("Bondarenko", "Why Are Put Options So Expensive?", "Quarterly Journal of Finance", 2014),
         _C("Israelov and Nielsen", "Covered Calls Uncovered", "Financial Analysts Journal", 2015)),
        practice_first=True),
    Entry(
        "post_event_crush",
        "Post-event volatility crush",
        "Implied volatility rises into a scheduled release (a macro print, a central bank decision, an earnings report) and "
        "falls once the uncertainty resolves; what remains elevated after the release decays toward realized volatility "
        "over the next sessions.",
        "Defined-risk short premium or a long butterfly opened after the release has printed (never held through it), on "
        "the event calendar's roots, closed within a few sessions. Condition on how far implied volatility stays above its "
        "pre-event level once the event is past.",
        ("iron_butterfly", "iron_condor", "credit_vertical", "long_butterfly"), ("index", "etf", "names"),
        ("event_premium", "volatility_risk_premium"), ("intraday", "days_1_3", "days_4_10"),
        (_C("Patell and Wolfson", "Anticipated Information Releases Reflected in Call Option Prices",
            "Journal of Accounting and Economics", 1979),
         _C("Beber and Brandt", "The Effect of Macroeconomic News on Beliefs and Preferences: Evidence from the Options "
            "Market", "Journal of Monetary Economics", 2006),
         _C("Dubinsky, Johannes, Kaeck and Seeger", "Option Pricing of Earnings Announcement Risks",
            "Review of Financial Studies", 2019))),
    Entry(
        "term_roll_down",
        "Term-structure roll-down",
        "In calm markets the implied volatility term structure slopes upward, and an option's implied volatility rolls down "
        "the curve as it ages; the variance premium is concentrated where the slope is steep, so a short-premium position "
        "at the steep part earns the roll-down on top of time decay.",
        "Defined-risk short premium (credit verticals, iron condors, iron butterflies) on SPY, QQQ or IWM at the tenor where "
        "the term structure is steepest, entered only when the curve is upward sloping and closed before the front of the "
        "curve; flat or inverted curves are no entry.",
        ("credit_vertical", "iron_condor", "iron_butterfly"), ("index", "etf"), ("term_structure", "volatility_risk_premium"),
        ("days_4_10", "days_11_plus"),
        (_C("Egloff, Leippold and Wu", "The Term Structure of Variance Swap Rates and Optimal Variance Swap Investments",
            "Journal of Financial and Quantitative Analysis", 2010),
         _C("Johnson", "Risk Premia and the VIX Term Structure", "Journal of Financial and Quantitative Analysis", 2017),
         _C("Vasquez", "Equity Volatility Term Structures and the Cross Section of Option Returns",
            "Journal of Financial and Quantitative Analysis", 2017))),
    Entry(
        "expiry_pinning",
        "Expiry-week pinning",
        "Into an expiration, hedging by option holders around strikes with large open interest pulls the underlying toward "
        "those strikes: closes cluster at heavily held strikes on expiration days more than chance allows.",
        "A long butterfly centered at the strike with the largest open interest near the money, opened in the sessions "
        "before an expiration and held into it or closed at its close; no entry when the price is far from any heavy strike.",
        ("long_butterfly",), ("index", "etf", "names"), ("pinning_gamma",), ("intraday", "days_1_3", "days_4_10"),
        (_C("Ni, Pearson and Poteshman", "Stock Price Clustering on Option Expiration Dates", "Journal of Financial Economics",
            2005),
         _C("Avellaneda and Lipkin", "A Market-Induced Mechanism for Stock Pinning", "Quantitative Finance", 2003),
         _C("Golez and Jackwerth", "Pinning in the S&P 500 Futures", "Journal of Financial Economics", 2012))),
    Entry(
        "dispersion",
        "Dispersion: index volatility against its constituents'",
        "Index options carry a correlation risk premium: implied correlation (index implied volatility against its "
        "constituents') sits above the correlation that is realized, so index premium is rich relative to constituent "
        "premium, most of all when implied correlation is high.",
        "Defined-risk short premium on the index or a broad ETF (iron condors, iron butterflies, credit verticals) or a long "
        "butterfly, entered when the index's implied volatility is high against its constituents' (read through cross-asset "
        "inputs); the constituents are signal roots, never single-name bets.",
        ("iron_condor", "iron_butterfly", "credit_vertical", "long_butterfly"), ("index", "etf", "names"), ("dispersion",),
        ("days_1_3", "days_4_10", "days_11_plus"),
        (_C("Driessen, Maenhout and Vilkov", "The Price of Correlation Risk: Evidence from Equity Options",
            "Journal of Finance", 2009),)),
    Entry(
        LEAD_LAG,
        "Cross-root lead-lag",
        "Information reaches related roots at different speeds: a leader root's move against its own norm predicts the "
        "lagging root's next move while a control root stays flat, because slow-moving capital and attention take time.",
        "A debit vertical on the lagging root, calls on one sign of the leader's move and puts on the other by the same "
        "rule, held one to a few sessions; the control root's condition is in code in every run. At most a quarter of "
        "births are this class.",
        ("debit_vertical",), ("index", "etf", "names"), ("relative_value",), ("days_1_3", "days_4_10"),
        (_C("Lo and MacKinlay", "When Are Contrarian Profits Due to Stock Market Overreaction?", "Review of Financial Studies",
            1990),
         _C("Hou", "Industry Information Diffusion and the Lead-Lag Effect in Stock Returns", "Review of Financial Studies",
            2007))),
    Entry(
        "timing_filtered_long_premium",
        "Bought premium under the two documented timing filters",
        "Option buyers lose to two documented frictions: time decay over non-trading days is priced into Friday's options, "
        "and bearish premium is most overpriced exactly when implied volatility is rich. A directional program that buys "
        "premium must respect both or it pays them.",
        "A long call, long put, long_single or debit vertical on SPY, QQQ, IWM or XSP with both filters in code: no long "
        "single opened on a Friday and held over the weekend, and no bearish premium (puts or put debit verticals) bought "
        "while implied volatility is rich against realized. Calls and puts by one rule, never one side alone.",
        ("long_single", "long_call", "long_put", "debit_vertical"), ("index", "etf"),
        ("trend_momentum", "reversal_liquidity", "calendar_flow", "volatility_underpricing"),
        ("days_1_3", "days_4_10", "days_11_plus"),
        (_C("Jones and Shemesh", "Option Mispricing Around Nontrading Periods", "Journal of Finance", 2018),
         _C("Goyal and Saretto", "Cross-Section of Option Returns and Volatility", "Journal of Financial Economics", 2009),
         _C("Garleanu, Pedersen and Poteshman", "Demand-Based Option Pricing", "Review of Financial Studies", 2009))),
)
LIBRARY: dict[str, Entry] = {e.name: e for e in ENTRIES}
#: The structures only the timing-filter entry may use (GOAL 2.2: "long_single kept only for the timing-filter class").
SINGLES = frozenset({"long_single", "long_call", "long_put"})


def entry(name: Any) -> Entry | None:
    return LIBRARY.get(str(name or "").strip().lower())


def names() -> tuple[str, ...]:
    return tuple(LIBRARY)


def _number(raw: Any) -> float | None:
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def activity(raw: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """A card's `library_class`, `sessions_per_year` and `structures_per_session`, canonical, and the problems: the class
    one of `LIBRARY`, the sessions a whole number from 1 to SESSIONS_MAX, the structures a number above 0 and at most
    STRUCTURES_MAX (two decimals). A field missing is a problem; the caller decides whether they are required."""
    out: dict[str, Any] = {}
    errors: list[str] = []
    found = entry(raw.get("library_class"))
    if found is None:
        errors.append(f"library_class: {raw.get('library_class')!r} is not one of {', '.join(LIBRARY)}")
    else:
        out["library_class"] = found.name
    sessions = _number(raw.get("sessions_per_year"))
    if sessions is None or sessions != int(sessions) or not 1 <= sessions <= SESSIONS_MAX:
        errors.append(f"sessions_per_year: the traded sessions a year you expect, a whole number from 1 to {SESSIONS_MAX} "
                      f"({raw.get('sessions_per_year')!r} given)")
    else:
        out["sessions_per_year"] = int(sessions)
    per = _number(raw.get("structures_per_session"))
    if per is None or not 0 < per <= STRUCTURES_MAX:
        errors.append(f"structures_per_session: the structures opened on a traded session, above 0 and at most "
                      f"{STRUCTURES_MAX} ({raw.get('structures_per_session')!r} given)")
    else:
        out["structures_per_session"] = round(per, 2)
    return out, errors


def check(card: Mapping[str, Any], structure: Any, roots: Sequence[str]) -> list[str]:
    """Why a carded proposal is outside the library (ADMISSION in the module docstring), each problem naming its field; []
    when it is inside. `card` is a validated card (cards.validate) carrying `library_class` and the expected activity."""
    from . import evidence
    from .strategist import root_group  # a local import: the strategist imports the architect, which imports this

    found = entry(card.get("library_class"))
    if found is None:
        return [f"library_class: {card.get('library_class')!r} is not one of {', '.join(LIBRARY)}"]
    out: list[str] = []
    if str(structure) not in found.structures:
        out.append(f"structure: {structure} is not one of {found.name}'s ({', '.join(found.structures)})")
    groups = sorted({root_group(r) for r in roots or []} - set(found.root_groups))
    if groups:
        out.append(f"roots: {found.name} trades {', '.join(found.root_groups)} roots, not {', '.join(groups)}")
    if card.get("mechanism_class") not in found.card_classes:
        out.append(f"mechanism_class: {card.get('mechanism_class')} is not one of {found.name}'s "
                   f"({', '.join(found.card_classes)})")
    if card.get("holding") not in found.holding:
        out.append(f"holding: {card.get('holding')} is not one of {found.name}'s ({', '.join(found.holding)})")
    sessions = card.get("sessions_per_year")
    per = card.get("structures_per_session")
    if not isinstance(sessions, int) or not isinstance(per, (int, float)):
        out.append("sessions_per_year and structures_per_session: both are required")
    elif sessions < evidence.MIN_DAYS or sessions * float(per) < evidence.MIN_TRADES:
        out.append(f"expected activity: {sessions} sessions a year at {per:g} structures a session can never reach the "
                   f"validation line's {evidence.MIN_TRADES} trades on {evidence.MIN_DAYS} days a year")
    return out


def library_text(structures: Sequence[str] | None = None) -> str:
    """THE MECHANISM LIBRARY as the architect and the strategist read it (model-safe: ASCII, no year or date, no figure
    of Validation or the holdout, no family name). `structures` (THE STRUCTURES the architect may bear) narrows each
    entry's list to those; an entry left with none is listed as closed."""
    allowed = None if structures is None else set(structures)
    lines = ["THE MECHANISM LIBRARY (every family is born from one entry: its card's library_class names it, and its "
             "structure, roots, mechanism_class and holding must be that entry's):"]
    for e in ENTRIES:
        types = [s for s in e.structures if allowed is None or s in allowed]
        head = f"- {e.name}: {e.title}."
        if not types:
            lines.append(head + " Closed: none of its structures may be born now.")
            continue
        lines.append(head)
        lines.append(f"  Premium: {e.premium}")
        lines.append(f"  Expressions: {e.expressions}")
        lines.append(f"  Structures: {', '.join(types)}. Roots: {', '.join(e.root_groups)}. Card classes: "
                     f"{', '.join(e.card_classes)}. Holding: {', '.join(e.holding)}.")
        lines.append("  Literature: " + "; ".join(c.text() for c in e.citations) + ".")
    lines.append("ENTRY FILTERS for every family that buys premium: no long single opened on a Friday and held over the "
                 "weekend; no bearish premium bought while implied volatility is rich. Single-name anomaly mining is not "
                 "in the library; cross_root_lead_lag is at most a quarter of births.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------------------------------- the lead-lag quota
def _born_at(raw: Any) -> float | None:
    try:
        return dt.datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


class LeadLagQuota:
    """THE LEAD-LAG QUOTA for one pass (the module docstring): the trailing window's architect births and how many were
    lead-lag (their cards' `library_class`), plus this pass's own births as `admit` makes them."""

    def __init__(self, store: Any, *, now: float, share: float = LEAD_LAG_SHARE, window_days: float = LEAD_LAG_WINDOW_DAYS):
        from . import cards

        self.share = float(share)
        since = now - float(window_days) * 86400.0
        rows = store._all("SELECT id, born_at FROM families WHERE origin='architect'")
        recent = [r["id"] for r in rows if (_born_at(r["born_at"]) or 0.0) >= since]
        self.births = len(recent)
        self.lead_lag = 0
        if recent and cards._tables(store):
            for fid in recent:
                row = store._one("SELECT card FROM family_cards WHERE family=?", (fid,))
                try:
                    card = json.loads(row["card"]) if row else {}
                except (TypeError, ValueError):
                    card = {}
                self.lead_lag += int(isinstance(card, dict) and card.get("library_class") == LEAD_LAG)
        self.refused = 0

    def admits(self, library_class: Any) -> bool:
        """Whether a birth of this class keeps lead-lag births at most `share` of the window's births, counting it."""
        if library_class != LEAD_LAG:
            return True
        ok = (self.lead_lag + 1) <= self.share * (self.births + 1) + 1e-9
        self.refused += int(not ok)
        return ok

    def born(self, library_class: Any) -> None:
        self.births += 1
        self.lead_lag += int(library_class == LEAD_LAG)

    def text(self) -> str:
        room = max(0, math.floor(self.share * (self.births + 1) + 1e-9) - self.lead_lag)
        return (f"LEAD-LAG QUOTA: cross_root_lead_lag holds {self.lead_lag} of the last {LEAD_LAG_WINDOW_DAYS} days' "
                f"{self.births} births; at most a quarter may be lead-lag, so "
                + ("one more may be born now." if room else "no lead-lag family is born now: propose another entry."))


__all__ = ["LIBRARY", "ENTRIES", "Entry", "Citation", "LEAD_LAG", "LEAD_LAG_SHARE", "LEAD_LAG_WINDOW_DAYS", "SINGLES",
           "SESSIONS_MAX", "STRUCTURES_MAX", "entry", "names", "activity", "check", "library_text", "LeadLagQuota"]
