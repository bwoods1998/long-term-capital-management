"""count_survivorship.py -- OUTCOME-FREE survivorship and point-in-time ticker counts.

(1) Issuers whose insiders filed a Form 4 naming an ISSUERTRADINGSYMBOL in year Y (SEC Insider Transactions Data Sets,
    all four quarters of 2016, 2019, 2022, 2025) that are ABSENT from today's company_tickers.json (the lane's current
    copy of the CIK->ticker map): the share of a year's insider-active issuers a current-copy map cannot place.
(2) Of those absent CIKs, how many still appear under the same symbol in today's map for ANOTHER CIK (symbol reuse).
(3) The point-in-time map size: distinct (issuer CIK, symbol) pairs and CIKs with > 1 symbol over the four years.
No price, share count or value column is parsed. Output: count_survivorship.out.json."""
import collections, csv, io, json, time, urllib.request, zipfile
UA = "ltcm (agent@blakewoods.us)"
csv.field_size_limit(10 ** 9)
def get(u):
    time.sleep(1.0)
    return urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=300).read()
cur = json.loads(get("https://www.sec.gov/files/company_tickers.json"))
cur_cik = {str(r["cik_str"]).zfill(10) for r in cur.values()}
cur_sym = {str(r["ticker"]).upper(): str(r["cik_str"]).zfill(10) for r in cur.values()}
out = {"current_map_rows": len(cur), "current_map_ciks": len(cur_cik)}
pairs = set(); per_cik_syms = collections.defaultdict(set)
for y in (2016, 2019, 2022, 2025):
    issuers = {}
    for q in (1, 2, 3, 4):
        z = zipfile.ZipFile(io.BytesIO(get(f"https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/{y}q{q}_form345.zip")))
        with z.open("SUBMISSION.tsv") as fh:
            rd = csv.reader(io.TextIOWrapper(fh, encoding="utf-8", errors="replace", newline=""), delimiter="\t", quoting=csv.QUOTE_NONE)
            head = next(rd); i_t, i_c, i_s = head.index("DOCUMENT_TYPE"), head.index("ISSUERCIK"), head.index("ISSUERTRADINGSYMBOL")
            for r in rd:
                if len(r) < len(head) or r[i_t] != "4":
                    continue
                cik = r[i_c].strip().zfill(10); sym = r[i_s].strip().upper()
                if not sym or sym in ("NONE", "N/A", "NA"):
                    continue
                issuers.setdefault(cik, sym); pairs.add((cik, sym)); per_cik_syms[cik].add(sym)
    absent = [c for c in issuers if c not in cur_cik]
    reused = sum(1 for c in absent if issuers[c] in cur_sym and cur_sym[issuers[c]] != c)
    out[str(y)] = {"issuers_with_symbol": len(issuers), "absent_from_current_map": len(absent),
                   "absent_share": round(len(absent) / max(1, len(issuers)), 4), "absent_whose_symbol_now_another_cik": reused}
    print(y, out[str(y)], flush=True)
out["pit_pairs_4yrs"] = len(pairs); out["ciks_with_gt1_symbol"] = sum(1 for s in per_cik_syms.values() if len(s) > 1)
json.dump(out, open("count_survivorship.out.json", "w"), indent=1); print(out)
