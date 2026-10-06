"""Remembered choices: where the user's files are, where VMD is, which model to talk to.

``vmd-agent setup`` asks once and stores the answers here, so that nothing needs to be
configured again: the chat, the MCP server and the other commands read these values as
their defaults. Flags and environment variables always win over what is stored.

The file lives in the usual per-user place for each OS (``~/Library/Application
Support/vmd-agent`` on macOS, ``%APPDATA%\\vmd-agent`` on Windows, ``~/.config/vmd-agent``
elsewhere) and is readable by the user only where the OS allows it, because it may hold
an API key. Set ``VMD_AGENT_CONFIG_DIR`` to use a different folder.

Nothing here imports the rest of the package, and reading never raises.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

ENV_DIR = "VMD_AGENT_CONFIG_DIR"
ENV_HOME = "VMD_AGENT_HOME"
KEYS = ("data_dir", "vmd_path", "llm_url", "llm_model", "llm_key", "setup_done",
        "ollama_mode", "ollama_port")


def config_dir(system_name: Optional[str] = None, home: Optional[str] = None,
               env: Optional[Dict[str, str]] = None) -> str:
    """The folder holding the settings file, for the given OS (default: this one)."""
    env = os.environ if env is None else env
    if env.get(ENV_DIR):
        return env[ENV_DIR]
    if env.get(ENV_HOME):                      # a contained install keeps everything in one folder
        return os.path.join(env[ENV_HOME], "config")
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
