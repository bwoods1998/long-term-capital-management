"""sample_accept_times.py -- OUTCOME-FREE timing facts for historical 8-K and Form 4 events, from the TRUE acceptance
time (the filing's .hdr.sgml <ACCEPTANCE-DATETIME>, Eastern), on a seeded uniform sample of DISTINCT filings
2016-01-01..2026-10-21 listed in the bulk submissions archive; plus the request budget of the Atom route
(browse-edgar getcompany, 100 filings a page) for 8-Ks. Reads only timestamps, form types and counts.
Output: sample_accept_times.out.json."""
import collections, datetime as dt, json, multiprocessing as mp, random, re, time, urllib.request, zipfile
from zoneinfo import ZoneInfo
import numpy as np
UA = "ltcm (agent@blakewoods.us)"; NY = ZoneInfo("America/New_York")
ZIP = "submissions.zip"; N = 400

def work(names):
    z = zipfile.ZipFile(ZIP)
    k8, f4 = [], []
    per_filer_8k = collections.Counter()
    for name in names:
        d = json.loads(z.read(name))
        rec = d["filings"]["recent"] if "filings" in d else d
        cik = int(name[3:13])
        for i, f in enumerate(rec.get("form") or []):
            fd = rec["filingDate"][i]
            if not ("2016-01-01" <= fd <= "2026-10-21"):
                continue
            if f == "8-K":
                k8.append((int(rec["accessionNumber"][i].replace("-", "")), cik)); per_filer_8k[cik] += 1
            elif f == "4":
                f4.append((int(rec["accessionNumber"][i].replace("-", "")), cik))
    return np.array(k8, dtype=np.int64).reshape(-1, 2), np.array(f4, dtype=np.int64).reshape(-1, 2), per_filer_8k

def bucket(et):
    if et.weekday() >= 5: return "weekend"
    hm = et.hour * 60 + et.minute
    return ("pre_0915" if hm < 555 else "0915_0930" if hm < 570 else "rth_to_1546" if hm < 946 else
            "1546_1600" if hm < 960 else "1600_1730" if hm < 1050 else "1730_2200" if hm < 1320 else "after_2200")

def main():
    names = [n for n in zipfile.ZipFile(ZIP).namelist() if n.endswith(".json")]
    with mp.Pool(4) as p:
        parts = p.map(work, [names[i::4] for i in range(4)])
    out = {}
    pages = 0; filers = collections.Counter()
    for _, _, c in parts: filers.update(c)
    pages = sum(-(-n // 100) for n in filers.values())
    out["atom_8k"] = {"filers_with_8k": len(filers), "pages_at_100": pages}
    rng = random.Random(20261022)
    for label, idx in (("8-K", 0), ("4", 1)):
        arr = np.concatenate([p[idx] for p in parts])
        _, first = np.unique(arr[:, 0], return_index=True)
        uniq = arr[np.sort(first)]
        out[label] = {"distinct_filings": int(len(uniq))}
        pick = [uniq[i] for i in rng.sample(range(len(uniq)), N)]
        b = collections.Counter(); date_shift = 0; errors = 0; per_year = collections.Counter()
        for acc, cik in pick:
            a = f"{acc:018d}"; a = f"{a[:10]}-{a[10:12]}-{a[12:]}"
            try:
                time.sleep(0.2)
                body = urllib.request.urlopen(urllib.request.Request(
                    f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc:018d}/{a}.hdr.sgml", headers={"User-Agent": UA}),
                    timeout=45).read().decode("latin-1")
                acc_t = re.search(r"<ACCEPTANCE-DATETIME>(\d{14})", body).group(1)
                fdate = re.search(r"<FILING-DATE>(\d{8})", body).group(1)
                et = dt.datetime.strptime(acc_t, "%Y%m%d%H%M%S")
                b[bucket(et)] += 1; per_year[acc_t[:4]] += 1
                if et.strftime("%Y%m%d") != fdate: date_shift += 1
            except Exception:  # noqa: BLE001
                errors += 1
        out[label].update({"sample": N, "errors": errors, "buckets_ET": dict(b),
                           "acceptance_date_differs_from_filing_date": date_shift, "sample_years": dict(sorted(per_year.items()))})
        print(label, out[label], flush=True)
    print(out["atom_8k"])
    json.dump(out, open("sample_accept_times.out.json", "w"), indent=1)

if __name__ == "__main__":
    main()
