"""count_universe.py: OUTCOME-FREE universe counts from SEC's public company_tickers_exchange.json (fetched once,
2026-10-22 ~03:20Z). No price, volume or return is read: only tickers, CIKs and listing exchanges.
Counts the SEC-registered tickers on the exchanges the lane's universe admits (NYSE, Nasdaq, NYSE American/AMEX,
NYSE Arca, Cboe BZX), the issuers (CIKs) among them, and the tickers that look like common shares (no warrant/unit/
right/preferred suffix): an UPPER BOUND on the eligible universe before the $3 price, $1M ADV and operating tests."""
import json, re, collections
d = json.load(open("sec_tickers_exchange.json"))
rows = d["data"]
by_ex = collections.Counter(r[3] for r in rows)
print("all rows", len(rows)); print("by exchange", dict(by_ex.most_common()))
LISTED = {"NYSE", "Nasdaq", "CBOE", "NYSE American", "NYSE Arca", "NYSE MKT", "BATS"}
listed = [r for r in rows if r[3] in LISTED]
common = [r for r in listed if re.fullmatch(r"[A-Z]{1,5}", r[2] or "")]
ciks = {r[0] for r in common}
print("listed rows", len(listed), "plain 1-5 letter tickers", len(common), "issuers (CIK)", len(ciks))
per_cik = collections.Counter(r[0] for r in common)
print("issuers with >1 plain ticker", sum(1 for v in per_cik.values() if v > 1))
