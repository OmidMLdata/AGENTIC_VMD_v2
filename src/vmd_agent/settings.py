"""Remembered choices: where the user's files are, where VMD is, which model to talk to.

``vmd-agent setup`` asks once and stores the answers here, so that nothing needs to be
configured again: the chat, the MCP server and the other commands read these values as
their defaults. Flags and environment variables always win over what is stored.

Where vmd-agent keeps its own data (these settings, the link to your VMD window, a private
copy of the model server and its models) is decided in this order:

1. ``VMD_AGENT_CONFIG_DIR`` (settings only) or ``VMD_AGENT_HOME`` (everything, in ``$VMD_AGENT_HOME``);
2. a ``.vmd-agent`` folder in the current folder or one above it: the **working folder** keeps its own data
   (``vmd-agent setup`` offers to create it and to move the model there), so the project can be moved or
   deleted as one piece;
3. ``VMD_AGENT_INSTALL``, the installer's folder (the installer's launcher sets it);
4. the usual per-user place for each OS (``~/Library/Application Support/vmd-agent`` on macOS,
   ``%APPDATA%\\vmd-agent`` on Windows, ``~/.config/vmd-agent`` elsewhere).

The settings file is readable by the user only where the OS allows it, because it may hold an API key.

Nothing here imports the rest of the package, and reading never raises.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

ENV_DIR = "VMD_AGENT_CONFIG_DIR"
ENV_HOME = "VMD_AGENT_HOME"
ENV_INSTALL = "VMD_AGENT_INSTALL"              # set by the installer's launcher: the folder holding the program itself
LOCAL = ".vmd-agent"                           # the folder a working folder keeps its own data in
KEYS = ("data_dir", "vmd_path", "llm_url", "llm_model", "llm_key", "setup_done",
        "ollama_mode", "ollama_port", "vmd_page_offered")


def local_home(start: Optional[str] = None) -> Optional[str]:
    """The ``.vmd-agent`` folder of the working folder: in ``start`` (default: the current folder) or the
    nearest folder above it that has one; ``None`` if there is none."""
    try:
        d = os.path.realpath(start or os.getcwd())
    except OSError:
        return None
    while True:
        cand = os.path.join(d, LOCAL)
        if os.path.isdir(cand):
            return cand
        up = os.path.dirname(d)
        if up == d:
            return None
        d = up


def make_local(folder: str) -> str:
    """Create ``<folder>/.vmd-agent`` (private to the user, and ignored by Git because it holds settings that
    may include an API key, the window link's token and downloaded models) and return its path."""
    d = os.path.join(os.path.abspath(folder), LOCAL)
    os.makedirs(d, exist_ok=True)
    try:
        os.chmod(d, 0o700)
    except OSError:
        pass
    ignore = os.path.join(d, ".gitignore")
    if not os.path.exists(ignore):
        with open(ignore, "w") as fh:
            fh.write("*\n")
    return d


def previous_home() -> str:
    """Where vmd-agent's data is kept when the working folder has none: the installer's folder or the per-user folder."""
    return os.environ.get(ENV_INSTALL) or home_dir(env={})


def movable(src: str, dst: str) -> list:
    """What ``move_data`` would move from ``src`` into ``dst``: the private model server with its models and the settings file."""
    out = []
    if os.path.realpath(src) == os.path.realpath(dst):
        return out
    if os.path.isdir(os.path.join(src, "ollama")) and not os.path.exists(os.path.join(dst, "ollama")):
        out.append("ollama")
    if os.path.isfile(os.path.join(src, "config", "settings.json")) and not os.path.exists(os.path.join(dst, "config", "settings.json")):
        out.append(os.path.join("config", "settings.json"))
    return out


def move_data(src: str, dst: str) -> list:
    """Move the things ``movable`` lists from ``src`` into ``dst`` (a rename, so instant and with no second copy on the same disk;
    across disks it copies and then removes). Returns what was moved. Never overwrites."""
    import shutil
    done = []
    for rel in movable(src, dst):
        os.makedirs(os.path.dirname(os.path.join(dst, rel)), exist_ok=True)
        shutil.move(os.path.join(src, rel), os.path.join(dst, rel))
        done.append(rel)
    return done


def config_dir(system_name: Optional[str] = None, home: Optional[str] = None,
               env: Optional[Dict[str, str]] = None) -> str:
    """The folder holding the settings file, for the given OS (default: this one)."""
    env = os.environ if env is None else env
    if env.get(ENV_DIR):
        return env[ENV_DIR]
    if env.get(ENV_HOME):                      # a contained install keeps everything in one folder
        return os.path.join(env[ENV_HOME], "config")
    if env is os.environ and local_home():     # the working folder keeps its own settings
        return os.path.join(local_home(), "config")
    if env.get(ENV_INSTALL):
        return os.path.join(env[ENV_INSTALL], "config")
    import platform
    name = (system_name or platform.system()).lower()
    home = home if home is not None else os.path.expanduser("~")
    if name in ("darwin", "macos"):
        return os.path.join(home, "Library", "Application Support", "vmd-agent")
    if name in ("windows", "win32"):
        return os.path.join(env.get("APPDATA") or os.path.join(home, "AppData", "Roaming"),
                            "vmd-agent")
    return os.path.join(env.get("XDG_CONFIG_HOME") or os.path.join(home, ".config"),
                        "vmd-agent")


def home_dir(system_name: Optional[str] = None, home: Optional[str] = None,
             env: Optional[Dict[str, str]] = None) -> str:
    """The folder for things the program downloads (a private copy of the model
    server and its models). In a contained install this is ``$VMD_AGENT_HOME``, the one
    folder that holds everything (delete it to remove all of it); otherwise a
    per-user data folder."""
    env = os.environ if env is None else env
    if env.get(ENV_HOME):
        return env[ENV_HOME]
    if env is os.environ and local_home():
        return local_home()
    if env.get(ENV_INSTALL):
        return env[ENV_INSTALL]
    import platform
    name = (system_name or platform.system()).lower()
    home = home if home is not None else os.path.expanduser("~")
    if name in ("darwin", "macos"):
        return os.path.join(home, "Library", "Application Support", "vmd-agent")
    if name in ("windows", "win32"):
        return os.path.join(env.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local"),
                            "vmd-agent")
    return os.path.join(env.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share"),
                        "vmd-agent")


def path() -> str:
    return os.path.join(config_dir(), "settings.json")


def load() -> Dict[str, Any]:
    """The stored settings; ``{}`` if there are none or the file is unreadable."""
    try:
        with open(path()) as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def get(key: str, default: Any = None) -> Any:
    v = load().get(key)
    return default if v in (None, "") else v


def save(**values: Any) -> str:
    """Merge ``values`` into the stored settings and return the file's path. A value
    of ``None`` removes that key. The file is made readable by the user only (it may
    hold an API key) where the OS supports it."""
    unknown = set(values) - set(KEYS)
    if unknown:
        raise KeyError(f"unknown setting(s): {sorted(unknown)}; known: {list(KEYS)}")
    data = load()
    for k, v in values.items():
        if v is None:
            data.pop(k, None)
        else:
            data[k] = v
    p = path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(data, fh, indent=2)
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, p)
    return p


def describe() -> Dict[str, Any]:
    """The settings with any key hidden, for showing to the user."""
    d = dict(load())
    if d.get("llm_key"):
        d["llm_key"] = "(saved)"
    return d
