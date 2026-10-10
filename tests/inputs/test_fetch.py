"""Downloading structures: routing, URL policy, size caps, mmCIF fallback.

No stand-ins. Two kinds of test:

* **Real services** (``requires_network``): RCSB, UniProt/AlphaFold and the RCSB
  search API are contacted for real, with small entries.
* **HTTP policy** against a **real local web server** that serves exact bytes
  (an oversized body, a gzip bomb, an HTML page, a real PDB file). It does not
  pretend to be any named service; it only gives the client something real to
  talk to, so the caps and checks run over a real socket.
"""
import gzip
import http.server
import os
import threading

import pytest

from vmd_agent import auto
from vmd_agent.inputs import fetch as F

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")


# ------------------------------------------------------- real local web server
class _Handler(http.server.BaseHTTPRequestHandler):
    routes = {}

    def do_GET(self):
        status, headers, body = self.routes.get(
            self.path, (404, {}, b"not found"))
        self.send_response(status)
        for k, v in headers.items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


@pytest.fixture
def web(monkeypatch):
    """A real HTTP server on 127.0.0.1; routes are ``path -> (status, headers, body)``."""
    monkeypatch.setenv(F.ENV_ALLOW_PRIVATE, "1")      # loopback is refused by default
    routes = {}
    handler = type("H", (_Handler,), {"routes": routes})
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    routes["_base"] = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        yield routes
    finally:
        srv.shutdown()
        srv.server_close()


def _real_pdb():
    with open(os.path.join(DATA, "1ubq.pdb"), "rb") as fh:
        return fh.read()


# ------------------------------------------------------------------- policy
def test_bad_identifier_has_a_hint(tmp_path):
    r = F.fetch_structure("not an id", out_dir=str(tmp_path))
    assert not r["ok"] and "search_pdb" in r["hint"]


@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "ftp://example.com/x.pdb", "http://127.0.0.1/x.pdb",
    "http://169.254.169.254/latest/meta-data/", "http://localhost/x.pdb",
    "http://[::1]/x.pdb"])
def test_unsafe_urls_refused(url, tmp_path):
    r = F.fetch_structure(url, out_dir=str(tmp_path), source="url")
    assert not r["ok"] and "refused" in r["error"]


def test_redirect_to_internal_address_is_refused():
    h = F._SafeRedirect()
    with pytest.raises(F.UnsafeURL):
        h.redirect_request(None, None, 302, "Found", {}, "http://127.0.0.1/x")


# ------------------------------------------- real local server: caps and checks
def test_a_real_structure_downloads_and_is_cached(web, tmp_path):
    web["/1ubq.pdb"] = (200, {}, _real_pdb())
    r = F.fetch_structure(web["_base"] + "/1ubq.pdb", out_dir=str(tmp_path),
                          source="url")
    assert r["ok"] and r["source"] == "url" and r["bytes"] == len(_real_pdb())
    assert open(r["path"], "rb").read() == _real_pdb()
    assert F.fetch_structure(web["_base"] + "/1ubq.pdb", out_dir=str(tmp_path),
                             source="url")["cached"]


def test_html_instead_of_structure_is_rejected(web, tmp_path):
    web["/x.pdb"] = (200, {"Content-Type": "text/html"},
                     b"<!DOCTYPE html><html><body>sign in</body></html>")
    r = F.fetch_structure(web["_base"] + "/x.pdb", out_dir=str(tmp_path),
                          source="url")
    assert not r["ok"] and "HTML" in r["error"]


def test_download_size_cap_over_a_real_socket(web):
    web["/big"] = (200, {}, b"x" * (6 << 20))
    with pytest.raises(ValueError, match="limit"):
        F._http_get(web["_base"] + "/big", max_bytes=5 << 20)


def test_gzip_bomb_is_capped_over_a_real_socket(web):
    web["/bomb"] = (200, {}, gzip.compress(b"0" * (30 << 20)))
    with pytest.raises(ValueError, match="size limit"):
        F._http_get(web["_base"] + "/bomb", max_bytes=1 << 20)


def test_gzip_responses_are_transparently_decoded(web):
    web["/z"] = (200, {}, gzip.compress(_real_pdb()))
    assert F._http_get(web["_base"] + "/z") == _real_pdb()


def test_missing_file_returns_none_not_an_exception(web):
    assert F._http_get(web["_base"] + "/absent") is None


# ------------------------------------------------------------ real services
@pytest.mark.requires_network
def test_identifier_routing_against_real_rcsb(tmp_path):
    r = F.fetch_structure("1UBQ", out_dir=str(tmp_path))
    assert r["ok"] and r["source"] == "rcsb" and r["format"] == "pdb"
    assert "UBIQUITIN" in r["metadata"]["title"].upper()
    from vmd_agent.inputs.molio import load_universe
    assert len(load_universe(r["path"]).atoms) > 500
    assert F.fetch_structure("1UBQ", out_dir=str(tmp_path))["cached"]


@pytest.mark.requires_network
def test_entry_without_a_pdb_file_falls_back_to_mmcif_and_the_pipeline_works(
        tmp_path):
    """An mmCIF download must be loadable.
    9NFN is a real entry too large for the PDB format (RCSB returns 404 for
    its .pdb), so only the mmCIF route can work."""
    pkg = auto.fetch_and_visualize("9NFN", out_dir=str(tmp_path),
                                   views=("front",), renderer="matplotlib")
    assert pkg["ok"], pkg
    assert pkg["fetched"]["format"] == "cif" and "mmCIF" in pkg["fetched"]["note"]
    assert pkg["detection"]["components"]["protein"]["n_residues"] > 100
    assert pkg["render_ok"]


@pytest.mark.requires_network
def test_alphafold_model_downloads_through_the_current_api(tmp_path):
    r = F.fetch_structure("P69905", out_dir=str(tmp_path))      # hemoglobin alpha
    assert r["ok"] and r["source"] == "alphafold" and "pLDDT" in r["note"]


@pytest.mark.requires_network
def test_search_pdb_against_the_real_search_api():
    r = F.search_pdb("hemoglobin", limit=5)
    assert r["ok"] and 0 < len(r["ids"]) <= 5
    assert all(len(i) == 4 for i in r["ids"])
