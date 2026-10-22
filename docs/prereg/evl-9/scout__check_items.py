"""check_items.py -- OUTCOME-FREE: do the bulk submissions JSON's 8-K `items` equal the filing's own .hdr.sgml <ITEMS>
lines (the codes the live getcurrent feed and the -index.htm carry)? A seeded uniform sample of 120 distinct 8-Ks
2016-2026. Reads only item codes. Output: check_items.out.json."""
import json, random, re, time, urllib.request, zipfile
UA = "ltcm (agent@blakewoods.us)"
z = zipfile.ZipFile("submissions.zip"); rng = random.Random(99)
names = [n for n in z.namelist() if n.endswith(".json") and "-submissions-" not in n]
rows = []; tries = 0
while len(rows) < 120 and tries < 20000:
    tries += 1
    d = json.loads(z.read(rng.choice(names))); rec = d.get("filings", {}).get("recent", {})
    c = [i for i, f in enumerate(rec.get("form", [])) if f == "8-K" and "2016" <= rec["filingDate"][i][:4] <= "2026"]
    if not c: continue
    i = rng.choice(c); acc = rec["accessionNumber"][i]
    time.sleep(0.25)
    try:
        body = urllib.request.urlopen(urllib.request.Request(f"https://www.sec.gov/Archives/edgar/data/{int(d['cik'])}/{acc.replace('-', '')}/{acc}.hdr.sgml", headers={"User-Agent": UA}), timeout=45).read().decode("latin-1")
    except Exception as exc:
        rows.append({"acc": acc, "error": str(exc)[:80]}); continue
    hdr = sorted(set(re.findall(r"<ITEMS>([0-9.]+)", body))); js = sorted(set(x.strip() for x in rec["items"][i].split(",") if x.strip()))
    rows.append({"acc": acc, "year": rec["filingDate"][i][:4], "json": js, "hdr": hdr, "equal": js == hdr})
ok = [r for r in rows if "equal" in r]
print("n", len(rows), "compared", len(ok), "equal", sum(r["equal"] for r in ok))
for r in ok:
    if not r["equal"]: print(r)
json.dump(rows, open("check_items.out.json", "w"), indent=1)
