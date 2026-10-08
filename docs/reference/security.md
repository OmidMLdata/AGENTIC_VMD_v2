# Security

An MCP server lets a model read paths, write paths, download files and run Tcl on your machine. These
controls limit the damage; none is a complete sandbox. **The container is the real boundary.**

## Path sandbox
`VMD_AGENT_ALLOWED_ROOTS` (an `os.pathsep`-separated list) confines every path the **server tools** read
or write. Paths are resolved through symlinks, so `..`, symlink escapes and prefix-sibling tricks
(`/data-evil` vs `/data`) are blocked. Unset = unrestricted (fine for a single-user local install). The
Docker image sets it to `/data`. The CLI is operator-run and is not sandboxed.
`view_image` only serves image files.

## The VMD window's bridge
The `window_*` tools drive a running VMD through a small listener inside it ([Your VMD window](../guide/window.md#how-it-is-kept-safe)). It binds to 127.0.0.1 only, accepts only requests with a one-time token kept in a
file that only the user can read, and has a fixed list of commands with no way to run Tcl, a program or read a file; every argument is checked in Python and again in VMD, and a request is taken apart as a list and
never evaluated. It is as private as the user account: another program running as the same user could read the token.

## `run_tcl` is off by default
Tcl can run any program, and **no filter can stop it**: command names can be built at run time
(`set c ex; append c ec; $c cmd`, `catch $built_script`, `\x65xec`, `rename exec e`). A second audit confirmed this
with a real `tclsh`: scripts that passed the deny-list below created files. The first audit "closed" five specific bypasses,
which was true only for those strings. So the MCP tool is **disabled unless the server is started with
`VMD_AGENT_ENABLE_TCL=1`**, and enabling it means trusting the caller with code execution on that machine.

When enabled (or when calling `vmd_agent.visual.render.run_tcl` from your own code), a deny-list still rejects the obvious
dangerous commands, in command position (start of a line, or after `;` `[` `{` `"`): `exec`, `open`, `source`, `play`,
`socket`, destructive `file` operations, `cd`, `system`, `eval`, `uplevel`, `interp`, `subst`, `load`, `unix`,
`mol urlload`, `render <method> <file> <command>`, and `package require` outside a short allow-list. That catches accidents
and careless scripts. It is **not a boundary**, and the Tcl screen is not a path sandbox either (`mol load` reads any path).
`VMD_AGENT_ALLOW_UNSAFE_TCL=1` disables even the guard rail.

## Scripts the toolkit generates
The Tcl the toolkit writes itself (recipes, render scripts) is **not** passed through the screen, so every value
interpolated into it is validated instead (`security.tcl_path`, `tcl_selection`, `tcl_word`, `safe_resnames`):

* paths must not contain braces, backslashes or control characters;
* selections are a character whitelist; representation, colour and material names are letters/digits/spaces and the
  representation must be in the catalogue; `background` must be `white` or `black`;
* **residue names read from a structure file are filtered** (`^[A-Za-z0-9_+\-']{1,8}$`), because mmCIF allows arbitrary
  text. Before this was fixed a crafted file could close a Tcl brace and run commands when rendered with VMD.
  Rejected names are reported in `detect_system(...)["warnings"]`.

Violations return a structured error (`blocked: true`), never an exception.

## Downloads (`fetch`)
http(s) only (no `file://`, `ftp://`), hosts resolving to loopback/private/link-local/reserved addresses
refused, every redirect hop re-checked, body capped (default 1024 MB, `VMD_AGENT_MAX_DOWNLOAD_MB`),
gzip decompression capped. Not defended: DNS rebinding between check and request. Run the container without
internal-network access if that matters. `VMD_AGENT_ALLOW_PRIVATE_URLS=1` lifts the address rule.

## Container hardening
Non-root (uid 10001), read-only root, tmpfs `/tmp`, `--cap-drop ALL`, `no-new-privileges`, data at `/data`
only; `--network none` for analysis-only work.

## Not covered
Prompt injection through file *contents* (a PDB `REMARK` line is data the model may read); resource
exhaustion by very large trajectories; the security of VMD/ffmpeg themselves. Treat model-driven access to
sensitive data accordingly.

---
