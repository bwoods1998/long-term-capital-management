"""Counts only (no filing content, no price): Form 4 and 8-K records in EDGAR's daily form index for the gap between
the Insider Transactions Data Sets' last quarter (2026q3, ends Sep 30) and the lane's first session (Oct 19), plus HEAD
sizes of the S2 quarters before 2016 (the PIT ticker map's look-back) and of the FSDS quarters (point-in-time SIC)."""
import datetime as dt, json, re, time, urllib.request
UA = {"User-Agent": "ltcm (agent@blakewoods.us)"}
def get(url, method="GET"):
    req = urllib.request.Request(url, headers=UA, method=method)
    for i in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, dict(r.headers), (r.read() if method == "GET" else b"")
        except urllib.error.HTTPError as e:
            if e.code == 404: return 404, {}, b""
            time.sleep(1 + i)
    return None, {}, b""
out = {"daily": {}, "s2_heads": {}, "fsds_heads": {}}
day = dt.date(2026, 10, 1)
while day <= dt.date(2026, 10, 21):
    if day.weekday() < 5:
        st, _, body = get(f"https://www.sec.gov/Archives/edgar/daily-index/2026/QTR4/form.{day:%Y%m%d}.idx")
        if st == 200:
            n4 = n8 = 0
            for line in body.decode("latin-1").splitlines():
                m = re.match(r"^(\S+(?: \S+)?)\s{2,}", line)
                if not m: continue
                if m.group(1) == "4": n4 += 1
                elif m.group(1) == "8-K": n8 += 1
            out["daily"][day.isoformat()] = {"form4": n4, "8k": n8}
        else:
            out["daily"][day.isoformat()] = {"status": st}
        time.sleep(0.2)
    day += dt.timedelta(days=1)
for q in ("2015q1", "2015q2", "2015q3", "2015q4"):
    st, h, _ = get(f"https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/{q}_form345.zip", "HEAD")
    out["s2_heads"][q] = {"status": st, "bytes": h.get("Content-Length") or h.get("content-length")}
    time.sleep(0.2)
tot = 0; n = 0
for y in range(2015, 2027):
    for qq in range(1, 5):
        q = f"{y}q{qq}"
        if (y, qq) > (2026, 3): break
        st, h, _ = get(f"https://www.sec.gov/files/dera/data/financial-statement-data-sets/{q}.zip", "HEAD")
        b = h.get("Content-Length") or h.get("content-length")
        out["fsds_heads"][q] = {"status": st, "bytes": b}
        if b: tot += int(b); n += 1
        time.sleep(0.2)
out["fsds_total_bytes"] = tot; out["fsds_files"] = n
d = [v for v in out["daily"].values() if "form4" in v]
out["oct1_16_form4"] = sum(v["form4"] for k, v in out["daily"].items() if "form4" in v and k <= "2026-10-16")
out["oct1_16_8k"] = sum(v["8k"] for k, v in out["daily"].items() if "8k" in v and k <= "2026-10-16")
json.dump(out, open("count_gap.out.json", "w"), indent=1)
print(json.dumps({k: out[k] for k in ("oct1_16_form4", "oct1_16_8k", "fsds_total_bytes", "fsds_files")}), json.dumps(out["s2_heads"]))
