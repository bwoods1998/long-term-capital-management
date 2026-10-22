"""count_fpi.py -- OUTCOME-FREE counts from the scout's pinned SEC submissions.zip (filings metadata only, no price).

Question: how many CIKs that SEC lists with an exchange ticker today (the kind the LIVE universe can admit through
company_tickers.json + Alpaca assets) would get NO point-in-time SYMBOL in PREREG-EVL-9's history universe, because the
draft's SYMBOL(i, D) comes only from Form 4 ISSUERTRADINGSYMBOL and these issuers had no Form 4 in the 365 days
before 2026-10-16. Foreign private issuers (20-F / 40-F filers) are exempt from Section 16 and file no Form 4.
Counts only: CIKs by (periodic family, has a Form 4 in the window). Nothing else is read or printed.
"""
import json, sys, zipfile, collections
from concurrent.futures import ProcessPoolExecutor

ZIP = "/home/bwoods1998/Work/.ltcm-main/goal-2026-10-19/evl9/scout/submissions.zip"
LO, HI = "2025-10-16", "2026-10-16"
EXCH = {"NYSE", "Nasdaq", "NYSE American", "NYSE Arca", "CBOE", "BATS"}

def work(names):
    out = collections.Counter()
    with zipfile.ZipFile(ZIP) as z:
        for n in names:
            raw = z.read(n)
            if b'"tickers":[]' in raw or b'"tickers"' not in raw:
                continue
            try:
                d = json.loads(raw)
            except ValueError:
                continue
            ex = set(x for x in (d.get("exchanges") or []) if x)
            if not ex & EXCH:
                continue
            rec = (d.get("filings") or {}).get("recent") or {}
            forms, dates = rec.get("form") or [], rec.get("filingDate") or []
            fam = None; f4 = 0; per = False
            for f, dte in zip(forms, dates):
                if f in ("20-F", "40-F", "20-F/A", "40-F/A") and dte >= "2024-07-16":
                    fam = fam or "fpi"
                if f in ("10-K", "10-Q", "10-K/A", "10-Q/A", "10-KT") and dte >= "2024-07-16":
                    fam = "domestic" if fam is None else fam
                if f == "4" and LO <= dte <= HI:
                    f4 += 1
            if fam is None:
                fam = "no-periodic-15m"
            out[(fam, f4 > 0)] += 1
    return out

def main():
    with zipfile.ZipFile(ZIP) as z:
        names = [n for n in z.namelist() if n.endswith(".json") and "-submissions-" not in n]
    chunks = [names[i::4] for i in range(4)]
    tot = collections.Counter()
    with ProcessPoolExecutor(4) as ex:
        for c in ex.map(work, chunks):
            tot.update(c)
    res = {f"{fam}|form4_in_365d={has}": n for (fam, has), n in sorted(tot.items())}
    print(json.dumps(res, indent=1))
    json.dump(res, open(__file__.replace(".py", ".out.json"), "w"), indent=1)

if __name__ == "__main__":
    main()
