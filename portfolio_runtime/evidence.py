"""Dated public evidence; model output never becomes a source of record."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, build_opener, HTTPRedirectHandler
import hashlib
import json
import re
import threading
import time

UNIVERSE_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
SEC_ROOT = "https://data.sec.gov/api/xbrl/companyfacts/"
UA = "Blake Woods Portfolio Agent contact blakewoods98@gmail.com"
TAGS = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
    ],
    "operating_cash": ["NetCashProvidedByUsedInOperatingActivities"],
    "capital_spending": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
    ],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "assets": ["Assets"],
    "equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "cash": ["CashAndCashEquivalentsAtCarryingValue"],
    "debt_current": ["LongTermDebtCurrent"],
    "debt_noncurrent": ["LongTermDebtNoncurrent"],
    "stock_compensation": ["ShareBasedCompensation"],
    "dividends_paid": ["PaymentsOfDividendsCommonStock", "PaymentsOfDividends"],
    "buybacks": ["PaymentsForRepurchaseOfCommonStock"],
    "shares": ["CommonStockSharesOutstanding"],
}

# These are different cash-flow definitions, not additive components or
# interchangeable aliases. Retain their exact tags for every source claim.
CAPITAL_SPENDING_DEFINITIONS = {
    "PaymentsToAcquirePropertyPlantAndEquipment": "Cash paid for property, plant and equipment.",
    "PaymentsToAcquireProductiveAssets": "Cash paid for property, plant and equipment, software and other intangible assets; broader than PP&E alone.",
}


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n")
    tmp.chmod(0o600)
    tmp.replace(path)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


class Fetcher:
    def __init__(self):
        self.lock = threading.Lock()
        self.next_sec = 0

    def get(self, url):
        if url.startswith(SEC_ROOT):
            with self.lock:
                wait = max(0, self.next_sec - time.monotonic())
                time.sleep(wait)
                self.next_sec = time.monotonic() + 0.35
        request = Request(
            url, headers={"User-Agent": UA, "Accept": "application/json,text/html"}
        )
        with build_opener(NoRedirect).open(request, timeout=45) as response:
            body = response.read(30_000_001)
            if len(body) > 30_000_000:
                raise ValueError("Source exceeds capture limit")
            return body


class Constituents(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inside = False
        self.row = None
        self.cell = None
        self.rows = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "table" and attrs.get("id") == "constituents":
            self.inside = True
        if self.inside and tag == "tr":
            self.row = []
        if self.inside and tag in ("td", "th"):
            self.cell = ""

    def handle_data(self, data):
        if self.cell is not None:
            self.cell += data

    def handle_endtag(self, tag):
        if self.inside and tag in ("td", "th") and self.cell is not None:
            self.row.append(" ".join(self.cell.split()))
            self.cell = None
        if self.inside and tag == "tr" and self.row:
            self.rows.append(self.row)
            self.row = None
        if self.inside and tag == "table":
            self.inside = False


def capture_universe(directory, fetcher=None):
    fetcher = fetcher or Fetcher()
    raw = fetcher.get(UNIVERSE_URL)
    parser = Constituents()
    parser.feed(raw.decode())
    rows = []
    for row in parser.rows[1:]:
        if (
            len(row) < 8
            or not re.fullmatch(r"[A-Z]{1,5}(?:\.[A-Z])?", row[0])
            or not row[6].isdigit()
        ):
            raise ValueError("Membership table changed")
        rows.append(
            {
                "symbol": row[0],
                "name": row[1],
                "sector": row[2],
                "industry": row[3],
                "cik": row[6].zfill(10),
            }
        )
    if not 490 <= len(rows) <= 510 or len({r["symbol"] for r in rows}) != len(rows):
        raise ValueError("Incomplete membership snapshot")
    captured = now()
    record = {
        "schema_version": 1,
        # The source may be byte-identical tomorrow, but its capture/expiry is a
        # new immutable membership observation in the persistent paper account.
        "id": "sp500-" + digest(raw + captured.encode())[:20],
        "captured_at": captured,
        "effective_at": captured,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "source": UNIVERSE_URL,
        "source_kind": "community-maintained constituent list; not licensed index data",
        "sha256": digest(raw),
        "companies": rows,
    }
    save(Path(directory) / "universe.json", record)
    return record


def facts_for_identity(company):
    """Explanatory tag labels are not new financial observations.

    Old packets lacked these labels. Excluding only that added field preserves
    their existing identity while new tags, periods and values still count.
    """
    facts = dict(company.get("facts", {}))
    if "capital_spending" in facts:
        facts["capital_spending"] = [
            {key: value for key, value in variant.items() if key != "definition"}
            for variant in facts["capital_spending"]
        ]
    return facts


def compact_facts(raw, company, captured_at, cutoff):
    """Keep annual/YTD/instant observations distinct, with accession and filing date."""
    data = json.loads(raw)
    facts = data.get("facts", {}).get("us-gaap", {})
    out = {}
    for metric, tags in TAGS.items():
        variants = []
        for tag in tags:
            definition = facts.get(tag, {})
            for unit, values in definition.get("units", {}).items():
                if unit not in ("USD", "shares"):
                    continue
                valid = [
                    v
                    for v in values
                    if v.get("form") in ("10-K", "10-Q", "20-F", "40-F")
                    and v.get("filed", "9999") <= cutoff
                    and v.get("end", "9999") <= cutoff
                    and isinstance(v.get("val"), (int, float))
                ]
                # A later filing can restate a period. Retain latest two versions if different.
                valid.sort(
                    key=lambda v: (v.get("end", ""), v.get("filed", "")), reverse=True
                )
                selected = []
                seen = set()
                for value in valid:
                    key = (value.get("start"), value["end"], value["val"])
                    if key in seen:
                        continue
                    seen.add(key)
                    duration = (
                        (
                            datetime.fromisoformat(value["end"])
                            - datetime.fromisoformat(value["start"])
                        ).days
                        if value.get("start")
                        else None
                    )
                    period_kind = (
                        "instant"
                        if duration is None
                        else "annual"
                        if 330 <= duration <= 380
                        else "quarter"
                        if 65 <= duration <= 110
                        else "year_to_date_or_other"
                    )
                    selected.append(
                        {
                            k: value[k]
                            for k in (
                                "val",
                                "start",
                                "end",
                                "filed",
                                "form",
                                "accn",
                                "fy",
                                "fp",
                            )
                            if k in value
                        }
                        | {"period_kind": period_kind}
                    )
                    if len(selected) >= 6:
                        break
                if selected:
                    variants.append(
                        {"tag": tag, "unit": unit, "observations": selected}
                        | ({"definition": CAPITAL_SPENDING_DEFINITIONS[tag]}
                           if metric == "capital_spending" else {})
                    )
        if variants:
            out[metric] = variants
    url = SEC_ROOT + "CIK" + company["cik"] + ".json"
    return {
        "schema_version": 1,
        **company,
        "captured_at": captured_at,
        "cutoff": cutoff,
        "source": url,
        "sha256": digest(raw),
        "facts": out,
        "limitations": [
            "Standard US-GAAP whole-company facts only; custom tags and business segments may be absent.",
            "Do not compare periods or capital-spending definitions without reconciling them.",
            "Capital-spending tags can overlap; do not add PP&E payments to productive-asset payments.",
        ],
    }


def capture_company(directory, company, fetcher, cutoff):
    path = Path(directory) / "companies" / f"{company['symbol']}.json"
    if path.exists():
        cached = json.loads(path.read_text())
        if cached.get("cutoff") == cutoff:
            return cached
    raw = fetcher.get(SEC_ROOT + "CIK" + company["cik"] + ".json")
    captured = now()
    # Raw source immutable and private; compressed to keep the deployment bundle small.
    import gzip

    rawpath = Path(directory) / "raw" / f"{company['cik']}-{digest(raw)[:16]}.json.gz"
    rawpath.parent.mkdir(parents=True, exist_ok=True)
    rawpath.write_bytes(gzip.compress(raw))
    record = compact_facts(raw, company, captured, cutoff)
    save(path, record)
    return record


def capture(directory, limit=None):
    directory = Path(directory)
    fetcher = Fetcher()
    universe = (
        json.loads((directory / "universe.json").read_text())
        if (directory / "universe.json").exists()
        else capture_universe(directory, fetcher)
    )
    cutoff = universe["captured_at"][:10]
    companies = universe["companies"][:limit] if limit else universe["companies"]
    failures = []
    success = 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            pool.submit(capture_company, directory, c, fetcher, cutoff): c
            for c in companies
        }
        for future in as_completed(futures):
            try:
                future.result()
                success += 1
            except Exception as error:
                failures.append(
                    {
                        "symbol": futures[future]["symbol"],
                        "error_type": type(error).__name__,
                    }
                )
    summary = {
        "captured_at": now(),
        "universe_id": universe["id"],
        "companies": len(companies),
        "captured": success,
        "failures": failures,
    }
    save(directory / "capture.json", summary)
    return summary


def assemble(directory, *, captured_at=None):
    """Assemble one complete dated packet without relabeling older captures.

    Prices are added separately by the service for selected names; an absent
    quote remains absent. This function makes no network requests.
    """
    directory = Path(directory)
    universe = json.loads((directory / "universe.json").read_text())
    companies = []
    overview = []
    for member in universe["companies"]:
        company = json.loads(
            (directory / "companies" / (member["symbol"] + ".json")).read_text()
        )
        if company["symbol"] != member["symbol"] or company["cik"] != member["cik"]:
            raise ValueError("Evidence does not match captured membership")
        if company["cutoff"] != universe["captured_at"][:10]:
            raise ValueError("Cannot silently carry yesterday's source cutoff forward")
        companies.append(company)
        facts = {}
        for metric, variants in company["facts"].items():
            if metric not in (
                "revenue", "operating_cash", "capital_spending", "net_income",
                "assets", "cash", "debt_noncurrent", "shares",
            ):
                continue
            observations = [
                (variant, observation)
                for variant in variants
                for observation in variant["observations"]
            ]
            if not observations:
                continue
            # Annual cash-flow/income comparisons must not silently use YTD.
            annual = [x for x in observations if x[1].get("period_kind") == "annual"]
            variant, observation = max(
                annual or observations, key=lambda x: (x[1]["end"], x[1].get("filed", ""))
            )
            facts[metric] = [observation["val"], observation.get("start"),
                             observation["end"], variant["unit"]]
        overview.append({"symbol": company["symbol"],
                         "sector": company.get("sector", ""), "facts": facts})
    return {"schema_version": 1, "captured_at": captured_at or now(),
            "universe": universe, "companies": companies, "overview": overview,
            "price_source": "Dated Yahoo research snapshots where available; missing prices are not inferred."}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", default=".data/runtime/evidence")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    print(json.dumps(capture(args.directory, args.limit)))
