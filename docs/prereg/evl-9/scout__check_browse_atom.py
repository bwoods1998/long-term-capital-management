"""check_browse_atom.py -- OUTCOME-FREE: does EDGAR's company browse Atom feed (www.sec.gov/cgi-bin/browse-edgar
?action=getcompany, the route ltcm/data/edgar.py documents) carry each filing's true acceptance time in <updated>?
A seeded sample of 8-K and Form 4 filings 2016-2026: the bulk JSON's acceptanceDateTime, the .hdr.sgml
<ACCEPTANCE-DATETIME> (Eastern), and the Atom <updated> (with offset), for the filing's CIK (an 8-K under its filer, a
Form 4 under the CIK file it was found in). Reads only timestamps. Output: check_browse_atom.out.json."""
import datetime as dt, json, random, re, time, urllib.request, zipfile
from zoneinfo import ZoneInfo
UA = "ltcm (agent@blakewoods.us)"; NY = ZoneInfo("America/New_York")
rng = random.Random(7)
z = zipfile.ZipFile("submissions.zip")
names = [n for n in z.namelist() if n.endswith(".json") and "-submissions-" not in n]
def get(u):
    time.sleep(0.25)
    return urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=45).read().decode("latin-1")
rows = []
while len(rows) < 24:
    d = json.loads(z.read(rng.choice(names)))
    rec = d.get("filings", {}).get("recent", {})
    cand = [i for i, f in enumerate(rec.get("form", [])) if f in ("8-K", "4") and "2016" <= rec["filingDate"][i][:4] <= "2026"]
    if not cand:
        continue
    i = rng.choice(cand)
    cik, acc, js, form, fdate = d["cik"], rec["accessionNumber"][i], rec["acceptanceDateTime"][i], rec["form"][i], rec["filingDate"][i]
    try:
        hdr = re.search(r"<ACCEPTANCE-DATETIME>(\d{14})", get(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{acc}.hdr.sgml")).group(1)
        dateb = (dt.date.fromisoformat(fdate) + dt.timedelta(days=1)).strftime("%Y%m%d")
        atom = get(f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type={form}&dateb={dateb}&owner=include&count=40&output=atom")
        upd = None
        for e in atom.split("<entry>")[1:]:
            if acc in e:
                m = re.search(r"<updated>(.*?)</updated>", e); upd = m.group(1) if m else None; break
        wall = dt.datetime.strptime(hdr, "%Y%m%d%H%M%S").replace(tzinfo=NY)
        jt = dt.datetime.fromisoformat(js.replace("Z", "+00:00"))
        ut = dt.datetime.fromisoformat(upd) if upd else None
        rows.append({"form": form, "fdate": fdate, "hdr_et": hdr, "json": js, "atom_updated": upd,
                     "json_minus_true_h": round((jt - wall).total_seconds() / 3600, 2),
                     "atom_minus_true_s": (ut - wall).total_seconds() if ut else None})
    except Exception as exc:  # noqa: BLE001
        rows.append({"form": form, "fdate": fdate, "error": str(exc)[:120]})
ok = [r for r in rows if r.get("atom_minus_true_s") is not None]
print("rows", len(rows), "atom found", len(ok), "atom exact", sum(1 for r in ok if r["atom_minus_true_s"] == 0))
print("json offsets", sorted({r.get("json_minus_true_h") for r in rows if "json_minus_true_h" in r}))
for r in rows: print(r)
json.dump(rows, open("check_browse_atom.out.json", "w"), indent=1)
