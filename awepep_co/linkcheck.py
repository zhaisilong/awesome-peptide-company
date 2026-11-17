"""Read-only HTTP checks for evidence links.

Link checks are explicitly invoked and are not part of the offline build.
An inaccessible URL may be temporary or blocked; only 404 and 410 are treated
as evidence that the resource is gone. No response body is read or stored.
"""

import csv
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .validation import HEADERS


@dataclass(frozen=True)
class LinkResult:
    evidence_id: str
    field: str
    url: str
    status: str
    detail: str


class _HeadPreservingRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        redirected = super().redirect_request(request, response, code, message, headers, new_url)
        # urllib otherwise changes HEAD to GET on common redirects, which can
        # download content even though we only need the response headers.
        if redirected is not None and request.get_method() == "HEAD":
            redirected.method = "HEAD"
        return redirected


def urlopen(request, timeout):
    return build_opener(_HeadPreservingRedirect()).open(request, timeout=timeout)


def _valid_url(url):
    try:
        parts = urlsplit(url)
        return parts.scheme in ("http", "https") and bool(parts.hostname)
    except ValueError:
        return False


def _classify(code):
    if 200 <= code < 300:
        return "ok", f"HTTP {code}"
    if code in (404, 410):
        return "broken", f"HTTP {code}"
    return "unknown", f"HTTP {code}"


def _request(url, method, timeout):
    request = Request(url, method=method, headers={"User-Agent": "awesome-peptide-company-linkcheck/0.2"})
    try:
        # GET is only a fallback for servers which reject HEAD. Closing the
        # stream immediately prevents reading or saving an article body.
        with urlopen(request, timeout=timeout) as response:
            return response.status, None
    except HTTPError as exc:
        # HTTPError is also a file-like response and must be closed.
        try:
            return exc.code, None
        finally:
            exc.close()
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        return None, type(exc).__name__


def check_url(url, timeout=10):
    """Return (status, detail) for an HTTP(S) URL without reading its body."""
    if timeout <= 0:
        raise ValueError("timeout must be greater than zero")
    if not _valid_url(url):
        return "unknown", "missing or invalid HTTP(S) URL"
    code, error = _request(url, "HEAD", timeout)
    if code in (405, 501):
        code, error = _request(url, "GET", timeout)
    if error:
        return "unknown", error
    return _classify(code)


def check_links(root, timeout=10):
    """Check the primary and present archive URLs from evidence.csv.

    A missing primary URL is reported as unknown. A missing archive URL is
    skipped: this tool checks existing links and never creates an archive.
    Identical URLs are requested once and results are returned in stable order.
    """
    if timeout <= 0:
        raise ValueError("timeout must be greater than zero")
    evidence_file = Path(root) / "data" / "evidence.csv"
    with evidence_file.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, strict=True)
        if reader.fieldnames != HEADERS["evidence"]:
            raise ValueError("evidence.csv has an invalid header")
        rows = list(reader)
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError("evidence.csv has a malformed row")
    results = []
    cache = {}
    for row in sorted(rows, key=lambda record: record["evidence_id"]):
        for field in ("url", "archive_url"):
            url = row[field].strip()
            if field == "archive_url" and not url:
                continue
            if url not in cache:
                cache[url] = check_url(url, timeout=timeout)
            status, detail = cache[url]
            results.append(LinkResult(row["evidence_id"], field, url, status, detail))
    return results
