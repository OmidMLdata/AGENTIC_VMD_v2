"""``vmd-agent ui``: the toolkit in a web page on your own computer.

One page with your files on the left, a chat in the middle (every model call and every tool call shown with the
seconds it took) and the whole jobs (workflows) in a second tab. It is the same tools and the same checks as the
terminal chat; nothing here measures or decides anything.

It runs only on this computer: the server listens on 127.0.0.1, answers only requests addressed to it by that name,
and wants a one-time key (printed as part of the address, then kept in a cookie) so that no other web page you have
open can talk to it. It can read and write only inside your files folder (the sandbox of :mod:`vmd_agent.security`).
Standard library only: no web framework to install.
"""
from __future__ import annotations

import hmac
import http.server
import json
import mimetypes
import os
import queue
import re
import secrets
import socketserver
import threading
import time
import webbrowser
from typing import Callable, Optional
from urllib.parse import parse_qs, quote, unquote, urlparse

from vmd_agent import agent as agent_mod, progress, security, toolset
from vmd_agent.structure import viewer

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui_assets")
SCRIPTS = {"style.css": "text/css; charset=utf-8", **{n: "text/javascript; charset=utf-8" for n in ("app.js", "viewer.js", "selection.js", "commands.js", "markdown.js")}}
MAX_UPLOAD = 1_000_000_000                       # bytes
KINDS = {".pdb": "structure", ".cif": "structure", ".mmcif": "structure", ".gro": "structure", ".psf": "structure",
         ".mol2": "structure", ".xyz": "structure", ".prmtop": "structure", ".dcd": "trajectory", ".xtc": "trajectory",
         ".trr": "trajectory", ".nc": "trajectory", ".png": "image", ".jpg": "image", ".jpeg": "image", ".gif": "image",
         ".mp4": "video", ".mov": "video", ".webm": "video", ".dx": "map", ".mrc": "map", ".ccp4": "map", ".cube": "map",
         ".md": "report", ".html": "report", ".json": "data", ".tcl": "script", ".namd": "script"}
#: tools a page may run directly on a file (read-only looks at it); everything else goes through the chat or a workflow
LOOKS = {"inspect_files": lambda p: {"paths": [p]}, "detect_system": lambda p: {"topology": p},
         "structure_stats": lambda p: {"topology": p}, "probe_video": lambda p: {"video": p}}


def kind_of(name: str) -> str:
    return KINDS.get(os.path.splitext(name)[1].lower(), "other")


def list_files(root: str, sub: str = "", limit: int = 500) -> dict:
    """One folder of the files folder: its files (newest first) and its folders (with how many files each holds, counting
    everything below it). Hidden entries are left out. ``sub`` is relative to ``root``."""
    here = os.path.join(root, sub) if sub else root
    files, folders = [], []
    for n in os.listdir(here):
        if n.startswith(".") or n == "__pycache__":
            continue
        full = os.path.join(here, n)
        rel = os.path.relpath(full, root).replace(os.sep, "/")
        try:
            st = os.stat(full)
        except OSError:
            continue
        if os.path.isdir(full):
            count = sum(len(fs) for _, _, fs in os.walk(full))
            folders.append({"path": rel, "n_files": count, "modified": st.st_mtime})
        else:
            files.append({"path": rel, "size": st.st_size, "kind": kind_of(n), "modified": st.st_mtime})
    files.sort(key=lambda f: -f["modified"])
    folders.sort(key=lambda f: -f["modified"])
    return {"files": files[:limit], "folders": folders[:limit]}


def all_files(root: str) -> list:
    """Every file below ``root`` (the page offers these when it asks you to pick a file for a job)."""
    out = []
    for base, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
        for n in names:
            if not n.startswith("."):
                full = os.path.join(base, n)
                out.append({"path": os.path.relpath(full, root).replace(os.sep, "/"), "kind": kind_of(n)})
    return out[:2000]


def images_in(result, root: str, found: Optional[list] = None) -> list:
    """Image files that a tool result names, as paths inside ``root`` (so the page can show them)."""
    found = [] if found is None else found
    if isinstance(result, dict):
        for v in result.values():
            images_in(v, root, found)
    elif isinstance(result, list):
        for v in result[:50]:
            images_in(v, root, found)
    elif isinstance(result, str) and kind_of(result) == "image" and os.path.isabs(result):
        try:
            full = security.check_path(result)
            if full and os.path.isfile(full) and security.is_within(full, root) and len(found) < 12:
                rel = os.path.relpath(full, root).replace(os.sep, "/")
                if rel not in found:
                    found.append(rel)
        except Exception:
            pass
    return found


class State:
    """Everything the page's requests share: the sandbox, the model connection, the chat, and one-job-at-a-time."""

    def __init__(self, data_dir: str, base_url: str, model: str, api_key: Optional[str], tools: str = "all"):
        self.root = os.path.realpath(data_dir)
        os.makedirs(self.root, exist_ok=True)
        os.environ[security.ENV_ROOTS] = self.root
        os.chdir(self.root)
        self.base_url, self.model, self.api_key, self.tools = base_url, model, api_key, tools
        self.token = secrets.token_urlsafe(24)
        self.busy = threading.Lock()
        self.session = agent_mod.Agent(base_url, model, api_key, tools=tools, echo=lambda m: None)
        self.models: dict = {}                       # structures opened in the viewer, most recent last
        self.model_lock = threading.Lock()

    def model_for(self, topology: str, trajectory: Optional[str] = None) -> "viewer.Model":
        """The viewer's model of a structure (and trajectory); opened once, then kept (the last eight)."""
        key = (topology, trajectory)
        with self.model_lock:
            if key not in self.models:
                self.models[key] = viewer.Model(topology, trajectory)
                while len(self.models) > 8:
                    self.models.pop(next(iter(self.models)))
            return self.models[key]

    def set_tools(self, profile: str) -> None:
        self.tools = profile
        self.session = agent_mod.Agent(self.base_url, self.model, self.api_key, tools=profile, echo=lambda m: None)

    def status(self) -> dict:
        from vmd_agent import __version__
        from vmd_agent.environment import probe_environment
        env = probe_environment()
        problem = agent_mod.check_connection(self.base_url, self.model, self.api_key)
        return {"version": __version__, "data_dir": self.root, "model": self.model, "server": self.base_url,
                "model_ready": problem is None, "model_problem": " ".join(problem) if problem else None,
                "vmd": env.get("vmd_path"), "vmd_version": env.get("vmd_version"), "tachyon": bool(env.get("tachyon_path")),
                "ffmpeg": bool(env.get("ffmpeg")), "n_tools": len(toolset.TOOLS), "tools_in_chat": len(self.session.names), "profile": self.tools,
                "profiles": {**{k: len(v) for k, v in toolset.PROFILES.items()}, "auto": 0},
                "clock": self.session.clock}


class Handler(http.server.BaseHTTPRequestHandler):
    state: State
    server_version = "vmd-agent-ui"

    def log_message(self, *a):
        pass

    # ---- plumbing
    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").lower()
        port = self.server.server_address[1]
        if host not in (f"127.0.0.1:{port}", f"localhost:{port}"):
            return False
        origin = self.headers.get("Origin")
        return not origin or origin in (f"http://127.0.0.1:{port}", f"http://localhost:{port}")

    def _authorised(self) -> bool:
        cookie = self.headers.get("Cookie") or ""
        m = re.search(r"(?:^|;\s*)vmd_ui=([\w-]+)", cookie)
        return bool(m) and hmac.compare_digest(m.group(1), self.state.token)

    def _send(self, code: int, body: bytes, ctype: str = "application/json", extra: Optional[dict] = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(obj, default=str).encode())

    def _body(self, limit: int = 1_000_000) -> bytes:
        n = int(self.headers.get("Content-Length") or 0)
        if n > limit:
            raise ValueError("request too large")
        return self.rfile.read(n)

    def _gate(self) -> bool:
        if not self._host_ok():
            self._send(403, b"This page answers only to http://127.0.0.1 and http://localhost.", "text/plain")
            return False
        return True

    # ---- GET
    def do_GET(self):
        if not self._gate():
            return
        url = urlparse(self.path)
        key = parse_qs(url.query).get("k", [""])[0]
        if key and hmac.compare_digest(key, self.state.token):         # the address printed in the terminal: set the cookie, go to /
            self._send(302, b"", "text/plain", {"Location": "/", "Set-Cookie": f"vmd_ui={self.state.token}; HttpOnly; SameSite=Strict; Path=/"})
            return
        if not self._authorised():
            self._send(403, b"Open the address that vmd-agent ui printed in your terminal: it has the one-time key.", "text/plain")
            return
        if url.path == "/":
            with open(os.path.join(ASSETS, "index.html"), "rb") as fh:
                self._send(200, fh.read(), "text/html; charset=utf-8",
                           {"Content-Security-Policy": "default-src 'self'; img-src 'self' data:; media-src 'self'; frame-src 'self'"})
        elif url.path.startswith("/assets/") and url.path[8:] in SCRIPTS:
            with open(os.path.join(ASSETS, url.path[8:]), "rb") as fh:
                self._send(200, fh.read(), SCRIPTS[url.path[8:]])
        elif url.path in ("/api/structure", "/api/frame"):
            self._structure(url.path, parse_qs(url.query))
        elif url.path == "/api/status":
            self._json(self.state.status())
        elif url.path == "/api/files":
            sub = parse_qs(url.query).get("dir", [""])[0]
            try:
                if sub:
                    security.check_path(os.path.join(self.state.root, sub))
                listing = list_files(self.state.root, sub)
            except (OSError, security.SecurityError):
                return self._json({"error": "no such folder"}, 404)
            self._json({"root": self.state.root, "dir": sub, **listing, "everything": all_files(self.state.root) if not sub else None})
        elif url.path == "/api/workflows":
            self._json(toolset.TOOLS["list_workflows"]())
        elif url.path.startswith("/files/"):
            self._serve_file(unquote(url.path[len("/files/"):]))
        else:
            self._send(404, b"not found", "text/plain")

    def _structure(self, which: str, q: dict) -> None:
        """The atoms of a structure for the viewer, or the coordinates of one frame."""
        try:
            top = security.check_path(os.path.join(self.state.root, q.get("path", [""])[0]))
            traj_rel = q.get("traj", [""])[0]
            traj = security.check_path(os.path.join(self.state.root, traj_rel)) if traj_rel else None
            for f in (top, traj):
                if f and not (os.path.isfile(f) and security.is_within(f, self.state.root)):
                    raise FileNotFoundError(os.path.basename(f))
            model = self.state.model_for(top, traj)
            if which == "/api/frame":
                i = int(q.get("i", ["0"])[0])
                with self.state.model_lock:
                    xyz = model.frame(i)
                return self._json({"i": i, "xyz": [round(float(x), 2) for x in xyz.ravel()]})
            with self.state.model_lock:
                return self._json(model.describe())
        except (security.SecurityError, FileNotFoundError):
            return self._json({"error": "no such file in your files folder"}, 404)
        except Exception as e:                                         # a file MDAnalysis cannot read is a message, not a crash
            return self._json({"error": f"cannot show this file: {type(e).__name__}: {str(e)[:200]}"}, 415)

    def _serve_file(self, rel: str) -> None:
        try:
            full = security.check_path(os.path.join(self.state.root, rel))
        except Exception:
            self._send(403, b"outside the files folder", "text/plain")
            return
        if not full or not os.path.isfile(full) or not security.is_within(full, self.state.root):
            self._send(404, b"no such file", "text/plain")
            return
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        extra = {}
        if ctype == "text/html":                       # a report: pictures and styling, no scripts
            extra["Content-Security-Policy"] = "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'"
        elif not ctype.startswith(("image/", "video/", "application/json")) and ctype != "text/plain":
            ctype = "text/plain; charset=utf-8" if os.path.getsize(full) < 5_000_000 and kind_of(full) in ("structure", "script", "data", "report") else ctype
        with open(full, "rb") as fh:
            data = fh.read()
        self._send(200, data, ctype, extra)

    # ---- POST
    def do_POST(self):
        if not self._gate():
            return
        if not self._authorised():
            self._send(403, b"not authorised", "text/plain")
            return
        url = urlparse(self.path)
        try:
            if url.path == "/api/upload":
                return self._upload(parse_qs(url.query).get("name", [""])[0])
            payload = json.loads(self._body() or b"{}")
            if url.path == "/api/chat":
                return self._stream(lambda emit: self._chat(payload, emit))
            if url.path == "/api/workflow":
                return self._stream(lambda emit: self._workflow(payload, emit))
            if url.path == "/api/look":
                return self._look(payload)
            if url.path == "/api/profile":
                profile = str(payload.get("tools") or "")
                if profile != "auto" and profile not in toolset.PROFILES:
                    return self._json({"error": f"tools must be one of {', '.join(list(toolset.PROFILES) + ['auto'])}"}, 400)
                if self.state.busy.locked():
                    return self._json({"error": "another job is still running; wait for it to finish"}, 409)
                self.state.set_tools(profile)
                return self._json(self.state.status())
            if url.path == "/api/reset":
                self.state.session.reset()
                return self._json({"ok": True})
            self._send(404, b"not found", "text/plain")
        except (ValueError, json.JSONDecodeError) as e:
            self._json({"error": str(e)}, 400)

    def _upload(self, name: str) -> None:
        name = os.path.basename(unquote(name)).strip().lstrip(".")
        if not name or not re.fullmatch(r"[\w .()+@=,-]{1,120}", name):
            return self._json({"error": "a file name with letters, digits, spaces and . _ - ( ) only"}, 400)
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_UPLOAD:
            return self._json({"error": f"larger than {MAX_UPLOAD // 10**6} MB"}, 413)
        stem, ext = os.path.splitext(name)
        dest, i = os.path.join(self.state.root, name), 1
        while os.path.exists(dest):                    # never overwrite what is there
            dest = os.path.join(self.state.root, f"{stem}_{i}{ext}")
            i += 1
        left = n
        with open(dest, "wb") as fh:
            while left > 0:
                chunk = self.rfile.read(min(1 << 20, left))
                if not chunk:
                    break
                fh.write(chunk)
                left -= len(chunk)
        self._json({"ok": True, "path": os.path.relpath(dest, self.state.root).replace(os.sep, "/"), "bytes": n})

    def _look(self, payload: dict) -> None:
        tool, rel = payload.get("tool"), str(payload.get("path") or "")
        if tool not in LOOKS:
            return self._json({"error": f"the page can run only: {', '.join(LOOKS)}"}, 400)
        started = time.time()
        full = os.path.join(self.state.root, rel)
        try:
            result = toolset.TOOLS[tool](**LOOKS[tool](full))
        except Exception as e:
            result = {"error": f"{type(e).__name__}: {e}"}
        self._json({"tool": tool, "seconds": round(time.time() - started, 3), "result": result})

    # ---- one job at a time, streamed as server-sent events
    def _stream(self, work: Callable[[Callable[[dict], None]], None]) -> None:
        if not self.state.busy.acquire(blocking=False):
            return self._json({"error": "another job is still running; wait for it to finish"}, 409)
        events: "queue.Queue[Optional[dict]]" = queue.Queue()

        def runner():
            try:
                work(events.put)
            except Exception as e:
                events.put({"type": "error", "text": f"{type(e).__name__}: {e}"})
            finally:
                events.put(None)
        threading.Thread(target=runner, daemon=True).start()
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            while True:
                ev = events.get()
                if ev is None:
                    break
                self.wfile.write(b"data: " + json.dumps(ev, default=str).encode() + b"\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass                                       # the page was closed; the job finishes on its own
        finally:
            self.state.busy.release()

    def _chat(self, payload: dict, emit: Callable[[dict], None]) -> None:
        text = str(payload.get("message") or "").strip()
        if not text:
            return emit({"type": "error", "text": "type a question first"})
        s, root = self.state.session, self.state.root

        def on_event(ev: dict) -> None:
            if ev["type"] == "tool_end":
                result = ev.pop("result", None)
                ev = {**ev, "images": images_in(result, root), "preview": json.dumps(agent_mod.digest(result), default=str)[:2400]}
            emit(ev)
        s.on_event = on_event
        try:
            answer = s.ask(text, on_token=lambda tok: emit({"type": "token", "text": tok}))
            emit({"type": "answer", "text": answer, "streamed": bool(s.streamed), "clock": s.last_turn, "line": agent_mod.clock_line(s.last_turn)})
        except agent_mod.LLMError as e:
            emit({"type": "error", "text": str(e)})
        finally:
            s.on_event = None

    def _workflow(self, payload: dict, emit: Callable[[dict], None]) -> None:
        name, files = str(payload.get("name") or ""), [os.path.join(self.state.root, f) for f in payload.get("files") or []]
        out = os.path.join(self.state.root, f"{name}_report")
        started = time.time()
        with progress.listen(lambda m, f=None: emit({"type": "tool_progress", "name": name, "text": str(m), "fraction": f})):
            result = toolset.TOOLS["run_workflow"](name=name, files=files, out_dir=out)
        rel = lambda p: os.path.relpath(p, self.state.root).replace(os.sep, "/") if isinstance(p, str) and os.path.isabs(p) else p   # noqa: E731
        emit({"type": "workflow", "seconds": round(time.time() - started, 3), "result": result,
              "report_md": rel(result.get("report")), "report_html": rel(result.get("report_html")),
              "images": images_in(result, self.state.root)})


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


def make_server(data_dir: str, port: int = 0, base_url: Optional[str] = None, model: Optional[str] = None,
                api_key: Optional[str] = None, tools: str = "all") -> Server:
    """The server, bound to this computer only (port 0 picks a free one). ``server.state.token`` is the one-time key."""
    base_url, model, api_key = agent_mod.resolve_connection(base_url, model, api_key)
    state = State(data_dir, base_url, model, api_key, tools)
    handler = type("BoundHandler", (Handler,), {"state": state})
    srv = Server(("127.0.0.1", port), handler)
    srv.state = state                                  # type: ignore[attr-defined]
    return srv


def address(srv: Server) -> str:
    return f"http://127.0.0.1:{srv.server_address[1]}/?k={quote(srv.state.token)}"       # type: ignore[attr-defined]


def main(data_dir: Optional[str] = None, port: int = 0, open_browser: bool = True, base_url: Optional[str] = None,
         model: Optional[str] = None, api_key: Optional[str] = None, tools: str = "all", say: Callable = lambda m: print(m, flush=True)) -> int:
    from vmd_agent import settings
    data_dir = data_dir or (security.allowed_roots() or [None])[0] or settings.get("data_dir") or os.getcwd()
    try:
        srv = make_server(data_dir, port, base_url, model, api_key, tools)
    except OSError as e:
        say(f"vmd-agent ui: cannot listen on port {port}: {e}")
        return 1
    url = address(srv)
    say(f"vmd-agent ui is running on this computer only.\n  files folder: {srv.state.root}\n  model: {srv.state.model} @ {srv.state.base_url}\n"   # type: ignore[attr-defined]
        f"\nOpen this address (it has a one-time key):\n  {url}\n\nPress Ctrl+C to stop.")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        say("\nstopped.")
    finally:
        srv.server_close()
    return 0

