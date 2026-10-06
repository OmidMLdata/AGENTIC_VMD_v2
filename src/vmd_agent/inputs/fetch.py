"""Download structures from the web so the agent can visualize them directly.

Supported sources
-----------------
* **RCSB PDB** — a 4-character PDB ID (``1UBQ``, ``4HHB``) or an extended
  12-character ID (``pdb_00006uv8``).
* **AlphaFold DB** — a UniProt accession (``P69905``) returns the predicted model.
* **Any URL** — a direct link to a ``.pdb``/``.cif``/``.gro``/... file.

Notes
-----
The legacy PDB text format cannot represent very large structures, and RCSB
plans to retire the legacy-format URLs as the archive moves to extended IDs.
``fetch_structure`` therefore tries PDB first and **falls back to mmCIF**
automatically, so large entries (ribosomes, capsids) still work. VMD reads
mmCIF via its ``pdbx`` plugin.

Only the Python standard library is used, so this adds no dependencies.
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

RCSB_FILE = "https://files.rcsb.org/download/{ident}.{ext}"
RCSB_META = "https://data.rcsb.org/rest/v1/core/entry/{ident}"
RCSB_SEARCH = "https://search.rcsb.org/rcsbsearch/v2/query"
ALPHAFOLD_FILE = "https://alphafold.ebi.ac.uk/files/AF-{acc}-F1-model_v{ver}.pdb"
ALPHAFOLD_API = "https://alphafold.ebi.ac.uk/api/prediction/{acc}"

_UA = {"User-Agent": "vmd-agent/0.3 (molecular visualization toolkit)"}

_PDB_ID = re.compile(r"^[0-9][A-Za-z0-9]{3}$")            # 1UBQ
_PDB_EXT_ID = re.compile(r"^pdb_[A-Za-z0-9]{8}$", re.I)   # pdb_00006uv8
_UNIPROT = re.compile(
    r"^([OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9]([A-Z][A-Z0-9]{2}[0-9]){1,2})$")


# --------------------------------------------------------------- downloading
MAX_BYTES = int(os.environ.get("VMD_AGENT_MAX_DOWNLOAD_MB", "1024")) * 1024 * 1024
ENV_ALLOW_PRIVATE = "VMD_AGENT_ALLOW_PRIVATE_URLS"


class UnsafeURL(ValueError):
    """Raised for a user-supplied URL the downloader refuses to fetch."""


def check_url(url: str) -> str:
    """Refuse URLs that could read local files or reach internal services.

    Only http(s) is allowed (``urllib`` would otherwise happily open
    ``file://`` and ``ftp://``), and hosts resolving to loopback, private,
    link-local or reserved addresses are rejected unless
    ``VMD_AGENT_ALLOW_PRIVATE_URLS=1``. This blocks the usual abuse of a
    download tool: reading cloud-metadata endpoints or localhost services.
    It does not defend against DNS rebinding between this check and the
    request; run the container without access to internal networks for that.
    """
    u = urllib.parse.urlparse(url)
    if u.scheme not in ("http", "https"):
        raise UnsafeURL(f"only http(s) URLs are allowed, got '{u.scheme}://'")
    host = u.hostname
    if not host:
        raise UnsafeURL("URL has no host")
    if os.environ.get(ENV_ALLOW_PRIVATE) == "1":
        return url
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise UnsafeURL(f"cannot resolve host '{host}': {e}") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise UnsafeURL(
                f"host '{host}' resolves to a non-public address ({ip}); set "
                f"{ENV_ALLOW_PRIVATE}=1 to allow internal URLs")
    return url


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    """Re-run the URL policy on every redirect hop (public -> internal)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_SafeRedirect)


def _http_get(url: str, timeout: int = 60,
              max_bytes: Optional[int] = None) -> Optional[bytes]:
    """GET a URL, transparently gunzipping. Returns None on 403/404.

    The body is read in chunks and abandoned beyond ``max_bytes`` (compressed
    and decompressed), so a hostile or runaway download cannot exhaust memory.
    """
    cap = MAX_BYTES if max_bytes is None else max_bytes
    req = urllib.request.Request(url, headers=_UA)
    try:
        with _OPENER.open(req, timeout=timeout) as resp:
            chunks, total = [], 0
            while True:
                block = resp.read(1 << 20)
                if not block:
                    break
                total += len(block)
                if total > cap:
                    raise ValueError(f"download exceeds {cap // (1 << 20)} MB "
                                     "limit (VMD_AGENT_MAX_DOWNLOAD_MB)")
                chunks.append(block)
            data = b"".join(chunks)
    except urllib.error.HTTPError as e:
        if e.code in (403, 404):
            return None
        raise
    if data[:2] == b"\x1f\x8b":          # gzip magic
        import zlib
        d = zlib.decompressobj(16 + zlib.MAX_WBITS)
        out = d.decompress(data, cap + 1)
        if len(out) > cap or d.unconsumed_tail:
            raise ValueError("decompressed download exceeds the size limit")
        data = out
    return data


def _looks_like_html(data: bytes) -> bool:
    head = data[:400].lstrip().lower()
    return head.startswith(b"<!doctype html") or head.startswith(b"<html")


def _write(data: bytes, path: str) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)
    return os.path.abspath(path)


# --------------------------------------------------------------- metadata
def _dig(obj, *keys, default=None):
    """Walk nested dict/list structures defensively."""
    cur = obj
    for k in keys:
        try:
            cur = cur[k]
        except (KeyError, IndexError, TypeError):
            return default
    return cur


def fetch_metadata(pdb_id: str, timeout: int = 30) -> dict:
    """Look up title / method / resolution for a PDB entry (best-effort).

    Never raises: metadata is a nice-to-have for the report, not a hard
    requirement for visualization.
    """
    try:
        raw = _http_get(RCSB_META.format(ident=pdb_id.lower()), timeout=timeout)
        if not raw:
            return {}
        j = json.loads(raw.decode("utf-8", "replace"))
    except Exception as e:
        return {"metadata_error": str(e)}
    res = _dig(j, "rcsb_entry_info", "resolution_combined", 0)
    return {k: v for k, v in {
        "title": _dig(j, "struct", "title"),
        "experimental_method": _dig(j, "exptl", 0, "method"),
        "resolution_A": res,
        "deposited": _dig(j, "rcsb_accession_info", "deposit_date"),
        "released": _dig(j, "rcsb_accession_info", "initial_release_date"),
        "polymer_entities": _dig(j, "rcsb_entry_info", "polymer_entity_count"),
        "molecular_weight_kDa": _dig(j, "rcsb_entry_info",
                                     "molecular_weight"),
    }.items() if v is not None}


# --------------------------------------------------------------- main entry
def fetch_structure(identifier: str, out_dir: str = ".",
                    source: str = "auto", file_format: str = "auto",
                    overwrite: bool = False, timeout: int = 60) -> dict:
    """Download a structure and return its local path.

    Parameters
    ----------
    identifier : str
        PDB ID (``1UBQ``), UniProt accession (``P69905``), or a full URL.
    source : {"auto", "rcsb", "alphafold", "url"}
    file_format : {"auto", "pdb", "cif"}
        ``auto`` tries PDB then falls back to mmCIF (needed for large entries).
    """
    ident = identifier.strip()
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    # ---- decide the source -------------------------------------------------
    if source == "auto":
        if ident.lower().startswith(("http://", "https://")):
            source = "url"
        elif _PDB_ID.match(ident) or _PDB_EXT_ID.match(ident):
            source = "rcsb"
        elif _UNIPROT.match(ident.upper()):
            source = "alphafold"
        else:
            return {"ok": False, "error":
                    f"Could not interpret '{identifier}'. Expected a 4-character "
                    "PDB ID (e.g. 1UBQ), a UniProt accession (e.g. P69905), or "
                    "a URL. Pass source='rcsb'|'alphafold'|'url' to force one.",
                    "hint": "Use search_pdb('hemoglobin') to find an ID by name."}

    # ---- direct URL --------------------------------------------------------
    if source == "url":
        try:
            check_url(ident)
        except UnsafeURL as e:
            return {"ok": False, "error": f"URL refused: {e}", "url": ident}
        name = os.path.basename(urllib.parse.urlparse(ident).path) or "download.pdb"
        if name.endswith(".gz"):
            name = name[:-3]
        dest = os.path.join(out_dir, name)
        if os.path.exists(dest) and not overwrite:
            return {"ok": True, "path": dest, "source": "url",
                    "identifier": ident, "cached": True}
        try:
            data = _http_get(ident, timeout=timeout)
        except Exception as e:
            return {"ok": False, "error": f"download failed: {e}", "url": ident}
        if not data:
            return {"ok": False, "error": f"not found (404/403): {ident}"}
        if _looks_like_html(data):
            return {"ok": False, "error":
                    "URL returned an HTML page, not a structure file. Use the "
                    "direct file link (e.g. files.rcsb.org/download/1UBQ.pdb).",
                    "url": ident}
        return {"ok": True, "path": _write(data, dest), "source": "url",
                "identifier": ident, "bytes": len(data), "cached": False}

    # ---- AlphaFold ---------------------------------------------------------
    if source == "alphafold":
        acc = ident.upper()
        dest = os.path.join(out_dir, f"AF-{acc}.pdb")
        if os.path.exists(dest) and not overwrite:
            return {"ok": True, "path": dest, "source": "alphafold",
                    "identifier": acc, "cached": True}
        last_err = None
        # Ask the API for the current file URL: AlphaFold DB bumps the model
        # version periodically and retires the old files, so a hardcoded
        # version list goes stale (v1-v4 are already 404).
        candidates = []
        try:
            meta = _http_get(ALPHAFOLD_API.format(acc=acc), timeout=timeout)
            if meta:
                entries = json.loads(meta.decode("utf-8", "replace"))
                if isinstance(entries, list) and entries:
                    url = _dig(entries[0], "pdbUrl")
                    if url:
                        candidates.append(url)
                    latest = _dig(entries[0], "latestVersion")
                    if isinstance(latest, int):
                        candidates += [ALPHAFOLD_FILE.format(acc=acc, ver=v)
                                       for v in range(latest, 0, -1)]
        except Exception as e:
            last_err = str(e)
        # Fallback if the API is unreachable: probe versions newest-first.
        if not candidates:
            candidates = [ALPHAFOLD_FILE.format(acc=acc, ver=v)
                          for v in range(8, 0, -1)]
        seen = set()
        candidates = [u for u in candidates
                      if not (u in seen or seen.add(u))]
        for url in candidates:
            try:
                data = _http_get(url, timeout=timeout)
            except Exception as e:
                last_err = str(e); continue
            if data and not _looks_like_html(data):
                return {"ok": True, "path": _write(data, dest),
                        "source": "alphafold", "identifier": acc,
                        "url": url, "bytes": len(data), "cached": False,
                        "note": "AlphaFold *predicted* model — the B-factor "
                                "column holds pLDDT confidence (0-100), not "
                                "crystallographic B-factors. Colour by Beta "
                                "in VMD to see per-residue confidence."}
        return {"ok": False, "error":
                f"No AlphaFold model found for accession '{acc}'."
                + (f" ({last_err})" if last_err else ""),
                "hint": "Check the UniProt accession, or pass a PDB ID instead."}

    # ---- RCSB PDB ----------------------------------------------------------
    exts = ["pdb", "cif"] if file_format == "auto" else [file_format]
    ident_l = ident.lower()
    errors = []
    for ext in exts:
        dest = os.path.join(out_dir, f"{ident_l}.{ext}")
        if os.path.exists(dest) and not overwrite:
            meta = fetch_metadata(ident_l, timeout=timeout)
            return {"ok": True, "path": dest, "source": "rcsb",
                    "identifier": ident.upper(), "format": ext,
                    "cached": True, "metadata": meta}
        url = RCSB_FILE.format(ident=ident_l, ext=ext)
        try:
            data = _http_get(url, timeout=timeout)
        except Exception as e:
            errors.append(f"{ext}: {e}")
            continue
        if not data or _looks_like_html(data):
            errors.append(f"{ext}: not available")
            continue
        path = _write(data, dest)
        meta = fetch_metadata(ident_l, timeout=timeout)
        out = {"ok": True, "path": path, "source": "rcsb",
               "identifier": ident.upper(), "format": ext,
               "bytes": len(data), "cached": False, "metadata": meta,
               "url": url}
        if ext == "cif":
            out["note"] = ("Legacy PDB format was unavailable for this entry "
                           "(usually because it is too large), so mmCIF was "
                           "downloaded. VMD reads it via the pdbx plugin.")
        return out
    return {"ok": False,
            "error": f"Could not download '{ident}' from RCSB. " + "; ".join(errors),
            "hint": "Verify the ID at https://www.rcsb.org/structure/" + ident.upper()}


# --------------------------------------------------------------- search
def search_pdb(query: str, limit: int = 10, timeout: int = 30) -> dict:
    """Full-text search of the PDB; returns candidate IDs for a name/keyword."""
    payload = {
        "query": {"type": "terminal", "service": "full_text",
                  "parameters": {"value": query}},
        "return_type": "entry",
        "request_options": {"paginate": {"start": 0, "rows": int(limit)}},
    }
    url = RCSB_SEARCH + "?json=" + urllib.parse.quote(json.dumps(payload))
    try:
        raw = _http_get(url, timeout=timeout)
        if not raw:
            return {"ok": False, "error": "no results / search unavailable",
                    "query": query}
        j = json.loads(raw.decode("utf-8", "replace"))
    except Exception as e:
        return {"ok": False, "error": f"search failed: {e}", "query": query}
    ids = [i.get("identifier") for i in j.get("result_set", [])
           if i.get("identifier")]
    return {"ok": bool(ids), "query": query, "n_hits": j.get("total_count"),
            "ids": ids[:limit],
            "note": "Pass one of these IDs to fetch_structure / "
                    "fetch_and_visualize."}
