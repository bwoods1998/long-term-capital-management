#!/usr/bin/env python
"""form4map_w9.py: COUNTS ONLY (the captain's W8; check 2's major 7). How often S2's RPTOWNER_RELATIONSHIP strings make
the two readings of "a director or officer" differ: the SUBSTRING rule this file pins (is_director = 'Director' in the
string, is_officer = 'Officer' in it) against a COMMA-SPLIT exact-token rule. Read from the scout's own counts
(evl9/scout/count_form345.out.json, owner_relationships_top per quarter: the most frequent strings only, so the figures
are a lower bound on the strings that differ). No filing is fetched; no price, share or value is read.
Usage: form4map_w9.py   (writes form4map_w9.out.json)
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(HERE), "scout", "count_form345.out.json")


def sub(s, k):
    return k in s


def split(s, k):
    return k in [t.strip() for t in s.split(",")]


def main():
    d = json.load(open(SRC))
    out = {"source": SRC, "quarters": {}}
    tot = dict(rows=0, dir_differ=0, off_differ=0, either_differ=0, insider_sub=0, insider_split=0)
    strings = set()
    for q, v in sorted(d["quarters"].items()):
        top = v.get("owner_relationships_top") or {}
        r = dict(rows=0, dir_differ=0, off_differ=0, either_differ=0, insider_sub=0, insider_split=0)
        for s, n in top.items():
            strings.add(s)
            r["rows"] += n
            dd = sub(s, "Director") != split(s, "Director")
            od = sub(s, "Officer") != split(s, "Officer")
            r["dir_differ"] += n * dd
            r["off_differ"] += n * od
            ins_sub = sub(s, "Director") or sub(s, "Officer")
            ins_split = split(s, "Director") or split(s, "Officer")
            r["insider_sub"] += n * ins_sub
            r["insider_split"] += n * ins_split
            r["either_differ"] += n * (ins_sub != ins_split)
        out["quarters"][q] = r
        for k in tot:
            tot[k] += r[k]
    tot["either_differ_share"] = round(tot["either_differ"] / max(tot["rows"], 1), 5)
    out["total_top_strings"] = tot
    out["strings_that_differ"] = sorted(s for s in strings if (sub(s, "Director") or sub(s, "Officer"))
                                        != (split(s, "Director") or split(s, "Officer")))
    out["n_strings"] = len(strings)
    print(json.dumps({k: out[k] for k in ("total_top_strings", "strings_that_differ", "n_strings")}, indent=1))
    json.dump(out, open(os.path.join(HERE, "form4map_w9.out.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
