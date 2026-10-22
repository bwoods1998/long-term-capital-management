"""count_fpi_s2.py -- OUTCOME-FREE counts (no price, no share or value column is parsed). Which exchange-listed SEC
filers (the scout's pinned submissions.zip: tickers + exchanges today) are the ISSUER of at least one original Form 4 in
SEC's Insider Transactions Data Sets 2025q4-2026q3 (SUBMISSION.tsv: DOCUMENT_TYPE '4', ISSUERCIK, FILING_DATE), i.e.
which can ever get PREREG-EVL-9 section 3.4's point-in-time SYMBOL near the clamp; split by periodic family (a 20-F/40-F
filed since 2024-07-16 = foreign private issuer, else a 10-K/10-Q family filer)."""
import csv, io, json, sys, time, urllib.request, zipfile, collections
from concurrent.futures import ProcessPoolExecutor
UA = {"User-Agent": "ltcm (agent@blakewoods.us)"}
ZIP = "/home/bwoods1998/Work/.ltcm-main/goal-2026-10-19/evl9/scout/submissions.zip"
EXCH = {"NYSE", "Nasdaq", "NYSE American", "NYSE Arca", "CBOE", "BATS"}
csv.field_size_limit(10 ** 9)

def s2_issuers():
    out = set()
    for y, q in ((2025, 4), (2026, 1), (2026, 2), (2026, 3)):
        base = "datastandardsinnovation" if (y, q) >= (2026, 2) else "structureddata"
        url = f"https://www.sec.gov/files/{base}/data/insider-transactions-data-sets/{y}q{q}_form345.zip"
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=300) as r:
            raw = r.read()
        z = zipfile.ZipFile(io.BytesIO(raw))
        name = [n for n in z.namelist() if n.upper().endswith("SUBMISSION.TSV")][0]
        with z.open(name) as fh:
            rd = csv.reader(io.TextIOWrapper(fh, encoding="utf-8", errors="replace", newline=""), delimiter="\t",
                            quoting=csv.QUOTE_NONE)
            head = next(rd); i_t, i_c = head.index("DOCUMENT_TYPE"), head.index("ISSUERCIK")
            for row in rd:
                if len(row) >= len(head) and row[i_t] == "4":
                    out.add(row[i_c].strip().lstrip("0"))
        time.sleep(1)
    return out

def work(names):
    out = []
    with zipfile.ZipFile(ZIP) as z:
        for n in names:
            raw = z.read(n)
            if b'"tickers":[]' in raw or b'"tickers"' not in raw:
                continue
            try:
                d = json.loads(raw)
            except ValueError:
                continue
            if not set(x for x in (d.get("exchanges") or []) if x) & EXCH:
                continue
            rec = (d.get("filings") or {}).get("recent") or {}
            fam = None
            for f, dte in zip(rec.get("form") or [], rec.get("filingDate") or []):
                if dte < "2024-07-16":
                    continue
                if f in ("20-F", "40-F", "20-F/A", "40-F/A"):
                    fam = "fpi"; break
                if f in ("10-K", "10-Q", "10-K/A", "10-Q/A", "10-KT") and fam is None:
                    fam = "domestic"
            out.append((str(d.get("cik") or "").lstrip("0"), fam or "no-periodic"))
    return out

def main():
    iss = s2_issuers()
    with zipfile.ZipFile(ZIP) as z:
        names = [n for n in z.namelist() if n.endswith(".json") and "-submissions-" not in n]
    listed = []
    with ProcessPoolExecutor(4) as ex:
        for part in ex.map(work, [names[i::4] for i in range(4)]):
            listed += part
    c = collections.Counter((fam, cik in iss) for cik, fam in listed)
    res = {"s2_form4_issuers_2025q4_2026q3": len(iss)}
    res.update({f"{fam}|issuer_of_a_form4={has}": n for (fam, has), n in sorted(c.items())})
    print(json.dumps(res, indent=1))
    json.dump(res, open(__file__.replace(".py", ".out.json"), "w"), indent=1)

if __name__ == "__main__":
    main()
