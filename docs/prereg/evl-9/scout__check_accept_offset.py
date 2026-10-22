"""check_accept_offset.py -- OUTCOME-FREE: the offset between the bulk submissions JSON's acceptanceDateTime and the
filing's own .hdr.sgml <ACCEPTANCE-DATETIME> (Eastern wall time), on a seeded random sample of 8-K and Form 4 filings
across 2016-2026 and across filers. Reads only timestamps. Output: check_accept_offset.out.json."""
import collections, datetime as dt, json, random, re, time, urllib.request, zipfile
from zoneinfo import ZoneInfo
UA = "ltcm (agent@blakewoods.us)"; NY = ZoneInfo("America/New_York")
rng = random.Random(20261022)
z = zipfile.ZipFile("submissions.zip")
names = [n for n in z.namelist() if n.endswith(".json") and "-submissions-" not in n]
picks = collections.defaultdict(list)
while sum(len(v) for v in picks.values()) < 88:
    d = json.loads(z.read(rng.choice(names)))
    rec = d.get("filings", {}).get("recent", {})
    cand = [i for i, f in enumerate(rec.get("form", [])) if f in ("8-K", "4") and "2016" <= rec["filingDate"][i][:4] <= "2026"]
    if not cand:
        continue
    i = rng.choice(cand)
    key = (rec["form"][i], rec["filingDate"][i][:4])
    if len(picks[key]) >= 4:
        continue
    picks[key].append((d["cik"], rec["accessionNumber"][i], rec["acceptanceDateTime"][i], rec["filingDate"][i]))
rows = []
for key, lst in sorted(picks.items()):
    for cik, acc, js, fdate in lst:
        url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{acc}.hdr.sgml"
        try:
            body = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30).read().decode("latin-1")
            m = re.search(r"<ACCEPTANCE-DATETIME>(\d{14})", body)
            wall = dt.datetime.strptime(m.group(1), "%Y%m%d%H%M%S").replace(tzinfo=NY)
            jt = dt.datetime.fromisoformat(js.replace("Z", "+00:00"))
            rows.append({"form": key[0], "year": key[1], "fdate": fdate, "hdr_et": m.group(1), "json": js,
                         "json_minus_true_utc_h": round((jt - wall.astimezone(dt.timezone.utc)).total_seconds() / 3600, 3),
                         "json_minus_et_wall_h": round((jt.replace(tzinfo=None) - wall.replace(tzinfo=None)).total_seconds() / 3600, 3)})
        except Exception as exc:  # noqa: BLE001
            rows.append({"form": key[0], "year": key[1], "acc": acc, "error": str(exc)[:120]})
        time.sleep(0.25)
by = collections.Counter((r["year"], r.get("json_minus_true_utc_h")) for r in rows)
summary = collections.Counter(r.get("json_minus_true_utc_h") for r in rows)
json.dump({"n": len(rows), "offset_hours_vs_true_utc": {str(k): v for k, v in summary.items()},
           "by_year": {f"{k[0]}:{k[1]}": v for k, v in sorted(by.items(), key=str)}, "rows": rows},
          open("check_accept_offset.out.json", "w"), indent=1)
print(dict(summary)); print(sorted(by.items(), key=str))
