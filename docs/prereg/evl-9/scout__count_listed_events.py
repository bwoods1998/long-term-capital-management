"""count_listed_events.py -- OUTCOME-FREE: how many historical 8-K and Form 4 events belong to LISTED-LOOKING issuers
(an issuer CIK whose insiders' Form 4s name an ISSUERTRADINGSYMBOL in the same year: the point-in-time proxy for "has a
ticker", before the lane's price, ADV, exchange and operating tests, which need bars), per year 2016-2026; the Form 4
Atom page budget per issuer (browse-edgar getcompany type=4 owner=only, 100 a page); and the Form 4 open-market
purchase filings (code P, acquired). Sources: SEC Insider Transactions Data Sets (2016q1..2026q3; 2026q2/q3 under
/files/datastandardsinnovation/...) and the bulk submissions archive (8-K filer CIKs). No price/share/value column is
parsed. Output: count_listed_events.out.json."""
import collections, csv, io, json, multiprocessing as mp, time, urllib.request, zipfile
UA = "ltcm (agent@blakewoods.us)"
csv.field_size_limit(10 ** 9)
def url(y, q):
    base = "datastandardsinnovation" if (y, q) >= (2026, 2) else "structureddata"
    return f"https://www.sec.gov/files/{base}/data/insider-transactions-data-sets/{y}q{q}_form345.zip"
def get(u):
    time.sleep(1.0)
    for w in (2, 4, None):
        try:
            return urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=300).read()
        except Exception:
            if w is None: raise
            time.sleep(w)
def tsv(z, name, cols):
    with z.open(name) as fh:
        rd = csv.reader(io.TextIOWrapper(fh, encoding="utf-8", errors="replace", newline=""), delimiter="\t", quoting=csv.QUOTE_NONE)
        head = next(rd); idx = [head.index(c) for c in cols]
        for r in rd:
            if len(r) >= len(head):
                yield [r[i] for i in idx]
def k8_work(names):
    z = zipfile.ZipFile("submissions.zip"); out = []
    for n in names:
        d = json.loads(z.read(n)); rec = d["filings"]["recent"] if "filings" in d else d; cik = n[3:13]
        for i, f in enumerate(rec.get("form") or []):
            fd = rec["filingDate"][i]
            if f == "8-K" and "2016-01-01" <= fd <= "2026-10-21":
                out.append((rec["accessionNumber"][i], cik, int(fd[:4])))
    return out
def main():
    issuers_by_year = collections.defaultdict(set); f4_per_issuer = collections.Counter(); f4_year = collections.Counter()
    f4_listed_year = collections.Counter(); p_year = collections.Counter(); syms_year = collections.defaultdict(set)
    for y in range(2016, 2027):
        for q in (1, 2, 3, 4):
            if (y, q) > (2026, 3): break
            z = zipfile.ZipFile(io.BytesIO(get(url(y, q))))
            doc = {}
            for acc, t, cik, sym, fd in tsv(z, "SUBMISSION.tsv", ["ACCESSION_NUMBER", "DOCUMENT_TYPE", "ISSUERCIK", "ISSUERTRADINGSYMBOL", "FILING_DATE"]):
                if t != "4": continue
                cik = cik.strip().zfill(10); s = sym.strip().upper(); fy = int(fd[-4:]) if "-" in fd and len(fd.split("-")[-1]) == 4 else int(fd[:4])
                doc[acc] = cik; f4_per_issuer[cik] += 1; f4_year[y] += 1
                if s and s not in ("NONE", "N/A", "NA"):
                    issuers_by_year[y].add(cik); syms_year[y].add(s); f4_listed_year[y] += 1
            pacc = set()
            for acc, code, ad in tsv(z, "NONDERIV_TRANS.tsv", ["ACCESSION_NUMBER", "TRANS_CODE", "TRANS_ACQUIRED_DISP_CD"]):
                if acc in doc and code == "P" and ad == "A": pacc.add(acc)
            p_year[y] += len(pacc)
            print(y, q, len(doc), flush=True)
    names = [n for n in zipfile.ZipFile("submissions.zip").namelist() if n.endswith(".json")]
    with mp.Pool(4) as p:
        rows = [r for part in p.map(k8_work, [names[i::4] for i in range(4)]) for r in part]
    seen = {}; k8_year = collections.Counter(); k8_listed = collections.Counter()
    for acc, cik, y in rows:
        listed = cik in issuers_by_year[y]
        if acc in seen:
            if listed and not seen[acc][1]:
                k8_listed[y] += 1; seen[acc] = (y, True)
            continue
        seen[acc] = (y, listed); k8_year[y] += 1
        if listed: k8_listed[y] += 1
    out = {"by_year": {y: {"8k": k8_year[y], "8k_listed_issuer": k8_listed[y], "f4": f4_year[y], "f4_with_symbol": f4_listed_year[y],
                           "f4_P_purchase_filings": p_year[y], "issuers_with_symbol": len(issuers_by_year[y]), "symbols": len(syms_year[y])}
                       for y in range(2016, 2027)},
           "form4_issuers_total": len(f4_per_issuer), "form4_atom_pages_owner_only": sum(-(-n // 100) for n in f4_per_issuer.values()),
           "distinct_symbols_2016_2026": len(set().union(*syms_year.values()))}
    json.dump(out, open("count_listed_events.out.json", "w"), indent=1); print(json.dumps(out, indent=1))
if __name__ == "__main__":
    main()
