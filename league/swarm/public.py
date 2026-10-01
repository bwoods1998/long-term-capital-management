"""What the swarm lets reach the public site: words, never code, never a parameter, never a number from a result.

The data licenses (ThetaData; the market-data subscription) forbid publishing quotes and anything fitted to them,
and the page and the repository are public. Researchers write their notebooks for themselves, in whatever form
helps them; only a filtered sentence ever leaves (`swarm.note`), and the House's publisher masks it again
(`league/publish.py` `words`).

A NUMBER, everywhere below (`numbered`, `plain_glyphs`; the swarm window's safety review, Oct 1, 2026): a digit or a
numeral of any script ("½", "Ⅻ", "〇", "٣"); a number word, cardinal or ordinal, any fraction word and their plurals
("eleventh", "twelfths", "the twenties", "a dozen", "a fortnight", "a nickel", "a dime", "a decile", "doubled"; "quarter"
but the calendar's, "each quarter", "quarter-end"); a number run together ("twentyfive", "tenpercent", "threefold");
"single" or "a"/"an" before a unit of spread ("a single sigma", "an ATR"); and "one" except as a pronoun ("one another",
"one of", "one on the other", "one or the other", "no one", "the one", "each one", "any one", "one's", "one-sided"): "one
stdev", "one ATR", "one trading session" and "one more week" are numbers. Text is read after NFKC folding, so a
fullwidth or styled letter is the letter it looks like; a sentence with an invisible format mark (a soft hyphen, a
zero-width joiner), a combining mark, a control character, or a letter or symbol beyond Latin-1 ("οne" with a Greek
omicron) is refused whole. A parameter name matches written with underscores, spaces, hyphens or nothing between its
words ("drift_window", "drift window", "drift-window", "driftwindow").

- `note_text` (a researcher's note): keeps only sentences with NO number (and here "one" in any use), no colon, nothing
  in brackets, no code mark (`= _ { } [ ] < > backtick # |`, `->`, `ctx.`, `np.`, `PARAMS`, `NEEDS`, `def `, `return `,
  `import `, `lambda`) and no parameter name of the family's program. Nothing left: nothing is published. The researcher
  is told its notes are public (the role prompt, the note tools).
- `mechanism_text` (a family's mechanism, for the roster and its birth news; Oct 1, 2026): its whole sentences in order
  while they fit, anything in brackets removed, each with no number, no code mark and no parameter name, so no entry
  window or threshold reaches the page ("when 8-21 DTE GLD IV trades below trailing realized vol" never shows).
- `news_text` (a band's reason, a retirement's cause): drops a sentence with a code mark or a parameter name, and removes
  every decimal number and anything in brackets; plain integers stay ("in 30 revisions": the swarm's own rule, never a
  program's).
- `thesis_text` (why an agent trades, for the site's rationale card, Oct 1, 2026): the family's full mechanism in WHOLE
  sentences only, in order while they fit (280), each with no number (the pronoun "one" passes: "investors reprice one on
  the other's news"), no colon, nothing in brackets, no code mark and no parameter name, and ending ".", "!" or "?" (a
  fragment a cut left never shows). Only when the first kept sentence alone is too long is it cut at a word, ending "…".
- `tag_text` (the short reason an order carried, its `why`): the same rules over the whole tag, which needs no full stop;
  None when it is longer than its limit, or exactly the 80 characters a stored tag is cut to (`positions.tag`).
- `unspelled`: the parameter names a thesis or a tag is filtered against, but those the agent's own public id already
  spells word for word (the id is on the page, so its words reveal nothing).

Standard library only.
"""

from __future__ import annotations

import ast
import re
import unicodedata
from typing import Any, Iterable

CODE = re.compile(r"[=_{}\[\]<>`#|\\]|->|::|\bctx\.|\bnp\.|\bPARAMS\b|\bNEEDS\b|\bdef\s|\breturn\s|\bimport\s|\blambda\b")
SENTENCE = re.compile(r"(?<=[.!?])\s+")
_CARDINALS = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen "
              "eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety hundred thousand million billion "
              "trillion").split()
_ORDINALS = ("first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth thirteenth fourteenth fifteenth "
             "sixteenth seventeenth eighteenth nineteenth twentieth thirtieth fortieth fiftieth sixtieth seventieth eightieth "
             "ninetieth hundredth thousandth millionth billionth").split()
#: Every ordinal's plural is a fraction ("two thirds", "sixteenths"), but "firsts" and "seconds".
_FRACTIONS = [word + "s" for word in _ORDINALS if word not in ("first", "second")]
_OTHER_NUMBERS = ("half halves halve halved halving quarter quarters twice thrice double doubles doubled doubling triple triples "
                  "tripled tripling quadruple quadrupled dozen dozens tens teens twenties thirties forties fifties sixties "
                  "seventies eighties nineties hundreds thousands millions billions point percent percentage percentages "
                  "fraction fractions basis bps pct fortnight fortnights nickel nickels dime dimes penny pennies tercile "
                  "terciles quartile quartiles quintile quintiles decile deciles").split()
#: A number written as a word: a fitted value can hide in words ("a twenty five delta", "point one eight", "two thirds").
NUMBER_WORDS = re.compile(r"\b(" + "|".join(_CARDINALS + _ORDINALS + _FRACTIONS + _OTHER_NUMBERS) + r")\b", re.I)
DECIMAL = re.compile(r"[-+]?\$?\d*\.\d+%?|\d+(?:\.\d+)?\s*%|\$\s*\d[\d,]*(?:\.\d+)?")
BRACKETED = re.compile(r"\s*\([^)]*\)")
#: A word that makes "single", or "one" in a pronoun's place, a measure ("the one day", "a single standard deviation").
UNIT_WORDS = frozenset({
    "day", "days", "session", "sessions", "week", "weeks", "month", "months", "year", "years", "hour", "hours", "minute",
    "minutes", "bar", "bars", "standard", "sigma", "sigmas", "deviation", "deviations", "strike", "strikes", "contract",
    "contracts", "lot", "lots", "leg", "legs", "percent", "point", "points", "dte", "delta", "deltas", "times", "x", "tick",
    "ticks", "cent", "cents", "dollar", "dollars", "stdev", "stdevs", "sd", "sds", "atr", "atrs", "hr", "hrs", "min", "mins",
    "sec", "secs", "wk", "wks", "mo", "mos", "yr", "yrs", "notch", "notches", "digit", "digits", "unit", "units", "step",
    "steps", "handle", "handles", "bp", "pip", "pips", "trading", "full", "more", "extra"})
#: A unit of spread: "a sigma", "an ATR" and "a standard deviation" are each a number of them.
SPREAD_WORDS = frozenset({"sigma", "stdev", "sd", "standard", "deviation", "atr"})
#: A number run together ("twentyfive", "tenpercent", "threefold", "oneday").
_COMPOUND = re.compile("(?:" + "|".join(_CARDINALS) + ")(?:" + "|".join(_CARDINALS + _ORDINALS + _FRACTIONS + ["fold", "folds"]
                       + sorted(UNIT_WORDS, key=len, reverse=True)) + ")+")
#: "one" is a pronoun right after these ("no one", "the one", "each one") ...
_ONE_BEFORE = frozenset({"no", "the", "each", "any", "every", "either", "neither", "which", "this", "that"})
#: ... or right before "another", "of" or "sided" ("one another", "one of them", "one-sided"), or before one of these and
#: then "the other", "another" or "the others" ("reprice one on the other's news", "one or the other", "one after another").
_ONE_RELATIONS = frozenset({"on", "to", "over", "against", "versus", "vs", "after", "or"})
_OTHER = frozenset({"other", "other's", "others", "another"})
#: "quarter" is the calendar's, never a fraction, after these ("each quarter", "a new quarter") or before these
#: ("quarter-end", "quarter end"), unless "of" or a number follows ("the last quarter of the session" is a fraction).
_CALENDAR_BEFORE = frozenset({"each", "every", "new", "this", "next", "last", "prior", "previous", "calendar", "fiscal"})
_CALENDAR_AFTER = frozenset({"end", "ends", "start", "starts", "turn", "close", "closes"})
#: The marks a thesis or a tag never carries (the site's `thesisWords`): a colon, brackets of any kind, and the marks only
#: code or a formula uses (`CODE` holds most of them too).
THESIS_MARKS = re.compile(r"[:()\[\]{}<>=_`#|\\]")
#: A stored tag is the order's reason cut to this many characters (`league/live/real.py`: `tag=order.why[:80]`): a tag
#: exactly this long was presumed cut, and a cut tag never shows.
STORED_TAG_LENGTH = 80


def _names(param_names: Iterable[str]) -> list[str]:
    """Each parameter name as it may be written: with underscores, spaces or nothing between its words (a hyphen reads as
    a space or as nothing, `_named`)."""
    out = []
    for name in param_names:
        name = str(name or "").strip().lower()
        if len(name) >= 3:
            out.append(name)
            if "_" in name:
                out.append(name.replace("_", " "))
                if len(name.replace("_", "")) >= 3:
                    out.append(name.replace("_", ""))
    return out


_DASHES = re.compile("[\u2010-\u2015\u2212\ufe58\ufe63\uff0d-]")


def _named(text: str, names: list[str]) -> bool:
    """`text` names one of `names` (`_names`), however its words are joined: "drift-window" and "look-back" name
    `drift_window` and `lookback`."""
    if not names:
        return False
    low = _DASHES.sub("-", unicodedata.normalize("NFKC", text).lower())
    forms = {low, low.replace("-", " "), low.replace("-", ""), low.replace("-", "_")}
    return any(name in form for form in forms for name in names)


def unspelled(param_names: Iterable[str], agent_id: Any) -> list[str]:
    """`param_names` but those the agent's public id already spells word for word (its id is on the page): "qqq_flat"
    for `googl-lags-msft-ai-cloud-qqq-flat`, never "lag" (the id says "lags") nor "flat_band"."""
    words = f"-{str(agent_id or '').lower()}-"
    return [n for n in param_names if f"-{str(n or '').strip().lower().replace('_', '-')}-" not in words]


def param_names_of(code: str | None) -> list[str]:
    """The keys of a program's PARAMS literal (none when it cannot be read)."""
    try:
        tree = ast.parse(code or "")
    except (SyntaxError, ValueError):
        return []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "PARAMS" for t in node.targets):
            if isinstance(node.value, ast.Dict):
                return [k.value for k in node.value.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)]
    return []


def note_text(text: Any, *, param_names: Iterable[str] = (), limit: int = 400) -> str | None:
    """A researcher's note as the public may read it, or None (see the module docstring)."""
    names = _names(param_names)
    keep = []
    for sentence in SENTENCE.split(" ".join(str(text or "").split())):
        if not sentence or not plain_glyphs(sentence) or CODE.search(sentence) or _named(sentence, names) \
                or NUMBER_WORDS.search(_folded(sentence)) or numbered(sentence) or any(mark in sentence for mark in ":()"):
            continue
        keep.append(sentence)
    out = " ".join(keep).strip()
    return out[:limit] if len(out) >= 12 else None


def _units(text: str) -> int:
    """A string's length as JavaScript counts it (UTF-16 code units): how the site measures every limit."""
    return len(text.encode("utf-16-le", "surrogatepass")) // 2


def _folded(text: str) -> str:
    """`text` as the number rules read it: NFKC-folded (a fullwidth or styled letter is the letter it looks like) and in
    lower case, with a typographic apostrophe as "'"."""
    return unicodedata.normalize("NFKC", text).lower().replace("\u2019", "'").replace("\u2018", "'")


def plain_glyphs(text: str) -> bool:
    """No numeral of any script ("½", "Ⅻ", "〇", "٣", "①"), before or after NFKC folding; no control, format or private
    character (a soft hyphen or a zero-width joiner hidden inside a word); no combining mark; and no letter or symbol beyond
    Latin-1 ("οne" with a Greek omicron, a fullwidth "ｏｎｅ", an emoji). Punctuation and mathematical signs pass."""
    for ch in text + unicodedata.normalize("NFKC", text):
        category = unicodedata.category(ch)
        if ch.isnumeric() or category[0] in "CM" or ((category[0] == "L" or category == "So") and ord(ch) > 0xFF):
            return False
    return True


def _number_word(token: str) -> bool:
    return bool(token) and (NUMBER_WORDS.fullmatch(token) is not None or _COMPOUND.fullmatch(token) is not None)


def _pronoun_one(tokens: list[str], i: int) -> bool:
    """`tokens[i]` ("one") is the pronoun (the module docstring), never a count."""
    before = tokens[i - 1] if i else ""
    rest = tokens[i + 1:i + 4]
    after = rest[0] if rest else ""
    if _number_word(before) or _number_word(after) or after in UNIT_WORDS:
        return False                      # "twenty one", "one twenty", "the one day"
    if before in _ONE_BEFORE or after in ("another", "of", "sided"):
        return True                       # "no one", "the one", "one another", "one of", "one-sided"
    if after in _ONE_RELATIONS:           # "one on the other", "one or the other", "one after another"
        tail = rest[1:]
        return bool(tail) and (tail[0] in _OTHER or len(tail) > 1 and tail[0] in ("the", "its") and tail[1] in _OTHER)
    return False


def _calendar(tokens: list[str], i: int) -> bool:
    """`tokens[i]` ("quarter") is the calendar's quarter, never a fraction (`_CALENDAR_BEFORE`, `_CALENDAR_AFTER`)."""
    before = tokens[i - 1] if i else ""
    after = tokens[i + 1] if i + 1 < len(tokens) else ""
    if after == "of" or _number_word(before) or _number_word(after) or after in UNIT_WORDS:
        return False
    return before in _CALENDAR_BEFORE or after in _CALENDAR_AFTER


def numbered(sentence: str) -> bool:
    """A number in words (the module docstring): any number word, a number run together, "single" or "a"/"an" before a
    unit of spread, and "one" unless it is the pronoun."""
    tokens = re.findall(r"[a-z']+", _folded(sentence))
    for i, token in enumerate(tokens):
        after = tokens[i + 1] if i + 1 < len(tokens) else ""
        if token == "one":
            if not _pronoun_one(tokens, i):
                return True
        elif token in ("quarter", "quarters") and _calendar(tokens, i):
            continue
        elif _number_word(token):
            return True
        elif token == "single" and (after in UNIT_WORDS or _number_word(after)):
            return True
        elif token in ("a", "an", "single") and after in SPREAD_WORDS:
            return True
    return False


def _plain(text: str, names: list[str]) -> bool:
    """`text` carries no number (`numbered`, `plain_glyphs`), no colon, no bracket, no code mark and no parameter name:
    the rules of `thesis_text` and `tag_text`."""
    return bool(text) and plain_glyphs(text) and not CODE.search(text) and not THESIS_MARKS.search(text) \
        and not _named(text, names) and not numbered(text)


def thesis_text(text: Any, *, param_names: Iterable[str] = (), limit: int = 280, minimum: int = 12) -> str | None:
    """Why an agent trades, in its family's own whole sentences, or None (the module docstring)."""
    names = _names(param_names)
    keep = [s for s in SENTENCE.split(" ".join(str(text or "").split())) if _plain(s, names) and s[-1] in ".!?"]
    out = _whole(keep, limit)
    return out if _units(out) >= minimum and _units(out) <= limit else None


def tag_text(text: Any, *, param_names: Iterable[str] = (), limit: int = 80, minimum: int = 6) -> str | None:
    """An order's short reason (its `why`) as the public may read it, or None (the module docstring)."""
    raw = str(text or "")
    if len(raw) > limit or len(raw) == STORED_TAG_LENGTH:
        return None  # too long to show whole, or a stored tag that was cut
    tag = " ".join(raw.split())
    if not _plain(tag, _names(param_names)):
        return None
    return tag if minimum <= _units(tag) <= limit else None


def news_text(text: Any, *, param_names: Iterable[str] = (), limit: int = 400) -> str | None:
    """A sentence of the swarm's news (a mechanism, a band's reason, a retirement's cause), or None."""
    names = _names(param_names)
    keep = []
    for sentence in SENTENCE.split(" ".join(str(text or "").split())):
        sentence = BRACKETED.sub("", sentence)
        sentence = DECIMAL.sub("", sentence)
        sentence = " ".join(sentence.split()).strip(" ,;")
        if not sentence or CODE.search(sentence) or _named(sentence, names):
            continue
        keep.append(sentence)
    out = " ".join(keep).strip()
    return out[:limit] if len(out) >= 8 else None


def _whole(sentences: list[str], limit: int) -> str:
    """`sentences` in order while they fit in `limit` (as JavaScript counts); when the first alone is too long, it is cut at a
    word, ending "…"."""
    out = ""
    for sentence in sentences:
        joined = (out + " " + sentence).strip()
        if _units(joined) > limit:
            break
        out = joined
    if not out and sentences:
        cut = sentences[0][:limit]
        while cut and _units(cut) > limit - 1:
            cut = cut[:-1]
        out = cut.rsplit(" ", 1)[0].rstrip(" ,;-") + "…" if " " in cut else ""
    return out


def mechanism_text(text: Any, *, param_names: Iterable[str] = (), limit: int = 240) -> str | None:
    """A family's mechanism for the roster and its birth news, or None (the module docstring): whole sentences with
    anything in brackets removed, each with no number, no code mark and no parameter name."""
    names = _names(param_names)
    keep = []
    for sentence in SENTENCE.split(" ".join(str(text or "").split())):
        sentence = " ".join(BRACKETED.sub("", sentence).split()).strip(" ,;")
        if sentence and plain_glyphs(sentence) and not CODE.search(sentence) and not _named(sentence, names) \
                and not numbered(sentence):
            keep.append(sentence)
    out = _whole(keep, limit)
    return out if len(out) >= 8 else None


__all__ = ["mechanism_text", "news_text", "note_text", "numbered", "param_names_of", "plain_glyphs", "tag_text", "thesis_text",
           "unspelled"]
