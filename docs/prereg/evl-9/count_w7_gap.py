#!/usr/bin/env python
"""count_w7_gap.py: OUTCOME-FREE COUNTS for the captain's W7 (check 2's major 6): how much of the live universe the
history universe can reach, before W7 (SYMBOL from Form 4s only) and after it (Form 4 symbols PLUS S1's current tickers
on their spells). Source: the scout's pinned copy of SEC's submissions.zip (evl9/scout/submissions.zip, sha256
b6534bf3efaca6ea2a0a9509deb9eb4c612cb9aa12d4913fdb641a526cc4b033): per filer CIK its current tickers and exchanges,
its SIC, and every filing's form and filingDate (recent plus overflow pages). No price, return, share or value is read;
no request is made.

For each evaluation date D: the OPERATING FILERS of D (a universe.PERIODIC form filed in the 15 months before D, current
SIC neither 6221 nor 6770), split into
  (a) F4: a Form 4 listed under the CIK with filingDate in [D - 365 days, D) (S1 lists a Form 4 under its issuer; its
      S2 ISSUERTRADINGSYMBOL gives SYMBOL(i, D)): reachable before and after W7;
  (b) S1-ONLY: not (a), with a current S1 ticker: reachable only with W7's S1 spells;
  (c) NEITHER: never a history candidate on D (a name that has since left every exchange without Form 4 activity, or
      one never listed, which the live rule never admits either: an UPPER BOUND of the gap).
At the clamp (2026-10-16) the CURRENTLY EXCHANGE-LISTED operating filers (S1 exchanges NYSE, Nasdaq, NYSE American,
CBOE) give the exact near-clamp gap before and after W7.
Usage: count_w7_gap.py [--procs 2]   (writes count_w7_gap.out.json)
"""
import argparse
import collections
import datetime as dt
import json
import os
import zipfile
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
ZIP = os.path.join(os.path.dirname(HERE), "scout", "submissions.zip")
PERIODIC = ("10-K", "10-Q", "20-F", "40-F", "10-K/A", "10-Q/A", "20-F/A", "40-F/A", "10-KT")
FPI = ("20-F", "40-F", "20-F/A", "40-F/A")
EXCH = {"NYSE", "Nasdaq", "NYSE American", "CBOE"}
DATES = ["2022-01-03", "2022-07-01", "2023-01-03", "2023-07-03", "2024-01-02", "2024-07-01", "2025-01-02",
         "2025-07-01", "2026-01-02", "2026-07-01", "2026-10-16"]
MARK = (b'"10-K"', b'"10-Q"', b'"20-F"', b'"40-F"', b'"10-K/A"', b'"10-Q/A"', b'"20-F/A"', b'"40-F/A"', b'"10-KT"')


def minus_months(d, m):
    y, mo = d.year, d.month - m
    while mo <= 0:
        mo += 12
        y -= 1
    return dt.date(y, mo, min(d.day, 28))


def parse(raw, overflow):
    d = json.loads(raw)
    rec = d if overflow else ((d.get("filings") or {}).get("recent") or {})
    forms = rec.get("form") or []
    dates = rec.get("filingDate") or []
    per = [x for f, x in zip(forms, dates) if f in PERIODIC]
    fpi = any(f in FPI for f in forms)
    f4 = [x for f, x in zip(forms, dates) if f == "4"]
    head = None if overflow else dict(cik=str(d.get("cik") or "").lstrip("0"), tickers=[t for t in (d.get("tickers") or []) if t],
                                      exch=[e for e in (d.get("exchanges") or []) if e], sic=str(d.get("sic") or ""),
                                      files=[f.get("name") for f in ((d.get("filings") or {}).get("files") or [])])
    return head, per, f4, fpi


def work(names):
    out = {}
    with zipfile.ZipFile(ZIP) as z:
        for n in names:
            raw = z.read(n)
            if not any(m in raw for m in MARK):
                continue
            try:
                head, per, f4, fpi = parse(raw, False)
            except ValueError:
                continue
            if not per or head["sic"] in ("6221", "6770"):
                continue
            for extra in head["files"]:
                try:
                    _, p2, f2, fp2 = parse(z.read(extra), True)
                except (KeyError, ValueError):
                    continue
                per += p2
                f4 += f2
                fpi = fpi or fp2
            out[head["cik"]] = dict(t=bool(head["tickers"]), x=bool(set(head["exch"]) & EXCH), per=sorted(set(per)),
                                    f4=sorted(set(f4)), fpi=fpi)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--procs", type=int, default=2)
    a = ap.parse_args()
    with zipfile.ZipFile(ZIP) as z:
        names = [n for n in z.namelist() if n.endswith(".json") and "-submissions-" not in n]
    filers = {}
    with Pool(a.procs) as pool:
        for part in pool.imap_unordered(work, [names[i::32] for i in range(32)]):
            filers.update(part)
    res = {"zip": ZIP, "operating_filers_ever": len(filers), "by_date": {}}
    for ds in DATES:
        D = dt.date.fromisoformat(ds)
        lo15 = minus_months(D, 15).isoformat()
        lo365 = (D - dt.timedelta(days=365)).isoformat()
        c = collections.Counter()
        for cik, f in filers.items():
            if not any(lo15 <= x < ds for x in f["per"]):
                continue
            fam = "fpi" if f["fpi"] else "domestic"
            has4 = any(lo365 <= x < ds for x in f["f4"])
            cell = "a_F4" if has4 else ("b_S1only" if f["t"] else "c_neither")
            c[cell] += 1
            c[f"{cell}|{fam}"] += 1
            if ds == DATES[-1] and f["x"]:
                c[f"listed_now|{cell}"] += 1
                c[f"listed_now|{cell}|{fam}"] += 1
        tot = c["a_F4"] + c["b_S1only"] + c["c_neither"]
        row = dict(sorted(c.items()))
        row["operating"] = tot
        row["share_reachable_before_W7"] = round(c["a_F4"] / max(tot, 1), 4)
        row["share_reachable_after_W7"] = round((c["a_F4"] + c["b_S1only"]) / max(tot, 1), 4)
        if ds == DATES[-1]:
            ln = c["listed_now|a_F4"] + c["listed_now|b_S1only"] + c["listed_now|c_neither"]
            row["listed_now"] = ln
            row["listed_now_share_reachable_before_W7"] = round(c["listed_now|a_F4"] / max(ln, 1), 4)
            row["listed_now_share_reachable_after_W7"] = round((c["listed_now|a_F4"] + c["listed_now|b_S1only"]) / max(ln, 1), 4)
        res["by_date"][ds] = row
    print(json.dumps(res, indent=1))
    json.dump(res, open(os.path.join(HERE, "count_w7_gap.out.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
