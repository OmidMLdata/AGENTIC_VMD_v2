"""What kind of computer is this, and what is installed on it?

One place that knows the differences between Linux, macOS and Windows, so the rest of
the toolkit can ask instead of guessing: where VMD usually lives, what its files are
called, where an MCP client keeps its configuration, whether Docker is running, whether
a GPU is available to it.

Everything takes the operating system as an optional argument (defaulting to the real
one) so the decisions can be tested for every OS from any OS. Probing the machine never
raises: a missing program is reported as missing.

Nothing here imports the rest of the package.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
from typing import Dict, List, Optional, Tuple

LINUX, MACOS, WINDOWS = "linux", "macos", "windows"


# ---------------------------------------------------------------- the basics
def system(name: Optional[str] = None) -> str:
    """``"linux"``, ``"macos"`` or ``"windows"`` (anything else is returned lower-cased)."""
    n = (name or platform.system()).lower()
    return {"darwin": MACOS, "macos": MACOS, "windows": WINDOWS,
            "win32": WINDOWS, "linux": LINUX}.get(n, n)


def arch(machine: Optional[str] = None) -> str:
    """``"amd64"``, ``"arm64"`` or the raw machine name, lower-cased."""
    m = (machine or platform.machine()).lower()
    if m in ("x86_64", "amd64", "x64"):
        return "amd64"
    if m in ("arm64", "aarch64", "armv8", "armv8l"):
        return "arm64"
    return m


def is_wsl() -> bool:
    """Linux running inside Windows' WSL."""
    if system() != LINUX:
        return False
    try:
        with open("/proc/version") as fh:
            return "microsoft" in fh.read().lower()
    except OSError:
        return False


def in_container() -> bool:
    """Best-effort: Docker, Podman or a cgroup that names a container runtime."""
    if os.path.exists("/.dockerenv") or os.path.exists("/run/.containerenv"):
        return True
    try:
        with open("/proc/1/cgroup") as fh:
            t = fh.read()
        return any(k in t for k in ("docker", "containerd", "kubepods", "lxc"))
    except OSError:
        return False


def docker_platform(machine: Optional[str] = None) -> str:
    """The Docker ``--platform`` of a Linux container on this CPU. VMD is a native
    binary, so the Linux VMD build you give an image must match this."""
    return "linux/arm64" if arch(machine) == "arm64" else "linux/amd64"


def console_safe() -> None:
    """Stop printing from crashing on a console that cannot show a character (an
    older Windows console printing an angstrom sign, for example): replace what
    cannot be encoded instead of raising."""
    import sys
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")           # type: ignore[attr-defined]
        except (AttributeError, ValueError, OSError):
            pass


# ------------------------------------------------------------- probing programs
def run(argv: List[str], timeout: float = 8.0) -> Tuple[int, str]:
    """Run a program and return ``(returncode, output)``; ``(127, "")`` if it is
    missing and ``(124, "")`` on timeout. Never raises."""
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except FileNotFoundError:
        return 127, ""
    except subprocess.TimeoutExpired:
        return 124, ""
    except OSError:
        return 126, ""


def docker_status(docker: str = "docker") -> Dict[str, object]:
    """Is Docker installed, running, has Compose v2, and an NVIDIA runtime?"""
    exe = shutil.which(docker)
    st: Dict[str, object] = {"installed": exe is not None, "path": exe,
                             "running": False, "compose": False,
                             "nvidia_runtime": False}
    if not exe:
        return st
    rc, out = run([docker, "info"], timeout=15)
    st["running"] = rc == 0
    st["nvidia_runtime"] = rc == 0 and "nvidia" in out.lower()
    st["compose"] = run([docker, "compose", "version"], timeout=15)[0] == 0
    return st


def nvidia_gpu() -> Optional[str]:
    """Name of the first NVIDIA GPU, or None."""
    if not shutil.which("nvidia-smi"):
        return None
    rc, out = run(["nvidia-smi", "-L"])
    if rc != 0:
        return None
    line = out.strip().splitlines()[0] if out.strip() else ""
    return line.split(" (UUID")[0].strip() or None


def ollama_installed() -> bool:
    return shutil.which("ollama") is not None


# ------------------------------------------------------------- where things live
def vmd_search_dirs(system_name: Optional[str] = None,
                    home: Optional[str] = None,
                    env: Optional[Dict[str, str]] = None) -> List[str]:
    """Glob patterns for directories that may hold a VMD launcher on this OS."""
    s = system(system_name)
    home = home if home is not None else os.path.expanduser("~")
    env = os.environ if env is None else env
    if s == WINDOWS:
        dirs = []
        for var in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            base = env.get(var)
            if base:
                dirs += [base + "/University of Illinois/VMD*",
                         base + "/VMD*", base + "/Programs/VMD*"]
        dirs += ["C:/Program Files/University of Illinois/VMD*",
                 "C:/Program Files (x86)/University of Illinois/VMD*"]
        return [d.replace("\\", "/") for d in dict.fromkeys(dirs)]
    if s == MACOS:
        return ["/Applications/VMD*.app/Contents/vmd",
                home + "/Applications/VMD*.app/Contents/vmd",
                "/opt/homebrew/bin", "/usr/local/bin"]
    return ["/usr/local/bin", "/usr/local/lib/vmd", "/opt/vmd", "/opt/vmd/bin",
            "/opt/vmd*", home + "/Software", home + "/software", home + "/vmd",
            home + "/.local/bin"]


def vmd_executable_names(system_name: Optional[str] = None) -> List[str]:
    """File names VMD's launcher or binary may have on this OS, most likely first."""
    s = system(system_name)
    if s == WINDOWS:
        return ["vmd.exe", "vmd"]
    if s == MACOS:
        return ["vmd", "vmd_MACOSXARM64", "vmd_MACOSXX86_64", "vmd_MACOSXX86"]
    return ["vmd", "vmd_LINUXAMD64", "vmd_LINUXARM64"]


def claude_desktop_config_path(system_name: Optional[str] = None,
                               home: Optional[str] = None,
                               env: Optional[Dict[str, str]] = None
                               ) -> Optional[str]:
    """Where Claude Desktop keeps its MCP configuration, or None where it has no
    official build (Linux)."""
    s = system(system_name)
    home = home if home is not None else os.path.expanduser("~")
    env = os.environ if env is None else env
    if s == MACOS:
        return os.path.join(home, "Library", "Application Support", "Claude",
                            "claude_desktop_config.json")
    if s == WINDOWS:
        base = env.get("APPDATA") or os.path.join(home, "AppData", "Roaming")
        return os.path.join(base, "Claude", "claude_desktop_config.json")
    return None


def server_command_path(system_name: Optional[str] = None) -> str:
    """Absolute path of the installed ``vmd-agent-server`` console script (next to
    this Python), or its bare name if it cannot be found."""
    import sys
    s = system(system_name)
    name = "vmd-agent-server" + (".exe" if s == WINDOWS else "")
    for d in (os.path.dirname(sys.executable),
              os.path.join(os.path.dirname(sys.executable), "Scripts")):
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    return shutil.which("vmd-agent-server") or name


# ------------------------------------------------------------- the whole picture
def detect(docker: str = "docker") -> Dict[str, object]:
    """Everything the launcher and the doctor need to know, in one dict."""
    s, a = system(), arch()
    d = docker_status(docker)
    return {
        "system": s, "arch": a, "wsl": is_wsl(), "in_container": in_container(),
        "python": platform.python_version(),
        "apple_silicon": s == MACOS and a == "arm64",
        "docker": d, "docker_platform": docker_platform(),
        "nvidia_gpu": nvidia_gpu(), "ollama": ollama_installed(),
        "claude_desktop_config": claude_desktop_config_path(),
    }


def docker_install_url(system_name: Optional[str] = None) -> str:
    s = system(system_name)
    return ("https://docs.docker.com/desktop/setup/install/mac-install/" if s == MACOS
            else "https://docs.docker.com/desktop/setup/install/windows-install/"
            if s == WINDOWS else "https://docs.docker.com/engine/install/")


def advice(info: Dict[str, object]) -> List[str]:
    """Plain-language notes for this machine, most important first. Docker is optional (the default route
    runs natively), so its notes appear only when Docker is installed."""
    s = info["system"]
    d: dict = info["docker"]                                # type: ignore[assignment]
    out: List[str] = []
    if info.get("in_container"):
        out.append("You are inside a container: VMD, if present, is the Linux build.")
    if not d.get("installed"):
        out.append("Docker is not installed. That is fine: it is only needed for the optional Docker route (`vmd-agent start`) "
                   "(" + docker_install_url(str(s)) + ").")
    elif not d.get("running"):
        out.append("Docker is installed but not running: start Docker Desktop (or the docker service) to use it.")
    elif not d.get("compose"):
        out.append("Docker Compose v2 is missing (it comes with Docker Desktop).")
    if d.get("installed"):
        if s == MACOS:
            out.append("A Mac's VMD cannot run inside Docker (it is a macOS program and Docker containers are "
                       "Linux): use the native route, or the Linux VMD build in Docker (" +
                       str(info["docker_platform"]) + ").")
            out.append("Docker Desktop on a Mac cannot use the Mac's GPU, so a model inside Docker runs on the CPU; "
                       "the native route (`vmd-agent setup`) uses it.")
        elif s == WINDOWS:
            out.append("A Windows VMD cannot run inside Docker: use the native route, or the Linux VMD build in "
                       "Docker. Docker Desktop should use the WSL 2 backend.")
        if info.get("nvidia_gpu") and not d.get("nvidia_runtime"):
            out.append("An NVIDIA GPU is present but Docker has no NVIDIA runtime: install the NVIDIA Container "
                       "Toolkit to let the containerised model use it.")
        if info.get("apple_silicon"):
            out.append("Apple Silicon: images and VMD builds for Docker must be arm64 (or run under emulation, "
                       "which is slow).")
    if s == LINUX and not info.get("nvidia_gpu"):
        out.append("No NVIDIA GPU found: a model runs on the CPU (slower).")
    return out
