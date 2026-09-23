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
                    may_spend=lambda: house.pacer.may_spend("openai") and house.frontier_tier() != "audits",
                    sources=Sources(house.ledger, worklist, niche_of=niche_of), summary_path=Path(house.root) / "repairs.json",
                    inbox=Path(house.root) / "repairs-inbox")


def build(root: str | Path, *, config: dict[str, Any] | None = None, local_sandbox: bool = False, research: bool = True,
          publish: bool = True, tape: str | None = None, game: dict[str, Any] | None = None, name_prefix: str = "league",
          merton: bool = True, canary: bool = False) -> House:
    """`canary=True` is a House that can hurt nothing: a simulated Alpaca account instead of the
    shared paper one (the real House reconciles that account to the cent, and a second trader on it
    would break the reconciliation), its own Kalshi shadow state, no real venues, no publishing,
    no research, no Merton. The watchdog runs new code this way before the House runs it."""
    from ltcm.adapters import GatewaySigner, VenueClient
    from ltcm.data.kalshi import KalshiMarketData
    from ltcm.data.news import News
    from ltcm.history import History
    from ltcm.provider import Provider
    from ltcm.sailbox import SailboxClient

    from .auditor import Auditor
    from .budget import Budget
    from .campaigns import CampaignBudget
    from .commons import Commons
    from .funded import FundedTransport
    from .frontier import Frontier
    from .paper import KalshiShadowBroker
    from .publish import Publisher
    from .sandbox import LocalSandbox, SailSandbox
    from .tapes import AlpacaData, KalshiData
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
    gateway_url = config["gateway_url"]
    token = lambda: secret("GATEWAY_TOKEN")  # noqa: E731
    real_money = bool(config.get("real_money"))

    market_data = KalshiMarketData()
    data_client = VenueClient(None, gateway_url=gateway_url, gateway=GatewaySigner(token()), venue="alpaca-paper")
    alpaca_data = AlpacaData(data_client, feed=config.get("alpaca_feed", "iex"))
    kalshi_data = KalshiData(market_data, History(cache_dir=root / "cache"))
    if canary:
        from .sim import SimBroker, touch_from

        paper: Any = SimBroker(root / "alpaca-sim.json", touch_from(alpaca_data))
    else:
        paper = gateway_broker("alpaca-paper", gateway_url=gateway_url, token=token(), feed=config.get("alpaca_feed", "iex"),
                               option_feed=config.get('alpaca_option_feed', 'indicative'))
    brokers: dict[str, Any] = {"alpaca-paper": paper, "kalshi-shadow": KalshiShadowBroker(root / "kalshi-shadow.json", market_data)}
    if real_money:
        brokers["alpaca"] = gateway_broker("alpaca", gateway_url=gateway_url, token=token(), feed=config.get("alpaca_feed", "iex"),
                                          option_feed=config.get('alpaca_option_feed', 'indicative'))
        brokers["kalshi"] = gateway_broker("kalshi", gateway_url=gateway_url, token=token())

    if local_sandbox:
        sandbox: Any = LocalSandbox(root / "boxes")
    else:
        sandbox = SailSandbox(SailboxClient(), root / "sandbox.json", image_checkpoint=config["agent_image_checkpoint"], name_prefix=name_prefix,
                              background_sleep=True)

    campaigns = CampaignBudget(root / "campaigns.sqlite") if not canary else None
    from .overnight import active
    burst = active(campaigns, time.time)
    inference_cap = Decimal(str(config.get('inference_daily_cap_usd', '3.00')))
    if burst:
        inference_cap += Decimal(burst['policy']['caps_usd']['sail'])
    provider = Provider(root / "provider.sqlite", floor_cap_usd_per_day=inference_cap) if research else None
    if provider is not None and campaigns is not None:
        provider.transport = FundedTransport(provider.transport, campaigns)
    house_settings = Settings(
        tick_seconds=int(config.get("tick_seconds", 60)), mark_every_seconds=int(config.get("mark_every_seconds", 300)),
        real_money=real_money, replay_days=int(config.get("replay_days", 21)), research=research,
        replay_timeout=120 if canary else 600, kalshi_replay_days=1 if canary else 7, kalshi_replay_markets=60 if canary else 2000,
        # Deep replay over the history store and the sealed holdout (league/deep_replay.py): on by
        # default, inert until `python -m league.history ingest` has fetched a strategy's inputs.
        deep_replay=bool(config.get("deep_replay", True)), holdout_gate=bool(config.get("holdout_gate", True)),
    )
    house = House(
        root, brokers=brokers, sandbox=sandbox, alpaca_data=alpaca_data, kalshi_data=kalshi_data, provider=provider,
        game=game, settings=house_settings, kill_switch=gateway_kill_switch(gateway_url, token) if real_money else None,
        campaigns=campaigns,
    )
    # The same clock as the House: `open_requests` drops a request nothing has closed after three
    # days, and a Commons reading a different clock would measure that window against the wrong now.
    house.commons = Commons(house.ledger, news=News(cache_dir=root / "cache"),
                            clock=house.clock)
    if house.researcher is not None:
        house.researcher.commons = house.commons
    frontier = Frontier(gateway_url, token, spend_guard=campaigns)
    house.frontier = frontier
    if config.get("options_history", True) and not canary:
        # Listed-option history (market-data GETs only): the options desk's replay and the
        # equity desks' IV/skew/activity features. Empty until ingested; then refreshed daily.
        from .options_history import OptionsHistory, gateway_get
        house.options_history = OptionsHistory(root / "options_history.sqlite", gateway_get(paper), ledger=house.ledger, clock=house.clock)
    if config.get("feeds", True) and not canary:
        # Live sports scoreboards and perpetual funding / open interest, and Deribit's DVOL and OKX's
        # settled funding as backfilled point-in-time history (league/feeds.py): public, keyless hosts
        # already on the House box's allowlist, recorded on a lane of their own. Agents ask for them
        # in NEEDS["feeds"]; replay uses the live ones once recorded, the backfilled ones at once.
        from .feeds import FeedRecorder
        house.feeds = FeedRecorder(house, root / "feeds.sqlite")
    # The continuous midpoint-direction labeler is off unless the config turns it back on. It burned
    # about $1/h of Jev's $20 lifetime allowance ($16.04 spent at the gateway by Sept 22, 2026), and
    # the capped evaluation of its own store found no tradable value: its labels predicted whether a
    # midpoint moves, not which way, and no threshold trade beat the spread
    # (docs/design/2026-09-22-jev-sensor.md).
    if campaigns is not None and campaigns.burst() and config.get("semantic_lab", False):
        from .semantic_lab import JevClient, SemanticLab
        house.semantic_lab = SemanticLab(root, JevClient(gateway_url, token), house.ledger,
                                         active=campaigns.running, clock=house.clock,
                                         proposer=frontier, burst=campaigns.burst())
    if house.researcher is not None and campaigns is not None:
        from .fast_research import FastResearch, ResearchRouter, MODEL as RESEARCH_MODEL, load_routes

        routes = load_routes()
        fast = FastResearch(root / 'fast-research.sqlite',
            Frontier(gateway_url, token, model=RESEARCH_MODEL, spend_guard=campaigns),
            house.ledger, balance=house.economy.balance, clock=house.clock, cache=routes.get('cache'))
        if burst:
            from .overnight import policy_with_turbo
            routes = {'enabled': True, 'cohort': burst['id'], 'fraction': policy_with_turbo(burst)['luna_fraction']}
        from .routing import TaskRouter

        task_router = TaskRouter(house.ledger, clock=house.clock, config=load_routes().get('routing'))
        house.researcher.provider = ResearchRouter(provider, fast, routes, tier=house.frontier_tier, task_router=task_router)
        house.researcher.routes = task_router
    if not canary and house.researcher is not None and config.get("research_traces", True):
        # Private research transcripts with their cost and outcome, for eventual fine-tuning.
        from .traces import TraceStore

        house.researcher.traces = TraceStore(root, house.ledger, clock=house.clock)
    if not canary and house.researcher is not None:
        # Jev for every researcher (`classify`): one question over many records, at cost.
        from .semantic_lab import JevClient
        house.researcher.jev = JevClient(gateway_url, token)
    jev = dict(config.get("jev") or {})
    if not canary and jev.get("enabled", True):
        # Jev as the cheap sensor in front of expensive work: research gate, explicit inactivity,
        # triage into repair reports, hypothesis links, exposure groups. Capped and cached here;
        # the gateway's lifetime allowance stays the authority (league/jev.py).
        from .jev import Sensor
        from .semantic_lab import JevClient
        from .sensors import JevFloor

        sensor = Sensor(root / "jev.sqlite", JevClient(gateway_url, token), clock=house.clock,
                        daily_usd=str(jev.get("daily_usd", "0.25")), daily_calls=int(jev.get("daily_calls", 400)),
                        purpose_calls=jev.get("purpose_calls") or None)
        house.jev_floor = JevFloor(house, sensor, jev)
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
                            pace=house.frontier_pace, backoff_max=pace.get("backoff_max"))
    if house.merton is not None:
        # Always built with Merton: switched off in league/engineer.json it still reports (free),
        # and buys nothing.
        house.engineer = repair_engineer(house, frontier, house.merton.forge)
    if merton and (house.game.get("hypotheses") or {}).get("enabled", True):
        # Merton writes hypothesis cards for the desks where the evidence is, and replay admits
        # them; routine refill stops breeding random mutations (league/hypotheses.py).
        from .hypotheses import Foundry, foundry_model

        # Its cards are judged by replay before any seat, so it writes on the model game.json names
        # (GPT-6 Sol from Sept 22, 2026: about a fifth of Astra's price, a call every quarter hour
        # inside the same daily budget); the auditor and the engineer keep Astra.
        model = foundry_model(house.game)
        writer = frontier if model in (None, frontier.model) else Frontier(gateway_url, token, model=model, spend_guard=campaigns)
        house.hypotheses = Foundry(house, writer)
    if house.researcher is not None and frontier is not None:
        # An agent may hire Merton with its own credits, whether or not his pull-request roles run:
        # what a good record buys is better thinking.
        from .merton import Merton as _Merton

        house.researcher.merton = house.merton or _Merton(frontier, None, house.ledger, evidence=lambda role: {})
        if campaigns is not None:
            from .grants import ResearchGrants

            house.researcher.grants = ResearchGrants.funded(root / 'grants.sqlite', gateway_url, token,
                house.ledger, campaigns, clock=house.clock)
    if provider is not None:
        # The owner's recorded Sail top-ups raise the account meter's monthly line as well as the
        # campaign's ceiling: otherwise the meter stops the floor with the new credit unspent.
        house.budget = Budget(house.ledger, lambda: provider.check_balance(),
                              topped_up=(lambda month: campaigns.topped_up("sail", month)) if campaigns is not None else None)
    if not canary and REPO.parent.name == "releases" and not local_sandbox:
        # On the House box only: a daily checkpoint of the box itself, so the ledger (every agent's
        # code, record and journal) outlives the one disk it lives on.
        from .backup import Backup

        house.backup = Backup(SailboxClient(), house.ledger)
    if not canary and REPO.parent.name == "releases" and config.get("auto_update", True):
        # On the House box the code runs from <base>/releases/<id>: there, main is pulled every
        # half hour and handed to the watchdog. On a developer's machine nothing updates itself.
        from .updater import Updater

        house.updater = Updater(REPO.parent.parent)
    if publish:
        # The balance chart is the REAL accounts whatever the agents are doing, so the publisher
        # reads them (balances only) even while every book is practice.
        readers = {
            "alpaca": brokers.get("alpaca") or gateway_broker("alpaca", gateway_url=gateway_url, token=token(), feed=config.get("alpaca_feed", "iex")),
            "kalshi": brokers.get("kalshi") or gateway_broker("kalshi", gateway_url=gateway_url, token=token()),
        }
        house.publisher = Publisher(
            config["site_url"], lambda: secret("CAPITAL_PUBLISH_TOKEN"), root / "publish.json", tape=tape or config.get("site_tape"),
            performance=config.get("performance"), real_brokers=readers,
            gateway_url=gateway_url, gateway_token=token,
        )
    return house
