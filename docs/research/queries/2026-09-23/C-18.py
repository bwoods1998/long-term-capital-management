"""C-18 (box, read-only): house.json top-level keys and the daily Kalshi survey: series no desk claims, ranked by volume."""
import json,pathlib,re
p=pathlib.Path('/workspace/state/house.json')
d=json.loads(p.read_text())
print('keys:',list(d.keys())[:60])
for k,v in d.items():
    if any(w in k.lower() for w in ('survey','series','universe','discover')):
        s=json.dumps(v); print('--',k,type(v).__name__,len(v) if hasattr(v,'__len__') else '',s[:1500])
