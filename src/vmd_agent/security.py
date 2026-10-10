"""Guards for tools an LLM can call.

An MCP server hands a model the ability to read paths, write paths and run
Tcl on your machine. Two controls limit the blast radius:

* **Path sandbox.** Set ``VMD_AGENT_ALLOWED_ROOTS`` to an ``os.pathsep``
  separated list of directories (the Docker image sets it to ``/data``). Every
  path the server touches must then resolve, after symlinks, inside one of
  them. Unset means unrestricted, which is the right default for a local
  single-user install.
* **Tcl screening.** ``run_tcl`` rejects scripts that can spawn processes,
  open sockets, delete files or evaluate dynamically built code.

Neither is a complete sandbox: Tcl screening is a deny-list and can be
out-flanked by a determined author. They are defence in depth. The real
boundary is the container: run it as a non-root user, mount only the data
directory, and drop network access for analysis-only work.
"""
from __future__ import annotations

import os
import re
from typing import List, Optional

ENV_ROOTS = "VMD_AGENT_ALLOWED_ROOTS"
ENV_UNSAFE_TCL = "VMD_AGENT_ALLOW_UNSAFE_TCL"


class SecurityError(PermissionError):
    """Raised when a request violates the configured policy."""


class InvalidInput(ValueError):
    """Raised for a value the toolkit refuses to use (unknown name, bad form)."""


def allowed_roots() -> Optional[List[str]]:
    """The sandbox roots: ``VMD_AGENT_ALLOWED_ROOTS`` if set, otherwise the data folder
    chosen in ``vmd-agent setup``, otherwise ``None`` (no sandbox)."""
    raw = os.environ.get(ENV_ROOTS, "").strip()
    if not raw:
        from vmd_agent import settings
        raw = str(settings.get("data_dir", "") or "").strip()
    if not raw:
        return None
    return [os.path.realpath(p) for p in raw.split(os.pathsep) if p.strip()]


def is_within(path: str, root: str, norm=os.path.normcase,
              sep: str = os.sep) -> bool:
    """Is ``path`` equal to ``root`` or inside it? Compared the way this OS compares
    paths (case-insensitively on Windows). Both must already be absolute, resolved
    paths. ``norm`` and ``sep`` are parameters so Windows rules can be tested anywhere."""
    p, r = norm(path), norm(root)
    return p == r or p.startswith(r.rstrip(sep) + sep)


def check_path(path: Optional[str]) -> Optional[str]:
    """Return ``path`` if policy allows it, else raise.

    ``None`` and empty strings pass through so optional arguments work. With
    no allowed roots configured the path is returned unchanged. With roots
    configured, an absolute path must lie inside one of them and is returned
    unchanged; a **relative path is taken relative to the first root** (not to
    the server's working directory, which is usually elsewhere) and is returned
    as that absolute path, so tools whose default output directory is relative
    write inside the sandbox.
    """
    if not path:
        return path
    if "\x00" in str(path):
        # Python 3.12's realpath raises ValueError on a NUL; older versions
        # tolerated it. A NUL byte is never a legitimate path.
        raise SecurityError("path contains a NUL byte")
    roots = allowed_roots()
    if roots is None:
        return path
    expanded = os.path.expanduser(path)
    if not os.path.isabs(expanded):
        path = expanded = os.path.join(roots[0], expanded)
    real = os.path.realpath(expanded)
    from vmd_agent import settings
    if is_within(real, os.path.realpath(settings.home_dir())):      # the settings (API key), the window link's token and the models
        raise SecurityError(f"path '{path}' is vmd-agent's own data folder, which tools may not read or write.")
    for r in roots:
        if is_within(real, r):
            return path
    raise SecurityError(
        f"path '{path}' is outside the allowed roots "
        f"({', '.join(roots)}); set {ENV_ROOTS} to widen access.")


# Commands that can leave the VMD process or build code at run time. Patterns
# match only in *command position* (start of a line, or after ; [ { "), so
# VMD's own ``mol load`` or a colour called "system" is not caught. The double
# quote matters: ``catch "exec ls"`` runs its argument as a script.
_CMD = r"(?:^|[;\[{\"])\s*"
_DENY = [
    (_CMD + r"exec\b", "exec (runs shell commands)"),
    (_CMD + r"open\s+[\"{]?\|", "open |pipe (runs shell commands)"),
    (_CMD + r"socket\b", "socket (network access)"),
    (_CMD + r"file\s+(delete|rename|copy|attributes|link)\b",
     "destructive file operations"),
    (_CMD + r"cd\b", "cd"),
    (_CMD + r"system\b", "system"),
    (_CMD + r"eval\b", "eval (dynamic code)"),
    (_CMD + r"uplevel\b", "uplevel (dynamic code)"),
    (_CMD + r"interp\b", "interp"),
    (_CMD + r"subst\b", "subst (dynamic code)"),
    (_CMD + r"load\b", "load (native libraries)"),
    (_CMD + r"unix\b", "unix"),
    # A script can write a file with `open` and then run it, so neither may be
    # allowed; `play` also executes a script file.
    (_CMD + r"open\b", "open (file access; with source it runs arbitrary code)"),
    (_CMD + r"source\b", "source (runs a script file)"),
    (_CMD + r"play\b", "play (runs a script file)"),
    # `render <method> <file> <command>`: VMD runs the third argument as a
    # shell command after writing the file.
    (_CMD + r"render\s+\S+\s+\S+\s+\S", "render with an external command"),
    (_CMD + r"mol\s+urlload\b", "mol urlload (network access)"),
    (_CMD + r"package\s+require\s+(?!vmd\b|animate\b|pbctools\b|topotools\b)",
     "package require"),
]


def check_tcl(script: str, allow_unsafe: Optional[bool] = None) -> None:
    """Raise :class:`SecurityError` if ``script`` uses a denied command."""
    if allow_unsafe is None:
        allow_unsafe = os.environ.get(ENV_UNSAFE_TCL, "") == "1"
    if allow_unsafe:
        return
    # strip comments so a mention in prose does not trip the filter
    body = "\n".join(l for l in script.splitlines()
                     if not l.lstrip().startswith("#"))
    for pat, label in _DENY:
        if re.search(pat, body, re.MULTILINE):
            raise SecurityError(
                f"Tcl rejected: {label}. Set {ENV_UNSAFE_TCL}=1 on the server "
                "to disable screening if you trust the caller.")


# ---------------------------------------------------------------------------
# Values the toolkit itself writes into the Tcl it generates. Those scripts are
# never passed through check_tcl, so every interpolated value must be validated
# here: a residue name read from a downloaded mmCIF, a user-supplied path or
# representation could otherwise close a brace and append commands.
_PATH_BAD = re.compile(r"[{}\\\x00-\x1f\x7f]")
# \Z, not $: "$" also matches before a trailing newline, which would let
# "name CA\n" through.
_SELECTION_OK = re.compile(r"^[A-Za-z0-9_ ()+\-.'*:,<>=]+\Z")
_WORD_OK = re.compile(r"^[A-Za-z][A-Za-z0-9_ ]{0,39}\Z")
_RESNAME_OK = re.compile(r"^[A-Za-z0-9_+\-']{1,8}\Z")


def tcl_path(path: str, windows: Optional[bool] = None) -> str:
    """Absolute path that is safe inside Tcl braces (``{...}``).

    On Windows, backslashes are the path separator, and Tcl (so VMD) accepts forward
    slashes there, so ``C:\\Users\\me\\a.pdb`` becomes ``C:/Users/me/a.pdb`` before
    the check. Elsewhere a backslash in a path is refused, because it could escape
    the brace quoting. ``windows`` forces the rules for testing."""
    import ntpath
    win = (os.name == "nt") if windows is None else windows
    p = ntpath.abspath(str(path)).replace("\\", "/") if win \
        else os.path.abspath(str(path))
    if _PATH_BAD.search(p):
        raise SecurityError(
            "path contains a brace, backslash or control character, which "
            "cannot be used safely in a VMD script")
    return p


def tcl_selection(sel: str) -> str:
    """A VMD atom selection restricted to a character set with no Tcl syntax."""
    if not _SELECTION_OK.match(str(sel)):
        raise SecurityError(f"selection contains characters not allowed in "
                            f"a generated script: {str(sel)[:60]!r}")
    return str(sel)


def tcl_word(value: str, what: str = "name") -> str:
    """A representation / colour / material name: letters, digits, spaces."""
    if not _WORD_OK.match(str(value)):
        raise SecurityError(f"invalid {what} for a generated script: "
                            f"{str(value)[:40]!r}")
    return str(value)


def safe_resnames(names) -> tuple:
    """Split residue names into ``(usable, rejected)``.

    Residue names come from the structure file, which may be hostile (mmCIF
    allows arbitrary text), and end up in VMD selections.
    """
    ok, bad = [], []
    for n in names:
        (ok if _RESNAME_OK.match(str(n)) else bad).append(str(n))
    return ok, bad
