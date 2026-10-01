"""What the swarm lets reach the public site: words, never code, never a parameter, never a number from a result.

The data licenses (ThetaData; the market-data subscription) forbid publishing quotes and anything fitted to them,
and the page and the repository are public. Researchers write their notebooks for themselves, in whatever form
helps them; only a filtered sentence ever leaves (`swarm.note`), and the House's publisher masks it again
(`league/publish.py` `words`).

A NUMBER, everywhere below (`numbered`, `plain_glyphs`; the swarm window's safety review, Oct 1, 2026, and its
post-fix verification): a digit or a numeral of any script ("½", "Ⅻ", "〇", "٣"); a number word, cardinal or ordinal, any
fraction word, every cardinal's plural ("fives", "sixes", "the twenties") and the multiples ("doubled", "treble",
"quintuple"); "a dozen", "a fortnight", "a nickel", "a dime", "a decile", "a couple", "unity"; "quarter" but the
calendar's ("each quarter", "quarter-end", "the quarter's end"); "score" as a count ("a score of", "scores of"; "the
z-score" passes; "pair" is never a number: a pairs trade); a number run together ("twentyfive", "tenpercent",
"threefold", "twentyish", "twentyodd", "thirtysomething", "tenpct", "fiftybps", "halfsigma"); a word split by marks that
joins into one ("twen·ty", "t.e.n", "fif-ty's"); "single" or "a"/"an" before a unit of spread ("a single sigma", "an
ATR"); "ones" beside a number or before a unit ("ones and twos"; "the ones that lag" passes); and "one" except as a
pronoun ("one another", "one of", "one on the other", "one or the other", "no one", "the one", "each one", "any one",
"one's", "one-sided"): "one stdev", "one ATR", "one trading session" and "one more week" are numbers. Text is read in
lower case after NFKD folding with every combining mark dropped, so a fullwidth or styled letter is the letter it looks
like and an accented one its bare letter ("twénty"); an apostrophe splits a word ("fifty's", "'twenty'"), but the
pronoun's "one's". A sentence with an invisible format mark (a soft hyphen, a zero-width joiner), a combining mark, a
control character, or a letter or symbol beyond Latin-1 ("οne" with a Greek omicron) is refused whole. A parameter name
matches written with underscores, spaces, hyphens or nothing between its words ("drift_window", "drift window",
"drift-window", "driftwindow"), and with accents folded away. The site mirrors the word rules (`numbered` in its
`capital/capital.js`); `league/tests/fixtures/number_words.json` is the case list both test against.

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
  None when it is longer than its limit, or exactly the length it was cut to where it was stored (`stored`: a tag's 80,
  `positions.tag`; the 240 of an open's reason on the tape, `league/publish.py` `tape_why`).
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
             "ninetieth hundredth thousandth millionth billionth trillionth").split()
#: Every ordinal's plural is a fraction ("two thirds", "sixteenths"), but "firsts" and "seconds".
_FRACTIONS = [word + "s" for word in _ORDINALS if word not in ("first", "second")]
#: Every cardinal's plural ("fives", "sixes", "the twenties", "hundreds", "zeros" and "zeroes"), but "ones", which is a
#: pronoun ("the ones that lag") unless a number or a unit is beside it (`numbered`).
_PLURALS = [w[:-1] + "ies" if w.endswith("y") else w + "es" if w.endswith("x") else w + "s" for w in _CARDINALS if w != "one"] \
    + ["zeroes"]
#: A multiple, as a word and its verb's forms ("double", "doubles", "doubled", "doubling"; "treble", "quintuple").
_MULTIPLES = [form for stem in ("double", "triple", "treble", "quadruple", "quintuple", "sextuple")
              for form in (stem, stem + "s", stem + "d", stem[:-1] + "ing")]
#: The rest. A couple is two ("a couple of sessions"; the verb's "coupled" and "coupling" pass) and unity is one ("above
#: unity"). Never a number: "pair" (a pairs trade, the pair: always the two names it trades, no fitted value) and "score"
#: but as a count ("a score of", "scores of": `numbered`; "the z-score" passes).
_OTHER_NUMBERS = ("half halves halve halved halving quarter quarters twice thrice dozen dozens teens couple couples unity "
                  "point percent percentage percentages fraction fractions basis bps pct fortnight fortnights nickel nickels "
                  "dime dimes penny pennies tercile terciles quartile quartiles quintile quintiles decile deciles").split()
_NUMBER_SET = frozenset(_CARDINALS + _ORDINALS + _FRACTIONS + _PLURALS + _MULTIPLES + _OTHER_NUMBERS)
#: A number written as a word: a fitted value can hide in words ("a twenty five delta", "point one eight", "two thirds").
NUMBER_WORDS = re.compile(r"\b(" + "|".join(sorted(_NUMBER_SET, key=len, reverse=True)) + r")\b", re.I)
DECIMAL = re.compile(r"[-+]?\$?\d*\.\d+%?|\d+(?:\.\d+)?\s*%|\$\s*\d[\d,]*(?:\.\d+)?")
BRACKETED = re.compile(r"\s*\([^)]*\)")
#: A word that makes "single", or "one" in a pronoun's place, a measure ("the one day", "a single standard deviation").
UNIT_WORDS = frozenset({
    "day", "days", "session", "sessions", "week", "weeks", "month", "months", "year", "years", "hour", "hours", "minute",
    "minutes", "bar", "bars", "standard", "sigma", "sigmas", "deviation", "deviations", "strike", "strikes", "contract",
    "contracts", "lot", "lots", "leg", "legs", "percent", "point", "points", "dte", "delta", "deltas", "times", "x", "tick",
    "ticks", "cent", "cents", "dollar", "dollars", "stdev", "stdevs", "sd", "sds", "atr", "atrs", "hr", "hrs", "min", "mins",
    "sec", "secs", "wk", "wks", "mo", "mos", "yr", "yrs", "notch", "notches", "digit", "digits", "unit", "units", "step",
    "steps", "handle", "handles", "bp", "pip", "pips", "trading", "business", "calendar", "full", "whole", "more", "less",
    "extra", "additional", "further"})
#: A unit of spread: "a sigma", "an ATR" and "a standard deviation" are each a number of them.
SPREAD_WORDS = frozenset({"sigma", "stdev", "sd", "standard", "deviation", "atr"})
#: What may follow a number run together, besides another number word and a unit: "threefold", "twentyish", "twentyodd",
#: "thirtysomething", "tenpct", "fiftybps".
_RUN_SUFFIXES = ("fold", "folds", "ish", "odd", "something", "somethings", "pct", "bps")
#: A number run together: a cardinal (or "half", "quarter") then one or more number words, units or `_RUN_SUFFIXES`
#: ("twentyfive", "tenpercent", "threefold", "oneday", "halfsigma", "thirtysomething").
_COMPOUND = re.compile("(?:" + "|".join(sorted(_CARDINALS + ["half", "quarter"], key=len, reverse=True)) + ")(?:"
                       + "|".join(sorted(set(_CARDINALS + _PLURALS + _ORDINALS + _FRACTIONS + list(_RUN_SUFFIXES)) | UNIT_WORDS,
                                         key=len, reverse=True)) + ")+")
#: A word as the number rules read it (`numbered`): a run of letters, or the possessive pronoun "one's" whole. An apostrophe
#: splits a word ("fifty's" is "fifty" and "s"; "'twenty'" is "twenty").
_TOKEN = re.compile(r"one's(?![a-z])|[a-z]+")
_APOSTROPHES = str.maketrans({"\u2018": "'", "\u2019": "'", "\u02bc": "'"})
#: "one" is a pronoun right after these ("no one", "the one", "each one") ...
_ONE_BEFORE = frozenset({"no", "the", "each", "any", "every", "either", "neither", "which", "this", "that"})
#: ... or right before "another", "of" or "sided" ("one another", "one of them", "one-sided"), or before one of these and
#: then "the other", "its other", "another" or "the others" ("reprice one on the other's news", "one or the other", "one
#: after another", "one from the other", "one and the other").
_ONE_RELATIONS = frozenset({"on", "to", "over", "against", "versus", "vs", "after", "or", "from", "than", "and"})
_OTHER = frozenset({"other", "others", "another"})
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
    low = _DASHES.sub("-", _folded(text))
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
    """`text` as the number rules and the parameter names read it: in lower case, NFKD-folded with every combining mark
    dropped (a fullwidth or styled letter is the letter it looks like, and an accented one its bare letter: "twénty" is
    "twenty"), with a typographic apostrophe (\u2018, \u2019, \u02bc) as "'". The site's `numbered` folds the same way:
    `toLowerCase().normalize('NFKD').replace(/\\p{M}/gu, '')`."""
    decomposed = unicodedata.normalize("NFKD", str(text).lower())
    return "".join(ch for ch in decomposed if not unicodedata.category(ch).startswith("M")).translate(_APOSTROPHES)


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
    return bool(token) and (token in _NUMBER_SET or _COMPOUND.fullmatch(token) is not None)


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
    """`tokens[i]` ("quarter") is the calendar's quarter, never a fraction (`_CALENDAR_BEFORE`, `_CALENDAR_AFTER`); the word
    after it is read past a possessive "s" ("the quarter's end")."""
    before = tokens[i - 1] if i else ""
    rest = tokens[i + 1:i + 3]
    after = rest[1] if rest[:1] == ["s"] and len(rest) > 1 else rest[0] if rest else ""
    if after == "of" or _number_word(before) or _number_word(after) or after in UNIT_WORDS:
        return False
    return before in _CALENDAR_BEFORE or after in _CALENDAR_AFTER


def _joined(chunk: str) -> bool:
    """A word split by marks inside it ("twen·ty", "t.e.n", "fif-ty's") is read whole too: the words (`_TOKEN`) of one
    whitespace-separated chunk, less a last "s" (a possessive), when two or more remain, joined, are a number word or a
    number run together. ("quarter's" is one word and an "s", read in its sentence: "the quarter's end" passes.)"""
    parts = _TOKEN.findall(chunk)
    if parts[-1:] == ["s"]:
        parts = parts[:-1]
    return len(parts) > 1 and _number_word("".join(parts))


def numbered(sentence: str) -> bool:
    """A number in words (the module docstring): any number word, a number run together, a word split by marks that joins
    into one, "single" or "a"/"an" before a unit of spread, "one" unless it is the pronoun, "ones" beside a number or before
    a unit, and "score" as a count. Read after `_folded`, word by word (`_TOKEN`)."""
    folded = _folded(sentence)
    if any(_joined(chunk) for chunk in folded.split()):
        return True
    tokens = _TOKEN.findall(folded)
    for i, token in enumerate(tokens):
        before = tokens[i - 1] if i else ""
        after = tokens[i + 1] if i + 1 < len(tokens) else ""
        if token == "one":
            if not _pronoun_one(tokens, i):
                return True
        elif token == "ones":
            if _number_word(before) or _number_word(after) or after in UNIT_WORDS:
                return True               # "ones and twos", "the ones digit"; "the ones that lag" passes
        elif token in ("quarter", "quarters") and _calendar(tokens, i):
            continue
        elif token in ("score", "scores"):
            if after == "of" and (token == "scores" or before == "a" or _number_word(before)):
                return True               # "a score of sessions", "scores of"; "the z-score" passes
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


def tag_text(text: Any, *, param_names: Iterable[str] = (), limit: int = 80, minimum: int = 6,
             stored: int = STORED_TAG_LENGTH) -> str | None:
    """An order's short reason (its `why`) as the public may read it, or None (the module docstring). `stored`: the length
    the reason was cut to where it was stored (a tag's 80; an open's `book.fill` reason's 240), so a reason exactly that
    long was presumed cut."""
    raw = str(text or "")
    if len(raw) > limit or len(raw) == stored:
        return None  # too long to show whole, or a stored reason that was cut
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
