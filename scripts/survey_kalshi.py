#!/usr/bin/env python3
"""What is trading on Kalshi that resolves within 48 hours, by series and by specialty.

The House runs this same survey once a day by itself, so the specialties of `league/niches.json`
follow the sporting calendar without an edit. Run it by hand to see what a new season brought, or
to decide whether a series deserves a place in a niche's listed universe. It reads Kalshi's public
API only: no key, no gateway, nothing written.

    python3 scripts/survey_kalshi.py            # the specialties, and what joined them by pattern
    python3 scripts/survey_kalshi.py --top 40   # and the 40 busiest series nobody claims
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from league import niches  # noqa: E402
from ltcm.data.kalshi import KalshiMarketData  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top", type=int, default=0)
    args = parser.parse_args()
    data = KalshiMarketData()
    table = niches.load()
    volumes = niches.survey(data)
    categories: dict[str, str] = {}

    def category_of(series: str) -> str:
        if series not in categories:
            raw = data._get(f"/series/{series}", what=f"kalshi series {series}")
            categories[series] = str((raw.get("series") or raw).get("category") or "")
        return categories[series]

    live = niches.apply_survey(table, volumes, category_of)
    print(f"{len(volumes)} series have markets resolving within 48 hours; {sum(volumes.values()):,.0f} contracts traded in 24 hours")
    claimed = set()
    for niche_id, rows in live.items():
        claimed.update(rows)
        joined = [s for s in rows if s not in table[niche_id].listed]
        print(f"{niche_id:24s} {len(rows):4d} live  {sum(volumes[s] for s in rows):14,.0f} contracts  joined by pattern: {', '.join(joined[:10]) or '-'}")
    if args.top:
        print("\nbusiest series no specialty claims:")
        for series in sorted((s for s in volumes if s not in claimed), key=lambda s: -volumes[s])[: args.top]:
            print(f"  {series:28s} {volumes[series]:12,.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
