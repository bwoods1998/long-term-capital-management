import unittest
from decimal import Decimal
from ltcm.performance import AccountPerformance, funding_flows, stamp

START = "2026-09-16T04:58:42.508Z"
NOW = "2026-09-17T07:00:00.000Z"
CONFIG = {"start_at": START, "start_equity": "976.11177639"}


class Broker:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def _call(self, method, path, **kwargs):
        assert method == "GET"
        self.calls.append((path, kwargs.get("params")))
        return self.rows[path]


def brokers(transactions=(), deposits=(), withdrawals=(), activities=None):
    rows = {"kalshi": Broker({"/portfolio/deposits": {"deposits": deposits},
                              "/portfolio/withdrawals": {"withdrawals": withdrawals}}),
            "coinbase": Broker({"/v2/accounts": {"data": [{"id": "account-1"}]},
                                "/v2/accounts/account-1/transactions": {"data": transactions}})}
    if activities is not None:
        rows["alpaca"] = Broker({"/v2/account/activities": list(activities)})
    return rows


def activity(kind="CSD", value="100", **kwargs):
    return {"id": kwargs.pop("id", f"act-{kind}-{value}"), "activity_type": kind,
            "date": NOW, "net_amount": value, "status": "executed", **kwargs}


def transaction(kind="fiat_deposit", value="100", **kwargs):
    return {"type": kind, "status": "completed", "created_at": NOW,
            "amount": {"amount": value, "currency": "USD"},
            "native_amount": {"amount": value, "currency": "USD"}, **kwargs}


class PerformanceTests(unittest.TestCase):
    def test_only_external_flows_since_baseline(self):
        before = transaction(value="500", created_at="2026-09-15T00:00:00Z")
        failed = transaction(status="failed")
        deposit = {"created_ts": stamp(NOW), "finalized_ts": stamp(NOW), "status": "applied", "amount_cents": 2500}
        rows = brokers([before, failed, transaction(), transaction("fiat_withdrawal", "-40"),
                        transaction("advanced_trade_fill", "-25"),
                        transaction("derivatives_settlement", "-109.51")], [deposit], [{**deposit, "amount_cents": 1000}])
        flows = funding_flows(rows, START)
        self.assertEqual(sum(value for _, _, value in flows), Decimal("75"))
        self.assertEqual(len(flows), 4)

    def test_alpaca_funding_counts_and_its_earnings_do_not(self):
        rows = brokers(activities=[
            activity("CSD", "500"),                                  # the owner funding the account
            activity("CSW", "-40"),                                  # and taking money back out
            activity("JNLC", "25"),
            activity("DIV", "3.10"),                                 # earnings, not funding
            activity("FEE", "-0.50"),
            activity("FILL", "-120"),                                # a trade, already in the ledger
            activity("CSD", "900", date="2026-09-15T00:00:00Z", id="old"),  # before the baseline
            # An instant deposit books on the next business day; the money moved when it was made.
            activity("CSD", "700", date="2026-09-30", created_at="2026-09-15T03:16:38Z", id="booked-later"),
        ])
        flows = [f for f in funding_flows(rows, START) if f[0] == "alpaca"]
        self.assertEqual(sum(value for _, _, value in flows), Decimal("485"))
        self.assertEqual(len(flows), 3)

    def test_an_unknown_alpaca_activity_fails_closed(self):
        # A funding type this runtime has never seen must not be counted as profit.
        with self.assertRaises(ValueError):
            funding_flows(brokers(activities=[activity("SURPRISE", "250")]), START)
        with self.assertRaises(ValueError):
            funding_flows(brokers(activities=[activity("CSD", "250", status="pending")]), START)

    def test_a_floor_without_alpaca_reads_two_venues_as_before(self):
        self.assertEqual(funding_flows(brokers(), START), [])

    def test_unknown_pending_and_unvalued_transactions_fail_closed(self):
        for row in [transaction("surprise"), transaction(status="pending"),
                    transaction(native_amount={"amount": "0", "currency": "USD"}),
                    transaction(native_amount={"amount": "100", "currency": "EUR"}),
                    transaction("fiat_withdrawal", "100")]:
            with self.subTest(row=row), self.assertRaises(ValueError):
                funding_flows(brokers([row]), START)

    def test_crypto_transfer_is_not_a_trade(self):
        row = transaction("send", "20", amount={"amount": ".001", "currency": "BTC"})
        self.assertEqual(funding_flows(brokers([row]), START)[0][2], Decimal("20"))

    def test_pagination_never_accepts_another_host_or_collection(self):
        for uri in ["https://evil.test/v2/accounts", "/v2/other", "/v2/accounts?limit=100"]:
            readers = brokers()
            readers["coinbase"].rows["/v2/accounts"]["pagination"] = {"next_uri": uri}
            with self.assertRaises(ValueError):
                funding_flows(readers, START)

    def test_cache_requires_complete_fresh_balances_and_funding(self):
        now = stamp(NOW)
        monitor = AccountPerformance(CONFIG, brokers(), lambda: now)
        monitor.attempted = now  # deterministic test: call the worker directly, never spawn it
        account = {"venues": [{"venue": venue, "as_of": NOW} for venue in ("kalshi", "coinbase")]}
        self.assertIsNone(monitor.read(account, NOW)["net_flows"])
        monitor._refresh(NOW)
        self.assertEqual(monitor.read(account, NOW)["net_flows"], "0")
        self.assertEqual(monitor.read(account, NOW)["start_equity"], CONFIG["start_equity"])
        self.assertIsNone(monitor.read({"venues": account["venues"][:1]}, NOW)["net_flows"])
        account["venues"][0]["stale"] = True
        self.assertIsNone(monitor.read(account, NOW)["net_flows"])
        del account["venues"][0]["stale"]
        self.assertIsNone(monitor.read(account, "2026-09-17T07:11:00.000Z")["net_flows"])
        monitor.brokers = brokers([transaction("unknown")])
        monitor._refresh(NOW)
        self.assertIsNone(monitor.read(account, NOW)["net_flows"])

    def test_flows_after_balance_timestamp_are_not_subtracted_yet(self):
        monitor = AccountPerformance(CONFIG, brokers([transaction()]), lambda: stamp(NOW))
        monitor.attempted = stamp(NOW)
        monitor._refresh(NOW)
        account = {"venues": [{"venue": v, "as_of": START} for v in ("kalshi", "coinbase")]}
        self.assertEqual(monitor.read(account, NOW)["net_flows"], "0")
        account["venues"][1]["as_of"] = NOW
        self.assertEqual(monitor.read(account, NOW)["net_flows"], "100")
