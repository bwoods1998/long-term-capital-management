"""THE SEATS AND THE SLEEVE AS TWO NUMBERS (release E5-S, Oct 11, 2026): the tests' own side of the rule, by hand.

`equity_money.probe.max_programs` (the seats) and `probe.sleeve_share` (a seat's share of E) are set together by one
mechanical step (`set_design SEATS SLEEVE`: the constitution's `probe` comment). No test of the tree may assume the
pair in force, so every expected size and count is computed HERE, from the table's rows and the rule written out in
this file, and never by calling the code under test:

- `Rows`, `rows_of`: the rows the rule reads, from a constitution (the one in force, or a candidate's: `constitution_at`).
- `walk`: the sizing rule of league/equity/sizing.py's docstring written out as arithmetic, one ask after another (the
  caps in the order ties are named, the floor to whole millionths of a share, the minimum order).
- `figures`: the closed forms the documents state (a one-ETF lot, how many lots fit under each cap, the budget's E).
  league/tests/test_equity_design.py holds each to `walk` and to the House's own `size_entry` (`Lane`).
- `Lane`: an equity lane sized by the REAL `size_entry` on the facts `EquityBook._size` states to it.
- `CANDIDATES`, `REFERENCE`, `DIGESTS`: the pre-registered study EQDONE-3's grid (seats 3, 4, 5, 6 x sleeve 0.50, 0.33,
  0.25), A20's design (three seats at 0.50: what E1 deployed, and the rollback) and each candidate's pinned digests.
- `design`, `reference`: the constitution patched to a candidate for a test's body, so a pin of A20's own figures
  (a digest, a dollar size) is read at A20's design whatever pair is in force.
- `block`, `BLOCKS`, `read_block`: THE DESIGN BLOCK of each document (the constitution's `probe` comment,
  docs/operations.md, league/equity/INTERFACES.md, CHANGELOG.md): the same sentences, whose figures are `figures` of the
  pair in force. `set_design` writes them from here and a test holds every file to them, so the two numbers and their
  rule arithmetic are the only words a design change moves.

Decimal throughout; rule arithmetic only (no figure here is a market's or an account's); standard library only."""

from __future__ import annotations

import copy
import re
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal as D
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence
from unittest.mock import patch

from league.constitution import CONSTITUTION, digest, money_digest

REPO = Path(__file__).resolve().parents[2]
ZERO = D(0)

#: THE GRID of the pre-registered study EQDONE-3: every pair `set_design` may be asked for.
SEATS = (3, 4, 5, 6)
SLEEVES = ("0.50", "0.33", "0.25")
CANDIDATES = tuple((seats, sleeve) for seats in SEATS for sleeve in SLEEVES)
#: A20's design (Oct 11, 2026): what release E1 deployed, and the rollback (`set_design 3 0.50`).
REFERENCE = (3, "0.50")
#: Each candidate's (money digest, full digest), pinned: the grant re-ratifies on the first, `PINNED_DIGEST` is the
#: second. The reference's pair is main's at 7d2d3c84, to the last hex: the rollback restores it exactly.
DIGESTS: dict[tuple[int, str], tuple[str, str]] = {
    (3, "0.50"): ("7e41909a9da3e3f44cb4edd8f37921d7f6edba5a9de84e328624570d94ca146a",
                  "e909eb1040231bc078e878df2d87fad7a1001d86ab3eac32be5f45f2b82c1895"),
    (3, "0.33"): ("900917743dcfa53badb99798ac87d9c69a2b157879d174e621f3514ba8d4bd88",
                  "48f83ee82fbb68d8aa41b1043ab445a566f1bb3c315181f62a8147f6569d8650"),
    (3, "0.25"): ("3a7c52d58911d0c1a39f58cbe79547e343683a18004355b52a9390c8aec04fd2",
                  "6d19fddd271cc46682e48e09ae14364976b76077ca084198874f47dbf4340b43"),
    (4, "0.50"): ("5b687cf48fc6bac3c5b130de7e63dfc71590ed0fdc8c2597e93558b96c41ef3a",
                  "5c531714096750545488d6a8699aa6eeb151ce35f262ad62c3db70e2e6b46c6a"),
    (4, "0.33"): ("1661e03b67f35de873bcd9d7aa66d59807bc70cdfe51c964f99879113da8a3e1",
                  "973363b3f96bffe970b84389cee2f69c8ddcc37a66ce91db5659035a8618987f"),
    (4, "0.25"): ("25f5a13b3b70935186b4b498fd58562b46ee3a6cbec2111fff2b68aa3593492a",
                  "f5d7f330cb2887077c6b7d29fa986b0e8bb4d15b877865790171a6b0d682904a"),
    (5, "0.50"): ("1d4919ebf67f1305032c69396e842011a9aea6f8e2155fd630af552e3345945e",
                  "ebae2274d06c4f470597156c7d83b386ba10e0c4124376fc252021f57803991e"),
    (5, "0.33"): ("ae0509b148b9b4dec10850c51138defd2d3e5c8a3806c00a397aafc36fe519e1",
                  "6c376e6ccffb4f0813c475694fdd183c2c963dddc881d0f7736259114def32b5"),
    (5, "0.25"): ("50cd8863a7576a18bec5371f52cb1c2c12835cd8e9d4f4b6f7720fd224526704",
                  "2195caac2c2447ee48c9ab1cfdcd11be4eef1ce078c044159018e7c440869cf3"),
    (6, "0.50"): ("4c83f17710c59341057d3e83d69da4cc9b146b9822aebb471782121fc738d32a",
                  "4126365e37ed851f119c36f5340834ed7ee56d5cf477c658dfe66e0af9d910b9"),
    (6, "0.33"): ("e66a31c519ab8134a29fd042181c6827b7001fcc1bb7dd0b23d9a4a0a14a1a55",
                  "735e375e170edbb6c459ba30fdd42233ace6fb648f033b7023efd2cc1f5dedcb"),
    (6, "0.25"): ("6c0bc42b8715f5ff7131dfc95c4312ac05d3453ef23e4c4a31bd8cbb195cb8eb",
                  "c3c061b0e320135486a53aedcd375eefb6b8773c9550eaf8f3244453305153b8"),
}
#: A share is floored to this many places of a share (league/equity/config.py `QTY_PLACES`, read here as a figure).
QTY = D("0.000001")
#: The order two caps that tie are named in (the sizing module's docstring, steps 3-7).
CAPS = ("instrument", "sleeve_cap", "sleeve_cash", "invested", "cash", "budget")


# ------------------------------------------------------------------------------------------------------- the rows
@dataclass(frozen=True)
class Rows:
    """What the rule reads: `seats` and `sleeve` (the two numbers), an ETF's share (`etf`: of E for the account, of the
    sleeve for a program), the invested share, the cash reserve, an ETF's open-risk weight, the shared budget's window
    and total, the minimum order, and the collar's two ends (basis points)."""

    seats: int
    sleeve: D
    etf: D
    invested: D
    reserve: D
    weight: D
    window: D
    total: D
    min_order: D
    sized: D
    entry_bp: int
    max_bp: int


def rows_of(constitution: Mapping[str, Any] | None = None) -> Rows:
    c = CONSTITUTION if constitution is None else constitution
    em, budget = c["equity_money"], c["options_money"]["probe"]
    path = em["order_path"]
    return Rows(seats=int(em["probe"]["max_programs"]), sleeve=D(em["probe"]["sleeve_share"]),
                etf=D(em["position_share"]["etf"]), invested=D(em["invested_share"]), reserve=D(em["cash_reserve_usd"]),
                weight=D(em["open_risk_weight"]["etf"]), window=D(budget["loss_budget_usd"]),
                total=D(budget["loss_total_usd"]), min_order=D(em["probe"]["min_order_usd"]),
                sized=D(em["sized"]["sleeve_share"]), entry_bp=int(path["entry_collar_bp"]["etf"]),
                max_bp=int(path["max_collar_bp"]["etf"]))


def in_force(constitution: Mapping[str, Any] | None = None) -> tuple[int, str]:
    """(seats, sleeve) of a constitution's `equity_money.probe`, the sleeve as the row's own string."""
    probe = (CONSTITUTION if constitution is None else constitution)["equity_money"]["probe"]
    return int(probe["max_programs"]), str(probe["sleeve_share"])


def constitution_at(seats: int, sleeve: str) -> dict[str, Any]:
    """A copy of the constitution with the two rows set, and nothing else moved."""
    c = copy.deepcopy(CONSTITUTION)
    c["equity_money"]["probe"]["max_programs"] = int(seats)
    c["equity_money"]["probe"]["sleeve_share"] = str(sleeve)
    return c


@contextmanager
def design(seats: int, sleeve: str) -> Iterator[None]:
    """The constitution in force patched to a pair for the body (the two rows; everything else as it stands)."""
    with patch.dict(CONSTITUTION["equity_money"]["probe"], {"max_programs": int(seats), "sleeve_share": str(sleeve)}):
        yield


def reference():
    """A20's design for the body: three seats at 0.50 (`REFERENCE`)."""
    return design(*REFERENCE)


# ------------------------------------------------------------------------------------------------ the rule, by hand
def walk(r: Rows, E: D, cash: D, asks: Sequence[tuple[str, str]], *, share: D = D("0.5"), price: D = D("100"),
         window_loss: D = ZERO, total_loss: D | None = None,
         held: Mapping[tuple[str, str], D] | None = None) -> list[tuple[D, str]]:
    """THE SIZING RULE WRITTEN OUT. `asks`: (program, ETF) in the order they are sized; each asks for `share` of its
    sleeve at `price` a share and is filled whole at it. `cash`: the account's cash before any lot. `window_loss`,
    `total_loss`: realized Probe losses already in the shared budget. `held`: lots already on the book ((program, ETF)
    -> dollars), bought with cash outside `cash`. [(dollars, the rule that set them)] in the asks' order.

    For each ask, in dollars:
      the sleeve          = sleeve x E
      the target          = share x the sleeve
      instrument room     = etf x E          - every program's holding of this ETF
      sleeve_cap room     = etf x the sleeve - this program's own holding of this ETF
      sleeve_cash room    = the sleeve       - everything this program holds
      invested room       = invested x E     - everything every program holds
      cash room           = the cash left    - the reserve
      budget room         = (the lower of window - window_loss and total - total_loss, less weight x everything held)
                            / weight
    The entry is the target unless a room is under it; then it is the smallest room, named by the first of the six, in
    that order, that is the smallest. Nothing or less: refused under that name. Else floored to whole millionths of a
    share at the price; under the minimum order after that: skipped ("min_order")."""
    lots: dict[tuple[str, str], D] = dict(held or {})
    spent = ZERO
    total_loss = window_loss if total_loss is None else total_loss
    out = []
    for program, symbol in asks:
        everything = sum(lots.values(), ZERO)
        sleeve = r.sleeve * E
        target = share * sleeve
        rooms = {
            "instrument": r.etf * E - sum((usd for (_, s), usd in lots.items() if s == symbol), ZERO),
            "sleeve_cap": r.etf * sleeve - lots.get((program, symbol), ZERO),
            "sleeve_cash": max(ZERO, sleeve - sum((usd for (p, _), usd in lots.items() if p == program), ZERO)),
            "invested": r.invested * E - everything,
            "cash": cash - spent - r.reserve,
            "budget": (min(r.window - window_loss, r.total - total_loss) - r.weight * everything) / r.weight,
        }
        usd, name = target, "intent"
        lowest = min(rooms.values())
        if lowest < target:
            usd, name = lowest, next(cap for cap in CAPS if rooms[cap] == lowest)
        if usd <= 0:
            out.append((ZERO, name))
            continue
        usd = (usd / price).quantize(QTY, rounding=ROUND_DOWN) * price
        if usd < r.min_order:
            out.append((ZERO, "min_order"))
            continue
        lots[(program, symbol)] = lots.get((program, symbol), ZERO) + usd
        spent += usd
        out.append((usd, name))
    return out


def figures(r: Rows, *, E: D = D("2000"), day_multiple: D = D(4)) -> dict[str, Any]:
    """THE CLOSED FORMS the documents state, as shares of E unless a name says dollars or a count:
    - `lot`: a one-ETF program's lot, the sleeve's own share of one ETF: sleeve x etf;
    - `seated`: a lot in every seat, as asked; `one_held`, `one_risk`: what the invested cap lets the lane hold of
      them (the lower of `seated` and the invested share), and its open risk at the ETF weight;
    - `same`, `rest`: how many programs hold a WHOLE lot of one ETF under the instrument cap (etf x E), and what the
      next program's lot of that ETF is;
    - `cash_fit`: how many of the seats' lots fit whole, each in its own ETF, when the account is all the capital
      (cash = E): under the invested cap and with the reserve left in cash;
    - `budget_fit`: how many fit whole in the window with nothing realized, at `E` dollars; `budget_e`: the largest
      whole-dollar E at which every seat's lot still fits the window;
    - `sleeves`, `held`, `held_risk`: whole sleeves asked for, what the invested cap lets the lane hold, its open risk;
    - `sends`, `ladder`, `ladders`: how many sends of one such lot the gateway's day line admits (`day_multiple` x
      equity of buys a day, a cancelled one too), the sends of the collar's whole ladder, and how many entries can
      each climb it."""
    lot = r.sleeve * r.etf
    seated = r.seats * lot
    same = int(r.etf // lot)
    sleeves = r.seats * r.sleeve
    held = min(sleeves, r.invested)
    ladder = r.max_bp // r.entry_bp
    sends = int(day_multiple // lot)
    return {
        "seats": r.seats, "sleeve": r.sleeve, "lot": lot, "seated": seated, "one_held": min(seated, r.invested),
        "one_risk": r.weight * min(seated, r.invested),
        "same": same, "rest": r.etf - same * lot,
        "cash_fit": min(r.seats, int(min(r.invested * E, E - r.reserve) // (lot * E))),
        "budget_fit": min(r.seats, int((r.window / r.weight) // (lot * E))),
        "budget_e": int(r.window / (r.weight * seated)),
        "sleeves": sleeves, "held": held, "held_risk": r.weight * held,
        "sends": sends, "ladder": ladder, "ladders": sends // ladder, "E": E, "day_multiple": day_multiple,
    }


# ------------------------------------------------------------------------------------- the House's own sizing function
class Lane:
    """An equity lane sized by THE REAL `size_entry` (league/equity/sizing.py) on the facts the book states to it
    (league/equity/live.py `EquityBook._size`): the sleeve is `probe.sleeve_share` x E (or the share passed), its free
    cash the sleeve less the program's own lots, the account's holding of the symbol every program's, the invested sum
    every lot, the available cash the account's cash less the reserve (`money.available_cash`), and the budget's room
    the lower of the window's and the total's less the open risk at the ETF weight (`EquityBook._budget_room`).
    Programs buy at their limit and are filled whole at it. `table`: a `league.live.money.Table` (the one in force, or
    a candidate's). `cash`: the account's cash before any lot. `held`: lots already on the book, as `walk`'s."""

    def __init__(self, table: Any, E: Any, cash: Any, *, window_loss: Any = "0", total_loss: Any = None,
                 held: Mapping[tuple[str, str], D] | None = None):
        self.table, self.eq = table, table.equity
        self.E, self.cash = D(str(E)), D(str(cash))
        self.window_loss = D(str(window_loss))
        self.total_loss = self.window_loss if total_loss is None else D(str(total_loss))
        self.lots: dict[tuple[str, str], D] = dict(held or {})
        self.spent = ZERO

    @property
    def invested(self) -> D:
        return sum(self.lots.values(), ZERO)

    def held(self, symbol: str) -> D:
        return sum((usd for (_, s), usd in self.lots.items() if s == symbol), ZERO)

    def own(self, program: str) -> D:
        return sum((usd for (p, _), usd in self.lots.items() if p == program), ZERO)

    def facts(self, program: str, symbol: str, *, share: Any = "0.5", limit: Any = "100.00",
              sleeve_share: D | None = None) -> Any:
        from league.equity.sizing import SizingInputs
        from league.live import money as M

        eq = self.eq
        weight = eq.open_risk_weight["etf"]
        sleeve = (eq.probe_sleeve_share if sleeve_share is None else sleeve_share) * self.E
        cash = self.cash - self.spent
        at_risk = weight * self.invested
        return SizingInputs(
            symbol=symbol, klass="etf", share=D(str(share)), usd=None, limit_price=D(str(limit)), E=self.E,
            sleeve_equity=sleeve, sleeve_free_cash=max(ZERO, sleeve - self.own(program)),
            sleeve_symbol_value=self.lots.get((program, symbol), ZERO), position_share=eq.position_share["etf"],
            account_symbol_value=self.held(symbol), invested_now=self.invested, invested_share=eq.invested_share,
            available_cash=M.available_cash({"cash": str(cash), "short_market_value": "0"}, working_buys_worst=ZERO,
                                            reserved=ZERO, reserve_usd=eq.cash_reserve),
            cash=cash, any_short=False,
            budget_room=min(self.table.probe_loss_budget - self.window_loss - at_risk,
                            self.table.probe_loss_total - self.total_loss - at_risk),
            weight=weight, min_order_usd=eq.min_order_usd)

    def buy(self, program: str, symbol: str, **kw: Any) -> Any:
        from league.equity.sizing import size_entry

        out = size_entry(self.facts(program, symbol, **kw))
        if out.usd > 0:
            self.lots[(program, symbol)] = self.lots.get((program, symbol), ZERO) + out.usd
            self.spent += out.usd
        return out


def table_at(seats: int, sleeve: str) -> Any:
    """The House's money table (`league.live.money.Table`) of a candidate's constitution."""
    from league.live import money as M

    return M.Table.from_constitution(constitution_at(seats, sleeve))


# ------------------------------------------------------------------------------------------------- the design blocks
def sh(value: D) -> str:
    """A share of E as the documents write it: at least two decimals, at most four, no trailing zero past two."""
    text = f"{D(value).quantize(D('0.0001'))}"
    while len(text.split(".")[1]) > 2 and text.endswith("0"):
        text = text[:-1]
    return text


def usd(value: Any) -> str:
    return f"${int(value):,}"


def gateway_day_multiple(repo: Path = REPO) -> D:
    """The gateway's STOCK_DAY_EQUITY_MULTIPLE (gateway/wrangler.jsonc, read as text: the var set once)."""
    [value] = re.findall(r'^\s*"STOCK_DAY_EQUITY_MULTIPLE"\s*:\s*"([^"]*)"', (repo / "gateway" / "wrangler.jsonc").read_text(),
                         flags=re.M)
    return D(value)


#: THE DESIGN BLOCK's sentences: the same words in every document; the slots are `figures` of the pair in force.
BODY = (
    "THE DESIGN IN FORCE: {seats} seats (`probe.max_programs`, `elane.roster`), a Probe sleeve of {sleeve} x E",
    "(`probe.sleeve_share`). A one-ETF program's lot is `position_share.etf` ({etf}) of its sleeve: {lot} x E.",
    "A lot in every seat asks for {seated} x E of ETFs; the lane holds at most {one_held} x E of them, {one_risk} x E of",
    "open risk at weight {weight}. One ETF across programs (the instrument cap, {etf} x E): {same} whole lots fit; the",
    "next program's lot of it is {rest} x E. At E = {E}, the account all cash and nothing realized: {cash_fit} of",
    "{seats} whole lots fit under the invested cap ({invested} x E) and the ${reserve} cash reserve alone, and",
    "{budget_fit} of {seats} in the ${window} window alone; the window alone holds all {seats} up to E = {budget_e}.",
    "Whole sleeves (programs that hold several ETFs) ask for {sleeves} x E; the lane holds at most {held} x E,",
    "{held_risk} x E of open risk. The options Probe lane keeps ${window} less the window's realized loss less {weight} x",
    "the equity lots: ${window} - {one_risk} x E against the one-ETF lots above. The gateway's day line ({day_multiple}x",
    "equity of buys a day, a cancelled one too) admits {sends} sends of such a lot: {ladders} entries can each climb the",
    "collar's ladder of {ladder} sends. A Sized sleeve (the step is parked) would be between {sleeve} x E and",
    "{sized} x E.",
)
#: The documents' line beside the block's: the digests of the pair in force (never in the constitution's own comment).
DIGEST_LINE = ("Money digest `{money}`, full digest `{full}` (`PINNED_DIGEST`); the rollback, `set_design 3 0.50`, is "
               "`{back_money}` / `{back_full}`.")
#: Where each block lives: (path, the line that opens it, the line that closes it, each line's prefix).
BLOCKS: dict[str, tuple[str, str, str, str]] = {
    "constitution": ("league/constitution.py", "    # <equity-design>", "    # </equity-design>", "    #   "),
    "operations": ("docs/operations.md", "<!-- equity-design:begin -->", "<!-- equity-design:end -->", ""),
    "interfaces": ("league/equity/INTERFACES.md", "<!-- equity-design:begin -->", "<!-- equity-design:end -->", ""),
    "changelog": ("CHANGELOG.md", "<!-- equity-design:begin -->", "<!-- equity-design:end -->", ""),
}


def slots(constitution: Mapping[str, Any] | None = None, *, repo: Path = REPO) -> dict[str, str]:
    """Every slot of `BODY` and `DIGEST_LINE` as text, from a constitution's rows (the one in force when None)."""
    c = CONSTITUTION if constitution is None else constitution
    r = rows_of(c)
    f = figures(r, day_multiple=gateway_day_multiple(repo))
    back = copy.deepcopy(dict(c))
    back["equity_money"]["probe"].update(max_programs=REFERENCE[0], sleeve_share=REFERENCE[1])
    return {
        "seats": str(f["seats"]), "sleeve": sh(f["sleeve"]), "etf": sh(r.etf), "lot": sh(f["lot"]),
        "seated": sh(f["seated"]), "one_held": sh(f["one_held"]), "one_risk": sh(f["one_risk"]),
        "weight": sh(r.weight), "same": str(f["same"]),
        "rest": sh(f["rest"]), "invested": sh(r.invested), "reserve": f"{r.reserve:f}", "cash_fit": str(f["cash_fit"]),
        "window": f"{r.window:f}", "budget_fit": str(f["budget_fit"]), "E": usd(f["E"]), "budget_e": usd(f["budget_e"]),
        "sleeves": sh(f["sleeves"]), "held": sh(f["held"]), "held_risk": sh(f["held_risk"]),
        "day_multiple": f"{f['day_multiple']:f}", "sends": str(f["sends"]), "ladders": str(f["ladders"]),
        "ladder": str(f["ladder"]), "sized": sh(r.sized),
        "money": money_digest(dict(c))[:8], "full": digest(dict(c))[:8],
        "back_money": money_digest(back)[:8], "back_full": digest(back)[:8],
    }


def block(kind: str, constitution: Mapping[str, Any] | None = None, *, repo: Path = REPO) -> list[str]:
    """THE DESIGN BLOCK of document `kind` (`BLOCKS`) as its lines, between (not with) the lines that open and close
    it: `BODY` filled from the constitution's rows, each line under the document's prefix; the digests' line after it
    in every document but the constitution itself."""
    prefix = BLOCKS[kind][3]
    values = slots(constitution, repo=repo)
    lines = [prefix + line.format(**values) for line in BODY]
    if kind != "constitution":
        lines.append(prefix + DIGEST_LINE.format(**values))
    return lines


def read_block(kind: str, *, repo: Path = REPO) -> list[str]:
    """The lines a document holds between its block's opening and closing lines (each exactly once in the file)."""
    path, begin, end, _ = BLOCKS[kind]
    lines = (repo / path).read_text(encoding="utf-8").split("\n")
    if lines.count(begin) != 1 or lines.count(end) != 1 or lines.index(begin) > lines.index(end):
        raise ValueError(f"{path}: the design block's lines ({begin!r}, {end!r}) are each there once, in order")
    return lines[lines.index(begin) + 1:lines.index(end)]


def write_block(kind: str, constitution: Mapping[str, Any] | None = None, *, repo: Path = REPO) -> bool:
    """Write document `kind`'s block from the constitution's rows; True when the file changed. (`set_design`'s.)"""
    path, begin, end, _ = BLOCKS[kind]
    file = repo / path
    text = file.read_text(encoding="utf-8")
    lines = text.split("\n")
    read_block(kind, repo=repo)
    a, b = lines.index(begin), lines.index(end)
    new = "\n".join(lines[:a + 1] + block(kind, constitution, repo=repo) + lines[b:])
    if new == text:
        return False
    file.write_text(new, encoding="utf-8")
    return True


__all__ = ["SEATS", "SLEEVES", "CANDIDATES", "REFERENCE", "DIGESTS", "Rows", "rows_of", "in_force", "constitution_at",
           "design", "reference", "walk", "figures", "Lane", "table_at", "sh", "usd", "gateway_day_multiple", "BODY",
           "DIGEST_LINE", "BLOCKS", "slots", "block", "read_block", "write_block"]
