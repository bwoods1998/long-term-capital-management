"""Metadata only: the member list (names, compressed and uncompressed sizes) of SEC Financial Statement Data Set zips,
read by HTTP range requests on the zip's central directory (no member content is read)."""
import io, json, struct, sys, time, urllib.request, zipfile
UA = "ltcm (agent@blakewoods.us)"
class RangeFile(io.RawIOBase):
    def __init__(self, url):
        self.url, self.pos, self.reqs = url, 0, 0
        r = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}, method="HEAD"), timeout=60)
        self.size = int(r.headers["Content-Length"])
    def seekable(self): return True
    def readable(self): return True
    def tell(self): return self.pos
    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else (self.pos + off if whence == 1 else self.size + off); return self.pos
    def readinto(self, b):
        n = min(len(b), self.size - self.pos)
        if n <= 0: return 0
        req = urllib.request.Request(self.url, headers={"User-Agent": UA, "Range": f"bytes={self.pos}-{self.pos+n-1}"})
        data = urllib.request.urlopen(req, timeout=60).read(); self.reqs += 1; time.sleep(0.15)
        b[:len(data)] = data; self.pos += len(data); return len(data)
out = {}
for q in sys.argv[1:]:
    f = RangeFile(f"https://www.sec.gov/files/dera/data/financial-statement-data-sets/{q}.zip")
    z = zipfile.ZipFile(io.BufferedReader(f, buffer_size=65536))
    out[q] = {"members": {i.filename: [i.compress_size, i.file_size] for i in z.infolist()}, "range_requests": f.reqs}
json.dump(out, open("fsds_members.out.json", "w"), indent=1); print(json.dumps(out))
