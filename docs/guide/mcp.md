# Use it from an MCP client

Setup offers to register vmd-agent with Claude Code for you when the `claude` command is installed; this page is the manual way and the details.

Optional. The chat (`vmd-agent chat`) needs no MCP client; this is for people who already use Claude Code, Claude Desktop or another MCP client.

The same 53 tools are available to any MCP client (Claude Code, Claude Desktop and others) through an MCP server. The server exposes the 53 tools below to an MCP client (Claude Code, Claude Desktop, or any other) over stdio. This
section is everything needed to run it on a **Linux machine that has VMD installed**.

## 1. What the Linux machine needs

| Need | Detail | Required? |
|---|---|---|
| **Python >= 3.10** | `python3 --version`. The MCP SDK needs it; the rest of the toolkit also runs on 3.9. | yes |
| **The toolkit with the server extra** | `python3 -m venv ~/vmd-agent-venv && ~/vmd-agent-venv/bin/pip install -e ".[server]"` (add `.[sasa]` for SASA analysis). Both MCP SDK generations (1.x and 2.x) are supported. | yes |
| **A data directory** | everything the agent reads or writes must be inside it (see the sandbox below) | yes |
| **VMD** | for VMD renders. Without it the server still works and draws with the built-in matplotlib renderer. | optional |
| `tcsh` and VMD's shared libraries | VMD's `vmd` launcher is a tcsh script, and the binary links OpenGL/X11 libraries even when run headless. `docker/Dockerfile` lists the Debian packages used for this (`tcsh libgl1 libglu1-mesa libx11-6 libxi6 libxinerama1 libxft2 libfontconfig1 libxext6 libxrender1`). That list is **untested against a real VMD**. | only with VMD |
| **Tachyon** | ships inside a VMD install (`tachyon_LINUXAMD64` or similar). The VMD renderer needs it to make images. | only with VMD |
| `ffmpeg` | only for the movie and video tools (`render_movie`, `probe_video`, `validate_video`, `interpret_video`, `extract_video_frames`) | optional; a copy comes with the `imageio-ffmpeg` dependency, so nothing to install |
| Outbound HTTPS | only for `fetch_structure`, `fetch_and_visualize` and `search_pdb` (RCSB, UniProt, AlphaFold) | optional |

No display is needed: VMD is always run headless (`-dispdev text`).

## 2. Check the install before connecting a client

Run these **as the same user the server will run as**:

```bash
~/vmd-agent-venv/bin/vmd-agent probe          # does this machine have VMD, Tachyon, ffmpeg, the libraries?
~/vmd-agent-venv/bin/vmd-agent mcp-check --roots /srv/md-data --vmd /opt/vmd/bin/vmd --render
```

`mcp-check` starts the server and talks to it with the real MCP client over stdio, which is what your client will do. It
gives the server **only** the environment you pass it (MCP clients typically do not forward your shell's exports or
`PATH`, and the SDK's own client does not), so a variable that works in your terminal but is missing from the client's
configuration shows up here. It reports:
`connect` (the server starts and speaks MCP), `tools` (53 registered), `analysis_libraries`, `vmd` and `tachyon` (found?
which version?), `ffmpeg`, the sandbox (a path outside the roots is refused; relative paths resolve inside the first root),
whether the raw Tcl tool is disabled, and with `--render` a real VMD + Tachyon render of a tiny structure. `FAIL` means a
client cannot work; `WARN` means reduced capability or a risk (no VMD, no sandbox). Exit code 2 on any `FAIL`.

## 3. Connect a client

The server command is the console script `vmd-agent-server` in the virtualenv (use its **absolute path**; a client does
not activate your virtualenv). Do not assume your shell's environment reaches the server; **list the variables you
need in the client's configuration**:

* `VMD_AGENT_ALLOWED_ROOTS`: the directory (or several, separated by `:`) the agent may read and write. **Set it.**
* `VMD_BIN`: your VMD launcher or install directory. Without it the server looks on `PATH` and a few common locations;
  do not rely on that.

**a. Claude Code on the same Linux machine**

```bash
claude mcp add vmd-agent \
  -e VMD_BIN=/opt/vmd/bin/vmd -e VMD_AGENT_ALLOWED_ROOTS=/srv/md-data \
  -- /home/you/vmd-agent-venv/bin/vmd-agent-server
```

(Check `claude mcp add --help` for your version's exact flags; then `claude mcp list` should show it connected.)

**b. A client on another machine (for example Claude Desktop on your laptop), over SSH**

The server runs on the Linux machine; the client starts it through `ssh`. Use key-based, non-interactive SSH, and make
sure the remote shell prints **nothing** on login (no banners, no output from `.bashrc`): anything written to stdout other
than MCP messages corrupts the connection. (The SSH route and the `claude mcp add` flags have **not been tested by the
author**; `mcp-check --command ssh --args -T you@linux-host "<remote command>"` tests the same path.)

```json
{ "mcpServers": { "vmd-agent": {
    "command": "ssh",
    "args": ["-T", "you@linux-host",
             "env VMD_BIN=/opt/vmd/bin/vmd VMD_AGENT_ALLOWED_ROOTS=/srv/md-data /home/you/vmd-agent-venv/bin/vmd-agent-server"] } } }
```

**c. Any client on the same machine (JSON config)**

```json
{ "mcpServers": { "vmd-agent": {
    "command": "/home/you/vmd-agent-venv/bin/vmd-agent-server",
    "env": { "VMD_BIN": "/opt/vmd/bin/vmd", "VMD_AGENT_ALLOWED_ROOTS": "/srv/md-data" } } } }
```

**d. In Docker with your VMD mounted** (Linux host, VMD build matching the image architecture; the image has no VMD of
its own). Build the `vmd-libs` image first (see [Docker](docker.md#docker)); **never built or run by the
author**:

```json
{ "mcpServers": { "vmd-agent": { "command": "docker",
    "args": ["run", "-i", "--rm", "--read-only", "--tmpfs", "/tmp", "--tmpfs", "/home/vmdagent", "--cap-drop", "ALL",
             "-v", "/srv/md-data:/data", "-v", "/opt/vmd:/opt/vmd:ro", "-e", "VMD_BIN=/opt/vmd/bin/vmd",
             "vmd-agent:hostvmd"] } } }
```

Inside the container the data directory is `/data` and the sandbox is already set to it. Without VMD, use the plain
`vmd-agent` image and drop the VMD lines.

## 4. How the server behaves

* **The sandbox.** With `VMD_AGENT_ALLOWED_ROOTS` set, every path a tool receives (inputs *and* output directories) must
  resolve inside one of the roots, with symlinks, `..` and prefix tricks resolved. **A relative path is taken relative
  to the first root**, not to the server's working directory, so a tool's default output directory (`vmd_agent_output`)
  lands inside it. **With it unset the sandbox is off** and the server prints a warning to stderr.
* **`run_vmd_tcl` is disabled** (it returns a refusal) unless the server environment has `VMD_AGENT_ENABLE_TCL=1`. The
  Tcl screen is an accident guard, not a security boundary: enable it only for a client and agent you trust.
* **Downloads** refuse non-http(s) URLs and loopback/private/link-local hosts (also after redirects). Optional:
  `VMD_AGENT_ALLOW_PRIVATE_URLS=1` for an internal mirror, `VMD_AGENT_MAX_DOWNLOAD_MB` for the size cap.
* **Renderers.** `renderer="auto"` uses VMD when it and Tachyon are found, otherwise matplotlib; every result says which
  drew the pictures. `view_image` returns images, so the client must support image content.
* **Logs** go to stderr only; stdout is the protocol stream. If you wrap the server in your own script, print nothing to
  stdout.

## 5. Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| client says the server exited / will not connect | run the exact command by hand and read stderr; usual causes: Python < 3.10, `mcp` not installed in *that* environment, or a relative or wrong path to `vmd-agent-server`. `mcp-check --command <your command>` tests the same command. |
| tool results say `vmd_found: false` | `VMD_BIN` is not in the **client's** `env` block. Your shell's `PATH` and exports may not be forwarded. |
| `path ... is outside the allowed roots` | the path (or an output directory) is not under `VMD_AGENT_ALLOWED_ROOTS`; use a path inside it, or add the directory to the roots. |
| renders fall back to "matplotlib" though VMD is installed | Tachyon was not found next to VMD, or VMD does not run headless here (missing `tcsh` or libraries). `vmd-agent probe` shows `tachyon_path`; try `vmd -dispdev text -eof` by hand. |
| `VMD did not produce a Tachyon scene` | VMD started but failed: run `mcp-check --render`, then run VMD by hand with a small script. Use `renderer="matplotlib"` meanwhile. |
| the connection works over SSH for a while, then breaks | something on the remote side wrote to stdout (login banner, `.bashrc` output). Make the remote shell silent. |
| movies or video tools fail | `vmd-agent probe` shows whether ffmpeg was found (the bundled copy normally is); check that the server runs in the environment where vmd-agent was installed. |

53 tools. The original 27: `probe_environment` · `inspect_files` · `detect_system` · `generate_visualization_recipe` · `structure_stats` ·
`color_key` · `annotate_image` · `list_representations` · `describe_representation` · `render_image` · `render_movie` ·
`run_vmd_tcl` · `search_pdb` · `fetch_structure` · `fetch_and_visualize` · `visualize_and_interpret` ·
`analyze_trajectory` · `select_keyframes` · `verify_claims` · `verify_provenance` · `extract_video_frames` ·
`probe_video` · `validate_video` · `interpret_video` · `view_image` · `record_visual_interpretation` · `assemble_report`. The 24 that drive VMD itself ([Driving VMD itself](vmd.md#6-drive-vmd-itself)): `vmd_capabilities` · `vmd_measure` · `vmd_interactions` · `vmd_secondary_structure` · `vmd_backbone_torsions` · `vmd_structure_check` · `vmd_align_structures` · `vmd_pbc_info` · `vmd_convert_trajectory` · `vmd_write_structure` · `vmd_volmap` · `vmd_volume_info` · `vmd_build_system` · `vmd_mutate_residue` · `vmd_merge_structures` · `vmd_render_scene` · `vmd_render_turntable` · `vmd_build_membrane` · `vmd_build_nanotube` · `export_vmd_session` · `vmd_fit_to_map` · `vmd_map_arithmetic` · `vmd_prepare_namd` · `vmd_slurm_script`. And the two that run whole jobs ([Whole jobs](workflows.md)): `list_workflows` · `run_workflow`.
