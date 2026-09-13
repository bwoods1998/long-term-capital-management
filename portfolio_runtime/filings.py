"""Bounded primary-filing retrieval for questions the initial fact bank cannot answer.

Destinations are derived from registered CIKs and SEC submission metadata. Model
text cannot supply a URL, code, credentials, or a new company identity. Captures
stay private; only the filing's public URL belongs in published source links.
"""

from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
import gzip
import hashlib
import json
import re
import time
from urllib.request import Request, build_opener
from .evidence import NoRedirect, UA, save

MAX_BYTES = 20_000_000
MAX_CONTEXT = 30000


class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "ix:header", "head"):
            self.hidden += 1
        elif not self.hidden and tag in (
            "p",
            "div",
            "tr",
            "li",
            "h1",
            "h2",
            "h3",
            "h4",
        ):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "ix:header", "head") and self.hidden:
            self.hidden -= 1
        elif not self.hidden and tag in (
            "p",
            "div",
            "tr",
            "li",
            "h1",
            "h2",
            "h3",
            "h4",
        ):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data + " ")

    def paragraphs(self):
        return [
            " ".join(s.split())
            for s in "".join(self.parts).splitlines()
            if len(" ".join(s.split())) >= 90
        ]


def select_context(paragraphs, question):
    fixed = {
        "capital",
        "liquidity",
        "cash",
        "debt",
        "financing",
        "competition",
        "margin",
        "demand",
        "capacity",
        "commitments",
        "revenue",
        "risk",
        "lease",
        "customer",
        "research",
        "dividend",
        "repurchase",
    }
    terms = {
        word.lower()
        for word in re.findall(r"[A-Za-z]{5,}", question)
        if word.lower()
        not in {
            "which",
            "would",
            "their",
            "about",
            "should",
            "could",
            "company",
            "investment",
            "evidence",
        }
    } | fixed
    scored = []
    for i, p in enumerate(paragraphs):
        words = set(re.findall(r"[a-z]+", p.lower()))
        score = len(words & terms)
        if score:
            scored.append((score, i, p))
    chosen = []
    size = 0
    for score, index, paragraph in sorted(scored, key=lambda x: (-x[0], x[1])):
        paragraph = paragraph[:4000]
        if size + len(paragraph) > MAX_CONTEXT:
            continue
        chosen.append((index, paragraph))
        size += len(paragraph)
        if len(chosen) >= 30:
            break
    return [{"paragraph": i, "text": text} for i, text in sorted(chosen)]


class Filings:
    def __init__(self, directory, *, opener=None, limit=120):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.opener = opener or build_opener(NoRedirect).open
        self.limit = limit
        self.next_at = 0

    def get(self, url):
        time.sleep(max(0, self.next_at - time.monotonic()))
        self.next_at = time.monotonic() + 0.6
        request = Request(
            url, headers={"User-Agent": UA, "Accept": "application/json,text/html"}
        )
        with self.opener(request, timeout=35) as response:
            raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise ValueError("Primary filing exceeds bounded source envelope")
            return raw

    def enrich(self, company, question):
        symbol = company["symbol"]
        cik = company["cik"]
        cutoff = company["cutoff"]
        if not re.fullmatch(r"\d{10}", cik):
            raise ValueError("Unregistered SEC identity")
        path = self.directory / (symbol + ".json")
        if path.exists():
            saved = json.loads(path.read_text())
            if saved["cik"] != cik or saved["cutoff"] != cutoff:
                raise ValueError("Filing capture identity changed")
        else:
            if len(list(self.directory.glob("*.json"))) >= self.limit:
                return None
            captured = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            base = {
                "cik": cik,
                "cutoff": cutoff,
                "captured_at": captured,
                "status": "unavailable",
            }
            try:
                submission = json.loads(
                    self.get("https://data.sec.gov/submissions/CIK" + cik + ".json")
                )
                recent = submission["filings"]["recent"]
                candidates = []
                for i, form in enumerate(recent["form"]):
                    if (
                        form in ("10-K", "20-F", "40-F")
                        and recent["filingDate"][i] <= cutoff
                    ):
                        candidates.append(i)
                if not candidates:
                    raise ValueError(
                        "No annual filing available before evidence cutoff"
                    )
                i = max(candidates, key=lambda i: recent["filingDate"][i])
                accn = recent["accessionNumber"][i]
                document = recent["primaryDocument"][i]
                if not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accn) or not re.fullmatch(
                    r"[A-Za-z0-9_.-]{1,200}\.(?:htm|html)", document
                ):
                    raise ValueError("Unrecognized primary filing path")
                source = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn.replace('-', '')}/{document}"
                raw = self.get(source)
                sha = hashlib.sha256(raw).hexdigest()
                rawpath = self.directory / (sha + ".html.gz")
                rawpath.write_bytes(gzip.compress(raw))
                rawpath.chmod(0o600)
                parser = Text()
                parser.feed(raw.decode("utf-8", errors="replace"))
                paragraphs = parser.paragraphs()
                if len(paragraphs) < 20:
                    raise ValueError("Filing did not yield enough usable prose")
                saved = {
                    **base,
                    "status": "captured",
                    "source": source,
                    "sha256": sha,
                    "filed_at": recent["filingDate"][i],
                    "form": recent["form"][i],
                    "paragraphs": paragraphs,
                }
            except Exception as error:
                saved = {**base, "error_type": type(error).__name__}
            save(path, saved)
        if saved["status"] != "captured":
            return None
        return {
            k: saved[k] for k in ("source", "sha256", "captured_at", "filed_at", "form")
        } | {
            "selection": "keyword-ranked excerpts; not a complete reading of the filing",
            "excerpts": select_context(saved["paragraphs"], question),
        }
