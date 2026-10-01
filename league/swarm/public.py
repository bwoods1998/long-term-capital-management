"""What the swarm lets reach the public site: words, never code, never a parameter, never a number from a result.

The data licenses (ThetaData; the market-data subscription) forbid publishing quotes and anything fitted to them,
and the page and the repository are public. Researchers write their notebooks for themselves, in whatever form
helps them; only a filtered sentence ever leaves (`swarm.note`), and the House's publisher masks it again
(`league/publish.py` `words`).

- `note_text` (a researcher's note): keeps only sentences with NO digit, NO number written as a word (zero to ninety,
  hundred, thousand, half, third, quarter, point, percent, the ordinals and fraction words), no colon, nothing in
  brackets, no code mark (`= _ { } [ ] < > backtick # |`, `->`, `ctx.`, `np.`, `PARAMS`, `NEEDS`, `def `, `return `,
  `import `, `lambda`) and no parameter name of the family's program (written with underscores or spaces). Nothing
  left: nothing is published. The researcher is told its notes are public (the role prompt, the note tools).
- `news_text` (a mechanism, a band's reason, a retirement's cause): drops a sentence with a code mark or a parameter
  name, and removes every decimal number and anything in brackets; plain integers stay ("in 30 revisions").
- `thesis_text` (why an agent trades, for the site's rationale card, Oct 1, 2026): the family's full mechanism in WHOLE
  sentences only, in order while they fit (280), each with no digit, no number written as a word (but the pronoun "one":
  "investors reprice one on the other's news"; never "one standard deviation", "one day", "one twenty"), no colon, nothing
  in brackets, no code mark and no parameter name, and ending ".", "!" or "?" (a fragment a cut left never shows). Only
  when the first kept sentence alone is too long is it cut at a word, ending "…".
- `tag_text` (the short reason an order carried, its `why`): the same rules over the whole tag, which needs no full stop;
  None when it is longer than its limit, or exactly the 80 characters a stored tag is cut to (`positions.tag`).
- `unspelled`: the parameter names a thesis or a tag is filtered against, but those the agent's own public id already
  spells word for word (the id is on the page, so its words reveal nothing).

Standard library only.
"""

from __future__ import annotations

import ast
import re
from typing import Any, Iterable

CODE = re.compile(r"[=_{}\[\]<>`#|\\]|->|::|\bctx\.|\bnp\.|\bPARAMS\b|\bNEEDS\b|\bdef\s|\breturn\s|\bimport\s|\blambda\b")
SENTENCE = re.compile(r"(?<=[.!?])\s+")
#: A number written as a word: a fitted value can hide in words ("a twenty five delta", "point one eight", "two thirds").
NUMBER_WORDS = re.compile(
    r"\b(zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|"
    r"eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|hundreds|thousand|thousands|million|"
    r"half|halves|halve|third|thirds|quarter|quarters|fourth|fourths|fifth|fifths|sixth|sixths|seventh|eighth|ninth|tenth|tenths|"
    r"hundredth|hundredths|first|second|twice|thrice|double|triple|dozen|point|percent|percentage|percentages|fraction|"
    r"fractions|basis|bps|pct)\b", re.I)
DECIMAL = re.compile(r"[-+]?\$?\d*\.\d+%?|\d+(?:\.\d+)?\s*%|\$\s*\d[\d,]*(?:\.\d+)?")
BRACKETED = re.compile(r"\s*\([^)]*\)")
#: A word that makes the number word before it a measure ("one standard deviation", "one day", "one strike"): the pronoun
#: "one" passes only away from these and from other number words (`thesis_text`).
UNIT_WORDS = frozenset({
    "day", "days", "session", "sessions", "week", "weeks", "month", "months", "year", "years", "hour", "hours", "minute",
    "minutes", "bar", "bars", "standard", "sigma", "sigmas", "deviation", "deviations", "strike", "strikes", "contract",
    "contracts", "lot", "lots", "leg", "legs", "percent", "point", "points", "dte", "delta", "deltas", "times", "x", "tick",
    "ticks", "cent", "cents", "dollar", "dollars"})
#: The marks a thesis or a tag never carries (the site's `thesisWords`): a colon, brackets of any kind, and the marks only
#: code or a formula uses (`CODE` holds most of them too).
THESIS_MARKS = re.compile(r"[:()\[\]{}<>=_`#|\\]")
#: A stored tag is the order's reason cut to this many characters (`league/live/real.py`: `tag=order.why[:80]`): a tag
#: exactly this long was presumed cut, and a cut tag never shows.
STORED_TAG_LENGTH = 80


def _names(param_names: Iterable[str]) -> list[str]:
    out = []
    for name in param_names:
        name = str(name or "").strip().lower()
        if len(name) >= 3:
            out.append(name)
            if "_" in name:
                out.append(name.replace("_", " "))
    return out


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
        low = sentence.lower()
        if not sentence or any(ch.isdigit() for ch in sentence) or CODE.search(sentence) or any(n in low for n in names) \
                or NUMBER_WORDS.search(sentence) or ":" in sentence or "(" in sentence or ")" in sentence:
            continue
        keep.append(sentence)
    out = " ".join(keep).strip()
    return out[:limit] if len(out) >= 12 else None


def _units(text: str) -> int:
    """A string's length as JavaScript counts it (UTF-16 code units): how the site measures every limit."""
    return len(text.encode("utf-16-le", "surrogatepass")) // 2


def numbered(sentence: str) -> bool:
    """A number written as a word, except the pronoun "one" ("investors reprice one on the other's news"): "one" counts
    as a number beside another number word or before a unit ("one standard deviation", "one day", "one twenty")."""
    tokens = re.findall(r"[a-z']+", sentence.lower())
    for i, token in enumerate(tokens):
        if NUMBER_WORDS.fullmatch(token):
            if token != "one":
                return True
            before = tokens[i - 1] if i else ""
            after = tokens[i + 1] if i + 1 < len(tokens) else ""
            if NUMBER_WORDS.fullmatch(before) or NUMBER_WORDS.fullmatch(after) or after in UNIT_WORDS:
                return True
    return False


def _plain(text: str, names: list[str]) -> bool:
    """`text` carries no digit, no number word (but the pronoun "one"), no colon, no bracket, no code mark and no
    parameter name: the rules of `thesis_text` and `tag_text`."""
    low = text.lower()
    return bool(text) and not any(ch.isdigit() for ch in text) and not CODE.search(text) and not THESIS_MARKS.search(text) \
        and not any(n in low for n in names) and not numbered(text)


def thesis_text(text: Any, *, param_names: Iterable[str] = (), limit: int = 280, minimum: int = 12) -> str | None:
    """Why an agent trades, in its family's own whole sentences, or None (the module docstring)."""
    names = _names(param_names)
    keep = [s for s in SENTENCE.split(" ".join(str(text or "").split())) if _plain(s, names) and s[-1] in ".!?"]
    out = ""
    for sentence in keep:  # whole sentences in order while they fit
        joined = (out + " " + sentence).strip()
        if _units(joined) > limit:
            break
        out = joined
    if not out and keep:  # the first alone is too long: cut at a word, ending "…"
        cut = keep[0][:limit]
        while cut and _units(cut) > limit - 1:
            cut = cut[:-1]
        out = cut.rsplit(" ", 1)[0].rstrip(" ,;-") + "…" if " " in cut else ""
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
        if not sentence or CODE.search(sentence) or any(n in sentence.lower() for n in names):
            continue
        keep.append(sentence)
    out = " ".join(keep).strip()
    return out[:limit] if len(out) >= 8 else None


__all__ = ["news_text", "note_text", "numbered", "param_names_of", "tag_text", "thesis_text", "unspelled"]
