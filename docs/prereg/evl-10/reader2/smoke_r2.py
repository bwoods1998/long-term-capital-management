"""smoke_r2.py: READER-2's structured-output smoke test, at most $0.01, BEFORE PREREG-EVL-10 is frozen (design-reader2).

Two streamed Claude Sonnet 5.5 calls through the House's gateway route /v1/claude/messages with R2's frozen request
shape (r2_spec.body: effort "low", adaptive thinking with display omitted, output_config.format json_schema, no
temperature), each on a PINNED SYNTHETIC text that names no real company, ticker or event, so no READER-2 read of any
event exists before registration. It measures what the frozen file needs and the design assumed:
  S1 the gateway admits the body (lib/claude.mjs admit: output_config {effort, format}, thinking adaptive + display,
     stream) and Anthropic accepts both schemas (integer enums, anyOf number|null, additionalProperties false);
  S2 the answer is ONE text block that r2_spec.parse reads 'ok' (stop_reason end_turn, never max_tokens);
  S3 the gateway's ltcm.cost event arrives (the stored cost), and usage's input/output tokens (thinking included);
  S4 the latency and the gap between stream events fit GAP_S / LIMIT_S.
THE $0.01 RULE: call 1 (DOC schema, max_tokens 400) worst case $0.0078 (cost_r2.out smoke_test); call 2 (NEWS schema,
max_tokens 300, worst $0.0060) is made ONLY IF call 1's stated cost plus call 2's worst case is <= $0.0100; otherwise
call 2 is not made, and the NEWS schema is tested by a second smoke (again at most $0.01) after 00:00 UTC; the file
is frozen only once both schemas have passed (or R2-J is pinned for the one that failed).
The smoke texts use max_tokens 400 / 300, below R2's frozen 1,600 / 1,200: a 'max_tokens' stop here is a FINDING
(thinking at effort low is longer than assumed), recorded, and does not fail S1.
OUTCOMES: PASS (S1-S3 hold for both): the frozen file names R2 as specified. FAIL S1 for output_config.format: R2-J
(the same texts plus "Answer with one JSON object with exactly these keys and no other text." and no format), pinned
by the registering amendment BEFORE THE FREEZE; the file is then frozen with R2-J's shas.
Usage: smoke_r2.py            (dry run: prints both bodies' shas, bytes and worst cases; no network)
       smoke_r2.py --send     (THE CAPTAIN, on the House box or with its gateway token; never a designer)
"""
from __future__ import annotations

import hashlib
import json
import sys
import time

import r2_spec as R

SMOKE_DOC = {"name": "Exemplar Widgets Inc. (a synthetic test company)", "ticker": "ZZXQ", "items": ["8.01", "9.01"],
             "acceptance_et": "2026-10-22 07:01",
             "text": ("Exemplar Widgets Inc. announced a multi-year supply agreement with a national retailer valued at "
                      "about $60 million and raised its full-year revenue outlook to $470-480 million from $455-465 "
                      "million. This is a synthetic test document; no such company exists."),
             "prior_news": ["2026-10-01 08:00 ET | synthetic | Exemplar Widgets to present at an industry conference"]}
SMOKE_NEWS = {"symbol": "ZZXQ", "name": "Exemplar Widgets Inc. (a synthetic test company)", "created_et": "2026-10-22 07:05",
              "source": "synthetic", "headline": "Exemplar Widgets Q3 EPS $0.42 Beats $0.38 Estimate, Raises FY Outlook",
              "summary": "A synthetic test item: no such company exists.",
              "prior_news": ["2026-10-01 08:00 ET | synthetic | Exemplar Widgets to report results on October 22"],
              "prior_filings": []}
SMOKE_MAX = {"doc": 400, "news": 300}
WORST = {"doc": 0.0078, "news": 0.0060}      # cost_r2.out smoke_test (pessimistic token counts)
CAP_USD = 0.0100


def bodies() -> dict:
    out = {}
    doc = R.render_doc(**SMOKE_DOC)
    news = R.render_news(**SMOKE_NEWS)
    for kind, text in (("doc", doc), ("news", news)):
        b = R.body(kind, text)
        b["max_tokens"] = SMOKE_MAX[kind]
        out[kind] = b
    return out


def dry() -> None:
    for kind, b in bodies().items():
        raw = json.dumps(b).encode()
        print(kind, "spec sha", R.sha(kind), "| body bytes", len(raw), "| body sha", hashlib.sha256(raw).hexdigest()[:16],
              "| max_tokens", b["max_tokens"], "| worst $%.4f" % WORST[kind])
    print("cap $%.4f; call 2 only if call 1's stated cost + $%.4f <= cap" % (CAP_USD, WORST["news"]))


def send() -> int:
    sys.path.insert(0, "/home/bwoods1998/Work/long-term-capital-management")
    from league.events import gw as G     # the House's own gateway client (token from its env file)

    gw = G.Gateway(G.token_from_env())
    spent = 0.0
    report = {}
    for kind in ("doc", "news"):
        if kind == "news" and spent + WORST["news"] > CAP_USD:
            report["news"] = {"skipped": f"spent ${spent:.4f}: call 2's worst case would pass ${CAP_USD}"}
            break
        b = bodies()[kind]
        t0 = time.time()
        try:
            code, payload = gw.post_stream("/v1/claude/messages", b, headers={"X-LTCM-Request": f"r2smoke:{kind}"},
                                           limit=R.LIMIT_S, gap=R.GAP_S)
        except Exception as exc:  # noqa: BLE001
            report[kind] = {"error": f"{type(exc).__name__}: {exc}"}
            break
        usd = gw.last_headers.get("X-LTCM-Cost-USD") or gw.last_headers.get("x-ltcm-cost-usd")
        spent += float(usd) if usd else WORST[kind]
        text = "".join(x.get("text") or "" for x in (payload or {}).get("content") or [] if x.get("type") == "text")
        status, fields = R.parse(text, kind)
        report[kind] = {"http": code, "seconds": round(time.time() - t0, 1), "stop": (payload or {}).get("stop_reason"),
                        "usage": (payload or {}).get("usage"), "usd": usd, "parse": status, "fields": fields,
                        "error": None if 200 <= code < 300 else payload}
    report["spent_usd"] = round(spent, 5)
    print(json.dumps(report, indent=1))
    ok = all(isinstance(report.get(k), dict) and report[k].get("parse") == "ok" for k in ("doc", "news"))
    return 0 if ok else 1


if __name__ == "__main__":
    if "--send" in sys.argv:
        raise SystemExit(send())
    dry()
