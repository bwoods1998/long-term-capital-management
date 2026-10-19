"""EDGAR filings for the event lane: the current-filings poller, the daily-index backfill, each filing's index page,
the document PREREG-EVL-1 reads, and Form 4 transactions.

Endpoints (www.sec.gov only: the House box's allowlist carries it, data.sec.gov it does not):
- `cgi-bin/browse-edgar?action=getcurrent&type=<8-K|4>&company=&dateb=&owner=include&start=<n>&count=100&output=atom`:
  the market-wide feed of the latest filings, newest first. An entry's title is `<form> - <name> (<CIK>) (<role>)`,
  its `<updated>` the acceptance time with its offset, its summary `Filed: ... AccNo: <accession> Size: ...` and, for an
  8-K, one `Item x.xx: ...` line per item; its link the filing's `-index.htm`. A Form 4 appears twice (Issuer and
  Reporting); the accession is the key.
- `Archives/edgar/daily-index/<YYYY>/QTR<q>/form.<YYYYMMDD>.idx`: every filing of a day (form, company, CIK, date,
  path), published after the day; the backfill's list.
- `Archives/edgar/data/<cik>/<accession digits>/<accession>-index.htm`: "Accepted" (Eastern wall time), "Items", and
  the documents table (Seq, Description, Document, Type, Size, link).

Rules from PREREG-EVL-1 section 3: form type exactly `8-K` or `4`; TEXT = the lowest-numbered `EX-99.*` exhibit, else
the primary 8-K document, HTML to text by `ltcm.data.strip_html`, whitespace collapsed, first 16,000 characters.
KNOWABLE = acceptance + 10 minutes. The SEC asks for a declared User-Agent with a contact (`ltcm.data
CONTACT_USER_AGENT`) and at most ten requests a second (`ltcm.data.edgar.MIN_INTERVAL`).
"""

from __future__ import annotations

import datetime as dt
import html
import json
import re
import xml.etree.ElementTree as ET
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

from . import store as S

SEC = "https://www.sec.gov"
NY = ZoneInfo("America/New_York")
FORMS = ("8-K", "4")
TEXT_CHARS = 16000
KNOWABLE_LAG = dt.timedelta(minutes=10)
CURRENT_PAGE = 100
MAX_CURRENT_PAGES = 40

_TITLE = re.compile(r"^\s*(?P<form>[^ ]+(?: [^ ]+)?) - (?P<name>.*) \((?P<cik>\d{1,10})\) \((?P<role>[A-Za-z ]+)\)\s*$")
_ACCESSION = re.compile(r"\b(\d{10}-\d{2}-\d{6})\b")
_ITEM = re.compile(r"Item\s+(\d{1,2}\.\d{2})")
_INFO = r'<div class="infoHead">{label}</div>\s*<div class="info">(.*?)</div>'


class EdgarError(Exception):
    """A filing the recorder could not read as PREREG-EVL-1 needs it (recorded as the filing's `failed:` status)."""


def pad(cik: Any) -> str:
    raw = str(cik).strip()
    if not raw.isdigit():
        raise EdgarError(f"not a CIK: {cik!r}")
    return raw.zfill(10)


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def eastern_to_utc(wall: str) -> dt.datetime:
    """'2026-10-16 17:30:16' (EDGAR's Eastern wall time) -> aware UTC."""
    naive = dt.datetime.strptime(wall.strip(), "%Y-%m-%d %H:%M:%S")
    return naive.replace(tzinfo=NY).astimezone(dt.timezone.utc)


def knowable(accepted: dt.datetime) -> dt.datetime:
    return accepted + KNOWABLE_LAG


def accession_path(cik: str, accession: str) -> str:
    return f"{SEC}/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}"


def index_url(cik: str, accession: str) -> str:
    return f"{accession_path(cik, accession)}/{accession}-index.htm"


# ---------------------------------------------------------------------------------------------------- current feed
def current_url(form: str, start: int = 0, count: int = CURRENT_PAGE) -> str:
    return (f"{SEC}/cgi-bin/browse-edgar?action=getcurrent&type={form}&company=&dateb=&owner=include"
            f"&start={int(start)}&count={int(count)}&output=atom")


def parse_current(body: bytes | str) -> list[dict[str, Any]]:
    """The entries of one getcurrent Atom page, in feed order (newest first). Unparseable entries are skipped."""
    text = body.decode("utf-8", "replace") if isinstance(body, bytes) else body
    out: list[dict[str, Any]] = []
    for raw in text.split("<entry>")[1:]:
        title = re.search(r"<title>(.*?)</title>", raw, re.S)
        updated = re.search(r"<updated>(.*?)</updated>", raw)
        summary = re.search(r"<summary[^>]*>(.*?)</summary>", raw, re.S)
        link = re.search(r'<link[^>]*href="([^"]+)"', raw)
        if not (title and updated):
            continue
        m = _TITLE.match(html.unescape(title.group(1)))
        if not m:
            continue
        summ = html.unescape(summary.group(1)) if summary else ""
        acc = _ACCESSION.search(summ) or (_ACCESSION.search(link.group(1)) if link else None)
        if not acc:
            continue
        try:
            accepted = dt.datetime.fromisoformat(updated.group(1).strip()).astimezone(dt.timezone.utc)
        except ValueError:
            continue
        out.append({"form": m.group("form"), "company": m.group("name"), "cik": pad(m.group("cik")),
                    "role": m.group("role").strip(), "accession": acc.group(1), "accepted_at": accepted,
                    "items": sorted(set(_ITEM.findall(summ))), "index_url": link.group(1) if link else None})
    return out


def poll_current(get: Any, form: str, known: Iterable[str], *, max_pages: int = MAX_CURRENT_PAGES) -> list[dict[str, Any]]:
    """New entries of `form` (exact type) since the newest known accession: pages are read until a page holds only
    known accessions or the feed ends. `get(url) -> bytes` raises on a transport failure."""
    seen = set(known)
    fresh: dict[str, dict[str, Any]] = {}
    for page in range(max_pages):
        entries = parse_current(get(current_url(form, start=page * CURRENT_PAGE)))
        if not entries:
            break
        new_here = 0
        for entry in entries:
            acc = entry["accession"]
            if entry["form"] != form or acc in seen:
                continue
            prior = fresh.get(acc)
            if prior is None:
                new_here += 1
                fresh[acc] = entry
            elif entry["role"] == "Issuer" and prior["role"] != "Issuer":
                # A Form 4 is listed under its issuer and its reporting owner: keep the issuer's CIK (the XML's
                # issuerCik overrides it anyway when the filing is fetched).
                fresh[acc] = entry
        seen.update(fresh)
        if new_here == 0:
            break
    return list(fresh.values())


# ---------------------------------------------------------------------------------------------------- daily index
def daily_index_url(day: dt.date) -> str:
    q = (day.month - 1) // 3 + 1
    return f"{SEC}/Archives/edgar/daily-index/{day.year}/QTR{q}/form.{day.strftime('%Y%m%d')}.idx"


def parse_daily_index(body: bytes | str, forms: Iterable[str] = FORMS) -> list[dict[str, Any]]:
    """Rows of a `form.YYYYMMDD.idx` whose form type is exactly one of `forms`: {form, company, cik, accession}."""
    text = body.decode("latin-1") if isinstance(body, bytes) else body
    want = set(forms)
    out = []
    for line in text.splitlines():
        m = re.match(r"^(?P<form>\S+(?: \S+)?)\s{2,}(?P<company>.+?)\s{2,}(?P<cik>\d+)\s+(?P<date>\d{8}|\d{4}-\d{2}-\d{2})\s+"
                     r"(?P<path>edgar/data/\S+)\s*$", line)
        if not m or m.group("form") not in want:
            continue
        acc = _ACCESSION.search(m.group("path"))
        if acc:
            out.append({"form": m.group("form"), "company": m.group("company").strip(), "cik": pad(m.group("cik")),
                        "accession": acc.group(1)})
    return out


# ---------------------------------------------------------------------------------------------------- filing index
def parse_index_page(body: bytes | str) -> dict[str, Any]:
    """{accepted_at (UTC), items [str], documents [{seq, description, document, type, size, url}]} of an -index.htm."""
    text = body.decode("utf-8", "replace") if isinstance(body, bytes) else body
    acc = re.search(_INFO.format(label="Accepted"), text, re.S)
    if not acc:
        raise EdgarError("index page: no Accepted time")
    items_m = re.search(_INFO.format(label="Items"), text, re.S)
    items = sorted(set(_ITEM.findall(_text(items_m.group(1))))) if items_m else []
    docs = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", text, re.S):
        cells = [_text(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        href = re.search(r'href="([^"]+)"', row)
        if len(cells) < 5 or not href:
            continue
        url = href.group(1)
        if url.startswith("/ix?doc="):
            url = url[len("/ix?doc="):]
        if url.startswith("/"):
            url = SEC + url
        document = cells[2].replace(" iXBRL", "").strip()
        docs.append({"seq": cells[0], "description": cells[1], "document": document, "type": cells[3],
                     "size": cells[4], "url": url})
    return {"accepted_at": eastern_to_utc(_text(acc.group(1))), "items": items, "documents": docs}


def _ex99_key(kind: str) -> tuple[int, int] | None:
    m = re.match(r"^EX-99(?:\.(\d+))?([A-Z]?)$", kind.strip().upper())
    if not m:
        return None
    return (int(m.group(1) or 0), ord(m.group(2)) if m.group(2) else 0)


def choose_8k_document(documents: list[Mapping[str, Any]]) -> tuple[str, str]:
    """(url, kind): the lowest-numbered EX-99.* exhibit, else the primary 8-K document (PREREG section 3)."""
    exhibits = []
    for doc in documents:
        key = _ex99_key(str(doc.get("type", "")))
        if key is not None and str(doc.get("url", "")).lower().endswith((".htm", ".html", ".txt")):
            exhibits.append((key, doc))
    if exhibits:
        exhibits.sort(key=lambda pair: pair[0])
        doc = exhibits[0][1]
        return str(doc["url"]), str(doc["type"]).upper()
    for doc in documents:
        if str(doc.get("type", "")).upper() in ("8-K", "8-K12B", "8-K12G3") and str(doc.get("url", "")).lower().endswith(
                (".htm", ".html", ".txt")):
            return str(doc["url"]), "primary"
    raise EdgarError("no EX-99 exhibit and no primary 8-K document")


def prereg_text(raw: bytes) -> str:
    """TEXT of PREREG-EVL-1: strip_html, whitespace collapsed, first 16,000 characters."""
    from ltcm.data import strip_html
    return " ".join(strip_html(raw).split())[:TEXT_CHARS]


def choose_form4_xml(documents: list[Mapping[str, Any]]) -> str:
    """The raw XML of a Form 4 (type 4, an .xml file not under the xsl rendering path)."""
    for doc in documents:
        url = str(doc.get("url", ""))
        if str(doc.get("type", "")).strip() == "4" and url.lower().endswith(".xml") and "/xsl" not in url.lower():
            return url
    raise EdgarError("no Form 4 XML document")


# ---------------------------------------------------------------------------------------------------- Form 4
def _val(node: ET.Element | None, path: str) -> str | None:
    if node is None:
        return None
    found = node.find(path)
    if found is None:
        return None
    inner = found.find("value")
    raw = (inner.text if inner is not None else found.text) or ""
    raw = raw.strip()
    return raw or None


def _flag(value: str | None) -> int:
    return 1 if str(value or "").strip().lower() in ("1", "true") else 0


def _num(value: str | None) -> float | None:
    try:
        return float(str(value).replace(",", "")) if value is not None else None
    except ValueError:
        return None


def parse_form4(body: bytes | str) -> dict[str, Any]:
    """{issuer_cik, symbol, owners [...], transactions [...]} from a Form 4 ownershipDocument (non-derivative table)."""
    text = body if isinstance(body, str) else body.decode("utf-8", "replace")
    try:
        root = ET.fromstring(text.strip().encode("utf-8"))
    except ET.ParseError as exc:
        raise EdgarError(f"form 4 xml: {exc}") from exc
    issuer = root.find("issuer")
    issuer_cik = _val(issuer, "issuerCik")
    if not issuer_cik:
        raise EdgarError("form 4 xml: no issuerCik")
    owners = []
    for owner in root.findall("reportingOwner"):
        rel = owner.find("reportingOwnerRelationship")
        cik = _val(owner, "reportingOwnerId/rptOwnerCik")
        if not cik:
            continue
        owners.append({"owner_cik": pad(cik), "owner_name": _val(owner, "reportingOwnerId/rptOwnerName"),
                       "is_director": _flag(_val(rel, "isDirector")), "is_officer": _flag(_val(rel, "isOfficer")),
                       "officer_title": _val(rel, "officerTitle"), "is_ten_pct": _flag(_val(rel, "isTenPercentOwner"))})
    txs = []
    table = root.find("nonDerivativeTable")
    for seq, tx in enumerate(table.findall("nonDerivativeTransaction") if table is not None else []):
        txs.append({"seq": seq, "security": _val(tx, "securityTitle"), "tx_date": _val(tx, "transactionDate"),
                    "code": _val(tx, "transactionCoding/transactionCode"),
                    "shares": _num(_val(tx, "transactionAmounts/transactionShares")),
                    "price": _num(_val(tx, "transactionAmounts/transactionPricePerShare")),
                    "acquired": _val(tx, "transactionAmounts/transactionAcquiredDisposedCode"),
                    "owned_after": _num(_val(tx, "postTransactionAmounts/sharesOwnedFollowingTransaction"))})
    return {"issuer_cik": pad(issuer_cik), "symbol": _val(issuer, "issuerTradingSymbol"), "owners": owners,
            "transactions": txs}


# ---------------------------------------------------------------------------------------------------- recording
def record_filing(store: S.Store, get: Any, entry: Mapping[str, Any], *, source: str,
                  now: dt.datetime | None = None, fetch: bool = True) -> str:
    """Store one filing (idempotent by accession) and, when `fetch`, its index page and document. Returns its status.
    `get(url) -> bytes`. A filing whose form is not exactly 8-K or 4 is never stored."""
    form = str(entry["form"])
    if form not in FORMS:
        return "ignored"
    accession = str(entry["accession"])
    row = store.db.execute("SELECT status FROM filings WHERE accession=?", (accession,)).fetchone()
    if row is not None and str(row["status"]) == "fetched":
        return "fetched"
    now = now or S.utc_now()
    cik = pad(entry["cik"])
    accepted = entry.get("accepted_at")
    if row is None:
        provisional = accepted or now
        store.db.execute(
            "INSERT INTO filings(accession, form, cik, company, items, accepted_at, knowable_at, received_at, source, "
            "index_url, status) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'listed')",
            (accession, form, cik, entry.get("company"), json.dumps(entry.get("items") or []), S.iso(provisional),
             S.iso(knowable(provisional)), S.iso(now), source, entry.get("index_url") or index_url(cik, accession)))
    if not fetch:
        return "listed"
    try:
        page = parse_index_page(get(entry.get("index_url") or index_url(cik, accession)))
        accepted = page["accepted_at"]
        items = page["items"] if form == "8-K" else []
        if form == "8-K":
            url, kind = choose_8k_document(page["documents"])
            raw = get(url)
            digest = store.put_document(raw, kind, now=now)
            text = prereg_text(raw)
            text_digest = store.put_document(text.encode("utf-8"), "TEXT", now=now)
            with store.tx() as db:
                db.execute("UPDATE filings SET accepted_at=?, knowable_at=?, items=?, doc_url=?, doc_kind=?, text_sha=?, "
                           "text_len=?, raw_sha=?, status='fetched' WHERE accession=?",
                           (S.iso(accepted), S.iso(knowable(accepted)), json.dumps(items), url, kind, text_digest,
                            len(text), digest, accession))
        else:
            url = choose_form4_xml(page["documents"])
            raw = get(url)
            digest = store.put_document(raw, "4", now=now)
            parsed = parse_form4(raw)
            with store.tx() as db:
                for owner in parsed["owners"]:
                    db.execute("INSERT OR IGNORE INTO form4_owners(accession, owner_cik, owner_name, is_director, "
                               "is_officer, officer_title, is_ten_pct) VALUES(?, ?, ?, ?, ?, ?, ?)",
                               (accession, owner["owner_cik"], owner["owner_name"], owner["is_director"],
                                owner["is_officer"], owner["officer_title"], owner["is_ten_pct"]))
                for tx in parsed["transactions"]:
                    db.execute("INSERT OR IGNORE INTO form4_tx(accession, seq, security, tx_date, code, shares, price, "
                               "acquired, owned_after) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                               (accession, tx["seq"], tx["security"], tx["tx_date"], tx["code"], tx["shares"],
                                tx["price"], tx["acquired"], tx["owned_after"]))
                db.execute("UPDATE filings SET cik=?, accepted_at=?, knowable_at=?, doc_url=?, doc_kind='4', raw_sha=?, "
                           "status='fetched' WHERE accession=?",
                           (parsed["issuer_cik"], S.iso(accepted), S.iso(knowable(accepted)), url, digest, accession))
        return "fetched"
    except Exception as exc:  # noqa: BLE001 - one filing's failure is its own status, never the pass's
        why = f"failed:{type(exc).__name__}:{str(exc)[:160]}"
        store.db.execute("UPDATE filings SET status=? WHERE accession=? AND status!='fetched'", (why, accession))
        return why


__all__ = ["parse_current", "poll_current", "parse_daily_index", "daily_index_url", "parse_index_page",
           "choose_8k_document", "choose_form4_xml", "parse_form4", "prereg_text", "record_filing", "knowable",
           "eastern_to_utc", "current_url", "index_url", "EdgarError", "TEXT_CHARS"]
