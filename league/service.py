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


def build(root: str | Path, *, config: dict[str, Any] | None = None, local_sandbox: bool = False, research: bool = True,
          publish: bool = True, tape: str | None = None, game: dict[str, Any] | None = None, name_prefix: str = "league",
          astra: bool = True, canary: bool = False) -> House:
    """`canary=True` is a House that can hurt nothing: a simulated Alpaca account instead of the
    shared paper one (the real House reconciles that account to the cent, and a second trader on it
    would break the reconciliation), its own Kalshi shadow state, no real venues, no publishing,
    no research, no Astra. The watchdog runs new code this way before the House runs it."""
    from ltcm.adapters import GatewaySigner, VenueClient
    from ltcm.data.kalshi import KalshiMarketData
    from ltcm.data.news import News
    from ltcm.history import History
    from ltcm.provider import Provider
    from ltcm.sailbox import SailboxClient

    from .auditor import Auditor
    from .budget import Budget
    from .commons import Commons, sail_search
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
        research = publish = astra = False
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
        paper = gateway_broker("alpaca-paper", gateway_url=gateway_url, token=token(), feed=config.get("alpaca_feed", "iex"))
    brokers: dict[str, Any] = {"alpaca-paper": paper, "kalshi-shadow": KalshiShadowBroker(root / "kalshi-shadow.json", market_data)}
    if real_money:
        brokers["alpaca"] = gateway_broker("alpaca", gateway_url=gateway_url, token=token(), feed=config.get("alpaca_feed", "iex"))
        brokers["kalshi"] = gateway_broker("kalshi", gateway_url=gateway_url, token=token())

    if local_sandbox:
        sandbox: Any = LocalSandbox(root / "boxes")
    else:
        sandbox = SailSandbox(SailboxClient(), root / "sandbox.json", image_checkpoint=config["agent_image_checkpoint"], name_prefix=name_prefix)

    provider = Provider(root / "provider.sqlite", floor_cap_usd_per_day=config.get("inference_daily_cap_usd", "3.00")) if research else None
    house_settings = Settings(
        tick_seconds=int(config.get("tick_seconds", 60)), mark_every_seconds=int(config.get("mark_every_seconds", 300)),
        real_money=real_money, replay_days=int(config.get("replay_days", 21)), research=research,
        replay_timeout=120 if canary else 600, kalshi_replay_days=1 if canary else 7, kalshi_replay_markets=60 if canary else 2000,
    )
    house = House(
        root, brokers=brokers, sandbox=sandbox, alpaca_data=alpaca_data, kalshi_data=kalshi_data, provider=provider,
        game=game, settings=house_settings, kill_switch=gateway_kill_switch(gateway_url, token) if real_money else None,
    )
    house.commons = Commons(house.ledger, search=sail_search(lambda: secret("SAIL_API_KEY")), news=News(cache_dir=root / "cache"))
    if house.researcher is not None:
        house.researcher.commons = house.commons
    frontier = Frontier(gateway_url, token)
    house.frontier = frontier
    house.auditor = Auditor(
        frontier, house.ledger, house.economy, house.evaluator,
        live_agents=lambda: [{"agent": a.id, "family": a.family, "niche": a.niche} for a in house.registry.living() if house.evaluator.rung(a.id) >= 2],
        lineage=house.registry.lineage,
    )
    if astra:
        from .astra import Astra, GatewayForge, evidence_from

        pace = house.game.get("astra") or {}
        house.astra = Astra(frontier, GatewayForge(gateway_url, token), house.ledger, evidence=evidence_from(house),
                            schedule_hours=pace.get("schedule_hours"), first_after_hours=pace.get("first_after_hours"), effort=pace.get("effort"))
    if provider is not None:
        house.budget = Budget(house.ledger, lambda: provider.check_balance())
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
