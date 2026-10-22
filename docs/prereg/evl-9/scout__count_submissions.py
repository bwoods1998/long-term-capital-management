"""count_submissions.py -- OUTCOME-FREE counts from SEC's nightly bulk submissions archive (submissions.zip).

Source: https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip (on www.sec.gov, the House box's
allowlisted host; one download, 1,570,171,728 bytes, last-modified 2026-10-21 04:51:16 GMT). Each member is one filer
CIK's JSON (`CIK##########.json`: `filings.recent` = its latest >= 1 year or 1,000 filings; overflow pages
`CIK##########-submissions-NNN.json` hold the rest), with per filing: accessionNumber, filingDate,
acceptanceDateTime, form, items, size, primaryDocument, ...

ACCEPTANCE TIME DECODE (measured by this scout, `acceptance_offset` below and the 24-filing Apple sample in the
report): the JSON's acceptanceDateTime ends in "Z" but is the true UTC instant PLUS New York's UTC offset (4 h in EDT,
5 h in EST) against the filing's own .hdr.sgml <ACCEPTANCE-DATETIME> (Eastern wall time) and its -index.htm
"Accepted". So true_utc = json - 4 h when NY is on EDT at (json - 4 h), else json - 5 h; Eastern wall = true_utc in NY.

Counted 2016-01-01 .. 2026-10-21, by filing year, for forms 8-K, 8-K/A, 4, 4/A, 10-K, 10-Q: DISTINCT accessions (a
filing appears under each filer CIK: a Form 4 under its issuer and its owners), 8-Ks with a non-empty `items`, item
code frequencies, and the Eastern acceptance-time bucket (pre 09:30 / 09:30-16:00 / 16:00-17:30 / after 17:30;
weekends separately); per filer CIK: 8-K filers since 2016 and how many of them list no current ticker (the
survivorship exposure of a current-copy ticker map). No price, return or document is read.
Output: count_submissions.out.json. Up to 4 worker processes.
"""
import collections
import datetime as dt
import json
import multiprocessing as mp
import sys
import zipfile
from zoneinfo import ZoneInfo

import numpy as np

ZIP = "submissions.zip"
NY = ZoneInfo("America/New_York")
FORMS = ("8-K", "8-K/A", "4", "4/A", "10-K", "10-Q")
FIRST, LAST = "2016-01-01", "2026-10-21"


def true_utc(js: str) -> dt.datetime:
    t = dt.datetime.fromisoformat(js.replace("Z", "+00:00"))
    cand = t - dt.timedelta(hours=4)
    off = cand.astimezone(NY).utcoffset()
    if off == dt.timedelta(hours=-4):
        return cand
    return t - dt.timedelta(hours=5)


def bucket(et: dt.datetime) -> str:
    if et.weekday() >= 5:
        return "weekend"
    hm = et.hour * 60 + et.minute
    if hm < 9 * 60 + 30:
        return "pre_0930"
    if hm < 16 * 60:
        return "rth"
    if hm < 17 * 60 + 30:
        return "1600_1730"
    return "after_1730"


def work(args):
    names, shard = args
    z = zipfile.ZipFile(ZIP)
    accs = collections.defaultdict(list)       # (form, year) -> accession ints (dups across filers)
    items_nonempty = collections.defaultdict(list)
    item_codes = collections.Counter()          # counted per (accession) later? counted per row under first filer
    buckets = collections.defaultdict(list)     # (form, year, bucket) -> accession ints
    item_rows = collections.defaultdict(list)   # (code, year) -> accession ints
    ciks_8k_since2016 = 0
    ciks_8k_no_ticker = 0
    ciks_8k_old_only_no_ticker = 0
    members = 0
    missing_accept = collections.Counter()
    for name in names:
        try:
            d = json.loads(z.read(name))
        except Exception:  # noqa: BLE001
            continue
        members += 1
        if "filings" in d:
            rec = d["filings"].get("recent") or {}
            tickers = d.get("tickers") or []
            main = True
        else:
            rec = d
            tickers = None
            main = False
        forms = rec.get("form") or []
        has8k = False
        last8k = ""
        for i, form in enumerate(forms):
            if form not in FORMS:
                continue
            fdate = rec["filingDate"][i]
            if not (FIRST <= fdate <= LAST):
                continue
            year = int(fdate[:4])
            acc = int(rec["accessionNumber"][i].replace("-", ""))
            accs[(form, year)].append(acc)
            js = rec.get("acceptanceDateTime", [None] * len(forms))[i]
            if js:
                et = true_utc(js).astimezone(NY)
                buckets[(form, year, bucket(et))].append(acc)
            else:
                missing_accept[form] += 1
            if form == "8-K":
                has8k = True
                last8k = max(last8k, fdate)
                its = (rec.get("items") or [""] * len(forms))[i]
                if its and its.strip():
                    items_nonempty[(form, year)].append(acc)
                    for code in its.split(","):
                        code = code.strip()
                        if code:
                            item_rows[(code, year)].append(acc)
        if main and has8k:
            ciks_8k_since2016 += 1
            if not tickers:
                ciks_8k_no_ticker += 1
    pack = lambda dd: {k: np.array(v, dtype=np.int64) for k, v in dd.items()}  # noqa: E731
    return {"accs": pack(accs), "items": pack(items_nonempty), "buckets": pack(buckets), "item_rows": pack(item_rows),
            "ciks_8k": ciks_8k_since2016, "ciks_8k_no_ticker": ciks_8k_no_ticker, "members": members,
            "missing_accept": dict(missing_accept)}


def merge(parts, key):
    out = collections.defaultdict(list)
    for p in parts:
        for k, v in p[key].items():
            out[k].append(v)
    return {k: int(np.unique(np.concatenate(v)).size) for k, v in out.items()}


def main() -> None:
    z = zipfile.ZipFile(ZIP)
    infos = z.infolist()
    names = [i.filename for i in infos if i.filename.endswith(".json")]
    main_n = sum(1 for n in names if "-submissions-" not in n)
    over_n = len(names) - main_n
    total_bytes = sum(i.file_size for i in infos)
    print("members", len(names), "main", main_n, "overflow", over_n, "uncompressed", total_bytes, flush=True)
    k = 4
    shards = [(names[i::k], i) for i in range(k)]
    with mp.Pool(k) as pool:
        parts = pool.map(work, shards)
    accs = merge(parts, "accs")
    items = merge(parts, "items")
    buckets = merge(parts, "buckets")
    item_rows = merge(parts, "item_rows")
    years = sorted({y for (_, y) in accs})
    table = {}
    for y in years:
        row = {}
        for f in FORMS:
            row[f] = accs.get((f, y), 0)
        row["8-K_items_nonempty"] = items.get(("8-K", y), 0)
        for f in ("8-K", "4"):
            for b in ("pre_0930", "rth", "1600_1730", "after_1730", "weekend"):
                row[f"{f}_{b}"] = buckets.get((f, y, b), 0)
        table[y] = row
    codes = collections.Counter()
    by_code_year = {}
    for (code, y), n in item_rows.items():
        codes[code] += n
        by_code_year.setdefault(code, {})[y] = n
    res = {"zip": ZIP, "members": len(names), "main_members": main_n, "overflow_members": over_n,
           "uncompressed_bytes": total_bytes, "by_year": table,
           "item_codes_total_2016_2026": dict(codes.most_common()), "item_codes_by_year": by_code_year,
           "ciks_with_8k_since_2016": sum(p["ciks_8k"] for p in parts),
           "of_them_no_current_ticker": sum(p["ciks_8k_no_ticker"] for p in parts),
           "rows_missing_acceptance": dict(sum((collections.Counter(p["missing_accept"]) for p in parts),
                                               collections.Counter()))}
    json.dump(res, open("count_submissions.out.json", "w"), indent=1, default=str)
    for y in years:
        print(y, table[y], flush=True)
    print("ciks", res["ciks_with_8k_since_2016"], "no ticker", res["of_them_no_current_ticker"])


if __name__ == "__main__":
    main()
