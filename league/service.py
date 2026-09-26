"""Build the options House. Venue and model credentials remain behind the gateway.

The House environment contains only GATEWAY_TOKEN, SAIL_API_KEY and CAPITAL_PUBLISH_TOKEN.
Live account authorization stays in the owner-created grant. The swarm owns all researchers,
programs and family budgets; the live path exclusively owns both trading accounts.
"""
from __future__ import annotations
import json
import os
import stat
import time
import urllib.request
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


def auto_update(config: dict[str, Any]) -> bool:
    """Whether the in-box updater pulls main by itself: only when `config.json` says `"auto_update":
    true`. A missing key means OFF (the options overhaul, Sept 26, 2026, trap 3: the old default of
    on let the updater ship main's heads into a House that nobody had deployed; the prune ships as
    the owner's deploys, and the updater stays off until the overhaul has run a day)."""
    return config.get("auto_update", False) is True


def performance_of(config: dict[str, Any]) -> dict[str, Any] | None:
    """`config.json` `performance` once the reset has filled both `start_at` and `start_equity`; None before (the
    publisher then shows the account's balance with no since-reset figure, rather than failing every minute)."""
    performance = dict(config.get("performance") or {})
    return performance if performance.get("start_at") and performance.get("start_equity") is not None else None


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
    from league.adapters import GatewaySigner, VenueClient
    from league.notify import post_json

    from .ledger import HOUSE

    gateway_url = config["gateway_url"]
    signer = GatewaySigner(token())
    table = live_money.Table.from_constitution()

    def client(venue: str) -> Any:
        return VenueClient(None, gateway_url=gateway_url, gateway=signer, venue=venue)

    market = MarketData(client("alpaca"), option_feed=str(config.get("alpaca_option_feed", "opra")),
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


def repair_engineer(house: House, *, frontier: Any, forge: Any, may_spend: Callable[[], bool] = lambda: False) -> Any:
    """Explicitly enabled repair helper loop; owner merges and deploys every proposed patch."""
    from .engineer import Engineer
    from .worklist import Worklist, Sources
    queue = Worklist(house.ledger, clock=house.clock)
    return Engineer(frontier, forge, house.ledger, queue, clock=house.clock, may_spend=may_spend,
                    sources=Sources(house.ledger, queue), summary_path=house.root / "repairs.json",
                    inbox=house.root / "repairs-inbox")


def build(root: str | Path, *, config: dict[str, Any] | None = None, local_sandbox: bool = False,
          research: bool = True, publish: bool = True, tape: str | None = None,
          game: dict[str, Any] | None = None, name_prefix: str = "league", merton: bool = True,
          canary: bool = False) -> House:
    """Connect the verified options components; a canary has no venue or paid worker.

    The compatibility keywords research/game/name_prefix/merton no longer select a second research
    system. The explicit swarm configuration controls the sole population and research loop.
    """
    from .swarm import settings as swarm_settings

    config = dict(config or load_config())
    load_env()
    root = Path(root)
    real_money = config.get("real_money") is True and not canary
    if real_money and local_sandbox:
        raise ValueError("real money requires the sealed Sail program runner")
    house = House(root, settings=Settings(tick_seconds=float(config.get("tick_seconds", 30)),
                                         publish_seconds=float(config.get("publish_seconds", 60)),
                                         real_money=real_money))
    if canary:
        return house
    gateway_url = str(config["gateway_url"])
    token = lambda: secret("GATEWAY_TOKEN")
    swarm_on = swarm_settings.load(root, config=config).get("enabled") is True
    if live_enabled(config):
        house.options_live = options_live(house, root, config, real_money=real_money,
                                         token=token, swarm_on=swarm_on)
    # The hook also owns the data daemon when research is disabled. It applies both switches.
    from .swarm.hook import attach
    attach(house, root, config)
    if REPO.parent.name == "releases" and not local_sandbox:
        from .backup import Backup
        from .sailbox import SailboxClient
        house.backup = Backup(SailboxClient(), house.ledger)
        if auto_update(config):
            from .updater import Updater
            house.updater = Updater(REPO.parent.parent)
    if config.get("repair_engineer") is True:
        from .frontier import Frontier, FrontierMonth
        from .merton import GatewayForge
        month = FrontierMonth(gateway_url, token)
        house.engineer = repair_engineer(house, frontier=Frontier(gateway_url, token),
                                        forge=GatewayForge(gateway_url, token),
                                        may_spend=lambda: (month.remaining() or 0) >= 5)
    if publish:
        from .publish import Publisher
        from .venues import gateway_broker
        reader = gateway_broker("alpaca", gateway_url=gateway_url, token=token(),
                                feed=str(config.get("alpaca_feed", "sip")),
                                option_feed=str(config.get("alpaca_option_feed", "opra")))
        house.publisher = Publisher(config["site_url"], lambda: secret("CAPITAL_PUBLISH_TOKEN"),
                                    root / "publish.json", tape=tape or config.get("site_tape"),
                                    performance=performance_of(config), real_brokers={"alpaca": reader},
                                    gateway_url=gateway_url, gateway_token=token)
    return house
