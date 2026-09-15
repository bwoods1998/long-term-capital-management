"""SEC EDGAR: ticker/CIK mapping, XBRL company facts, submissions, filing text, full-text search.

Everything here is public primary-source data. The SEC requires a declared User-Agent carrying a
contact address and asks for no more than ten requests a second; `HttpTransport` supplies the
first and `min_interval` the second.

Endpoints, verified against the SEC's own developer pages:
  - https://www.sec.gov/search-filings/edgar-application-programming-interfaces  (the API index)
  - https://www.sec.gov/os/webmaster-faq#developers  (User-Agent and rate policy)
  - https://www.sec.gov/files/company_tickers.json  (ticker -> CIK)
  - https://data.sec.gov/submissions/CIK##########.json  (filing history)
  - https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json  (every reported XBRL fact)
  - https://efts.sec.gov/LATEST/search-index?q=...  (EDGAR full-text search, the JSON the UI at
    https://www.sec.gov/edgar/search/ calls)

Captured filing text is capped at 400 KB and always returned with the SHA-256 of the bytes that
were actually fetched, so a memo can cite a document the floor can prove it read.
"""

from __future__ import annotations

import hashlib
import re
import urllib.parse
from typing import Any, Iterable

from . import (
    DataError,
    HttpTransport,
    read_json,
    require,
    strip_html,
)

SEC_HOST = "https://www.sec.gov"
DATA_HOST = "https://data.sec.gov"
SEARCH_HOST = "https://efts.sec.gov"

TICKERS_URL = SEC_HOST + "/files/company_tickers.json"
SUBMISSIONS_URL = DATA_HOST + "/submissions/CIK{cik}.json"
COMPANYFACTS_URL = DATA_HOST + "/api/xbrl/companyfacts/CIK{cik}.json"
COMPANYCONCEPT_URL = DATA_HOST + "/api/xbrl/companyconcept/CIK{cik}/{taxonomy}/{tag}.json"
FULL_TEXT_SEARCH_URL = SEARCH_HOST + "/LATEST/search-index"

ARCHIVE_PREFIXES = (SEC_HOST + "/Archives/", SEC_HOST + "/cgi-bin/", DATA_HOST + "/")

MAX_FILING_BYTES = 400 * 1024
MAX_SEARCH_HITS = 100
TICKER = re.compile(r"^[A-Za-z][A-Za-z0-9.\-]{0,14}$")
FORM = re.compile(r"^[A-Z0-9][A-Z0-9./\- ]{0,19}$")
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

#: Ten requests a second is the SEC's published ceiling; the floor stays well under it.
MIN_INTERVAL = 0.15


def pad_cik(value: Any) -> str:
    """A CIK in the ten-digit zero-padded form every data.sec.gov path expects."""
    raw = str(value).strip().upper()
    if raw.startswith("CIK"):
        raw = raw[3:]
    if not raw.isdigit() or not 1 <= len(raw.lstrip("0") or "0") <= 10:
        raise DataError(f"not a CIK: {value!r}")
    return raw.zfill(10)


class Edgar:
    """Bounded, strict access to the EDGAR APIs. One instance per process is plenty."""

    source = "sec:edgar"

    def __init__(
        self,
        transport: Any = None,
        *,
        timeout: float = 30.0,
        cache_dir: Any = None,
        cache_ttl: float = 3600.0,
    ):
        self.transport = transport or HttpTransport(
            cache_dir=cache_dir, ttl=cache_ttl, min_interval=MIN_INTERVAL
        )
        self.timeout = float(timeout)
        self._tickers: dict[str, str] | None = None

    # -------------------------------------------------------------- identity
    def ticker_to_cik(self, refresh: bool = False) -> dict[str, str]:
        """Every listed ticker mapped to its ten-digit CIK, upper-cased keys.

        `company_tickers.json` is an object keyed by row index:
        `{"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, ...}`.
        """
        if self._tickers is not None and not refresh:
            return self._tickers
        payload = read_json(
            self.transport,
            TICKERS_URL,
            headers={"Accept": "application/json"},
            timeout=self.timeout,
            what="sec tickers",
        )
        rows: Iterable[Any]
        if isinstance(payload, dict):
            rows = payload.values()
        elif isinstance(payload, list):
            rows = payload
        else:
            raise DataError("sec tickers: unexpected top-level type")
        mapping: dict[str, str] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            ticker = row.get("ticker")
            cik = row.get("cik_str", row.get("cik"))
            if not isinstance(ticker, str) or cik is None:
                continue
            try:
                mapping[ticker.strip().upper()] = pad_cik(cik)
            except DataError:
                continue
        require(mapping, "sec tickers: no usable rows")
        self._tickers = mapping
        return mapping

    def cik_for(self, ticker: str) -> str:
        """The CIK for one ticker. Raises rather than returning a wrong company."""
        if not isinstance(ticker, str) or not TICKER.match(ticker.strip()):
            raise DataError(f"not a ticker: {ticker!r}")
        mapping = self.ticker_to_cik()
        cik = mapping.get(ticker.strip().upper())
        if cik is None:
            raise DataError(f"sec: no CIK registered for {ticker!r}")
        return cik

    # ----------------------------------------------------------------- facts
    def companyfacts(self, cik: Any) -> dict[str, Any]:
        """Every XBRL fact a filer has reported: `{cik, entityName, facts{taxonomy{tag{units}}}}`."""
        padded = pad_cik(cik)
        payload = read_json(
            self.transport,
            COMPANYFACTS_URL.format(cik=padded),
            headers={"Accept": "application/json"},
            timeout=self.timeout,
            what=f"sec companyfacts {padded}",
        )
        require(isinstance(payload, dict), f"sec companyfacts {padded}: not an object")
        require("facts" in payload, f"sec companyfacts {padded}: no facts block")
        return payload

    def companyconcept(self, cik: Any, tag: str, *, taxonomy: str = "us-gaap") -> dict[str, Any]:
        """One XBRL concept's full history, far smaller than the whole facts document."""
        padded = pad_cik(cik)
        if not re.match(r"^[A-Za-z][A-Za-z0-9]{0,80}$", tag or ""):
            raise DataError(f"not an XBRL tag: {tag!r}")
        if taxonomy not in ("us-gaap", "ifrs-full", "dei", "srt", "invest"):
            raise DataError(f"unknown taxonomy {taxonomy!r}")
        return read_json(
            self.transport,
            COMPANYCONCEPT_URL.format(cik=padded, taxonomy=taxonomy, tag=tag),
            headers={"Accept": "application/json"},
            timeout=self.timeout,
            what=f"sec companyconcept {padded} {tag}",
        )

    # ----------------------------------------------------------- submissions
    def submissions(self, cik: Any) -> dict[str, Any]:
        """A filer's profile and recent filing history (`filings.recent`, parallel arrays)."""
        padded = pad_cik(cik)
        payload = read_json(
            self.transport,
            SUBMISSIONS_URL.format(cik=padded),
            headers={"Accept": "application/json"},
            timeout=self.timeout,
            what=f"sec submissions {padded}",
        )
        require(isinstance(payload, dict), f"sec submissions {padded}: not an object")
        require("filings" in payload, f"sec submissions {padded}: no filings block")
        return payload

    def recent_filings(
        self, cik: Any, *, forms: "Iterable[str] | None" = None, limit: int = 40
    ) -> list[dict[str, Any]]:
        """`filings.recent` flattened into rows, newest first, with each document's URL.

        The SEC returns column-oriented arrays; row shape is far easier for a desk to reason
        about. Archive URLs follow
        `https://www.sec.gov/Archives/edgar/data/{cik}/{accession without dashes}/{document}`.
        """
        padded = pad_cik(cik)
        payload = self.submissions(padded)
        recent = payload.get("filings", {}).get("recent")
        require(isinstance(recent, dict), f"sec submissions {padded}: filings.recent missing")
        wanted = {str(form).upper() for form in forms} if forms else None
        columns = {
            name: recent.get(name) or []
            for name in (
                "accessionNumber",
                "filingDate",
                "reportDate",
                "acceptanceDateTime",
                "form",
                "primaryDocument",
                "primaryDocDescription",
                "items",
                "size",
                "isXBRL",
            )
        }
        count = len(columns["accessionNumber"])
        rows: list[dict[str, Any]] = []
        for index in range(count):
            form = _at(columns["form"], index)
            if wanted is not None and str(form).upper() not in wanted:
                continue
            accession = _at(columns["accessionNumber"], index)
            document = _at(columns["primaryDocument"], index)
            rows.append(
                {
                    "cik": padded,
                    "accession": accession,
                    "form": form,
                    "filed": _at(columns["filingDate"], index),
                    "period": _at(columns["reportDate"], index),
                    "accepted": _at(columns["acceptanceDateTime"], index),
                    "description": _at(columns["primaryDocDescription"], index),
                    "items": _at(columns["items"], index),
                    "size": _at(columns["size"], index),
                    "url": archive_url(padded, accession, document) if accession and document else None,
                }
            )
            if len(rows) >= limit:
                break
        return rows

    # ------------------------------------------------------------ documents
    def filing_text(self, url: str) -> dict[str, Any]:
        """Fetch one filing document and return `{text, sha256, url}`.

        Only `sec.gov` archive URLs are accepted: a model-supplied destination can never point
        this at an arbitrary host. HTML is stripped to visible text and the text is capped at
        400 KB; `sha256` always covers the raw bytes received, capped or not.
        """
        if not isinstance(url, str) or not url.startswith(ARCHIVE_PREFIXES):
            raise DataError(f"refusing a non-EDGAR document URL: {url!r}")
        status, headers, body = self.transport.get(
            url, {"Accept": "text/html,application/xhtml+xml,text/plain"}, self.timeout
        )
        if status != 200:
            raise DataError(f"sec filing: HTTP {status} from {url}")
        digest = hashlib.sha256(body).hexdigest()
        content_type = str(headers.get("content-type", "")).lower()
        if "html" in content_type or "xml" in content_type or _looks_like_html(body):
            text = strip_html(body)
        else:
            text = body.decode("utf-8", "replace")
            text = "\n".join(line for line in (" ".join(l.split()) for l in text.splitlines()) if line)
        truncated = len(text) > MAX_FILING_BYTES
        return {
            "url": url,
            "sha256": digest,
            "text": text[:MAX_FILING_BYTES],
            "bytes": len(body),
            "truncated": truncated,
        }

    # --------------------------------------------------------------- search
    def full_text_search(
        self,
        query: str,
        *,
        forms: "Iterable[str] | None" = None,
        start: "str | None" = None,
        end: "str | None" = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """EDGAR full-text search over filings since 2001.

        Hits come back as `hits.hits[]` with `_id` of the form
        `"{accession}:{document}"` and a `_source` carrying `ciks`, `display_names`,
        `file_type`, `file_date`, `adsh` and `root_forms`.
        """
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 200:
            raise DataError("full_text_search needs a 1-200 character query")
        params: dict[str, str] = {"q": query.strip()}
        if forms:
            cleaned = [str(form).strip().upper() for form in forms]
            for form in cleaned:
                if not FORM.match(form):
                    raise DataError(f"not an EDGAR form type: {form!r}")
            params["forms"] = ",".join(cleaned)
        if start or end:
            for label, value in (("startdt", start), ("enddt", end)):
                if value is not None:
                    if not ISO_DATE.match(str(value)):
                        raise DataError(f"{label} must be YYYY-MM-DD, got {value!r}")
                    params[label] = str(value)
            params["dateRange"] = "custom"
        url = FULL_TEXT_SEARCH_URL + "?" + urllib.parse.urlencode(params)
        payload = read_json(
            self.transport,
            url,
            headers={"Accept": "application/json"},
            timeout=self.timeout,
            what="sec full-text search",
        )
        require(isinstance(payload, dict), "sec full-text search: not an object")
        hits = payload.get("hits", {})
        rows = hits.get("hits") if isinstance(hits, dict) else None
        if not isinstance(rows, list):
            return []
        capped = max(1, min(int(limit), MAX_SEARCH_HITS))
        results: list[dict[str, Any]] = []
        for hit in rows[:capped]:
            if not isinstance(hit, dict):
                continue
            source = hit.get("_source") or {}
            identity = str(hit.get("_id") or "")
            accession, _, document = identity.partition(":")
            ciks = source.get("ciks") or []
            cik = pad_cik(ciks[0]) if ciks and str(ciks[0]).strip().isdigit() else None
            names = source.get("display_names") or []
            results.append(
                {
                    "accession": accession or source.get("adsh"),
                    "document": document or None,
                    "form": source.get("file_type") or source.get("root_forms"),
                    "filed": source.get("file_date"),
                    "cik": cik,
                    "company": names[0] if names else None,
                    "url": archive_url(cik, accession or source.get("adsh"), document)
                    if cik and document
                    else None,
                }
            )
        return results


def _at(column: Any, index: int) -> Any:
    if isinstance(column, list) and 0 <= index < len(column):
        return column[index]
    return None


def _looks_like_html(body: bytes) -> bool:
    head = body[:2048].lstrip().lower()
    return head.startswith(b"<") and (b"<html" in head or b"<?xml" in head or b"<!doctype" in head)


def archive_url(cik: Any, accession: Any, document: Any) -> str:
    """`https://www.sec.gov/Archives/edgar/data/{cik}/{accession no dashes}/{document}`."""
    padded = pad_cik(cik)
    bare = str(accession or "").replace("-", "")
    if not bare.isdigit() or len(bare) != 18:
        raise DataError(f"not an accession number: {accession!r}")
    name = str(document or "").strip().lstrip("/")
    if not name or ".." in name or "//" in name:
        raise DataError(f"not a filing document name: {document!r}")
    return f"{SEC_HOST}/Archives/edgar/data/{int(padded)}/{bare}/{urllib.parse.quote(name)}"


__all__ = [
    "Edgar",
    "archive_url",
    "pad_cik",
    "TICKERS_URL",
    "SUBMISSIONS_URL",
    "COMPANYFACTS_URL",
    "FULL_TEXT_SEARCH_URL",
    "MAX_FILING_BYTES",
]
