"""A live link to a real VMD window: the agent drives the VMD you are looking at.

The other tools run VMD headless and return numbers and pictures. This module starts (or finds) a **VMD with its window** and gives the
agent a small, fixed set of commands for it: load a molecule, add or change a representation, set the display, move the view, step
through frames, ask what is selected, take a picture of the window. Everything seen is VMD's own drawing.

How it works. :func:`open_window` starts VMD with ``vmdkit/live_bridge.tcl``, which listens on 127.0.0.1 on a random port and
accepts only requests that carry a one-time token kept in a file only you can read. A request is ``verb arg ...``: the verb is one of
:data:`VERBS` and every argument is checked here and again inside VMD; nothing is ever evaluated as Tcl, and there is no verb for
running Tcl, a program or a file. See the header of the bridge for the details.

Nothing here imports the rest of the toolkit except the settings (where the link's file lives), the security checks and the VMD finder.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import signal
import socket
import subprocess
import time
from typing import Any, Dict, List, Optional, Sequence

from vmd_agent import security, settings
from vmd_agent.environment import find_vmd, vmd_runtime_env

BRIDGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vmdkit", "live_bridge.tcl")

#: the commands the bridge accepts (the same list is written into the bridge, which refuses any other)
VERBS = ("ping", "state", "mol_list", "mol_new", "mol_addfile", "mol_delete", "mol_top", "mol_rename", "mol_show", "mol_clear",
         "rep_list", "rep_add", "rep_modify", "rep_delete", "display", "view", "anim", "query", "measure",
         "snapshot", "save_state")
STYLES = ("Lines", "Bonds", "DynamicBonds", "HBonds", "Points", "VDW", "CPK", "Licorice", "Beads", "Tube", "Trace", "Ribbons",
          "NewRibbons", "Cartoon", "NewCartoon", "PaperChain", "Twister", "QuickSurf", "MSMS", "Surf", "Dotted", "Solvent",
          "Isosurface", "VolumeSlice")
COLORS = ("Name", "Type", "Element", "ResName", "ResType", "ResID", "Chain", "SegName", "Structure", "Molecule", "Beta", "Occupancy",
          "Mass", "Charge", "Index", "Backbone", "Fragment", "Position")
MATERIALS = ("Opaque", "Transparent", "BrushedMetal", "Diffuse", "Ghost", "Glass1", "Glass2", "Glass3", "Glossy", "HardPlastic",
             "MetallicPastel", "Steel", "Translucent", "Edgy", "EdgyShiny", "AOShiny", "AOChalky", "AOEdgy", "BlownGlass",
             "GlassBubble", "RTChrome")
FILETYPES = ("pdb", "psf", "gro", "mol2", "xyz", "pdbx", "parm7", "pqr", "pdbqt", "lammps", "lammpstrj", "dcd", "xtc", "trr", "netcdf",
             "crd", "dx", "ccp4", "cube", "situs", "namdbin")
BACKGROUNDS = ("black", "white", "gray", "silver", "blue", "red", "orange", "yellow", "tan", "green", "cyan", "purple", "pink", "lime",
               "mauve", "ochre", "iceblue")
AXES = ("Off", "LowerLeft", "LowerRight", "UpperLeft", "UpperRight", "Origin")
#: display setting -> the values it takes ("on/off", "number", or a list of names)
DISPLAY = {"projection": ("Perspective", "Orthographic"), "depthcue": "on/off", "cuestart": "number", "cueend": "number",
           "cuedensity": "number", "background": BACKGROUNDS, "axes": AXES, "shadows": "on/off", "ambientocclusion": "on/off",
           "aoambient": "number", "aodirect": "number", "culling": "on/off", "antialias": "on/off"}
MAP_TYPES = {"dx": "dx", "mrc": "ccp4", "map": "ccp4", "ccp4": "ccp4", "cube": "cube", "cub": "cube", "situs": "situs", "sit": "situs"}
_TYPE_BY_EXT = {"pdb": "pdb", "ent": "pdb", "psf": "psf", "gro": "gro", "mol2": "mol2", "xyz": "xyz", "dcd": "dcd", "xtc": "xtc", "trr": "trr",
                "prmtop": "parm7", "parm7": "parm7", "nc": "netcdf", "netcdf": "netcdf", "data": "lammps", "lammps": "lammps",
                "lammpstrj": "lammpstrj", "cif": "pdbx", "mmcif": "pdbx", "pqr": "pqr", "pdbqt": "pdbqt", "crd": "crd", "namdbin": "namdbin",
                **MAP_TYPES}
#: structure files that hold coordinates of their own: with a trajectory after them, VMD's frame 0 is the structure itself and is dropped
HAS_COORDS = {".pdb", ".pdbqt", ".gro", ".mol2", ".xyz", ".cif", ".mmcif", ".pqr", ".crd", ".data", ".lammps"}

_SAFE_ARG = re.compile(r"[A-Za-z0-9_./:+@=,%-]")


class LinkError(RuntimeError):
    """The VMD window could not be reached, or VMD refused a command (its message says why)."""


def file_type(path: str) -> str:
    """The type VMD wants for a file, from its extension."""
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    kind = _TYPE_BY_EXT.get(ext)
    if kind is None:
        raise security.InvalidInput(f"VMD cannot be given a .{ext} file here; use one of: " + ", ".join(sorted(set(_TYPE_BY_EXT))))
    return kind


# ------------------------------------------------------------------------------------------------ the request format
def quote(arg: Any) -> str:
    """One word of a Tcl list that stays one word and means exactly its text (backslash before anything that is not plain). Control
    characters are refused: a request is one line."""
    text = str(arg)
    if any(ord(c) < 32 or ord(c) == 127 for c in text):
        raise security.InvalidInput("a command argument cannot contain a control character")
    if text == "":
        return '{}'
    return "".join(c if _SAFE_ARG.fullmatch(c) else "\\" + c for c in text)


def request_line(token: str, rid: int, verb: str, args: Sequence[Any]) -> str:
    if verb not in VERBS:
        raise security.InvalidInput(f"not a VMD window command: {verb}")
    return " ".join([quote(token), str(int(rid)), verb, *[quote(a) for a in args]]) + "\n"


def bridge_script(port: int, token: str, headless: bool = False) -> str:
    """The bridge, with this session's port and token and the lists of allowed names filled in."""
    with open(BRIDGE, encoding="utf-8") as fh:
        text = fh.read()
    fill = {"@TOKEN@": token, "@PORT@": str(int(port)), "@HEADLESS@": "1" if headless else "0", "@STYLES@": " ".join(STYLES),
            "@COLORS@": " ".join(COLORS), "@MATERIALS@": " ".join(MATERIALS), "@FILETYPES@": " ".join(FILETYPES),
            "@BGCOLORS@": " ".join(BACKGROUNDS)}
    for k, v in fill.items():
        text = text.replace(k, v)
    return text


# ------------------------------------------------------------------------------------------------ the link
class Link:
    """A connection to a running bridge: ``call(verb, *args)`` returns VMD's answer (parsed JSON) or raises :class:`LinkError`."""

    def __init__(self, port: int, token: str, pid: Optional[int] = None, headless: bool = False):
        self.port, self.token, self.pid, self.headless = int(port), token, pid, headless
        self._id = 0

    def call(self, verb: str, *args: Any, timeout: float = 120.0) -> Any:
        self._id += 1
        line = request_line(self.token, self._id, verb, args)
        try:
            with socket.create_connection(("127.0.0.1", self.port), timeout=timeout) as s:
                s.settimeout(timeout)
                s.sendall(line.encode("utf-8"))
                buf = b""
                while not buf.endswith(b"\n"):
                    chunk = s.recv(65536)
                    if not chunk:
                        break
                    buf += chunk
        except (OSError, socket.timeout) as e:
            raise LinkError(f"the VMD window does not answer ({e}). It may have been closed: open it again.")
        if not buf:
            raise LinkError("the VMD window closed the connection (a wrong token, or VMD is shutting down)")
        try:
            reply = json.loads(buf.decode("utf-8"))
        except ValueError:
            raise LinkError("VMD sent an answer that is not understood")
        if not reply.get("ok"):
            raise LinkError(str(reply.get("error") or "VMD refused the command"))
        return reply.get("result")


# ------------------------------------------------------------------------------------------------ starting, finding, stopping
def link_dir() -> str:
    d = os.path.join(settings.home_dir(), "live")
    os.makedirs(d, exist_ok=True)
    try:
        os.chmod(d, 0o700)
    except OSError:
        pass
    return d


def _state_file() -> str:
    """Where the link is recorded (reading it never creates the folder: only starting a window does)."""
    return os.path.join(settings.home_dir(), "live", "link.json")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _write_private(path: str, text: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)


def _forget() -> None:
    try:
        os.remove(_state_file())
    except OSError:
        pass


def _kill_group(pid: Optional[int]) -> None:
    if not pid or os.name == "nt":
        return
    try:
        os.killpg(pid, signal.SIGTERM)
    except (OSError, ProcessLookupError):
        pass


def attach(timeout: float = 2.0) -> Optional[Link]:
    """The link to the VMD window vmd-agent started earlier (by any process), if it still answers; otherwise None (and what was left of it is cleaned up)."""
    try:
        with open(_state_file(), encoding="utf-8") as fh:
            st = json.load(fh)
    except (OSError, ValueError):
        return None
    link = Link(st["port"], st["token"], st.get("pid"), bool(st.get("headless")))
    try:
        link.call("ping", timeout=timeout)
        return link
    except LinkError:
        _kill_group(st.get("pid"))
        _forget()
        return None


def open_window(vmd_path: Optional[str] = None, headless: bool = False, wait: float = 60.0) -> Link:
    """Attach to the VMD window that is already open, or start one. ``headless`` starts VMD with no window (the same commands work; used by
    tests and on a machine with no display): pictures then come from VMD's built-in ray tracer."""
    headless = headless or os.environ.get("VMD_AGENT_WINDOW_HEADLESS") == "1"        # tests and benchmarks: the same commands, no window on anyone's screen
    existing = attach()
    if existing is not None and existing.headless == headless:
        return existing
    if existing is not None:
        stop()
    vmd = find_vmd(vmd_path)
    if not vmd:
        raise LinkError("VMD was not found. Install VMD (https://www.ks.uiuc.edu/Research/vmd/) and run `vmd-agent setup` (or `vmd-agent setup --vmd /path/to/VMD` if it is somewhere unusual), or set VMD_BIN.")
    if not headless and os.name == "posix" and os.uname().sysname == "Linux" and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        raise LinkError("this computer has no display to open a VMD window on")
    port, token = _free_port(), secrets.token_urlsafe(24)
    script = os.path.join(link_dir(), "bridge.tcl")
    _write_private(script, bridge_script(port, token, headless))
    logfile = open(os.path.join(link_dir(), "vmd.log"), "ab")
    args = ["-e", script] + (["-dispdev", "text"] if headless else ["-nt"])
    kw: Dict[str, Any] = {"stdout": logfile, "stderr": logfile, "stdin": subprocess.DEVNULL, "env": vmd_runtime_env(vmd)}
    if os.name == "posix":
        # VMD quits when its input ends, so give it an input that never does: it then lives until its window is closed
        cmd = ["sh", "-c", 'tail -f /dev/null | exec "$0" "$@"', vmd, *args]
        kw["start_new_session"] = True
    else:
        cmd = [vmd, *args]
        kw["creationflags"] = 0x00000008 | 0x00000200
    proc = subprocess.Popen(cmd, **kw)
    link = Link(port, token, proc.pid, headless)
    end = time.time() + wait
    while time.time() < end:
        if proc.poll() is not None:
            raise LinkError(f"VMD exited right away (see {os.path.join(link_dir(), 'vmd.log')})")
        try:
            link.call("ping", timeout=2.0)
            _write_private(_state_file(), json.dumps({"port": port, "token": token, "pid": proc.pid, "headless": headless, "vmd": vmd}))
            return link
        except LinkError:
            time.sleep(0.4)
    _kill_group(proc.pid)
    raise LinkError("VMD started but did not answer in time")


def stop() -> bool:
    """Close the VMD window vmd-agent started. True if there was one."""
    try:
        with open(_state_file(), encoding="utf-8") as fh:
            st = json.load(fh)
    except (OSError, ValueError):
        return False
    _kill_group(st.get("pid"))
    _forget()
    return True


def status() -> Dict[str, Any]:
    """Is a VMD window open (started by vmd-agent), and what does it hold? Never starts one."""
    link = attach()
    vmd = find_vmd()
    if link is None:
        return {"installed": bool(vmd), "vmd_path": vmd, "connected": False}
    try:
        return {"installed": True, "vmd_path": vmd, "connected": True, "headless": link.headless, **link.call("state")}
    except LinkError:
        return {"installed": bool(vmd), "vmd_path": vmd, "connected": False}


# ------------------------------------------------------------------------------------------------ the safe command layer
def _int(value: Any, what: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        raise security.InvalidInput(f"{what} must be a whole number")


def _num(value: Any, what: str) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise security.InvalidInput(f"{what} must be a number")
    if v != v or v in (float("inf"), float("-inf")):
        raise security.InvalidInput(f"{what} must be finite")
    return v


def _choice(value: Any, allowed: Sequence[str], what: str) -> str:
    if value not in allowed:
        raise security.InvalidInput(f"{what} must be one of: {', '.join(allowed)}")
    return str(value)


def _color(value: Any) -> str:
    if isinstance(value, str) and re.fullmatch(r"ColorID \d{1,4}", value):
        return value
    return _choice(value, COLORS, "color (or 'ColorID <n>')")


def _selection(text: Any) -> str:
    t = security.tcl_selection(str(text))
    if not t.strip():
        raise security.InvalidInput("the selection is empty")
    return t


def _path(path: str) -> str:
    """An absolute path inside the folders the toolkit may use, in the form the bridge accepts."""
    return security.tcl_path(security.check_path(path))


def _params(values: Optional[Sequence[Any]]) -> List[str]:
    out = []
    for v in values or []:
        f = _num(v, "a style parameter")
        out.append(str(int(f)) if f == int(f) else repr(f))
    if len(out) > 8:
        raise security.InvalidInput("a style has at most 8 parameters")
    return out


class Window:
    """The commands for a VMD window. Each method validates its arguments, then sends one request; the answer is VMD's own."""

    def __init__(self, link: Link):
        self.link = link

    # -- state
    def state(self) -> dict:
        return self.link.call("state")

    def molecules(self) -> list:
        return self.link.call("mol_list")

    # -- molecules
    def new_molecule(self, path: str, kind: Optional[str] = None) -> dict:
        p = _path(path)
        return self.link.call("mol_new", p, _choice(kind or file_type(p), FILETYPES, "file type"))

    def add_file(self, molecule: int, path: str, kind: Optional[str] = None, drop_first: bool = False) -> dict:
        p = _path(path)
        return self.link.call("mol_addfile", _int(molecule, "molecule"), p, _choice(kind or file_type(p), FILETYPES, "file type"), "1" if drop_first else "0")

    def delete(self, molecule: int) -> dict:
        return self.link.call("mol_delete", _int(molecule, "molecule"))

    def top(self, molecule: int) -> dict:
        return self.link.call("mol_top", _int(molecule, "molecule"))

    def rename(self, molecule: int, name: str) -> dict:
        return self.link.call("mol_rename", _int(molecule, "molecule"), str(name))

    def show(self, molecule: int, shown: bool) -> dict:
        return self.link.call("mol_show", _int(molecule, "molecule"), "on" if shown else "off")

    def clear(self) -> dict:
        return self.link.call("mol_clear")

    # -- representations
    def reps(self, molecule: int) -> list:
        return self.link.call("rep_list", _int(molecule, "molecule"))

    def add_rep(self, molecule: int, selection: str = "all", style: str = "NewCartoon", color: str = "Name", material: str = "Opaque",
                params: Optional[Sequence[Any]] = None) -> dict:
        return self.link.call("rep_add", _int(molecule, "molecule"), _selection(selection), _choice(style, STYLES, "style"), _color(color),
                              _choice(material, MATERIALS, "material"), *_params(params))

    def modify_rep(self, molecule: int, rep: int, key: str, value: Any, params: Optional[Sequence[Any]] = None) -> dict:
        key = _choice(key, ("selection", "style", "color", "material", "show"), "what to change")
        if key == "selection":
            value = _selection(value)
        elif key == "style":
            value = _choice(value, STYLES, "style")
        elif key == "color":
            value = _color(value)
        elif key == "material":
            value = _choice(value, MATERIALS, "material")
        else:
            value = "on" if value in (True, "on", "true", "1", 1) else "off"
        return self.link.call("rep_modify", _int(molecule, "molecule"), _int(rep, "representation"), key, value, *(_params(params) if key == "style" else []))

    def delete_rep(self, molecule: int, rep: int) -> dict:
        return self.link.call("rep_delete", _int(molecule, "molecule"), _int(rep, "representation"))

    # -- display, view, animation
    def display(self, setting: str, value: Any) -> dict:
        allowed = DISPLAY.get(setting)
        if allowed is None:
            raise security.InvalidInput("display setting must be one of: " + ", ".join(DISPLAY))
        if allowed == "on/off":
            value = "on" if value in (True, "on", "true", "1", 1) else "off"
        elif allowed == "number":
            value = repr(_num(value, setting))
        else:
            value = _choice(value, allowed, setting)
        return self.link.call("display", setting, value)

    def view(self, kind: str, *args: Any) -> dict:
        kind = _choice(kind, ("reset", "rotate", "scale", "translate", "center", "save", "restore"), "view action")
        if kind == "rotate":
            axis, deg = args
            return self.link.call("view", "rotate", _choice(axis, ("x", "y", "z"), "axis"), repr(_num(deg, "degrees")))
        if kind == "scale":
            f = _num(args[0], "factor")
            if f <= 0:
                raise security.InvalidInput("the factor must be positive")
            return self.link.call("view", "scale", repr(f))
        if kind == "translate":
            return self.link.call("view", "translate", *[repr(_num(a, n)) for a, n in zip(args, "xyz")])
        if kind == "center":
            selection, molecule = args
            return self.link.call("view", "center", _selection(selection), _int(molecule, "molecule"))
        if kind in ("save", "restore"):
            name = str(args[0])
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,30}", name):
                raise security.InvalidInput("a view name has letters, digits, _ and - only")
            return self.link.call("view", kind, name)
        return self.link.call("view", "reset")

    def animate(self, kind: str, value: Any = None) -> dict:
        kind = _choice(kind, ("goto", "forward", "reverse", "pause", "style", "speed", "skip"), "animation action")
        if kind == "goto":
            return self.link.call("anim", "goto", _int(value, "frame"))
        if kind == "style":
            return self.link.call("anim", "style", _choice(value, ("once", "loop", "rock"), "animation style"))
        if kind == "speed":
            return self.link.call("anim", "speed", repr(_num(value, "speed")))
        if kind == "skip":
            return self.link.call("anim", "skip", _int(value, "skip"))
        return self.link.call("anim", kind)

    # -- asking VMD
    def query(self, selection: str, molecule: int) -> dict:
        return self.link.call("query", _selection(selection), _int(molecule, "molecule"))

    def measure(self, kind: str, molecule: int, *args: Any) -> dict:
        kind = _choice(kind, ("bond", "angle", "dihedral", "sasa"), "measurement")
        if kind == "sasa":
            radius, selection = args
            return self.link.call("measure", "sasa", _int(molecule, "molecule"), repr(_num(radius, "probe radius")), _selection(selection))
        return self.link.call("measure", kind, _int(molecule, "molecule"), *[str(_int(a, "an atom index")) for a in args])

    # -- pictures and state files
    def snapshot(self, out_png: str, quality: str = "fast") -> dict:
        """A picture of what the VMD window shows (``quality`` fast: the window's own picture; tachyon: VMD's built-in ray tracer)."""
        import tempfile
        from PIL import Image
        quality = _choice(quality, ("fast", "tachyon"), "quality")
        dest = security.check_path(out_png)
        os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
        tmp = tempfile.NamedTemporaryFile(suffix=".tga", delete=False, dir=os.path.dirname(os.path.abspath(dest)))
        tmp.close()
        try:
            info = self.link.call("snapshot", _path(tmp.name), quality, timeout=300.0)
            with Image.open(tmp.name) as im:
                im = im.convert("RGB")
                im.save(dest, "PNG")
                size = im.size
        finally:
            try:
                os.remove(tmp.name)
            except OSError:
                pass
        return {"path": dest, "width": size[0], "height": size[1], "renderer": info.get("renderer")}

    def save_state(self, path: str) -> dict:
        return self.link.call("save_state", _path(path))
