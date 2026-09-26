"""Builds the real House from `league/config.json` and the environment.

Secrets: the House box holds exactly three, in its environment or in a 0600 `.env` beside the
code: `GATEWAY_TOKEN` (venues and the frontier model, through the gateway), `SAIL_API_KEY`
(agent boxes and cheap-model inference) and `CAPITAL_PUBLISH_TOKEN` (the public site). No venue
key and no OpenAI key ever reaches Sail.
"""

from __future__ import annotations

import json
import os
import stat
import time
import urllib.request
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

from .house import House, Settings

PACKAGE = Path(__file__).resolve().parent
REPO = PACKAGE.parent
SECRET_NAMES = ("GATEWAY_TOKEN", "SAIL_API_KEY", "CAPITAL_PUBLISH_TOKEN")


def load_config(path: Path | None = None) -> dict[str, Any]:
    return json.loads((path or PACKAGE / "config.json").read_text(encoding="utf-8"))


def load_env(path: Path | None = None) -> None:
    """Read NAME=value lines into the environment (never overriding what is already set). The
    file must not be readable by anyone but its owner."""
    # On the House box the code lives in a release directory and the secrets beside them all.
    env = path or Path(os.environ.get("LEAGUE_ENV") or REPO / ".env")
    if not env.exists():
        return
    if stat.S_IMODE(env.stat().st_mode) & 0o077:
        raise PermissionError(f"{env} is readable by others; chmod 600 it")
    for line in env.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            name, value = line.split("=", 1)
            os.environ.setdefault(name.strip(), value.strip().strip('"').strip("'"))


def secret(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if len(value) < 16:
        raise RuntimeError(f"{name} is not set")
    return value


def gateway_kill_switch(gateway_url: str, token_source: Callable[[], str], *, ttl: float = 60.0) -> Callable[[], bool]:
    """The kill switch lives in the gateway, which refuses real orders while it is engaged. The
    House asks so it can refuse first and say why. Unreadable counts as engaged."""
    state = {"at": 0.0, "value": True}

    def engaged() -> bool:
        if time.time() - state["at"] < ttl:
            return state["value"]
        try:
            request = urllib.request.Request(gateway_url.rstrip("/") + "/v1/health", headers={"Authorization": "Bearer " + token_source(), "User-Agent": "ltcm-floor/1.0"})
            with urllib.request.urlopen(request, timeout=20) as response:
                state["value"] = bool(json.load(response).get("kill_switch"))
        except Exception:  # noqa: BLE001
            state["value"] = True
        state["at"] = time.time()
        return state["value"]

    return engaged


def evidence_weight_of(house: House, *, ttl: float = 300.0) -> Callable[[Any], float]:
    """How a repair's turn follows the forward record of the agents it concerns (`Engineer.
    _by_evidence`): x3 when one of them holds real money or has an earning record, x0.5 when every
    one is dead or still on replay, x1 otherwise (and for a House-level job that names no agent).
    Standings are read at most every `ttl` seconds: the engineer steps every two minutes."""
    cache: dict[str, Any] = {"at": float("-inf"), "rows": {}}

    def weight(agents: Any) -> float:
        now = house.clock()
        if now - cache["at"] >= ttl:
            cache["rows"] = {s.agent: s for s in house.standings()}
            cache["at"] = now
        names = [str(a) for a in agents or []]
        if not names:
            return 1.0
        rows = [cache["rows"].get(name) for name in names]
        if any(row is not None and (row.rung >= 2 or (row.score_observations > 0 and row.score_growth > 0)) for row in rows):
            return 3.0
        if all(row is None or row.rung == 0 for row in rows):
            return 0.5
        return 1.0

    return weight


def repair_engineer(house: House, frontier: Any, forge: Any) -> Any:
    """The repair worklist's worker, wired to the House's own ledger, frontier client and forge.
    It spends only while the day's OpenAI allowance is open and the frontier tier still pays for
    code (`TIER_ROLES`: not in "audits"), like the architect and the toolsmith."""
    from .engineer import Engineer
    from .worklist import Sources, Worklist

    def code_of(agent_id: str) -> dict[str, Any] | None:
        agent = house.registry.agents.get(agent_id)
        if agent is None:
            return None
        return {"family": agent.family, "niche": agent.niche, "venue": agent.venue, "horizon": agent.horizon,
                "needs": agent.needs, "params": agent.params, "code": agent.code}

    def niche_of(agent_id: str) -> str | None:
        agent = house.registry.agents.get(agent_id)
        return agent.niche if agent is not None else None

    worklist = Worklist(house.ledger, clock=house.clock)
    return Engineer(frontier, forge, house.ledger, worklist, clock=house.clock, code_of=code_of,
                    evidence_weight=evidence_weight_of(house),
                    may_spend=lambda: house.pacer.may_spend("openai") and house.frontier_tier() != "audits",
                    sources=Sources(house.ledger, worklist, niche_of=niche_of), summary_path=Path(house.root) / "repairs.json",
                    inbox=Path(house.root) / "repairs-inbox")


def auto_update(config: dict[str, Any]) -> bool:
    """Whether the in-box updater pulls main by itself: only when `config.json` says `"auto_update":
    true`. A missing key means OFF (the options overhaul, Sept 26, 2026, trap 3: the old default of
    on let the updater ship main's heads into a House that nobody had deployed; the prune ships as
    the owner's deploys, and the updater stays off until the overhaul has run a day)."""
    return config.get("auto_update", False) is True


def lab_box_key(config: dict[str, Any], *, canary: bool = False) -> str:
    """The Alpha Lab's box key when `config.json` `lab` names its box by id (`box_id`, the box
    `scripts/lab_box.py create` made, which `LabBox.from_config` binds under this same key) and is
    not switched off; "" otherwise, and always on a canary. A box's name alone (`box`) is not
    enough: nothing could be bound, and the sandbox would make an agent-sized box instead."""
    lab = dict(config.get("lab") or {})
    if canary or lab.get("enabled") is False or not lab.get("box_id"):
        return ""
    return str(lab.get("box_key") or "lab")


def performance_of(config: dict[str, Any]) -> dict[str, Any] | None:
    """`config.json` `performance` once the reset has filled both `start_at` and `start_equity`; None before (the
    publisher then shows the account's balance with no since-reset figure, rather than failing every minute)."""
    performance = dict(config.get("performance") or {})
    return performance if performance.get("start_at") and performance.get("start_equity") is not None else None


def options_shadow_broker(root: Path, config: dict[str, Any], data_client: Any, alpaca_data: Any) -> Any:
    """The options shadow account (`league/options_shadow.py`, Sept 25, 2026, the options-desk run's
    Track S): every level-3 structure on practice, filled on the live option
    quotes the House's market-data client reads (read-only GETs through the gateway, on a canary too,
    which gets its own state file under its own root). On by default; `config.json`
    `options_structures.shadow.enabled: false` leaves it out. `options_structures.book` (read by the
    House) says whether structure agents trade here or on `alpaca-paper`; the account is built either
    way, so a structure it holds is still marked and closable after the switch."""
    from .options_shadow import OptionsShadowBroker, alpaca_leg_quotes, alpaca_underlying_close

    shadow = dict((config.get("options_structures") or {}).get("shadow") or {})
    if shadow.get("enabled") is False:
        return None
    feed = str(config.get("alpaca_option_feed", "indicative"))
    return OptionsShadowBroker(Path(root) / "options-shadow.json", alpaca_leg_quotes(data_client, feed=feed),
                               underlying_close=alpaca_underlying_close(alpaca_data),
                               starting_cash=str(shadow.get("starting_cash", "100000")), feed=feed)


def live_enabled(config: dict[str, Any], *, canary: bool = False) -> bool:
    """Whether the live options path (`league/live/`, Wave 5) runs: `config.json` `live.enabled`, never on a canary."""
    return not canary and (config.get("live") or {}).get("enabled") is True


def options_live(house: House, root: Path, config: dict[str, Any], *, real_money: bool, token: Callable[[], str],
                 swarm_on: bool = False) -> Any:
    """`House.options_live` (`league/live/step.py`): live chains, the shadow book, the paper proof and the real route,
    through the gateway. It owns both Alpaca accounts: no old `Book` is built for them beside it (`build`). None, with an
    error alert, when numpy is missing on the box (the main session installs it at deploy). `swarm_on`: `build`'s own
    reading of the swarm's settings (config.json < <state>/swarm.json): the families are then the swarm's store."""
    try:
        import numpy  # noqa: F401 - the live path needs it; the rest of the House does not

        from .live import money as live_money
        from .live.families import MemoryFamilies, SwarmFamilies
        from .live.step import OptionsLive
        from .live.venue import Account as LiveAccount, MarketData
    except ImportError as exc:
        house.alert("error", f"the live options path is not running: {exc} (pip install numpy in the House's venv)")
        return None
    from ltcm.adapters import GatewaySigner, VenueClient
    from ltcm.notify import post_json

    from .ledger import HOUSE

    gateway_url = config["gateway_url"]
    signer = GatewaySigner(token())
    table = live_money.Table.from_constitution()

    def client(venue: str) -> Any:
        return VenueClient(None, gateway_url=gateway_url, gateway=signer, venue=venue)

    market = MarketData(client("alpaca" if real_money else "alpaca-paper"), option_feed=str(config.get("alpaca_option_feed", "opra")),
                        stock_feed=str(config.get("alpaca_feed", "sip")))
    real = LiveAccount(client("alpaca"), venue="alpaca", max_requests_minute=table.max_requests_minute) if real_money else None
    paper = LiveAccount(client("alpaca-paper"), venue="alpaca-paper", max_requests_minute=table.max_requests_minute)
    families = SwarmFamilies(root) if swarm_on else MemoryFamilies()

    def record(kind: str, payload: dict[str, Any], agent: str | None = None) -> None:
        house.ledger.append(kind, payload, agent=agent or HOUSE)

    def notify(facts: dict[str, Any]) -> Any:
        return post_json(f"{gateway_url.rstrip('/')}/v1/notify", token(), facts)

    return OptionsLive(root, market=market, real=real, paper=paper, families=families, grant=house.grant,
                       kill_switch=gateway_kill_switch(gateway_url, token), table=table, config=dict(config.get("live") or {}),
                       real_money=real_money, performance=performance_of(config), clock=house.clock, record=record,
                       alert=house.alert, notify=notify)


def build(root: str | Path, *, config: dict[str, Any] | None = None, local_sandbox: bool = False, research: bool = True,
          publish: bool = True, tape: str | None = None, game: dict[str, Any] | None = None, name_prefix: str = "league",
          merton: bool = True, canary: bool = False) -> House:
    """The options House (the options overhaul, Sept 26, 2026, Wave 2a): the books are the Brokerage
    Account (`alpaca`, only when `real_money`), the Alpaca practice account (`alpaca-paper`) and the
    options shadow book (`options-shadow`). Nothing Kalshi (real or shadow), no Jev, no Alpha Lab, no
    hypothesis foundry, no semantic lab, no feeds or recorders, no research traces, no campaign store,
    burst or funded transport is built, and no config key that is absent switches one on. Real money
    turns on only through the owner's grant (`league/live_trading.py`, `House.grant`), which the House
    reads from its own state root.

    The swarm (Wave 4) and the options live path (Wave 5) plug into the tick as `House.swarm` and
    `House.options_live` (see `House.PLUGGABLE_STEPS`); both are None here until their builders fill them.

    `canary=True` is a House that can hurt nothing: a simulated Alpaca account instead of the shared
    paper one (the real House reconciles that account to the cent, and a second trader on it would
    break the reconciliation), no real venue, no publishing, no research, no Merton. The watchdog runs
    new code this way before the House runs it."""
    from ltcm.adapters import GatewaySigner, VenueClient
    from ltcm.data.news import News
    from ltcm.provider import Provider

    from .auditor import Auditor
    from .budget import Budget
    from .commons import Commons, gateway_fetch
    from .frontier import Frontier
    from .publish import Publisher
    from .sailbox import SailboxClient
    from .sandbox import LocalSandbox, SailSandbox
    from .tapes import AlpacaData
    from .venues import gateway_broker

    config = dict(config or load_config())
    if canary:
        from .economy import load_game

        config.update(real_money=False, replay_days=2)
        research = publish = merton = False
        name_prefix = "canary"
        # Two agents are enough to exercise every path: the canary does not refill itself to the
        # league's population floor (the first canary on the box founded all twelve seeds).
        game = dict(game or load_game())
        game["economy"] = {**game["economy"], "min_population": 0}
    load_env()
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    # The options swarm (Sept 26, 2026, Wave 4; league/swarm/) owns the population, the research and the Gym when it is
    # enabled: the House then seats no agent of its own (`Settings.births`), builds no old researcher, provider or
    # Merton, and runs the swarm's step (`league/swarm/hook.py`: it keeps `python -m league.swarm run` alive beside the
    # loop, mirrors the swarm's events into the ledger and reads its bands). Never in a canary.
    from .swarm import settings as swarm_settings

    swarm_on = bool(swarm_settings.load(root, config=config).get("enabled")) and not canary  # config < <root>/swarm.json
    if swarm_on:
        research = merton = False
    gateway_url = config["gateway_url"]
    token = lambda: secret("GATEWAY_TOKEN")  # noqa: E731
    real_money = bool(config.get("real_money"))
    feed, option_feed = config.get("alpaca_feed", "iex"), config.get("alpaca_option_feed", "indicative")

    # Market data reads through the real account's credentials when real money is on (the gateway's kill switch stops
    # orders, never reads), and through the practice account's otherwise (a canary, a House with real money off).
    data_venue = "alpaca" if real_money else "alpaca-paper"
    data_client = VenueClient(None, gateway_url=gateway_url, gateway=GatewaySigner(token()), venue=data_venue)
    alpaca_data = AlpacaData(data_client, feed=feed)
    live_on = live_enabled(config, canary=canary)
    brokers: dict[str, Any] = {}
    if live_on:
        # The live options path owns both Alpaca accounts (Wave 5, Sept 26, 2026): an old `Book` reconciling or
        # repairing the same account beside it would fight it (its short-leg buy-back, its freezes). No old book is
        # built, the old options shadow account neither (the live path's shadow book is the Gym's engine).
        pass
    else:
        if canary:
            from .sim import SimBroker, touch_from

            paper: Any = SimBroker(root / "alpaca-sim.json", touch_from(alpaca_data))
        else:
            paper = gateway_broker("alpaca-paper", gateway_url=gateway_url, token=token(), feed=feed, option_feed=option_feed)
        brokers["alpaca-paper"] = paper
        if real_money:
            brokers["alpaca"] = gateway_broker("alpaca", gateway_url=gateway_url, token=token(), feed=feed, option_feed=option_feed)
        # Last: the House's passes walk the books in this order (the horizon rule's has no guard of its own for one
        # book), and practice must never stand in front of real money.
        shadow_options = options_shadow_broker(root, config, data_client, alpaca_data)
        if shadow_options is not None:
            brokers[shadow_options.venue] = shadow_options

    if local_sandbox:
        sandbox: Any = LocalSandbox(root / "boxes")
    else:
        sandbox = SailSandbox(SailboxClient(), root / "sandbox.json", image_checkpoint=config["agent_image_checkpoint"], name_prefix=name_prefix,
                              background_sleep=True)

    inference_cap = Decimal(str(config.get('inference_daily_cap_usd', '3.00')))
    provider = Provider(root / "provider.sqlite", floor_cap_usd_per_day=inference_cap) if research else None
    house_settings = Settings(
        tick_seconds=int(config.get("tick_seconds", 60)), mark_every_seconds=int(config.get("mark_every_seconds", 300)),
        real_money=real_money, replay_days=int(config.get("replay_days", 21)), research=research,
        replay_timeout=120 if canary else 600,
        # Cut with the prune (Wave 2b deletes them): the stock/crypto history store and its sealed holdout, the Alpha
        # Lab, Kalshi's founders and survey, and the credit economy's wake gate, culling and payouts. The options
        # swarm's Gym (league/gym/) and its evidence lines replace them; nothing here turns one back on.
        deep_replay=False, holdout_gate=False, history_coverage=False, lab_box="", kalshi_founders=False,
        niche_survey_hours=0.0, credit_economy=False, births=not swarm_on,
    )
    house = House(
        root, brokers=brokers, sandbox=sandbox, alpaca_data=alpaca_data, kalshi_data=None, provider=provider,
        game=game, settings=house_settings, kill_switch=gateway_kill_switch(gateway_url, token) if real_money else None,
    )
    if live_on:
        house.options_live = options_live(house, root, config, real_money=real_money, token=token, swarm_on=swarm_on)
    # The same clock as the House: `open_requests` drops a request nothing has closed after three
    # days, and a Commons reading a different clock would measure that window against the wrong now.
    # `fetch`: research's `web_fetch` reads one public page through the gateway (I1, Sept 25, 2026).
    house.commons = Commons(house.ledger, news=News(cache_dir=root / "cache"),
                            clock=house.clock, fetch=gateway_fetch(gateway_url, token))
    if house.researcher is not None:
        house.researcher.commons = house.commons
    frontier = Frontier(gateway_url, token)
    house.frontier = frontier
    if config.get("options_history", True) and not canary:
        # Listed-option history (market-data GETs only): the options desk's replay. Empty until ingested; then
        # refreshed daily. Superseded by the Gym (league/gym/) and deleted with it in Wave 2b.
        from .options_history import OptionsHistory, gateway_get
        reader = brokers["alpaca"] if real_money else paper
        house.options_history = OptionsHistory(root / "options_history.sqlite", gateway_get(reader), ledger=house.ledger, clock=house.clock)
    if not canary:
        from .frontier import FrontierMonth

        house.frontier_month = FrontierMonth(gateway_url, token)
    house.auditor = Auditor(
        frontier, house.ledger, house.economy, house.evaluator,
        live_agents=lambda: [{"agent": a.id, "family": a.family, "niche": a.niche} for a in house.registry.living() if house.evaluator.rung(a.id) >= 2],
        lineage=house.registry.lineage,
        book_evidence=lambda agent, book: house.books[book].evidence_integrity(agent) if book in house.books else None,
    )
    if merton:
        from .merton import Merton, GatewayForge, evidence_from

        pace = house.game.get("merton") or {}
        house.merton = Merton(frontier, GatewayForge(gateway_url, token), house.ledger, evidence=evidence_from(house),
                            schedule_hours=pace.get("schedule_hours"), first_after_hours=pace.get("first_after_hours"), effort=pace.get("effort"),
                            pace=house.frontier_pace, backoff_max=pace.get("backoff_max"),
                            # Sept 24, 2026 (L2): these roles wait while the floor's 24-hour real P&L is not positive.
                            paused_until_profit=pace.get("paused_until_profit"), lift=pace.get("lift"))
    if house.merton is not None:
        # Always built with Merton: switched off in league/engineer.json it still reports (free),
        # and buys nothing.
        house.engineer = repair_engineer(house, frontier, house.merton.forge)
    if house.researcher is not None and frontier is not None:
        # An agent may hire Merton with its own credits, whether or not his pull-request roles run:
        # what a good record buys is better thinking.
        from .merton import Merton as _Merton

        house.researcher.merton = house.merton or _Merton(frontier, None, house.ledger, evidence=lambda role: {})
    if provider is not None:
        house.budget = Budget(house.ledger, lambda: provider.check_balance())
    if not canary and REPO.parent.name == "releases" and not local_sandbox:
        # On the House box only: a daily checkpoint of the box itself, so the ledger (every agent's
        # code, record and journal) outlives the one disk it lives on.
        from .backup import Backup

        house.backup = Backup(SailboxClient(), house.ledger)
    if not canary and REPO.parent.name == "releases" and auto_update(config):
        # On the House box the code runs from <base>/releases/<id>: there, main is pulled every
        # half hour and handed to the watchdog. On a developer's machine nothing updates itself.
        from .updater import Updater

        house.updater = Updater(REPO.parent.parent)
    if swarm_on:
        from .swarm.hook import attach

        attach(house, root, config)
    if publish:
        # The balance chart is the REAL account whatever the agents are doing, so the publisher
        # reads it (balances only) even while every book is practice.
        readers = {"alpaca": brokers.get("alpaca") or gateway_broker("alpaca", gateway_url=gateway_url, token=token(), feed=feed)}
        house.publisher = Publisher(
            config["site_url"], lambda: secret("CAPITAL_PUBLISH_TOKEN"), root / "publish.json", tape=tape or config.get("site_tape"),
            performance=performance_of(config), real_brokers=readers,
            gateway_url=gateway_url, gateway_token=token,
        )
    return house
