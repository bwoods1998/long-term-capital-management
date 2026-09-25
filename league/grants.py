"""Two kinds of grant: House-funded startup research, and the scale rule of the owner's live grant.

**Startup research** (`ResearchGrants`), separate from rewards for demonstrated trading skill.
One nonrenewable grant per family/niche in the current campaign, twelve for the whole floor.
The claim is durable before inference; an interrupted/ambiguous call never buys a replacement.
Children and restarts cannot reset it. Candidate code still needs the normal replay/adoption
path. These grants confer neither trading credit nor qualification.

**The scale rule** (K5 of the Kalshi-scale run, Sept 25, 2026; `docs/goals/LTCM_KALSHI_SCALE.md`):
version 2 of the owner's live grant (`league/live_trading.py` `policy(..., version=2)`), which is
version 1 plus `scale_tranches`. Version 1 says "later deposits do not enlarge this allocation";
version 2 lets a venue's owner deposit enter that venue's envelope in tranches, each only when the
proven families there would use the envelope and the venue has made real money. It is in force only
after the owner ratifies it (`scripts/live_trading.py --ratify <grant> --grant-version 2`), and only
while the ratified policy is the code's version 2 for the grant's capital: a money rule or a
constant below that moves switches it off until the owner ratifies again. The functions here are
pure arithmetic over readings; `league/live_trading.py` reads the readings (the board and the
ledger) and the owner's ratification. The formulas:

- **Capacity used** (`family_capacity`, `capacity_used`): over the venue's PROVEN families (state
  "proven" or "swing" in the mechanism ledger), the dollars their members would commit at the
  stakes their capacity curve supports:

      capacity_used = sum over proven families f of  members_real(f) x stake_usd(f) x m*(f)

  where `members_real` is the family's members on real money, `stake_usd` the stake a member on real
  money is lent (the family's bunt, or its swing stake), and m* the largest multiple of that stake
  before fills halve (`supported_multiple`): walking 1x, 2x, 4x, 8x the family's position size, a
  step counts while its fill rate is measured and is at least `fills_halve_ratio` (the family
  swing's `capacity_fill_ratio`, 0.5) of both the rate at 1x and the rate at the step before. m* is 0
  when the rate at the stake itself is unmeasured or zero, and 1 while the capacity record carries
  no fill curve beyond its own size (a size never measured is never assumed). The curve is the K2
  capacity study's (`scripts/kalshi_capacity.py --json`, the smaller m* of its estimate and its
  floor) for the report's WHAT-IF when it is given one; the rule itself reads the family records' `capacity` (the
  board's, and each `family.record` row's), so a study never decides a tranche or a deposit (review of #313).
  capacity_used counts dollars COMMITTED, never dollars earned: no edge enters it, and capacity alone
  unlocks nothing -- (b) below is the guard against a short streak's edge (Sept 25, 2026: the proven
  sports family's `edge_per_dollar` read +0.27 while a market-wide three-week measure of the same
  mechanism read -0.14).
- **Share** of a day: that day's LOWEST capacity_used over the envelope, against the larger of the
  envelope in force that day and the envelope now: share(d) = min_t capacity_used(t) / max(E(d), E_now).
- **Deposit left**: the venue account's equity (the ledger's last `floor.mark`) above the envelope
  in force, never negative: max(0, funded - E_now).
- **A tranche** = min(deposit left, `tranche_share` x E_now), to the cent, rounded down.
- **Unlock** (`evaluate`), decided at 00:00Z each day (and at the owner's ratification) on the
  `window_days` complete UTC days just before: (a) share(d) >= `min_capacity_share` on EVERY day of
  the window (a day with no allocator reading fails), and (b) the venue's real P&L over the window
  > 0: P(end of the window) - P(start), where P(t) is the sum over every account on the venue's real
  book of equity less what it was lent (`book.mark`, the allocator's `floor_pnl` for one venue):
  realized plus marked, losses in full. A tranche needs a deposit left > 0.
- **Relock** (`replay`): an unlocked tranche is withdrawn the first time the venue's real P&L since
  its unlock, P(t) - P(unlock), falls below `relock_share` x its size, where `relock_share` is the
  allocator's throttle line (`allocator.throttle.halve_below`, -0.30); after a withdrawal the next
  tranche needs a whole window of days after the day of it, and a re-ratification does not erase a withdrawal: the
  grant's earlier version-2 intervals are replayed first (review of #313). Tranches never lift the envelope above
  the account's equity: unlocked <= max(0, funded - base envelope).

Everything else of the grant is unchanged: the throttle, the kill switch, the order and day caps,
and no cap above funded money.
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN
import hashlib
import json
from pathlib import Path
import sqlite3
import time
from typing import Any, Mapping, Sequence

from .campaigns import CampaignClosed
from .frontier import Frontier, FrontierError
from .merton import CONSULT

MODEL = 'gpt-6-luna'  # the research model (league/fast_research.py)
MAX_GRANTS = 12
MAX_CALL_USD = Decimal('0.25')  # at most $3 reserved; inside foundation-review, not extra money


class GrantGuard:
    def __init__(self, campaign):
        self.campaign = campaign

    def reserve(self, ident, name, amount):
        if Decimal(amount) > MAX_CALL_USD:
            raise CampaignClosed('research grant exceeds its per-call reservation ceiling')
        return self.campaign.reserve(ident, name, amount)

    def settle(self, ident, amount):
        return self.campaign.settle(ident, amount)


class ResearchGrants:
    def __init__(self, path, frontier, ledger, *, phase: str, clock=time.time):
        self.path, self.frontier, self.ledger = Path(path), frontier, ledger
        self.phase, self.clock = phase, clock
        db = self._db()
        try:
            db.execute('''CREATE TABLE IF NOT EXISTS grants (
                phase TEXT, family TEXT, niche TEXT, agent TEXT, session TEXT, created REAL,
                status TEXT, reply TEXT, PRIMARY KEY(phase,family,niche))''')
            db.commit()
        finally:
            db.close()

    def _db(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA synchronous=FULL')
        return db

    @classmethod
    def funded(cls, path, gateway_url, token, ledger, campaign, *, clock=time.time):
        model = Frontier(gateway_url, token, model=MODEL, spend_guard=GrantGuard(campaign))
        return cls(path, model, ledger, phase=f'{campaign.started:.6f}', clock=clock)

    def request(self, agent, proposal, evidence, *, session, contract):
        record = evidence.get('record') or {}
        if int(record.get('rung', 0)) > 1 or int(record.get('active_blocks') or 0) > 0:
            return {'error': 'startup grants are for untraded research/paper agents; use earned consultation'}
        fields = ('question', 'hypothesis', 'acceptance_check')
        if any(not isinstance(proposal.get(k), str) or len(proposal[k].strip()) < 30 for k in fields):
            return {'error': 'supply a specific question, falsifiable hypothesis and acceptance_check (30+ characters each)'}
        proposal = {k: proposal[k].strip()[:2000] for k in fields}
        key = (self.phase, agent.family, agent.niche)
        # Each invocation owns a separate connection: concurrent workers/restarted processes
        # serialize admission in SQLite, without holding a transaction over a network call.
        db = self._db()
        try:
            db.execute('BEGIN IMMEDIATE')
            prior = db.execute('SELECT session,status,reply FROM grants WHERE phase=? AND family=? AND niche=?', key).fetchone()
            if prior:
                if prior[0] == session and prior[1] == 'completed':
                    return json.loads(prior[2])
                return {'error': 'this family/niche already used its startup grant; birth, death and restart do not renew it'}
            if db.execute('SELECT COUNT(*) FROM grants WHERE phase=?', (self.phase,)).fetchone()[0] >= MAX_GRANTS:
                return {'error': 'the campaign startup-grant allocation is exhausted'}
            db.execute('INSERT INTO grants VALUES(?,?,?,?,?,?,?,NULL)', (*key, agent.id, session, self.clock(), 'claimed'))
            db.commit()
        finally:
            db.close()
        ident = hashlib.sha256(json.dumps(key).encode()).hexdigest()
        self.ledger.append('agent.research', {'tool': 'research_grant', 'status': 'claimed',
            'session': session, 'model': self.frontier.model, 'proposal': proposal,
            'max_reserved_usd': str(MAX_CALL_USD)}, agent=agent.id, id='grant-claim:'+ident)
        reply = None
        try:
            reply = self.frontier.ask(system=CONSULT + '\n\nHouse startup research grant: resolve the stated hypothesis. '
                'Preserve known-good code when repairing it. Propose no qualification or budget changes. '
                'Report missing evidence explicitly; your confidence does not establish profit.\n\n' + contract,
                user=json.dumps({'proposal': proposal, 'evidence': evidence}, default=str),
                agent='grant-'+agent.id, max_output_tokens=8000, effort='medium')
            answer = reply.json()
            if not isinstance(answer.get('answer'), str) or len(answer['answer'].strip()) < 20:
                raise FrontierError('grant returned no usable answer')
            if answer.get('code') is not None and not isinstance(answer['code'], str):
                raise FrontierError('grant strategy must be source text')
            result = {'answer': answer['answer'][:6000], 'code': answer.get('code') or '',
                'confidence': str(answer.get('confidence') or 'low')[:20], 'model': reply.model,
                'cost_usd': str(reply.cost_usd), 'house_funded': True,
                'note': 'Proposed code only. Preflight inputs and replay it; the House applies normal qualification rules.'}
        except FrontierError as exc:
            result = {'error': str(exc)[:300], 'house_funded': True,
                'cost_usd': str(reply.cost_usd) if reply else None,
                'note': 'Grant consumed; unknown bills retain their campaign reservation. No automatic retry.'}
        db = self._db()
        try:
            with db:
                db.execute('UPDATE grants SET status=?,reply=? WHERE phase=? AND family=? AND niche=?',
                           ('completed', json.dumps(result), *key))
        finally:
            db.close()
        self.ledger.append('agent.research', {'tool': 'research_grant', 'status': 'completed', 'session': session,
            **{k: v for k, v in result.items() if k != 'code'}, 'wrote_code': bool(result.get('code'))},
            agent=agent.id, id='grant-result:'+ident)
        return result


# ------------------------------------------------------------------ the scale rule (K5)
#: The live grant's version that carries `scale_tranches` (`league/live_trading.py` `policy`).
SCALE_VERSION = 2
#: One tranche is the smaller of the deposit left and this share of the envelope in force.
TRANCHE_SHARE = Decimal('0.5')
#: The share of the envelope the proven families must use at capacity on every day of the window.
MIN_CAPACITY_SHARE = Decimal('0.70')
#: The window: this many consecutive complete UTC days before the decision.
WINDOW_DAYS = 3
#: The mechanism ledger's states of a proven family (`league/families.py` STATES).
PROVEN_STATES = ('proven', 'swing')
#: The multiples of a family's position size a fill curve is read at (K2; forward-first's C6).
CURVE_MULTIPLES = (1, 2, 4, 8)
CENT = Decimal('0.01')
ZERO = Decimal(0)
DAY_SECONDS = 86400.0


def _d(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        out = Decimal(str(value))
    except ArithmeticError:
        return None
    return out if out.is_finite() else None


def _cents(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_DOWN)


def day_of(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime('%Y-%m-%d')


def midnight(day: str) -> float:
    return datetime.strptime(day, '%Y-%m-%d').replace(tzinfo=timezone.utc).timestamp()


def iso(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def window_of(today: str, days: int = WINDOW_DAYS) -> list[str]:
    """The `days` complete UTC days just before `today`, oldest first."""
    first = datetime.strptime(today, '%Y-%m-%d')
    return [(first - timedelta(days=k)).strftime('%Y-%m-%d') for k in range(days, 0, -1)]


def scale_tranches(constitution: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """The `scale_tranches` block of the grant's version 2: the constants above, and the two lines it borrows from the
    money rules -- the throttle's `halve_below` (the relock line) and the family swing's `capacity_fill_ratio` (where
    fills halve) -- so that moving either moves the version-2 policy, and the owner ratifies again."""
    from .constitution import CONSTITUTION
    allocator = (constitution or CONSTITUTION).get('allocator') or {}
    throttle = allocator.get('throttle') or {'halve_below': -0.30}  # the allocator's own default (`allocator._params`)
    swing = allocator.get('family_swing') or {}
    return {
        'tranche_share': str(TRANCHE_SHARE), 'min_capacity_share': str(MIN_CAPACITY_SHARE), 'window_days': WINDOW_DAYS,
        'relock_share': str(_d(throttle['halve_below'])), 'fills_halve_ratio': str(_d(swing.get('capacity_fill_ratio', '0.5'))),
        'capacity': ('capacity_used = sum over the venue\'s proven families of members on real money x stake x the largest '
                     'multiple of the stake before fills halve; a day counts its lowest reading against the larger of the '
                     'envelope then and now'),
        'unlock': ('a tranche = min(deposit left, tranche_share x the envelope), when capacity_used >= min_capacity_share x the '
                   'envelope on each of the last window_days complete UTC days and the venue\'s real P&L over them is > 0'),
        'pnl': 'the venue\'s real book: every account\'s equity less what it was lent (book.mark), realized plus marked, losses in full',
        'deposit': 'the venue account\'s equity above the envelope in force (floor.mark); tranches never lift the envelope above it',
        'relock': 'a tranche is withdrawn when the venue\'s real P&L since its unlock falls below relock_share x its size',
        # What a tranche moves once ratified (K5b, Sept 26, 2026: the allocator's line, `Allocator.grant_capital`).
        'reach': ('unlocked tranches raise the envelope, the tuition line and the throttle\'s dollar line by the same amount: '
                  'the allocator\'s envelope at the venue (Allocator.grant_capital, the grant\'s venue capital plus the '
                  'tranches), which every band\'s stakes and headroom read; the House\'s tuition loss line, under which '
                  'every promotion to real money, a new rung-2 seat too, must fit; and the throttle\'s lines (halve_below '
                  f'{_d(throttle["halve_below"])} and restore_above x the envelope summed over the venues), which widen in '
                  'proportion. The daily real_halt basis is unchanged: it stays the grant\'s ratified venue capital, and '
                  'so does the seat count (max_agents).'),
    }


def fill_curve(capacity: Mapping[str, Any] | None) -> dict[int, float]:
    """The fill rate by multiple of the family's position size, from its capacity record: `fill_rate_at_size` is 1x;
    a curve beyond it is read from `fill_curve` ({multiple: rate}, or a list of {"multiple", "fill_rate"}) or from
    `fill_rate_at_<m>x` keys, whichever the record carries (the board carries 1x alone until forward-first's C6)."""
    cap = capacity or {}
    rates: dict[int, float] = {}

    def put(multiple: Any, rate: Any) -> None:
        try:
            m = int(str(multiple).lower().rstrip('x'))
            r = float(rate)
        except (TypeError, ValueError):
            return
        if m in CURVE_MULTIPLES and r == r and 0 <= r <= 1 and m not in rates:
            rates[m] = r

    if cap.get('fill_rate_at_size') is not None:
        put(1, cap['fill_rate_at_size'])
    curve = cap.get('fill_curve')
    if isinstance(curve, Mapping):
        for m, r in curve.items():
            put(m, (r.get('fill_rate') if isinstance(r, Mapping) else r))
    elif isinstance(curve, (list, tuple)):
        for row in curve:
            if isinstance(row, Mapping):
                put(row.get('multiple'), row.get('fill_rate'))
    for m in CURVE_MULTIPLES[1:]:
        if cap.get(f'fill_rate_at_{m}x') is not None:
            put(m, cap[f'fill_rate_at_{m}x'])
    return rates


def supported_multiple(capacity: Mapping[str, Any] | None, ratio: Any) -> int:
    """m*: the largest multiple of the family's stake before fills halve. Walking 1x, 2x, 4x, 8x, a step counts while its
    fill rate is measured and at least `ratio` of both the rate at 1x and the rate at the step before (the family swing's
    `capacity_holds` reads consecutive steps; the base is read too, so a slow slide that halves fills in two steps stops).
    0 when the rate at the stake itself is unmeasured or zero; 1 when the record carries no curve beyond its own size."""
    rates, ratio = fill_curve(capacity), float(ratio)
    base = rates.get(1)
    if base is None or not base > 0:
        return 0
    best, before = 1, base
    for m in CURVE_MULTIPLES[1:]:
        rate = rates.get(m)
        if rate is None or rate < ratio * base or rate < ratio * before:
            break
        best, before = m, rate
    return best


def study_curves(study: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """The fill curves of the K2 capacity study (`scripts/kalshi_capacity.py --json`, Kalshi families only): per family,
    its estimate and its floor as capacity records (`fill_rate_at_size` at 1x, `fill_curve` beyond), and where each
    halves. A family whose study has no rate at 1x is left out: the board's record is read for it."""
    out: dict[str, dict[str, Any]] = {}
    rows = study.get('families') or []
    for row in (rows.values() if isinstance(rows, Mapping) else rows):
        if not isinstance(row, Mapping) or not row.get('family'):
            continue
        curve = row.get('curve') or {}
        records = {}
        for key, field in (('estimate', 'fill_rate'), ('floor', 'fill_floor')):
            rates = {str(k).lower().rstrip('x'): (point or {}).get(field) for k, point in curve.items() if isinstance(point, Mapping)}
            if rates.get('1') is not None:
                records[key] = {'fill_rate_at_size': rates['1'], 'fill_curve': {k: r for k, r in rates.items() if k != '1' and r is not None}}
        if 'estimate' in records:
            out[str(row['family'])] = {**records, 'halves_at': row.get('halves_at'), 'halves_at_floor': row.get('halves_at_floor'),
                                       'edge_per_dollar': row.get('edge_per_dollar')}
    return out


def family_capacity(name: str, row: Mapping[str, Any], ratio: Any, study: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """One family's dollars at capacity: members on real money x its stake x m*, for a PROVEN family; else $0. m* is read
    from the K2 study's curve when `study` (`study_curves`) has the family -- the smaller of what its estimate and its
    floor support -- else from the board's (or the `family.record` row's) capacity record."""
    proven = row.get('state') in PROVEN_STATES
    members = int(row.get('members_real') or 0)
    stake = _d(row.get('stake_usd')) or ZERO
    cap = row.get('capacity') or {}
    measured = (study or {}).get(name)
    if measured:
        multiple = min(supported_multiple(measured[k], ratio) for k in ('estimate', 'floor') if measured.get(k))
        basis, shown = 'K2 capacity study (the smaller of its estimate and floor)', measured['estimate']
    else:
        multiple, basis, shown = supported_multiple(cap, ratio), 'board capacity record', cap
    usd = _cents(members * stake * multiple) if proven and stake > 0 else ZERO
    return {'family': name, 'state': row.get('state'), 'proven': proven, 'members_real': members, 'stake_usd': str(stake),
            'multiple': multiple, 'multiple_basis': basis, 'fill_rate_at_size': shown.get('fill_rate_at_size'),
            'size_usd': cap.get('size_usd'), 'curve': {str(m): r for m, r in sorted(fill_curve(shown).items()) if m > 1} or None,
            'floor_curve': ({str(m): r for m, r in sorted(fill_curve(measured['floor']).items())}
                            if measured and measured.get('floor') else None),
            'halves_at': measured.get('halves_at') if measured else None,
            'edge_per_dollar': row.get('edge_per_dollar'), 'usd_per_day': cap.get('usd_per_day'), 'usd': str(usd)}


def capacity_used(families: Mapping[str, Mapping[str, Any]], ratio: Any,
                  study: Mapping[str, Any] | None = None) -> tuple[Decimal, list[dict[str, Any]]]:
    """(capacity_used in dollars, each proven family's line), for one venue's family rows ({family: row})."""
    lines = [family_capacity(name, row, ratio, study) for name, row in sorted(families.items()) if row.get('state') in PROVEN_STATES]
    lines.sort(key=lambda line: (-Decimal(line['usd']), line['family']))
    return _cents(sum((Decimal(line['usd']) for line in lines), ZERO)), lines


@dataclass(frozen=True)
class Day:
    """One venue's evidence on one UTC day."""
    day: str  # YYYY-MM-DD
    capacity_usd: Decimal  # the day's LOWEST capacity_used
    envelope_usd: Decimal | None  # the LARGEST envelope in force that day (None: no allocator reading)
    readings: int  # the allocator's recorded readings that day (`alloc.board` rows naming the venue)
    pnl_usd: Decimal | None  # the venue's real P&L over the day: P(end) - P(end of the day before); None: unmeasured


def value_before(series: Sequence[tuple[float, Decimal]], t: float, *, inclusive: bool = True) -> Decimal | None:
    """The last value of a time series ((epoch, value), time-ordered) at or before `t` (before, if not `inclusive`)."""
    if inclusive:
        i = bisect.bisect_right(series, (t, Decimal('Infinity')))
    else:
        i = bisect.bisect_left(series, (t, Decimal('-Infinity')))
    return series[i - 1][1] if i > 0 else None


def build_days(venue: str, *, family_rows: Sequence[tuple[float, Mapping[str, Any]]],
               envelopes: Sequence[tuple[float, Decimal]], pnl: Sequence[tuple[float, Decimal]],
               first_day: str, last_day: str, ratio: Any, study: Mapping[str, Any] | None = None) -> dict[str, Day]:
    """Each UTC day from `first_day` to `last_day` from the allocator's recorded rows: `family_rows` (the `family.record`
    rows, oldest first, EVERY one up to the last day: a family's row is written only when it changes, so its state on a
    day is its last row before), `envelopes` (the venue's envelope at each `alloc.board` row) and `pnl` (the venue's
    real P&L at each mark pass). capacity_used is piecewise constant between family rows: the day's lowest is the least
    of its value at the day's start and after each row inside the day."""
    rows = [(t, p) for t, p in family_rows if p.get('venue') == venue and p.get('family')]
    current: dict[str, Mapping[str, Any]] = {}
    out: dict[str, Day] = {}
    i, day = 0, first_day
    while day <= last_day:
        start = midnight(day)
        end = start + DAY_SECONDS
        while i < len(rows) and rows[i][0] < start:
            current[rows[i][1]['family']] = rows[i][1]
            i += 1
        values = [capacity_used(current, ratio, study)[0]]
        while i < len(rows) and rows[i][0] < end:
            current[rows[i][1]['family']] = rows[i][1]
            values.append(capacity_used(current, ratio, study)[0])
            i += 1
        seen = [value for at, value in envelopes if start <= at < end]
        before, after = value_before(pnl, start, inclusive=False), value_before(pnl, end, inclusive=False)
        k = bisect.bisect_left(pnl, (start, Decimal('-Infinity')))
        if not (k < len(pnl) and pnl[k][0] < end):
            # No mark pass inside the day (review of #313): its P&L is unmeasured, not $0 -- the books were dark (a venue
            # whose poll failed all day, the House down) while the allocator may still have published readings.
            after = None
        out[day] = Day(day, min(values), max(seen) if seen else None, len(seen),
                       None if before is None or after is None else after - before)
        day = day_of(end)
    return out


def evaluate(block: Mapping[str, Any], days: Mapping[str, Day], *, today: str, envelope: Any,
             funded: Any) -> dict[str, Any]:
    """Whether the evidence unlocks a tranche today, against the envelope in force now; when it does not, every condition
    that fails, with its number. `days` carries the envelope IN FORCE each day (with any tranche then unlocked)."""
    need, share_of = Decimal(block['min_capacity_share']), Decimal(block['tranche_share'])
    names = window_of(today, int(block['window_days']))
    envelope = _d(envelope) or ZERO
    fails: list[dict[str, Any]] = []
    shares: list[float | None] = []
    target = ZERO
    lowest: Decimal | None = None
    for name in names:
        day = days.get(name)
        if day is None or day.readings <= 0 or day.envelope_usd is None:
            shares.append(None)
            target = max(target, _cents(need * envelope))
            lowest = ZERO
            fails.append({'condition': 'capacity', 'day': name, 'share': None, 'need': float(need),
                          'text': f'no allocator reading on {name}'})
            continue
        against = max(day.envelope_usd, envelope)
        share = day.capacity_usd / against if against > 0 else ZERO
        shares.append(float(share))
        target = max(target, _cents(need * against))
        lowest = day.capacity_usd if lowest is None else min(lowest, day.capacity_usd)
        if share < need:
            fails.append({'condition': 'capacity', 'day': name, 'share': float(share), 'need': float(need),
                          'capacity_usd': str(day.capacity_usd), 'envelope_usd': str(against),
                          'text': f'capacity used {share:.1%} < {need:.0%} on {name} (${day.capacity_usd} of ${against})'})
    pnls = [days[name].pnl_usd if name in days else None for name in names]
    window_pnl = None if any(p is None for p in pnls) else sum(pnls, ZERO)
    if window_pnl is None:
        missing = [name for name, p in zip(names, pnls) if p is None]
        fails.append({'condition': 'pnl', 'pnl_usd': None, 'text': f'the venue\'s real P&L is unmeasured on {", ".join(missing)}'})
    elif window_pnl <= 0:
        fails.append({'condition': 'pnl', 'pnl_usd': str(window_pnl),
                      'text': f'the venue\'s real P&L over {names[0]}..{names[-1]} is ${window_pnl} (needs > $0)'})
    funded = _d(funded)
    deposit = None if funded is None else _cents(max(ZERO, funded - envelope))
    full = _cents(envelope * share_of)
    evidence = not fails
    tranche = min(deposit, full) if evidence and deposit is not None else _cents(ZERO)
    if evidence and not tranche > 0:
        fails.append({'condition': 'deposit', 'deposit_usd': None if deposit is None else str(deposit),
                      'text': ('the account equity is unread (no floor.mark)' if deposit is None
                               else 'no deposit above the envelope: the evidence would unlock a tranche, and nothing is there to enter')})
    return {'today': today, 'window': names, 'shares': shares, 'window_pnl_usd': None if window_pnl is None else str(window_pnl),
            'evidence': evidence, 'unlock': evidence and tranche > 0, 'tranche_usd': str(tranche), 'full_tranche_usd': str(full),
            'deposit_left_usd': None if deposit is None else str(deposit),
            # Unread equity names no deposit (review of #313): the account may already hold it.
            'deposit_to_work_usd': ('0.00' if not evidence else None if deposit is None
                                    else str(_cents(max(ZERO, full - deposit)))),
            'capacity_needed_usd': str(target), 'capacity_gap_usd': str(_cents(max(ZERO, target - (lowest or ZERO)))),
            'fails': fails}


def _live(tranche: Mapping[str, Any], t: float) -> bool:
    return (tranche['unlocked_at'] <= t and (tranche['relocked_at'] is None or tranche['relocked_at'] > t)
            and (tranche.get('ended_at') is None or tranche['ended_at'] > t))


def unlocked_usd(tranches: Sequence[Mapping[str, Any]], t: float, *, base: Any, funded: Any) -> Decimal:
    """The tranches in force at `t`, never lifting the envelope above the account's equity: min(their sum,
    max(0, funded - base)); $0 while the equity is unread."""
    base, funded = _d(base), _d(funded)
    total = sum((Decimal(x['usd']) for x in tranches if _live(x, t)), ZERO)
    if base is None or funded is None:
        return ZERO
    return _cents(min(total, max(ZERO, funded - base)))


def _relock(tranches: list[dict[str, Any]], pnl: Sequence[tuple[float, Decimal]], until: float) -> None:
    for tranche in tranches:
        if tranche['relocked_at'] is not None:
            continue
        line, limit = tranche['line'], min(until, tranche.get('track_until', float('inf')))
        for at, value in pnl:
            if at <= tranche['checked_to']:
                continue
            if at > limit:
                break
            tranche['checked_to'] = at
            if value - tranche['pnl_at_unlock'] < line:
                tranche['relocked_at'] = at
                tranche['pnl_at_relock'] = value - tranche['pnl_at_unlock']
                break
        else:
            tranche['checked_to'] = max(tranche['checked_to'], limit)


def replay(block: Mapping[str, Any], days: Mapping[str, Day], *, pnl: Sequence[tuple[float, Decimal]],
           funded: Sequence[tuple[float, Decimal]], envelopes: Sequence[tuple[float, Decimal]],
           ratified_at: float, now: float, earlier: Sequence[Sequence[Any]] = ()) -> dict[str, Any]:
    """The tranches since the owner's ratification, from the recorded evidence alone (no state is kept, so the same
    ledger always gives the same answer): a decision at the ratification and at every 00:00Z after it (`evaluate`, on
    the window before that day, the envelope in force, the equity then); a relock at the first mark pass after an unlock
    where the venue's real P&L since it is below `relock_share` x its size. `envelopes` is the base envelope (the
    allocator's, before tranches) at each reading; a day's envelope in force adds every tranche live at any moment of it.

    `earlier`: the grant's EARLIER version-2 intervals, [(ratified, switched off, the `scale_tranches` block ratified
    then)], oldest first (review of #313); each tranche keeps the relock line of the block that unlocked it. They are
    replayed first, so a re-ratification never erases a withdrawal: a tranche live when version 2 went off ends
    there (it is not restored; the rule re-earns it), but its relock line is still watched until the next ratification,
    and a withdrawal in an earlier interval, or in the gap after it, holds the next tranche for a whole window. Without
    it, the routine re-ratification after a money-rule change unlocked a tranche hours after one was withdrawn, on the
    same window of days that preceded the loss."""
    tranches: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    intervals = [(float(x[0]), float(x[1]), (x[2] if len(x) > 2 and x[2] else block)) for x in earlier
                 if float(x[0]) < float(x[1]) <= ratified_at] + [(ratified_at, now, block)]
    for k, (begin, end, rule) in enumerate(intervals):
        last = k == len(intervals) - 1
        moments, t = [begin], midnight(day_of(begin)) + DAY_SECONDS
        while t <= end if last else t < end:
            moments.append(t)
            t += DAY_SECONDS
        for moment in moments:
            _decide(rule, days, tranches, decisions, pnl=pnl, funded=funded, envelopes=envelopes, moment=moment)
        if not last:
            _relock(tranches, pnl, end)
            for tranche in tranches:
                if tranche['relocked_at'] is None and tranche.get('ended_at') is None:
                    tranche['ended_at'], tranche['track_until'] = end, intervals[k + 1][0]
    _relock(tranches, pnl, now)
    base, equity = value_before(envelopes, now), value_before(funded, now)
    live = unlocked_usd(tranches, now, base=base, funded=equity)
    shown = [{'n': x['n'], 'unlocked_at': iso(x['unlocked_at']), 'usd': x['usd'], 'relock_line_usd': str(x['line']),
              'pnl_since_usd': (None if x['relocked_at'] is not None or x.get('ended_at') is not None or not pnl
                                else str(value_before(pnl, now) - x['pnl_at_unlock'])),
              'relocked_at': None if x['relocked_at'] is None else iso(x['relocked_at']),
              'pnl_at_relock_usd': None if x['pnl_at_relock'] is None else str(x['pnl_at_relock']),
              'switched_off_at': None if x.get('ended_at') is None else iso(x['ended_at'])} for x in tranches]
    return {'tranches': shown, 'unlocked_usd': str(live), 'decisions': decisions}


def _decide(block: Mapping[str, Any], days: Mapping[str, Day], tranches: list[dict[str, Any]], decisions: list[dict[str, Any]],
            *, pnl: Sequence[tuple[float, Decimal]], funded: Sequence[tuple[float, Decimal]],
            envelopes: Sequence[tuple[float, Decimal]], moment: float) -> None:
    """One decision of `replay` at `moment` (the ratification, or a 00:00Z while version 2 is in force), under `block`."""
    _relock(tranches, pnl, moment)
    today = day_of(moment)
    base, equity = value_before(envelopes, moment), value_before(funded, moment)
    if base is None:
        decisions.append({'at': iso(moment), 'today': today, 'unlock': False, 'tranche_usd': '0.00',
                          'fails': [{'condition': 'capacity', 'text': 'no allocator reading before the decision'}]})
        return
    names = window_of(today, int(block['window_days']))
    withdrawn = [x['relocked_at'] for x in tranches if x['relocked_at'] is not None and x['relocked_at'] <= moment]
    if withdrawn and names[0] <= day_of(max(withdrawn)):
        # A withdrawn tranche's evidence is spent: the next one needs a whole window after the day it was withdrawn.
        decisions.append({'at': iso(moment), 'today': today, 'unlock': False, 'tranche_usd': '0.00', 'window': names,
                          'fails': [{'condition': 'relock', 'text': f'a tranche was withdrawn on {day_of(max(withdrawn))}: '
                                     f'the next needs {len(names)} full days after it'}]})
        return
    in_force = {}
    for name in names:
        day = days.get(name)
        if day is not None and day.envelope_usd is not None:
            start = midnight(name)
            extra = sum((Decimal(x['usd']) for x in tranches if x['unlocked_at'] < start + DAY_SECONDS
                         and (x['relocked_at'] is None or x['relocked_at'] > start)
                         and (x.get('ended_at') is None or x['ended_at'] > start)), ZERO)
            day = Day(day.day, day.capacity_usd, day.envelope_usd + extra, day.readings, day.pnl_usd)
        if day is not None:
            in_force[name] = day
    envelope = base + unlocked_usd(tranches, moment, base=base, funded=equity)
    result = evaluate(block, in_force, today=today, envelope=envelope, funded=equity)
    result['at'] = iso(moment)
    decisions.append(result)
    reference = value_before(pnl, moment)
    if result['unlock'] and reference is not None:
        tranches.append({'n': len(tranches) + 1, 'unlocked_at': moment, 'day': today, 'usd': result['tranche_usd'],
                         'pnl_at_unlock': reference, 'checked_to': moment, 'relocked_at': None, 'pnl_at_relock': None,
                         'ended_at': None, 'track_until': float('inf'),
                         'line': Decimal(block['relock_share']) * Decimal(result['tranche_usd'])})
