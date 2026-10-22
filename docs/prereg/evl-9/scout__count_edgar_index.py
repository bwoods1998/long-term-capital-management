"""count_edgar_index.py -- OUTCOME-FREE record counts from SEC EDGAR's quarterly full index (form.gz).

Reads https://www.sec.gov/Archives/edgar/full-index/<YYYY>/QTR<q>/form.gz for 2016Q1..2026Q4 (streamed, nothing kept
but counts), with the House's declared User-Agent and >= 0.2 s between requests (SEC fair access: <= 10/s).
Counts, per year: rows and DISTINCT accessions (the path's file name <accession>.txt; the directory is the filer's CIK) (a filing is listed once per filer: a Form 4 under its issuer and
each reporting owner, a co-registered 8-K under each co-registrant) for the forms the lane reads (8-K, 4) and their
amendments, plus the periodic forms, and the distinct filer CIKs of 8-Ks. No price, return or document is read.
Output: count_edgar_index.out.json beside this file.
"""
import collections
import gzip
import io
import json
import re
import sys
import time
import urllib.request

UA = "ltcm (agent@blakewoods.us)"
FORMS = {"8-K", "8-K/A", "4", "4/A", "3", "5", "10-K", "10-Q", "6-K", "SC 13D", "SC 13G", "SC 13D/A", "SC 13G/A",
         "S-1", "424B4", "DEF 14A", "SCHEDULE 13D", "SCHEDULE 13G", "SCHEDULE 13D/A", "SCHEDULE 13G/A", "144"}
LINE = re.compile(r"^(?P<form>\S+(?: \S+)?)\s{2,}(?P<company>.+?)\s{2,}(?P<cik>\d+)\s+(?P<date>\d{4}-?\d{2}-?\d{2})\s+"
                  r"(?P<path>edgar/data/\S+)\s*$")


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "identity"})
    for wait in (1, 2, 4, 8, None):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except Exception as exc:  # noqa: BLE001
            if wait is None:
                raise
            print("retry", url, exc, file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(url)


def main() -> None:
    out = {}
    for year in range(2016, 2027):
        for q in (1, 2, 3, 4):
            key = f"{year}Q{q}"
            url = f"https://www.sec.gov/Archives/edgar/full-index/{year}/QTR{q}/form.gz"
            try:
                raw = get(url)
            except Exception as exc:  # noqa: BLE001
                out[key] = {"error": str(exc)[:200]}
                continue
            text = gzip.decompress(raw).decode("latin-1")
            rows = collections.Counter()
            accs = collections.defaultdict(set)
            ciks_8k = set()
            dates = set()
            total = 0
            for line in text.splitlines():
                m = LINE.match(line)
                if not m:
                    continue
                total += 1
                form = m.group("form")
                dates.add(m.group("date"))
                if form in FORMS:
                    rows[form] += 1
                    accs[form].add(m.group("path").rsplit("/", 1)[-1])  # the accession file name, not the filer's directory
                    if form == "8-K":
                        ciks_8k.add(m.group("cik"))
            out[key] = {"bytes_gz": len(raw), "rows_all": total, "filing_dates": len(dates),
                        "rows": dict(rows), "accessions": {f: len(s) for f, s in accs.items()},
                        "ciks_8k": len(ciks_8k)}
            print(key, len(raw), total, out[key]["accessions"].get("8-K"), out[key]["accessions"].get("4"), flush=True)
            time.sleep(0.25)
    years = {}
    for key, v in out.items():
        if "error" in v:
            continue
        y = years.setdefault(key[:4], {"bytes_gz": 0, "rows_all": 0, "filing_dates": 0, "accessions": collections.Counter(),
                                       "quarters": 0})
        y["bytes_gz"] += v["bytes_gz"]
        y["rows_all"] += v["rows_all"]
        y["filing_dates"] += v["filing_dates"]
        y["accessions"].update(v["accessions"])
        y["quarters"] += 1
    for y in years.values():
        y["accessions"] = dict(y["accessions"])
    json.dump({"source": "www.sec.gov full-index form.gz", "fetched_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "quarters": out, "years": years}, open(__file__.replace(".py", ".out.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
