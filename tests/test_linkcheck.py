import csv
import io
from urllib.error import HTTPError, URLError

import pytest

from awepep_co.linkcheck import check_links, check_url
from awepep_co.validation import HEADERS


class Response:
    def __init__(self, status):
        self.status = status
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def read(self, *args):
        raise AssertionError("link checks must not read response bodies")


def error(code):
    return HTTPError("https://example.test/", code, "failure", {}, io.BytesIO(b"private content"))


@pytest.mark.parametrize("code,expected", [(200, "ok"), (204, "ok"), (404, "broken"), (410, "broken"), (401, "unknown"), (403, "unknown"), (429, "unknown"), (500, "unknown")])
def test_http_statuses(monkeypatch, code, expected):
    responses = []
    def open_mock(request, timeout):
        assert request.get_method() == "HEAD"
        assert timeout == 7
        if code >= 400:
            raise error(code)
        response = Response(code)
        responses.append(response)
        return response
    monkeypatch.setattr("awepep_co.linkcheck.urlopen", open_mock)
    assert check_url("https://example.test/article", timeout=7) == (expected, f"HTTP {code}")
    assert all(r.closed for r in responses)


@pytest.mark.parametrize("code", [405, 501])
def test_get_fallback_when_head_not_supported(monkeypatch, code):
    methods = []
    response = Response(200)
    def open_mock(request, timeout):
        methods.append(request.get_method())
        if request.get_method() == "HEAD":
            raise error(code)
        return response
    monkeypatch.setattr("awepep_co.linkcheck.urlopen", open_mock)
    assert check_url("https://example.test/article") == ("ok", "HTTP 200")
    assert methods == ["HEAD", "GET"]
    assert response.closed


@pytest.mark.parametrize("exc", [URLError("blocked"), TimeoutError(), OSError("unavailable")])
def test_network_failure_is_unknown(monkeypatch, exc):
    def open_mock(request, timeout):
        raise exc
    monkeypatch.setattr("awepep_co.linkcheck.urlopen", open_mock)
    assert check_url("https://example.test/")[0] == "unknown"


def test_invalid_urls_and_timeout_do_not_request(monkeypatch):
    def open_mock(*args, **kwargs):
        raise AssertionError("must not request invalid URLs")
    monkeypatch.setattr("awepep_co.linkcheck.urlopen", open_mock)
    for url in ("", "file:///etc/passwd", "javascript:alert(1)", "https://"):
        assert check_url(url)[0] == "unknown"
    with pytest.raises(ValueError, match="timeout"):
        check_url("https://example.test/", timeout=0)


def test_evidence_urls_are_read_only_sorted_and_deduplicated(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    path = tmp_path / "data/evidence.csv"
    rows = [
        {"evidence_id": "b", "url": "https://example.test/a", "archive_url": "https://example.test/archive"},
        {"evidence_id": "a", "url": "https://example.test/a"},
        {"evidence_id": "c", "url": ""},
    ]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=HEADERS["evidence"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    before = path.read_bytes()
    requested = []
    def open_mock(request, timeout):
        requested.append(request.full_url)
        return Response(200)
    monkeypatch.setattr("awepep_co.linkcheck.urlopen", open_mock)
    result = check_links(tmp_path)
    assert [(r.evidence_id, r.field, r.status) for r in result] == [
        ("a", "url", "ok"), ("b", "url", "ok"), ("b", "archive_url", "ok"), ("c", "url", "unknown"),
    ]
    assert requested == ["https://example.test/a", "https://example.test/archive"]
    assert path.read_bytes() == before


def test_evidence_header_and_row_width_are_checked(tmp_path):
    (tmp_path / "data").mkdir()
    path = tmp_path / "data/evidence.csv"
    path.write_text("evidence_id,url\nwrong,https://example.test\n")
    with pytest.raises(ValueError, match="header"):
        check_links(tmp_path)
    path.write_text(",".join(HEADERS["evidence"]) + "\nonly-one-field\n")
    with pytest.raises(ValueError, match="malformed"):
        check_links(tmp_path)


def test_redirects_are_followed_without_reading_body():
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from threading import Thread

    paths = []
    class Handler(BaseHTTPRequestHandler):
        def do_HEAD(self):
            paths.append(self.path)
            if self.path == "/old":
                self.send_response(302)
                self.send_header("Location", "/new")
                self.end_headers()
                return
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert check_url(f"http://127.0.0.1:{server.server_port}/old", timeout=2) == ("ok", "HTTP 200")
        assert paths == ["/old", "/new"]
    finally:
        server.shutdown()
        thread.join()
        server.server_close()
