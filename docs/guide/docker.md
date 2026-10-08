# Docker

## Why VMD is not in the image

VMD's license (<https://www.ks.uiuc.edu/Research/vmd/current/LICENSE.html>) lets you build tools that
interoperate with VMD and point users to the official download, but restricts redistributing VMD itself,
and requires a commercial license for commercial use. A published image containing VMD would likely
breach that. So the **published image is open source and contains no VMD**. VMD is something *you*
supply, on *your* machine. (This is not legal advice; contact `vmd@ks.uiuc.edu` before redistributing.)

> Also read [NOTICE.md](../NOTICE.md): MDAnalysis is GPL-licensed, which affects redistributing an image
> that bundles it.

## Operating systems

All OS differences are in `platform_info.py` (and the few places that consume it), written as functions of the OS name so they are
tested for Linux, macOS and Windows from any OS: VMD install folders and file names (`vmd.exe` on Windows, the app bundle's
`vmd_MACOSX*` binary on macOS), Claude Desktop's config location, the Docker platform, case-insensitive path comparison for the sandbox,
Windows paths turned into forward slashes for Tcl, the Windows system variables a child process needs, a console that cannot show a
character, and the version check that no longer relies on a Linux/macOS-only device file. **Only macOS has been run by the author.**

## The all-in-one chat stack (`vmd-agent start`)

`vmd-agent start` (in Docker mode; `--down` stops it) runs `docker/chat.compose.yml`: an **Ollama** model server (official image, models
kept in a named volume so they download once) and the `vmd-agent` image running `vmd-agent chat`, with your `./data` folder
mounted at `/data` as the only place the agent can read or write (read-only root, no capabilities). If a Linux VMD tarball
is in `docker/vmd-dist/` the image is built with it (`VMD_TARGET=with-vmd`, never to be shared); otherwise figures use the
built-in renderer. `docker/chat.gpu.yml` adds NVIDIA GPU access when `nvidia-smi` and Docker's NVIDIA runtime are found.
A Mac's Docker cannot use its GPU, so the model runs on the CPU there. The default model `granite4.1:8b` is a suggestion
that has not been tested; choose another with `--model`. **Never run:** the tests check the compose structure, the plan the
launcher makes and the no-Docker error path only.

## Three images

| Target | Contains | Use |
|---|---|---|
| `runtime` (default) | Python, toolkit, ffmpeg, matplotlib renderer | everything except VMD rendering. **Safe to publish.** |
| `vmd-libs` | `runtime` + shared libraries VMD needs | mount **your** VMD at `/opt/vmd` |
| `with-vmd` | `vmd-libs` + VMD built from **your** tarball | local use only. **Never push.** |

```bash
# from the repository root
docker build -f docker/Dockerfile -t vmd-agent .                              # open-source image
docker build -f docker/Dockerfile --target vmd-libs -t vmd-agent:hostvmd .     # libs only
docker build -f docker/Dockerfile --target with-vmd -t vmd-agent:vmd-local .   # needs docker/vmd-dist/*.tar.gz
```

#### Open-source image

```bash
docker run --rm -v "$PWD/data:/data" vmd-agent probe
docker run --rm -v "$PWD/data:/data" vmd-agent \
    visualize /data/protein.pdb --out-dir /data/out --renderer matplotlib
docker run -i --rm -v "$PWD/data:/data" vmd-agent            # MCP server on stdio
```

#### With your VMD, mounted (Linux hosts)

Install VMD on a **Linux host of the same CPU architecture** (on a Mac use the baked-in image below), then:

```bash
docker run -i --rm \
  -v "$PWD/data:/data" -v /opt/vmd-1.9.4:/opt/vmd:ro \
  -e VMD_BIN=/opt/vmd/bin/vmd \
  vmd-agent:hostvmd
```

(or `VMD_HOME=/opt/vmd-1.9.4 docker compose -f docker/docker-compose.yml --profile hostvmd run --rm hostvmd probe`).

#### With VMD baked in (local use)

1. Download the Linux binary from the VMD site after accepting its license.
2. Put `vmd-*.tar.gz` in `docker/vmd-dist/`.
3. `docker build -f docker/Dockerfile --target with-vmd -t vmd-agent:vmd-local .`

The image is labelled `vmd-agent.redistributable=false`.

## Running the benchmark with your VMD (and your key)

Three ways to supply VMD. Pick by where you work:

| Route | When | Command prefix |
|---|---|---|
| **Native** | You run on the machine that has VMD (a Mac with VMD.app, or a Linux box). Simplest, but model-written code runs on your machine: use a disposable VM. | `vmd-agent bench ... --vmd <path>` |
| **Mounted VMD** (`--mode hostvmd`) | Linux host, VMD installed there, same CPU architecture as the image. | `VMD_HOME=/opt/vmd vmd-agent bench docker ... --mode hostvmd` |
| **Baked VMD** (`--mode withvmd`) | **Use this on a Mac.** Put the **Linux** VMD tarball in `docker/vmd-dist/`; it is installed inside a local image. Local use only; never push. | `vmd-agent bench docker ... --mode withvmd` |

A Mac's VMD.app is a macOS binary and **cannot run in a Linux container**, so mounting it fails (`vmd-agent bench docker
check-vmd` says so). VMD is also architecture-specific: the Linux tarball must match `VMD_PLATFORM` (default
`linux/amd64`; on Apple Silicon this runs under emulation, which is slow). Check what VMD offers for your CPU.

```bash
export ANTHROPIC_API_KEY=...        # a dedicated key with a spending limit; passed by name, never stored
export DATA_DIR=$PWD/data           # holds your trajectories; the suite and outputs go here too

vmd-agent bench docker preflight --mode withvmd --arms vmd_agent python_mdanalysis vmd_plain \
    --allow-exec --model anthropic:<id> --live-api            # first: prove VMD, selection, key, scrubbing
vmd-agent bench docker suite --mode withvmd --out /data/suite --seed 100 \
    --base /data/top.pdb /data/traj.dcd --structures /data/real/*.pdb
vmd-agent bench docker plan --mode withvmd --suite /data/suite --labels 6 --repeats 3 --price-in <USD/M> --price-out <USD/M>
vmd-agent bench docker run --mode withvmd --suite /data/suite --out-dir /data/out --repeats 3 --allow-exec \
    --model anthropic:<id> --arms vmd_agent vmd_agent_no_verify python_mdanalysis vmd_plain
```

Native equivalent: `vmd-agent bench agent-preflight --vmd "/Applications/VMD 1.9.4.app/Contents/vmd" --arms vmd_plain
--allow-exec --no-require-container`. On macOS the app's bare `vmd_MACOSX...` binary is found and `VMDDIR` is set for you
when it is unset.

**What `preflight` checks** (and `agent-run` re-runs, refusing to start if a blocking check fails): VMD found and
launching headless; a PDB loads and counts atoms; VMD evaluates a selection to 0-based indices (how the plain-VMD arm
is scored); `render TachyonInternal` writes an image (the plain-VMD arm's only way to make keyframe images); code
execution only with `--allow-exec` and only inside a container; model-written code sees no key, token or secret
variable; the key is set and the SDK installed; the suite and output directories exist. A model call is made only
with `--live-api`. The run's `manifest.json` records versions, the VMD path and version, the renderer, whether it ran in
a container and a hash of the suite, never a secret.

**What protects the key.** The benchmark process holds `ANTHROPIC_API_KEY`. Code the model writes (`run_python`,
`run_vmd_tcl`) runs with a **whitelisted environment** (search paths, locale, `VMD*`), so it cannot read the key. This is
not a sandbox: that code can still use the network from inside the container, so use a dedicated, spend-capped key and
a throwaway data directory. The container is also limited (`pids_limit`, `mem_limit`, read-only root, no
capabilities, no new privileges).

**Selections differ by arm.** For the plain-VMD arm the task asks for a *VMD* atom-selection string and a real VMD
scores it; every other arm uses MDAnalysis syntax. Results on the `selection` family therefore compare tool-native
syntax, not identical strings.

> **Status: never run against Docker or a Linux VMD.** Docker does not exist on the machine this was written on. The
> real-VMD tests (headless load, selection evaluation, rendering, the plain-VMD arm's workspace) were run once, on
> 2026-10-06, against VMD 1.9.4a57 on macOS Apple Silicon, and passed; they have not been run on Linux or Windows. What
> is tested without Docker: the shell scripts' syntax, the compose file's structure, the macOS-binary guard, the scrubbed
> environment, input screening before anything launches, preflight decisions, and the manifest. Whether `docker/install_vmd.sh` works for your tarball, whether the image
> builds, and whether VMD behaves headless in the container are unverified. `preflight` is how you find out, and
> `pytest -m requires_vmd -rs` runs the real-VMD tests on a machine that has it.

## Writing to the mounted folder

The image runs as an unprivileged user, so a folder mounted at `/data` must be writable by that user. If a command fails with
"Permission denied: '/data/...'", run the container as the owner of the folder: `docker run --user "$(id -u):$(id -g)" -e HOME=/tmp ...`
(or make the folder writable). Caught by the CI smoke test; not yet tried on a Docker Desktop for Mac or Windows.

## Hardening used by the compose file

Non-root user (uid 10001), read-only root filesystem, tmpfs `/tmp` and `/home/vmdagent`, all capabilities dropped,
`no-new-privileges`, and `VMD_AGENT_ALLOWED_ROOTS=/data` so the **server** tools can only touch `/data`.
For analysis-only work add `--network none` (downloads from RCSB/AlphaFold then fail by design).

## Status: not yet built or run

The Dockerfile, entrypoint, compose file and `docker/install_vmd.sh` were written **without Docker available**.
They are syntactically checked (YAML parses) and the CI workflow builds the open-source image and smoke-tests
it on first push. In particular **`docker/install_vmd.sh` is untested against a real VMD tarball**; VMD's
`configure` layout varies between releases. If it fails, use the mounted-VMD route above.

Apple-silicon note: VMD's Linux builds are x86-64 (and some aarch64); mounting a host install requires the
same architecture as the container.

---
