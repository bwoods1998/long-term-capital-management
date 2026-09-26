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


def _names(param_names: Iterable[str]) -> list[str]:
    out = []
    for name in param_names:
        name = str(name or "").strip().lower()
        if len(name) >= 3:
            out.append(name)
            if "_" in name:
                out.append(name.replace("_", " "))
    return out


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


__all__ = ["note_text", "news_text", "param_names_of"]
