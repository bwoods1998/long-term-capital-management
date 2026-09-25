"""Owner-activated persistent trading, using a fixed allocation of existing venue cash.

No calendar expiry and no performance bypass. Provider commitments and monetary caps survive.
Reporting and deployment do not activate trading. The account owner runs --enable.

**Grant versions** (K5 of the Kalshi-scale run, Sept 25, 2026). Version 1 -- what `policy(capital)`
returns and what `CampaignBudget.live_trading` checks the stored grant against -- is unchanged, byte
for byte. Version 2 is version 1 plus `scale_tranches`, the scale rule (`league/grants.py`): a
deposit enters a venue's envelope in tranches that proven capacity and real profit unlock. Nothing
makes version 2 the grant in force but the account owner's `--ratify <grant> --grant-version 2`,
which ratifies the grant under the current money rules (`ratify_live_trading`) and records the
version-2 policy in `live_grant_versions` (campaigns.sqlite; only `ratify_version` writes it).
`grant_version` reads it: version 2 is in force only while the grant is active and the ratified
policy is the code's version 2 for the grant's capital, so a money rule or a scale constant that
moves switches it off until the owner ratifies again, and a run's own re-ratify (no
`--grant-version`) never switches it on. `--ratify <grant> --grant-version 1` switches it off.
`--scale-report` is read-only: per venue, the envelope, proven capacity, the evidence of the last
three UTC days, the tranche it would unlock today and the deposit that would put it to work.

What reads version 2 at run time: nothing yet. The allocator's envelope (`Allocator.grant_capital`,
the forward-first run's file) would add `unlocked_usd` from `scale_state`; that line lands with
that run's agreement after its Deploy B, and until it does a ratified version 2 changes the report
alone.
"""
from decimal import Decimal, ROUND_DOWN
import hashlib
import json
from pathlib import Path
import sqlite3
import time
import urllib.parse

#: The live grant's versions: 1, the fixed allocation; 2, with the scale rule (`league/grants.py`).
GRANT_VERSIONS = (1, 2)
#: The owner's ratified grant versions (campaigns.sqlite), appended by `ratify_version` alone.
VERSIONS_TABLE = 'live_grant_versions'
#: The kinds of ledger row the scale report reads (all written by the House; the report writes nothing).
SCALE_KINDS = {'family.record': 'proven families, their members on real money, stakes and capacity',
               'alloc.board': 'the envelope, and which days the allocator read it',
               'book.mark': "the venue's real P&L (equity less what was lent, every account on its real book)",
               'floor.mark': "the venue account's equity (the deposit above the envelope)"}


def policy(venue_capital, version=1):
    """The grant's policy for this capital. Version 1 is the fixed allocation (what a stored grant is checked
    against); version 2 adds the scale rule (`scale_tranches`), and is only ever read through `grant_version`."""
    from .constitution import CONSTITUTION, money_digest
    if version not in GRANT_VERSIONS:
        raise ValueError(f'unknown grant version {version!r}')
    if set(venue_capital) != {'alpaca', 'kalshi'}:
        raise ValueError('capital must name Alpaca and Kalshi')
    amounts = {k: Decimal(str(v)) for k, v in venue_capital.items()}
    if any(not v.is_finite() or v < 0 for v in amounts.values()):
        raise ValueError('venue capital must be finite and nonnegative')
    amounts = {k: v.quantize(Decimal('.01'), rounding=ROUND_DOWN) for k, v in amounts.items()}
    total = sum(amounts.values())
    stake = Decimal(CONSTITUTION['rungs']['2']['stake_usd'])
    allocator = CONSTITUTION.get('allocator') or {}
    probes = allocator.get('probe_bunt_usd') or {}
    if allocator.get('enabled'):
        # Capital is the ladder (Sept 23, 2026): the smallest real stake is a bunt, and the envelope
        # in dollars -- not a head count sized for $60 stakes -- is what bounds the real money. Since
        # Sept 24, 2026 (P1, the close-the-gaps run) it is a PROBE, an unproven family's first stake:
        # $10 at Kalshi seats more agents than a $30 bunt, floor($1,017.75 / $10) = 101 (40 at $25).
        stake = min(Decimal(str(v)) for v in (*allocator['bunt_usd'].values(), *probes.values()))
    if max(amounts.values()) < stake or not stake <= total <= Decimal('10000'):
        raise ValueError('live allocation must cover a micro stake and remain within the $10,000 project envelope')
    granted = {'version': 1, 'max_rung': 3, 'max_agents': int(total // stake),
            'max_loss_usd': str(total), 'stake_usd': str(stake),
            'venue_capital_usd': {k: str(v) for k, v in amounts.items()},
            'constitution_digest': money_digest(), 'expires': None,
            'research_funding': 'Only unused original burst allowance within campaign caps; no calendar expiry or replenishment.',
            'scaling': ((f"Capital is the ladder: "
                         + (f"probes of {', '.join(f'${v} at {k}' for k, v in sorted(probes.items()))} for an unproven family, " if probes else '')
                         + f"bunts of {', '.join(f'${v} at {k}' for k, v in sorted(allocator['bunt_usd'].items()))}"
                         + (" for a proven one" if probes else '') + ", "
                         f"swings sized by evidence up to {allocator['max_share_of_venue']:g} of a venue; "
                         'venue and aggregate capital limits include historical losses; realized profit enlarges a venue.')
                        if allocator.get('enabled') else
                        (f"Existing performance gates and {CONSTITUTION['rungs']['3']['kelly_fraction']:g} of Kelly on the lower bound; "
                         'venue and aggregate capital limits include historical losses.')),
            'capital_source': 'Existing cash only; later deposits do not enlarge this allocation.'}
    if version == 1:
        return granted
    from .grants import scale_tranches
    return {**granted, 'version': 2, 'scale_tranches': scale_tranches(),
            'capital_source': ('Existing cash; a later deposit enters a venue\'s envelope only in the tranches the scale '
                               'rule unlocks (scale_tranches), never above the account\'s equity.')}


def read_venue_capital():
    """Read account cash; never construct House, submit orders or transfer collateral."""
    from .service import load_config, load_env, secret
    from .venues import gateway_broker
    load_env()
    config = load_config()
    amounts = {}
    for venue in ('alpaca', 'kalshi'):
        broker = gateway_broker(venue, gateway_url=config['gateway_url'], token=secret('GATEWAY_TOKEN'))
        balance = broker.balance()
        if balance.currency != 'USD':
            raise ValueError('live capital must be denominated in USD')
        # Buying power can include leverage. It is deliberately not part of this allocation.
        amounts[venue] = str(max(Decimal(0), min(balance.cash, balance.equity)))
    return policy(amounts)['venue_capital_usd']


def _digest(value):
    from .ledger import canonical
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def ratify_version(guard, ident, version):
    """Account-owner action: keep the grant `ident` under the current money rules (`ratify_live_trading`, the existing
    ratification) at grant version `version` -- 2 adds the scale rule, 1 switches it off -- recorded in
    `live_grant_versions`. The only writer of that table. A revoked or inactive grant takes no version."""
    from .campaigns import CampaignClosed
    from .ledger import canonical
    if version not in GRANT_VERSIONS:
        raise ValueError(f'unknown grant version {version!r}')
    live = guard.ratify_live_trading(ident)
    if not live or not live['active']:
        raise CampaignClosed('the grant is not active under the current money rules; no version can be ratified onto it')
    encoded = canonical(policy(live['policy']['venue_capital_usd'], version=version))
    with guard.lock:
        guard.db.execute('BEGIN IMMEDIATE')
        try:
            guard.db.execute(f'CREATE TABLE IF NOT EXISTS {VERSIONS_TABLE}(id TEXT NOT NULL, version INTEGER NOT NULL, '
                             'at REAL NOT NULL, policy TEXT NOT NULL)')
            last = guard.db.execute(f'SELECT version, policy FROM {VERSIONS_TABLE} WHERE id=? ORDER BY rowid DESC LIMIT 1',
                                    (ident,)).fetchone()
            if last is None or int(last[0]) != version or last[1] != encoded:
                guard.db.execute(f'INSERT INTO {VERSIONS_TABLE} VALUES(?,?,?,?)', (ident, version, guard.clock(), encoded))
            guard.db.execute('COMMIT')
        except BaseException:
            guard.db.execute('ROLLBACK')
            raise
    return grant_version(guard.db, now=guard.clock())


def grant_version(db, *, now):
    """The owner's grant and the version in force, read through any connection to campaigns.sqlite (nothing is written).
    Version 2 is in force only while the grant is active (`CampaignBudget.live_trading`'s own test) AND the owner's last
    ratified version for it is 2 AND that ratified policy is the code's version 2 for the grant's capital now."""
    from .campaigns import _grant_matches
    try:
        row = db.execute('SELECT id, started, policy, revoked FROM live_trading').fetchone()
    except sqlite3.Error:
        row = None
    if row is None:
        return {'id': None, 'active': False, 'version': None, 'scale_policy': None, 'ratified': None,
                'why_off': 'no live grant'}
    ident, started, stored, revoked = row[0], row[1], json.loads(row[2]), row[3]
    capital = stored['venue_capital_usd']
    try:
        current = policy(capital)
    except ValueError:
        current = None
    try:
        scaled = policy(capital, version=2)
    except Exception:  # noqa: BLE001 - the scale rule never costs the grant its own reading: version 2 reads as off
        scaled = None
    active = revoked is None and started <= now and current is not None and _grant_matches(stored, current)
    try:
        last = db.execute(f'SELECT version, at, policy FROM {VERSIONS_TABLE} WHERE id=? ORDER BY rowid DESC LIMIT 1',
                          (ident,)).fetchone()
    except sqlite3.Error:  # no table: the owner never ratified a version
        last = None
    ratified = None if last is None else {'version': int(last[0]), 'at': float(last[1]), 'policy': json.loads(last[2])}
    on = bool(active and ratified and ratified['version'] == 2 and scaled is not None and ratified['policy'] == scaled)
    why = (None if on else 'the grant is not active' if not active else 'the owner never ratified version 2' if ratified is None
           else 'the owner ratified version 1 last' if ratified['version'] != 2
           else 'the ratified version 2 is not the code\'s version 2 now (a money rule or a scale constant moved)')
    return {'id': ident, 'active': active, 'version': 2 if on else 1, 'policy_digest': _digest(stored),
            'constitution_digest': stored.get('constitution_digest'),
            'proposed_digest': None if scaled is None else _digest(scaled),
            'scale_policy': scaled if on else None, 'ratified': None if ratified is None else
            {'version': ratified['version'], 'at': ratified['at'], 'digest': _digest(ratified['policy'])}, 'why_off': why}


def report(guard, *, prepared_capital=None):
    live = guard.live_trading()
    burst = guard.burst()
    unused = ({k: str(max(Decimal(0), Decimal(str(cap)) - Decimal(guard._burst_used(k, burst)) / 1000000))
               for k, cap in burst['policy']['caps_usd'].items()} if burst else {})
    try:
        with guard.lock:
            version = grant_version(guard.db, now=guard.clock())
    except Exception as exc:  # noqa: BLE001 - the owner's enable/ratify output (and its restart) never waits on the scale rule
        version = {'error': f'{type(exc).__name__}: {str(exc)[:200]}'}
    return {'live_trading': live, 'micro_entries_allowed': guard.allows_live(2),
            'scaled_entries_allowed': guard.allows_live(3), 'research_running': guard.running(),
            'research_remaining_usd': {k: str(guard.remaining(k)) for k in ('sail', 'openai')},
            'unused_burst_allowance_usd': unused, 'meters_ready': {k: guard.ready(k) for k in ('sail', 'openai')},
            'grant_version': {k: v for k, v in version.items() if k != 'scale_policy'},
            'prepared_policy': policy(prepared_capital) if prepared_capital else live['policy'] if live else None}


# ------------------------------------------------------------------ the scale report (read-only)
def _connect_ro(path):
    db = sqlite3.connect(f'file:{urllib.parse.quote(str(Path(path).resolve()))}?mode=ro', uri=True, timeout=30)
    db.execute('PRAGMA query_only=ON')
    return db


def _epoch(at):
    from datetime import datetime
    return datetime.fromisoformat(str(at).replace('Z', '+00:00')).timestamp()


class _LedgerRows:
    """The House ledger, opened read-only: the rows the scale report reads, by kind, from a time on."""

    def __init__(self, path):
        self.path = Path(path)
        self.db = _connect_ro(self.path)

    def close(self):
        self.db.close()

    def seq_at(self, t):
        """The first sequence number whose row is stamped at or after `t` (rows are appended in time order)."""
        from .ledger import now_iso
        stamp = now_iso(lambda: t)
        lo, hi = 1, int(self.db.execute('SELECT COALESCE(MAX(seq), 0) FROM ledger').fetchone()[0]) + 1
        while lo < hi:
            mid = (lo + hi) // 2
            row = self.db.execute('SELECT at FROM ledger WHERE seq>=? ORDER BY seq LIMIT 1', (mid,)).fetchone()
            if row is None or row[0] >= stamp:
                hi = mid
            else:
                lo = mid + 1
        return lo

    def family_rows(self, until):
        rows = self.db.execute("SELECT at, payload FROM ledger WHERE kind='family.record' ORDER BY seq").fetchall()
        return [(_epoch(at), json.loads(payload)) for at, payload in rows if _epoch(at) <= until]

    def envelopes(self, since, until):
        """{venue: [(t, capital)]}: the allocator's envelope at each `alloc.board` row."""
        out = {}
        for at, envelope in self.db.execute("SELECT at, json_extract(payload, '$.envelope') FROM ledger "
                                            "WHERE kind='alloc.board' AND seq>=? ORDER BY seq", (self.seq_at(since),)):
            t = _epoch(at)
            if t > until:
                continue
            for venue, row in (json.loads(envelope) if envelope else {}).items():
                capital = row.get('capital_usd') if isinstance(row, dict) else None
                if capital is not None:
                    out.setdefault(venue, []).append((t, Decimal(str(capital))))
        return out

    def pnl(self, venues, since, until):
        """{venue: [(t, P)]}: P at each mark pass, the sum over the venue's real book of equity less what was lent."""
        marks = {}
        wanted = tuple(venues)
        if not wanted:
            return {}
        for at, book, equity, staked in self.db.execute(
                "SELECT at, json_extract(payload, '$.book'), json_extract(payload, '$.equity'), json_extract(payload, '$.staked') "
                "FROM ledger WHERE kind='book.mark' AND seq>=? AND json_extract(payload, '$.real_money') "
                f"AND json_extract(payload, '$.book') IN ({','.join('?' for _ in wanted)}) ORDER BY seq",
                (self.seq_at(since), *wanted)):
            t = _epoch(at)
            if t > until:
                continue
            passes = marks.setdefault(book, {})
            passes[t] = passes.get(t, Decimal(0)) + Decimal(str(equity)) - Decimal(str(staked))
        return {venue: sorted(passes.items()) for venue, passes in marks.items()}

    def funded(self, since, until):
        """{venue: [(t, equity)]}: the venue account's equity at each `floor.mark` row."""
        out = {}
        for at, venues in self.db.execute("SELECT at, json_extract(payload, '$.venues') FROM ledger "
                                          "WHERE kind='floor.mark' AND seq>=? ORDER BY seq", (self.seq_at(since),)):
            t = _epoch(at)
            if t > until:
                continue
            for row in (json.loads(venues) if venues else []):
                if isinstance(row, dict) and row.get('venue') and row.get('equity') is not None and not row.get('stale'):
                    out.setdefault(row['venue'], []).append((t, Decimal(str(row['equity']))))
        return out


def _read_grant(root, now):
    path = Path(root) / 'campaigns.sqlite'
    if not path.is_file():
        return {'id': None, 'active': False, 'version': None, 'scale_policy': None, 'ratified': None,
                'why_off': f'no campaign database at {path}'}
    db = _connect_ro(path)
    try:
        return grant_version(db, now=now)
    finally:
        db.close()


def capacity_study(data, source):
    """The K2 capacity study (`scripts/kalshi_capacity.py --json`, Kalshi families), reduced to what the scale rule reads:
    each family's estimate and floor fill curves (`grants.study_curves`). Already reduced input passes through."""
    from .grants import study_curves
    if isinstance(data, dict) and data.get('reduced') == 'k5':
        return data
    return {'reduced': 'k5', 'source': str(source), 'since': data.get('since'), 'until': data.get('until') or data.get('box_now'),
            'families': study_curves(data)}


def scale_state(root, *, now=None, board=None, funded=None, grant=None, study=None):
    """Per venue, the scale rule's reading at `now` from the board (`allocator-board.json`, one snapshot) and the ledger's
    rows (`SCALE_KINDS`): the envelope, proven capacity today, the evidence of each day of the window, and today's
    decision -- replayed from the owner's ratification when version 2 is in force, else what the evidence WOULD unlock.
    Read-only: the board, the ledger and campaigns.sqlite are opened read-only, and nothing is written anywhere.
    `study` (`capacity_study`): the K2 study's fill curves, read for Kalshi's families in place of the board's record."""
    from . import grants
    root = Path(root)
    now = time.time() if now is None else float(now)
    if board is None:
        board = json.loads((root / 'allocator-board.json').read_text(encoding='utf-8'))
    grant = _read_grant(root, now) if grant is None else grant
    block = grant['scale_policy']['scale_tranches'] if grant.get('scale_policy') else grants.scale_tranches()
    ratio = block['fills_halve_ratio']
    today = grants.day_of(now)
    ratified_at = grant['ratified']['at'] if grant.get('version') == 2 and grant.get('ratified') else None
    first = grants.window_of(grants.day_of(ratified_at) if ratified_at else today, int(block['window_days']))[0]
    since = grants.midnight(first) - 2 * grants.DAY_SECONDS  # a mark pass before the window's first day: its P&L start
    venues = sorted((board.get('envelope') or {}).keys())
    ledger_path = root / 'ledger.sqlite'
    history = {'board': f"one snapshot (allocator-board.json at {board.get('at')}): the board keeps no history",
               'curves': (f"Kalshi: the K2 capacity study {study['source']} ({study.get('since')}..{study.get('until')}; "
                          f"families with a curve: {len(study['families'])}), else the board's capacity record" if study
                          else "the board's capacity record (fill at the position size; no curve beyond it until C6 or a K2 study)")}
    rows = {'families': [], 'envelopes': {}, 'pnl': {}, 'funded': {}}
    if ledger_path.is_file():
        ledger = _LedgerRows(ledger_path)
        try:
            rows = {'families': ledger.family_rows(now), 'envelopes': ledger.envelopes(since, now),
                    'pnl': ledger.pnl(venues, since, now), 'funded': ledger.funded(since, now)}
        finally:
            ledger.close()
        history['ledger'] = {'path': str(ledger_path), 'kinds': SCALE_KINDS,
                             'rows': {'family.record': len(rows['families']),
                                      'alloc.board': sum(len(v) for v in rows['envelopes'].values()),
                                      'book.mark passes': sum(len(v) for v in rows['pnl'].values()),
                                      'floor.mark': sum(len(v) for v in rows['funded'].values())}}
    else:
        history['ledger'] = f'no ledger at {ledger_path}: no day of the window has a reading'
    out = {}
    for venue in venues:
        env = board['envelope'][venue]
        base = Decimal(str(env.get('capital_usd') or 0))
        committed = Decimal(str(env.get('committed_usd') or 0))
        curves = (study or {}).get('families') if venue == 'kalshi' else None
        used, lines = grants.capacity_used((board.get('families') or {}).get(venue) or {}, ratio, curves)
        others = sorted(name for name, row in ((board.get('families') or {}).get(venue) or {}).items()
                        if row.get('state') not in grants.PROVEN_STATES)
        pnl, envelopes = rows['pnl'].get(venue, []), rows['envelopes'].get(venue, [])
        equity_series = list(rows['funded'].get(venue, []))
        if funded and venue in funded:
            equity_series.append((now, Decimal(str(funded[venue]))))
            funded_basis = 'given (--funded)'
        elif equity_series:
            funded_basis = f'floor.mark at {grants.iso(equity_series[-1][0])}'
        else:
            funded_basis = 'unread: no floor.mark row'
        equity = grants.value_before(equity_series, now)
        days = grants.build_days(venue, family_rows=rows['families'], envelopes=envelopes, pnl=pnl,
                                 first_day=first, last_day=today, ratio=ratio, study=curves)
        state = None
        if ratified_at:
            state = grants.replay(block, days, pnl=pnl, funded=equity_series, envelopes=envelopes or [(now, base)],
                                  ratified_at=ratified_at, now=now)
            unlocked = Decimal(state['unlocked_usd'])
            decision = state['decisions'][-1] if state['decisions'] else None
        else:
            unlocked = Decimal(0)
            decision = grants.evaluate(block, days, today=today, envelope=base, funded=equity)
        envelope = base + unlocked
        window = grants.window_of(today, int(block['window_days']))
        start, end = grants.value_before(pnl, grants.midnight(window[0]), inclusive=False), grants.value_before(pnl, now)
        out[venue] = {
            'envelope_usd': str(envelope), 'base_envelope_usd': str(base), 'unlocked_usd': str(unlocked),
            'committed_usd': str(committed), 'committed_share': float(committed / envelope) if envelope > 0 else None,
            'funded_usd': None if equity is None else str(equity), 'funded_basis': funded_basis,
            'deposit_left_usd': None if equity is None else str(grants._cents(max(Decimal(0), equity - envelope))),
            'families': lines, 'families_not_proven': len(others),
            'capacity_used_usd': str(used), 'capacity_share_today': float(used / envelope) if envelope > 0 else None,
            'capacity_gap_today_usd': str(grants._cents(max(Decimal(0), Decimal(block['min_capacity_share']) * envelope - used))),
            'days': [{'day': d.day, 'capacity_used_usd': str(d.capacity_usd),
                      'envelope_usd': None if d.envelope_usd is None else str(d.envelope_usd), 'readings': d.readings,
                      'share': (float(d.capacity_usd / max(d.envelope_usd, envelope)) if d.envelope_usd is not None
                                and max(d.envelope_usd, envelope) > 0 else None),
                      'pnl_usd': None if d.pnl_usd is None else str(d.pnl_usd), 'complete': d.day < today}
                     for d in (days[k] for k in sorted(days) if k >= window[0])],
            'window': window, 'window_pnl_usd': decision.get('window_pnl_usd') if decision else None,
            'pnl_window_to_now_usd': None if start is None or end is None else str(end - start),
            'decision': decision, 'tranches': state['tranches'] if state else [],
            'decisions': [{k: d.get(k) for k in ('at', 'today', 'unlock', 'tranche_usd')} | {'fails': [f['text'] for f in d['fails']]}
                          for d in state['decisions']] if state else [],
        }
    return {'at': grants.iso(now), 'grant': {k: v for k, v in grant.items() if k != 'scale_policy'},
            'rule': block, 'history': history, 'venues': out,
            'ratify': f"python scripts/live_trading.py --ratify {grant.get('id') or '<grant-id>'} --grant-version 2",
            'switch_off': f"python scripts/live_trading.py --ratify {grant.get('id') or '<grant-id>'} --grant-version 1"}


def scale_report(root, *, now=None, board_path=None, funded=None, study=None):
    board = json.loads(Path(board_path).read_text(encoding='utf-8')) if board_path else None
    return scale_state(root, now=now, board=board, funded=funded, study=study)


def _money(value):
    return 'n/a' if value is None else f'${Decimal(str(value)):,.2f}'


def _pct(value):
    return 'n/a' if value is None else f'{value:.1%}'


def render_scale_report(report):
    """The scale report as plain text for the owner."""
    grant, rule = report['grant'], report['rule']
    lines = [f"Scale report at {report['at']} (read-only; nothing is written)"]
    if grant.get('id'):
        lines.append(f"Grant {grant['id']}: {'active' if grant['active'] else 'NOT active'}; version {grant['version']} in force "
                     f"(policy {str(grant.get('policy_digest'))[:12]}, money rules {str(grant.get('constitution_digest'))[:8]}).")
    else:
        lines.append(f"Grant: none read ({grant.get('why_off')}).")
    if grant.get('version') == 2:
        lines.append('Version 2 (scale_tranches) is RATIFIED and in force: tranches below are replayed from its ratification.')
    else:
        lines.append(f"Version 2 (scale_tranches) is OFF: {grant.get('why_off')}. Nothing reads it; the numbers below are what "
                     'the evidence WOULD unlock.')
    lines.append(f"Rule: tranche = min(deposit left, {rule['tranche_share']} x envelope); unlocked when proven capacity >= "
                 f"{Decimal(rule['min_capacity_share']):.0%} of the envelope on each of the last {rule['window_days']} UTC days and the "
                 f"venue's real P&L over them > $0; withdrawn when real P&L since its unlock < {rule['relock_share']} x its size.")
    ledger = report['history']['ledger']
    lines.append(f"Fill curves: {report['history']['curves']}.")
    lines.append('Caution: capacity counts dollars committed, not earned, and never unlocks a tranche alone; the $/day beside a '
                 "family multiplies its edge_per_dollar, a pooled estimate that can be a short streak's. The venue's real "
                 'P&L over the window (losses in full) is the guard.')
    lines.append(f"History: {report['history']['board']}; "
                 + (f"days from the ledger ({', '.join(f'{k} {v}' for k, v in ledger['rows'].items())})"
                    if isinstance(ledger, dict) else ledger) + '.')
    for venue, v in report['venues'].items():
        lines += ['', venue]
        lines.append(f"  envelope {_money(v['envelope_usd'])} (base {_money(v['base_envelope_usd'])} + tranches "
                     f"{_money(v['unlocked_usd'])}); committed {_money(v['committed_usd'])} ({_pct(v['committed_share'])})")
        lines.append(f"  funded (account equity) {_money(v['funded_usd'])} [{v['funded_basis']}]; deposit above the envelope "
                     f"{_money(v['deposit_left_usd'])}")
        if v['families']:
            lines.append('  proven families at capacity (members on real money x stake x m*):')
            for f in v['families']:
                curve = ('no curve beyond 1x' if not f['curve'] else 'curve ' + ', '.join(f'{m}x {r:.2f}' for m, r in f['curve'].items()))
                rate = f['fill_rate_at_size']
                edge = f.get('edge_per_dollar')
                lines.append(f"    {f['family']} ({f['state']}): {f['members_real']} x {_money(f['stake_usd'])} x {f['multiple']} = "
                             f"{_money(f['usd'])}  [m* from the {f['multiple_basis']}: fill {'n/a' if rate is None else f'{float(rate):.2f}'} "
                             f"at 1x ({_money(f['size_usd'])} a position); {curve}"
                             + (f"; floor {', '.join(f'{m}x {r:.2f}' for m, r in f['floor_curve'].items())}" if f.get('floor_curve') else '')
                             + (f"; halves at {f['halves_at']}" if f.get('halves_at') is not None else '')
                             + f"; {_money(f['usd_per_day'])} a day at edge {'n/a' if edge is None else f'{float(edge):+.2f}'}]")
        else:
            lines.append('  proven families: none')
        lines.append(f"  families not proven: {v['families_not_proven']}")
        lines.append(f"  capacity used today (the board's families): {_money(v['capacity_used_usd'])} = {_pct(v['capacity_share_today'])} of the envelope")
        for d in v['days']:
            seen = (f"capacity {_money(d['capacity_used_usd'])} = {_pct(d['share'])} (lowest of {d['readings']} readings)"
                    if d['readings'] else 'no allocator reading')
            lines.append(f"    {d['day']}{'' if d['complete'] else ' (today, so far)'}: {seen}; real P&L {_money(d['pnl_usd'])}")
        lines.append(f"  real P&L over {v['window'][0]}..{v['window'][-1]}: {_money(v['window_pnl_usd'])}; "
                     f"from {v['window'][0]} to now {_money(v['pnl_window_to_now_usd'])}")
        for t in v['tranches']:
            lines.append(f"  tranche {t['n']}: {_money(t['usd'])} unlocked {t['unlocked_at']}; "
                         + (f"withdrawn {t['relocked_at']} (P&L since {_money(t['pnl_at_relock_usd'])})" if t['relocked_at']
                            else f"P&L since {_money(t['pnl_since_usd'])}, withdrawn below {_money(t['relock_line_usd'])}"))
        d = v['decision'] or {}
        if d.get('unlock'):
            lines.append(f"  TODAY: the evidence unlocks a tranche of {_money(d['tranche_usd'])} (full tranche {_money(d['full_tranche_usd'])}).")
        else:
            lines.append('  TODAY: no tranche. ' + '; '.join(f['text'] for f in d.get('fails', [])) + '.')
        lines.append(f"  deposit that would put it to work: {_money(d.get('deposit_to_work_usd'))}"
                     + ('' if d.get('evidence') else f" (none until proven capacity reaches {_money(d.get('capacity_needed_usd'))} on "
                        f"{rule['window_days']} straight UTC days, {_money(v['capacity_gap_today_usd'])} more than today's "
                        f"{_money(v['capacity_used_usd'])}, with the venue's real P&L positive over them)"))
    lines += ['', "The owner's ratification (switches the scale rule on; nothing else does):", f"  {report['ratify']}",
              f"Switch it off again: {report['switch_off']}"]
    return '\n'.join(lines)


def main(argv=None):
    import argparse
    from .campaigns import CampaignBudget
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--enable', help='Account-owner authorization identity; enables persistent trading.')
    action.add_argument('--disable', action='store_true', help='Revoke new live entries; keep exits and accounting.')
    action.add_argument('--ratify', help='Account-owner: keep this grant, same capital, under revised money rules.')
    action.add_argument('--scale-report', action='store_true',
                        help='Read-only: per venue, proven capacity against the envelope and the tranche the evidence unlocks.')
    parser.add_argument('--grant-version', type=int, choices=GRANT_VERSIONS,
                        help='With --ratify, account-owner: 2 adds the scale rule (scale_tranches); 1 switches it off.')
    parser.add_argument('--json', action='store_true', help='With --scale-report: JSON rather than text.')
    parser.add_argument('--board', type=Path, help='With --scale-report: the board file (default: <root>/allocator-board.json).')
    parser.add_argument('--funded', action='append', default=[], metavar='VENUE=USD',
                        help="With --scale-report: a venue account's equity (default: the ledger's last floor.mark).")
    study = parser.add_mutually_exclusive_group()
    study.add_argument('--capacity-json', type=Path, metavar='PATH',
                       help="With --scale-report: the K2 study's output (scripts/kalshi_capacity.py --json); its fill curves "
                            "give Kalshi's m*, else the board's capacity record.")
    study.add_argument('--capacity-curves', metavar='JSON', help=argparse.SUPPRESS)  # the study, reduced (the owner script)
    args = parser.parse_args(argv)
    if args.grant_version is not None and not args.ratify:
        parser.error('--grant-version goes with --ratify')
    if (args.json or args.board or args.funded or args.capacity_json or args.capacity_curves) and not args.scale_report:
        parser.error('--json, --board, --funded and --capacity-json go with --scale-report')
    if args.scale_report:
        funded = {}
        for item in args.funded:
            venue, _, amount = item.partition('=')
            try:
                funded[venue.strip()] = str(Decimal(amount))
            except ArithmeticError:
                parser.error(f'--funded {item!r}: VENUE=USD')
        curves = (capacity_study(json.loads(args.capacity_json.read_text(encoding='utf-8')), args.capacity_json)
                  if args.capacity_json else capacity_study(json.loads(args.capacity_curves), 'given')
                  if args.capacity_curves else None)
        shown = scale_report(args.root, board_path=args.board, funded=funded, study=curves)
        print(json.dumps(shown, indent=2, sort_keys=True) if args.json else render_scale_report(shown))
        return
    if not (args.root / 'campaigns.sqlite').is_file():
        parser.error('an existing campaign database is required')
    guard = CampaignBudget(args.root / 'campaigns.sqlite')
    try:
        live = guard.live_trading()
        capital = live['policy']['venue_capital_usd'] if live else None if (args.disable or args.ratify) else read_venue_capital()
        if args.enable:
            guard.activate_live_trading(args.enable, capital)
        elif args.disable:
            guard.revoke_live_trading()
        elif args.ratify and args.grant_version is not None:
            ratify_version(guard, args.ratify, args.grant_version)
        elif args.ratify:
            guard.ratify_live_trading(args.ratify)
        print(json.dumps(report(guard, prepared_capital=capital), indent=2))
    finally:
        guard.close()


if __name__ == '__main__':
    main()
