"""A private copy of the Ollama model server, kept inside the one vmd-agent folder.

The usual Ollama installers (brew, winget, the Linux script) put it on the whole system
and the Linux one needs sudo. This module instead downloads Ollama's own *standalone*
release archive into ``<home>/ollama``, checks it against the checksum file published
with that release, runs it on a private port with its models stored in ``<home>/ollama/models``,
and so leaves nothing outside the folder. Deleting the folder removes it all.

Downloads are large (Ollama's Linux and Windows archives are over 1 GB because they bundle
GPU libraries), so callers must ask the user first; nothing here asks, and nothing here runs
unless called.

Run on macOS (Apple Silicon): the install, the server start, the model download and a chat through it. Not run on Linux or
Windows: there the release file names, the checksum check and the paths are tested, the download itself is not.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import re
import tarfile
import time
import urllib.error
import urllib.request
import zipfile
from typing import Callable, Dict, List, Optional

from vmd_agent import platform_info as P
from vmd_agent import settings

RELEASE_API = "https://api.github.com/repos/ollama/ollama/releases/latest"
DEFAULT_PORT = 11435                 # not 11434, so it never meets a system-wide Ollama
#: Ollama's own default context is 4096 tokens, which the tool list alone nearly fills; the model then silently loses its
#: instructions and tools. 16384 tokens costs about 2 GB more memory for an 8B model.
DEFAULT_CONTEXT = 16384


def asset_name(system_name: Optional[str] = None, machine: Optional[str] = None) -> str:
    """Name of Ollama's standalone archive for this OS and CPU (names as listed on its
    releases page when this was written)."""
    s, a = P.system(system_name), P.arch(machine)
    if s == P.MACOS:
        return "ollama-darwin.tgz"
    if s == P.WINDOWS:
        return f"ollama-windows-{'arm64' if a == 'arm64' else 'amd64'}.zip"
    if s == P.LINUX:
        return f"ollama-linux-{'arm64' if a == 'arm64' else 'amd64'}.tar.zst"
    raise ValueError(f"no standalone Ollama archive known for {system_name!r}")


#: approximate sizes of the archives on the release checked 2026-10-06 (the real size is read
#: from the release before downloading)
APPROX_GB = {"ollama-darwin.tgz": 0.16, "ollama-linux-amd64.tar.zst": 1.44,
             "ollama-linux-arm64.tar.zst": 1.56, "ollama-windows-amd64.zip": 1.47,
             "ollama-windows-arm64.zip": 0.21}


def ollama_dir(env: Optional[Dict[str, str]] = None) -> str:
    return os.path.join(settings.home_dir(env=env), "ollama")


def models_dir(env: Optional[Dict[str, str]] = None) -> str:
    return os.path.join(ollama_dir(env), "models")


def port() -> int:
    try:
        return int(settings.get("ollama_port", DEFAULT_PORT))
    except (TypeError, ValueError):
        return DEFAULT_PORT


def url() -> str:
    """The OpenAI-style address of the private server."""
    return f"http://127.0.0.1:{port()}/v1"


def server_env(base: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Environment that makes Ollama keep everything inside the folder."""
    env = dict(os.environ if base is None else base)
    env["OLLAMA_MODELS"] = models_dir()
    env["OLLAMA_HOST"] = f"127.0.0.1:{port()}"
    env["OLLAMA_NOPRUNE"] = "1"
    env.setdefault("OLLAMA_CONTEXT_LENGTH", str(DEFAULT_CONTEXT))          # an environment value wins
    return env


def find_binary(root: Optional[str] = None) -> Optional[str]:
    """The ``ollama`` program inside the private folder (wherever the archive put it)."""
    root = root or ollama_dir()
    want = "ollama.exe" if P.system() == P.WINDOWS else "ollama"
    for dp, _dn, fs in os.walk(root):
        if os.path.relpath(dp, root).split(os.sep)[0] == "models":
            continue
        if want in fs and os.access(os.path.join(dp, want), os.X_OK):
            return os.path.join(dp, want)
    return None


def checksum_for(sums_text: str, name: str) -> Optional[str]:
    """The SHA-256 listed for ``name`` in a ``sha256sum.txt`` body, or None."""
    for line in sums_text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*").split("/")[-1] == name:
            return parts[0].lower()
    return None


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _get(u: str, timeout: float = 30.0) -> bytes:
    req = urllib.request.Request(u, headers={"User-Agent": "vmd-agent"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


RELEASE_DOWNLOAD = "https://github.com/ollama/ollama/releases/latest/download"


def closest_asset(name: str, assets) -> Optional[str]:
    """The release file that most plausibly is ``name`` under another spelling: same system, same CPU where the name has one, same kind of archive (never a GPU-specific extra)."""
    low = name.lower()
    want_os = next((o for o in ("darwin", "linux", "windows") if o in low), "")
    want_arch = next((a for a in ("arm64", "amd64") if a in low), "")
    ext = ".tar.zst" if low.endswith(".tar.zst") else os.path.splitext(low)[1]
    best = [a for a in assets if want_os in a.lower() and a.lower().endswith(ext) and (not want_arch or want_arch in a.lower())
            and not any(x in a.lower() for x in ("rocm", "jetpack", "sbsa", "cuda"))]
    return sorted(best, key=len)[0] if best else None


def _direct_release(name: str) -> Dict[str, object]:
    """The same file through GitHub's plain download address, which needs no API call (the API refuses an address that asks too often)."""
    url = f"{RELEASE_DOWNLOAD}/{name}"
    try:
        sha = checksum_for(_get(f"{RELEASE_DOWNLOAD}/sha256sum.txt").decode(), name)
    except (urllib.error.URLError, OSError, ValueError):
        sha = None
    return {"tag": None, "url": url, "size": 0, "sha256": sha}


def latest_release(name: str) -> Dict[str, object]:
    """``{"tag", "url", "size", "sha256"}`` for archive ``name`` in Ollama's latest release. If GitHub's API cannot be used, the plain download address is used; if the file was
    renamed, the closest one of the same kind is used."""
    try:
        rel = json.loads(_get(RELEASE_API).decode())
    except (urllib.error.URLError, OSError, ValueError):
        return _direct_release(name)
    assets = {a["name"]: a for a in rel.get("assets", [])}
    if name not in assets:
        alt = closest_asset(name, list(assets))
        if alt is None:
            raise RuntimeError(f"Ollama's latest release ({rel.get('tag_name')}) has no file for this computer (looked for {name}); install Ollama from https://ollama.com/download "
                               "and run `vmd-agent setup` again")
        name = alt
    sha = None
    if "sha256sum.txt" in assets:
        sha = checksum_for(_get(assets["sha256sum.txt"]["browser_download_url"]).decode(), name)
    return {"tag": rel.get("tag_name"), "url": assets[name]["browser_download_url"],
            "size": assets[name].get("size", 0), "sha256": sha}


def download(u: str, dest: str, progress: Optional[Callable[[int], None]] = None) -> None:
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    req = urllib.request.Request(u, headers={"User-Agent": "vmd-agent"})
    done = 0
    with urllib.request.urlopen(req, timeout=60) as r, open(dest + ".part", "wb") as fh:
        for chunk in iter(lambda: r.read(1 << 20), b""):
            fh.write(chunk)
            done += len(chunk)
            if progress:
                progress(done)
    os.replace(dest + ".part", dest)


def _safe_members(names: List[str], dest: str) -> None:
    root = os.path.realpath(dest)
    for n in names:
        if not os.path.realpath(os.path.join(dest, n)).startswith(root + os.sep):
            raise RuntimeError(f"unsafe path in archive: {n}")


def extract(archive: str, dest: str) -> None:
    """Unpack ``.zip``, ``.tgz`` or ``.tar.zst`` into ``dest`` (refusing paths that escape it)."""
    os.makedirs(dest, exist_ok=True)
    if archive.endswith(".zip"):
        with zipfile.ZipFile(archive) as z:
            _safe_members(z.namelist(), dest)
            z.extractall(dest)
    elif archive.endswith((".tgz", ".tar.gz")):
        with tarfile.open(archive) as t:
            _safe_members(t.getnames(), dest)
            t.extractall(dest)
    elif archive.endswith(".tar.zst"):
        tar, zstd = shutil.which("tar"), shutil.which("zstd")
        if tar and zstd:
            r = subprocess.run([tar, "--use-compress-program=zstd -d", "-xf", archive, "-C", dest],
                               capture_output=True, text=True)
            if r.returncode != 0:
                raise RuntimeError("could not unpack: " + r.stderr[:200])
            return
        try:
            import zstandard                                   # type: ignore
        except ImportError:
            raise RuntimeError("this archive is .tar.zst and needs the 'zstd' program or the "
                               "'zstandard' Python package; neither was found")
        with open(archive, "rb") as fh, zstandard.ZstdDecompressor().stream_reader(fh) as rd:
            with tarfile.open(fileobj=rd, mode="r|") as t:
                t.extractall(dest)
    else:
        raise ValueError(f"unknown archive type: {archive}")


def install(confirm_size: Optional[Callable[[str, int], bool]] = None,
            progress: Optional[Callable[[int], None]] = None) -> str:
    """Download, verify and unpack Ollama into the private folder; return the program's path.
    ``confirm_size(name, bytes)`` is asked before the download and may return False to stop.
    Refuses to install an archive whose SHA-256 is missing or does not match."""
    existing = find_binary()
    if existing:
        return existing
    name = asset_name()
    rel = latest_release(name)
    if confirm_size and not confirm_size(name, int(rel["size"] or 0)):
        raise RuntimeError("download declined")
    if not rel["sha256"]:
        raise RuntimeError("the release lists no checksum for this file, so I will not install it")
    tmp = os.path.join(ollama_dir(), "download", name)
    download(str(rel["url"]), tmp, progress)
    if file_sha256(tmp) != rel["sha256"]:
        os.remove(tmp)
        raise RuntimeError("the downloaded file does not match its published checksum; deleted it")
    extract(tmp, ollama_dir())
    os.remove(tmp)
    binary = find_binary()
    if not binary:
        raise RuntimeError("unpacked the archive but found no 'ollama' program in it")
    try:
        os.chmod(binary, 0o755)
    except OSError:
        pass
    settings.save(ollama_mode="private", ollama_port=port())
    return binary


def installed_models(root: Optional[str] = None) -> List[str]:
    """The models downloaded into the private folder, read from the files themselves (the server need not be running): ``name:tag``."""
    base = os.path.join(root or models_dir(), "manifests")
    found: List[str] = []
    if not os.path.isdir(base):
        return found
    for host in sorted(os.listdir(base)):
        for ns in sorted(os.listdir(os.path.join(base, host))):
            nsdir = os.path.join(base, host, ns)
            if not os.path.isdir(nsdir):
                continue
            for name in sorted(os.listdir(nsdir)):
                ndir = os.path.join(nsdir, name)
                if os.path.isdir(ndir):
                    found += [(f"{name}:{tag}" if ns == "library" else f"{ns}/{name}:{tag}") for tag in sorted(os.listdir(ndir)) if not tag.startswith(".")]
    return found


def running(timeout: float = 2.0) -> bool:
    try:
        _get(f"http://127.0.0.1:{port()}/api/version", timeout)
        return True
    except Exception:
        return False


def unload(tag: str, timeout: float = 60.0) -> bool:
    """Ask the model server to free the memory a model holds (a benchmark of several models runs them one after another). True if it answered."""
    import json as _json
    req = urllib.request.Request(f"http://127.0.0.1:{port()}/api/generate", data=_json.dumps({"model": tag, "keep_alive": 0}).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=timeout).read()
        return True
    except Exception:
        return False


def start(wait: float = 20.0) -> bool:
    """Start the private server if it is not already answering. True once it answers."""
    if running():
        return True
    binary = find_binary()
    if not binary:
        return False
    kw: dict = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "env": server_env()}
    if P.system() == P.WINDOWS:
        kw["creationflags"] = 0x00000008 | 0x00000200          # detached, new process group
    else:
        kw["start_new_session"] = True
    os.makedirs(models_dir(), exist_ok=True)
    try:
        subprocess.Popen([binary, "serve"], **kw)
    except OSError:
        return False
    end = time.time() + wait
    while time.time() < end:
        if running():
            return True
        time.sleep(0.5)
    return False


_ANSI = __import__("re").compile(r"\x1b\[[0-9;?]*[A-Za-z]|[\u2800-\u28ff]")


def _plain(line: str) -> str:
    """A progress line without the terminal's cursor and colour codes and its spinner."""
    text = " ".join(_ANSI.sub(" ", line).split())
    if "%" in text and "pulling manifest" in text:               # Ollama redraws two lines in place; keep the one with the progress
        text = " ".join(text.replace("pulling manifest", " ").split())
    return text


def free_gb(path: str) -> Optional[float]:
    """Free space in GB on the disk that holds ``path`` (or the nearest folder above it that exists); None if it cannot be read."""
    p = os.path.abspath(path)
    while p and not os.path.exists(p) and os.path.dirname(p) != p:
        p = os.path.dirname(p)
    try:
        return round(shutil.disk_usage(p).free / 1e9, 1)
    except OSError:
        return None


_WRONG_NAME = re.compile(r"file does not exist|not found|404|manifest unknown|invalid model name|pull model manifest", re.I)


def pull_model(model: str, on_line: Optional[Callable[[str], None]] = None, attempts: int = 3, pause: float = 4.0) -> str:
    """Download ``model`` into the private folder, trying again (a pull resumes where it stopped) when the connection drops. Returns "" on success, else why not: a name
    the library does not have is reported at once, since trying again cannot help."""
    last = ""
    for i in range(max(1, attempts)):
        seen: List[str] = []

        def note(text: str) -> None:
            seen.append(text)
            if on_line:
                on_line(text)
        if pull(model, on_line=note) and model in installed_models():
            return ""
        last = (seen[-1] if seen else "no answer from the model server")[:200]
        if _WRONG_NAME.search(last):
            return f"the Ollama library has no model called '{model}' ({last})"
        if i + 1 < attempts:
            if on_line:
                on_line(f"the download stopped ({last}); trying again, it resumes where it stopped")
            time.sleep(pause)
    return f"the download did not finish ({last}). Check the internet connection and run the same command again: it resumes where it stopped"


def pull(model: str, on_line: Optional[Callable[[str], None]] = None) -> bool:
    """Download a model into the private models folder. With ``on_line`` the progress text is passed to it as it arrives (about twice a second);
    without, it goes to the terminal as before."""
    binary = find_binary()
    if not binary:
        return False
    if on_line is None:
        return subprocess.run([binary, "pull", model], env=server_env()).returncode == 0
    proc = subprocess.Popen([binary, "pull", model], env=server_env(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    last, buf = 0.0, b""
    assert proc.stdout is not None
    while True:
        chunk = proc.stdout.read1(512) if hasattr(proc.stdout, "read1") else proc.stdout.read(512)
        if not chunk:
            break
        buf += chunk
        parts = buf.replace(b"\r", b"\n").split(b"\n")
        buf = parts.pop()
        text = next((_plain(p.decode("utf-8", "replace")) for p in reversed(parts) if _plain(p.decode("utf-8", "replace"))), "")
        if text and time.time() - last > 0.5:
            last = time.time()
            on_line(text[:160])
    return proc.wait() == 0
