"""Verdicts: PREREG-EVL-1 section 4, verbatim.

Model `claude-haiku-4-5-20251001` through the gateway's `/v1/claude/messages`, temperature 0, max_tokens 300, no
thinking, no tools. Each verdict is stored once (event, prompt SHA-256, model) with the request id, the answer, the
times and the gateway's settled cost; replay reads the stored verdict and never asks again. An answer that is not valid
JSON with an integer `score` in -3..3 is `unparsed` and trades nothing. A failed call is retried at most 3 times.

The two prompts below are PREREG-EVL-1's text exactly (a test reads the prereg file and compares). Their SHA-256
(`PROMPTS[...].sha`) names the prompt version in every stored verdict.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
import re
from typing import Any, Mapping

from . import calendar as C
from . import store as S

MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 300
TEMPERATURE = 0
ATTEMPTS = 3
PATH = "/v1/claude/messages"
REQUEST_HEADER = "X-LTCM-Request"
COST_HEADER = "x-ltcm-cost-usd"

SYSTEM_DOC = ("You are an equity analyst reading a company's SEC filing the moment it is published. You see no market "
              "prices. Judge only from the text.")
SYSTEM_NEWS = ("You are an equity analyst reading a news headline the moment it is published. You see no market prices. "
               "Judge only from the text.")

USER_DOC = """Company: {name} (ticker {ticker}). SEC Form 8-K, items {items}, accepted {acceptance_et} ET.
Document (its first 16,000 characters):
<document>
{text}
</document>
Relative to what investors most likely expected before this filing, is this news likely to make the stock
outperform or underperform the overall stock market over the next trading day? Answer with JSON only:
{{"score": an integer from -3 (strongly underperform) to 3 (strongly outperform), 0 if neutral or unclear,
 "guidance": one of "raised", "maintained", "lowered", "none", "unclear",
 "reasons": up to three short strings}}"""

USER_NEWS = """Stock: {symbol}. Published {created_et} ET by {source}.
Headline: {headline}
Summary: {summary}
Relative to what investors most likely expected before this news, is it likely to make the stock outperform or
underperform the overall stock market over the next trading day? Answer with JSON only:
{{"score": an integer from -3 (strongly underperform) to 3 (strongly outperform), 0 if neutral or unclear,
 "reasons": up to three short strings}}"""


@dataclasses.dataclass(frozen=True)
class Prompt:
    name: str
    system: str
    user: str

    @property
    def sha(self) -> str:
        spec = {"model": MODEL, "temperature": TEMPERATURE, "max_tokens": MAX_TOKENS, "system": self.system,
                "user": self.user}
        return hashlib.sha256(json.dumps(spec, sort_keys=True).encode("utf-8")).hexdigest()


PROMPTS = {"doc": Prompt("doc", SYSTEM_DOC, USER_DOC), "news": Prompt("news", SYSTEM_NEWS, USER_NEWS)}
GUIDANCE = ("raised", "maintained", "lowered", "none", "unclear")


def et_minute(moment: dt.datetime) -> str:
    return moment.astimezone(C.NY).strftime("%Y-%m-%d %H:%M")


def render_doc(*, name: str, ticker: str, items: list[str], accepted_at: dt.datetime, text: str) -> str:
    return USER_DOC.format(name=name, ticker=ticker, items=", ".join(items), acceptance_et=et_minute(accepted_at),
                           text=text)


def render_news(*, symbol: str, created_at: dt.datetime, source: str, headline: str, summary: str) -> str:
    return USER_NEWS.format(symbol=symbol, created_et=et_minute(created_at), source=source, headline=headline,
                            summary=summary)


def parse_answer(text: str, *, kind: str) -> tuple[str, int | None, str | None]:
    """(status, score, guidance): 'ok' with an integer score in -3..3, else 'unparsed' (trades nothing)."""
    body = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", body, re.S)
    if fence:
        body = fence.group(1)
    try:
        data = json.loads(body)
    except ValueError:
        return "unparsed", None, None
    if not isinstance(data, dict):
        return "unparsed", None, None
    score = data.get("score")
    if type(score) is not int or not -3 <= score <= 3:
        return "unparsed", None, None
    guidance = data.get("guidance") if kind == "doc" else None
    if kind == "doc" and guidance not in GUIDANCE:
        guidance = None
    return "ok", score, guidance


def stored(store: S.Store, event: str, prompt: Prompt) -> Mapping[str, Any] | None:
    row = store.db.execute("SELECT * FROM verdicts WHERE event=? AND prompt_sha=? AND model=?",
                           (event, prompt.sha, MODEL)).fetchone()
    return None if row is None else dict(row)


def ask(store: S.Store, gw: Any, event: str, prompt: Prompt, user_text: str, *,
        now: Any = None) -> Mapping[str, Any]:
    """The stored verdict for (event, prompt, model), asking the gateway once if there is none. `now()` -> UTC."""
    have = stored(store, event, prompt)
    if have is not None and have["status"] in ("ok", "unparsed", "refused"):
        return have
    clock = now or S.utc_now
    request_id = f"evl:{event}:{prompt.sha[:12]}"[:160]
    body = {"model": MODEL, "max_tokens": MAX_TOKENS, "temperature": TEMPERATURE, "system": prompt.system,
            "messages": [{"role": "user", "content": user_text}]}
    asked_at = clock()
    status, score, guidance, answer, usd = "failed", None, None, None, None
    for _ in range(ATTEMPTS):
        code, payload = gw.post_json(PATH, body, headers={REQUEST_HEADER: request_id})
        try:
            usd = float(gw.last_headers.get(COST_HEADER)) if gw.last_headers.get(COST_HEADER) else usd
        except ValueError:
            pass
        if 200 <= code < 300 and isinstance(payload, dict):
            text = "".join(b.get("text") or "" for b in payload.get("content") or []
                           if isinstance(b, dict) and b.get("type") == "text")
            answer = text
            if payload.get("stop_reason") == "refusal":
                status = "refused"
            else:
                status, score, guidance = parse_answer(text, kind=prompt.name)
            break
        answer = json.dumps(payload)[:2000] if payload is not None else None
        if code in (400, 401, 403, 404):  # not a transient failure: retrying asks the same refusal again
            status = f"error:{code}"
            break
    with store.tx() as db:
        db.execute("INSERT INTO verdicts(event, prompt_sha, model, request_id, asked_at, answered_at, status, score, "
                   "guidance, answer, usd) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(event, prompt_sha, model) "
                   "DO UPDATE SET request_id=excluded.request_id, asked_at=excluded.asked_at, answered_at=excluded."
                   "answered_at, status=excluded.status, score=excluded.score, guidance=excluded.guidance, answer="
                   "excluded.answer, usd=COALESCE(verdicts.usd, 0) + COALESCE(excluded.usd, 0)",
                   (event, prompt.sha, MODEL, request_id, S.iso(asked_at), S.iso(clock()), status, score, guidance, answer,
                    usd))
    return stored(store, event, prompt)


__all__ = ["MODEL", "PROMPTS", "Prompt", "render_doc", "render_news", "parse_answer", "ask", "stored", "SYSTEM_DOC",
           "SYSTEM_NEWS", "USER_DOC", "USER_NEWS"]
