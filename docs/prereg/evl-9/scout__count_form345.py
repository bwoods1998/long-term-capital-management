"""count_form345.py -- OUTCOME-FREE record counts from SEC's Insider Transactions Data Sets (Forms 3/4/5 XML, quarterly).

https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/<YYYY>q<q>_form345.zip, 2016q1..2026q3,
one request each (>= 1 s apart), read in memory and dropped. Counted per quarter: SUBMISSION rows by DOCUMENT_TYPE,
Form 4 filings with an ISSUERTRADINGSYMBOL, distinct issuer CIKs and symbols of Form 4s, NONDERIV_TRANS rows by
TRANS_CODE (P open-market purchase, S sale, ...), Form 4 filings with >= 1 code-P row and their distinct issuers, and the
REPORTINGOWNER relationship strings. The price, share and value columns are never parsed or printed.
Output: count_form345.out.json beside this file.
"""
import collections
import csv
import io
import json
import sys
import time
import urllib.request
import zipfile

UA = "ltcm (agent@blakewoods.us)"
BASE = "https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/{y}q{q}_form345.zip"
csv.field_size_limit(10 ** 9)


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for wait in (2, 4, 8, None):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return r.read()
        except Exception as exc:  # noqa: BLE001
            if wait is None:
                raise
            print("retry", url, exc, file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(url)


def rows(z: zipfile.ZipFile, name: str, cols: list[str]):
    with z.open(name) as fh:
        reader = csv.reader(io.TextIOWrapper(fh, encoding="utf-8", errors="replace", newline=""), delimiter="\t",
                            quoting=csv.QUOTE_NONE)
        head = next(reader)
        idx = [head.index(c) for c in cols]
        for r in reader:
            if len(r) < len(head):
                continue
            yield [r[i] for i in idx]


def main() -> None:
    out = {}
    for y in range(2016, 2027):
        for q in (1, 2, 3, 4):
            if (y, q) > (2026, 3):
                break
            key = f"{y}q{q}"
            try:
                raw = get(BASE.format(y=y, q=q))
            except Exception as exc:  # noqa: BLE001
                out[key] = {"error": str(exc)[:200]}
                continue
            z = zipfile.ZipFile(io.BytesIO(raw))
            doc = {}
            types = collections.Counter()
            f4_sym = 0
            f4_issuers, f4_symbols = set(), set()
            fdates = set()
            for acc, ftype, cik, sym, fdate in rows(z, "SUBMISSION.tsv", ["ACCESSION_NUMBER", "DOCUMENT_TYPE",
                                                                         "ISSUERCIK", "ISSUERTRADINGSYMBOL",
                                                                         "FILING_DATE"]):
                types[ftype] += 1
                doc[acc] = (ftype, cik)
                fdates.add(fdate)
                if ftype == "4":
                    f4_issuers.add(cik)
                    if sym.strip():
                        f4_sym += 1
                        f4_symbols.add(sym.strip().upper())
            codes = collections.Counter()
            p_accs, p_issuers = set(), set()
            for acc, code, ad in rows(z, "NONDERIV_TRANS.tsv", ["ACCESSION_NUMBER", "TRANS_CODE",
                                                               "TRANS_ACQUIRED_DISP_CD"]):
                d = doc.get(acc)
                if not d or d[0] != "4":
                    continue
                codes[code] += 1
                if code == "P" and ad == "A":
                    p_accs.add(acc)
                    p_issuers.add(d[1])
            rel = collections.Counter()
            for acc, r in rows(z, "REPORTINGOWNER.tsv", ["ACCESSION_NUMBER", "RPTOWNER_RELATIONSHIP"]):
                d = doc.get(acc)
                if d and d[0] == "4":
                    rel[r] += 1
            out[key] = {"zip_bytes": len(raw), "documents": dict(types), "form4_with_symbol": f4_sym,
                        "form4_issuers": len(f4_issuers), "form4_symbols": len(f4_symbols),
                        "filing_dates": len(fdates), "nonderiv_codes_form4": dict(codes.most_common(15)),
                        "form4_with_P_acquired": len(p_accs), "issuers_with_P": len(p_issuers),
                        "owner_relationships_top": dict(rel.most_common(8))}
            print(key, len(raw), types.get("4"), len(p_accs), flush=True)
            del raw, z
            time.sleep(1.0)
    json.dump({"source": "SEC Insider Transactions Data Sets", "fetched_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
              time.gmtime()), "quarters": out}, open(__file__.replace(".py", ".out.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
