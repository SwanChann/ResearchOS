from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest

from researchflow.cli import main
from researchflow.config import configure_zotero
from researchflow.errors import ResearchFlowError
from researchflow.project import ResearchProject, add_project
from researchflow.zotero import ZoteroClient, validate_base_url
from researchflow.zotero import diagnose_zotero


ITEM = {
    "key": "ABCD1234",
    "version": 7,
    "data": {
        "key": "ABCD1234",
        "version": 7,
        "itemType": "journalArticle",
        "title": "TEST Local Paper",
        "creators": [{"creatorType": "author", "firstName": "Ada", "lastName": "Lovelace"}],
        "publicationTitle": "TEST Journal",
        "date": "2026-04",
        "DOI": "10.0000/test",
        "tags": [{"tag": "navigation"}],
    },
}


@pytest.fixture
def zotero_server():
    requests: list[tuple[str, str, dict[str, list[str]]]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlsplit(self.path)
            requests.append(("GET", parsed.path, parse_qs(parsed.query)))
            if parsed.path in {"/api/groups/999/items", "/api/users/0/items/MISSING1"}:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Zotero-API-Version", "3")
            self.send_header("Zotero-Schema-Version", "42")
            self.send_header("Zotero-Server-ID", "TESTSERVER")
            if parsed.path == "/api/users/0/items/ATTACH01/file/view/url":
                body = b"file:///C:/Zotero/storage/ATTACH01/test.pdf"
                self.send_header("Content-Type", "text/plain; charset=utf-8")
            elif parsed.path == "/api/users/0/items" and parse_qs(parsed.query).get("format") == ["bib"]:
                body = b"<div class=\"csl-bib-body\">TEST bibliography</div>"
                self.send_header("Content-Type", "text/html; charset=utf-8")
            else:
                payload = self.payload(parsed.path)
                body = json.dumps(payload).encode("utf-8")
                self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def payload(self, path):
            if path == "/api/":
                return {}
            if path == "/api/users/0/groups":
                return [{"data": {"id": 123, "name": "TEST Group"}}]
            if path == "/api/users/0/collections":
                return [{"key": "COLL1234", "data": {"name": "TEST Collection"}}]
            if path == "/api/users/0/items/top":
                return [ITEM, {"key": "NOTE1234", "data": {"itemType": "note"}}]
            if path == "/api/users/0/items":
                return [ITEM]
            if path == "/api/users/0/items/ABCD1234":
                return ITEM
            if path == "/api/users/0/items/ABCD1234/children":
                return [
                    {"key": "ATTACH01", "data": {"itemType": "attachment", "filename": "test.pdf"}},
                    {"key": "NOTE0001", "data": {"itemType": "note", "note": "TEST note"}},
                ]
            if path == "/api/users/0/items/ATTACH01/children":
                return [{"key": "ANNOT001", "data": {"itemType": "annotation", "annotationText": "TEST quote"}}]
            if path == "/api/users/0/items/ATTACH01":
                return {"key": "ATTACH01", "data": {"itemType": "attachment", "filename": "test.pdf"}}
            raise AssertionError(f"Unexpected TEST endpoint: {path}")

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/api", requests
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_zotero_client_is_loopback_read_only_and_uses_full_text_search(zotero_server):
    base_url, requests = zotero_server
    client = ZoteroClient(base_url)
    results = client.search("local paper")
    assert [item["key"] for item in results] == ["ABCD1234"]
    context = client.context("ABCD1234")
    assert context["attachments"][0]["annotations"][0]["key"] == "ANNOT001"
    assert context["attachments"][0]["file_url"] == "file:///C:/Zotero/storage/ATTACH01/test.pdf"
    assert "TEST bibliography" in client.bibliography(["ABCD1234"])
    assert {method for method, _, _ in requests} == {"GET"}
    search_request = next(query for _, path, query in requests if path.endswith("/items/top"))
    assert search_request["qmode"] == ["everything"]
    with pytest.raises(ResearchFlowError, match="loopback"):
        validate_base_url("https://api.zotero.org")


def test_link_creates_analysis_reference_without_copying_pdf_and_is_idempotent(rf_env, zotero_server):
    base_url, _ = zotero_server
    add_project("toy", rf_env["repo"])
    configure_zotero(base_url, "users/0")
    project = ResearchProject.open("toy")
    client = ZoteroClient(base_url)
    paper_id = project.evidence.link_zotero(client, "ABCD1234")
    assert project.evidence.link_zotero(ZoteroClient(base_url), "ABCD1234") == paper_id
    record = project.evidence.show(paper_id)
    assert record["metadata"]["source"]["local_pdf"] is None
    assert record["metadata"]["source"]["zotero"]["server_id"] == "TESTSERVER"
    assert record["metadata"]["authors"] == ["Ada Lovelace"]
    assert "Zotero owns the bibliography, PDF" in record["body"]
    assert not list((project.root / "evidence" / "papers" / "pdf").glob("*.pdf"))
    assert len(project.evidence.list("paper")) == 1


def test_zotero_authority_blocks_manual_pdf_copy(rf_env, tmp_path, zotero_server):
    base_url, _ = zotero_server
    add_project("toy", rf_env["repo"])
    configure_zotero(base_url, "users/0")
    pdf = tmp_path / "manual.pdf"
    pdf.write_bytes(b"%PDF-1.4\n% TEST")
    with pytest.raises(ResearchFlowError, match="Manual PDF copying is disabled"):
        ResearchProject.open("toy").evidence.add_paper(pdf, "TEST manual")


def test_cli_configure_status_link_and_refresh(rf_env, zotero_server, capsys):
    base_url, _ = zotero_server
    assert main(["project", "add", "toy", "--repo", str(rf_env["repo"])]) == 0
    assert main(["evidence", "zotero", "configure", "--base-url", base_url]) == 0
    assert main(["evidence", "zotero", "status"]) == 0
    assert "read_only" in capsys.readouterr().out
    assert main(["evidence", "zotero", "link", "ABCD1234"]) == 0
    output = capsys.readouterr().out
    assert "PAPER-0001" in output
    project = ResearchProject.open("toy")
    analysis = project.root / "evidence" / "papers" / "analysis" / "PAPER-0001.md"
    analysis.write_text(analysis.read_text(encoding="utf-8").replace("Needs verification.", "TEST analysis preserved."), encoding="utf-8")
    assert main(["evidence", "zotero", "refresh", "PAPER-0001"]) == 0
    assert "PAPER-0001" in capsys.readouterr().out
    assert "TEST analysis preserved." in analysis.read_text(encoding="utf-8")


def test_zotero_doctor_classifies_config_connection_library_and_target(rf_env, zotero_server):
    base_url, requests = zotero_server
    bad_url = diagnose_zotero(config={
        "preferences": {"literature": {"authority": "zotero", "zotero": {"base_url": "https://api.zotero.org", "library": "users/0"}}}
    })
    assert bad_url["checks"][0]["category"] == "invalid_base_url"
    bad_library = diagnose_zotero(config={
        "preferences": {"literature": {"authority": "zotero", "zotero": {"base_url": base_url, "library": "bad"}}}
    })
    assert bad_library["checks"][0]["category"] == "invalid_library"

    unavailable = ZoteroClient("http://127.0.0.1:1/api", timeout=0.2).diagnose()
    assert unavailable["checks"][0]["category"] == "desktop_not_running_or_port_refused"

    missing_library = ZoteroClient(base_url, "groups/999").diagnose()
    assert missing_library["checks"][-1]["category"] == "target_or_library_not_found"
    missing_item = ZoteroClient(base_url).diagnose(item_key="MISSING1")
    assert any(check["category"] == "target_or_library_not_found" for check in missing_item["checks"])
    attachment_item = ZoteroClient(base_url).diagnose(item_key="ATTACH01")
    assert any(check["category"] == "attachment_or_nonbibliographic_item" for check in attachment_item["checks"])
    assert {method for method, _, _ in requests} == {"GET"}


def test_zotero_verbose_diagnoses_server_identity_and_missing_attachment(rf_env, zotero_server, capsys):
    base_url, requests = zotero_server
    assert main(["project", "add", "toy", "--repo", str(rf_env["repo"])]) == 0
    configure_zotero(base_url, "users/0")
    project = ResearchProject.open("toy")
    project.evidence.link_zotero(ZoteroClient(base_url), "ABCD1234")

    result = ZoteroClient(base_url).diagnose(project)
    assert result["status"] == "PASS_WITH_WARNINGS"
    assert result["attachments"][0]["exists"] is False
    assert any(check["category"] == "attachment_path_missing" for check in result["checks"])

    index = project.root / "evidence" / "papers" / "index.jsonl"
    index.write_text(index.read_text(encoding="utf-8").replace("TESTSERVER", "OLD-SERVER"), encoding="utf-8")
    changed = ZoteroClient(base_url).diagnose(project)
    assert changed["healthy"] is False
    assert any(check["category"] == "server_identity_changed" for check in changed["checks"])

    assert main(["evidence", "zotero", "status", "--verbose"]) == 1
    output = capsys.readouterr().out
    assert "read_only_get_only" in output
    assert "No API key, write, PDF download" in output
    assert {method for method, _, _ in requests} == {"GET"}
