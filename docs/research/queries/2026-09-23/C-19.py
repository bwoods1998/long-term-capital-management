"""C-19 (box, read-only): full surveyed series_category and niche_live from house.json."""
import json,pathlib
d=json.loads(pathlib.Path('/workspace/state/house.json').read_text())
print(json.dumps({'series_category':d.get('series_category'),'niche_live':d.get('niche_live'),'last_niche_survey':d.get('last_niche_survey')}))
