#!/bin/sh
# vmd-agent installer for macOS and Linux. Paste ONE line into a terminal:
#
#   curl -LsSf https://raw.githubusercontent.com/OmidMLdata/AGENTIC_VMD_v2/main/install.sh | sh
#
# Everything goes into ONE folder (default ~/vmd-agent; set VMD_AGENT_HOME to choose another):
#   uv, Python, vmd-agent and its packages, uv's cache, your settings, and (if you choose it) a private
#   copy of the Ollama model server with its models. Nothing is installed system-wide, no sudo is used,
#   and your PATH / shell files are NOT edited. To remove everything:  delete that folder.
#
# Steps (each is said out loud as it runs):
#   1. fetches "uv" (uv's official installer, https://astral.sh/uv/) into <folder>/uv, if not already there.
#   2. downloads vmd-agent from GitHub as a zip (no Git needed) and installs it with that private uv.
#   3. writes a launcher <folder>/bin/vmd-agent and starts the guided setup.
#
# STATUS: NEVER RUN. uv, GitHub access and a clean machine were not available where this was written.
# Its syntax is checked by the tests; the uv variables it sets were checked against uv's own installer
# script and docs. If a step fails, the message says which, and the README lists the manual alternative.
set -eu

SOURCE="${VMD_AGENT_SOURCE:-https://github.com/OmidMLdata/AGENTIC_VMD_v2/archive/refs/heads/main.zip}"
PYTHON="${VMD_AGENT_PYTHON:-3.12}"

say() { printf '\n==> %s\n' "$*"; }
die() { printf '\nvmd-agent installer: %s\n' "$*" >&2; exit 1; }

# If this script sits inside a downloaded copy of vmd-agent, install that copy instead of fetching one.
HERE=""
if [ -f "$0" ]; then HERE="$(cd "$(dirname "$0")" 2>/dev/null && pwd || echo "")"; fi
if [ -n "$HERE" ] && [ -f "$HERE/pyproject.toml" ] && grep -q 'name = "vmd-agent"' "$HERE/pyproject.toml" 2>/dev/null; then
  SOURCE="file://$HERE"
fi

command -v curl >/dev/null 2>&1 || die "curl is needed to download things and was not found. On Linux install it with your package manager (for example: sudo apt install curl), then run this again."

VMD_AGENT_HOME="${VMD_AGENT_HOME:-$HOME/vmd-agent}"
export VMD_AGENT_HOME
mkdir -p "$VMD_AGENT_HOME/bin" "$VMD_AGENT_HOME/internal-bin" "$VMD_AGENT_HOME/uv"
# Point every uv setting inside the one folder, so uv never writes anywhere else.
export UV_INSTALL_DIR="$VMD_AGENT_HOME/uv" UV_UNMANAGED_INSTALL="$VMD_AGENT_HOME/uv" UV_NO_MODIFY_PATH=1
export UV_CACHE_DIR="$VMD_AGENT_HOME/cache" UV_TOOL_DIR="$VMD_AGENT_HOME/tools"
export UV_TOOL_BIN_DIR="$VMD_AGENT_HOME/internal-bin" UV_PYTHON_INSTALL_DIR="$VMD_AGENT_HOME/python"
export UV_PYTHON_BIN_DIR="$VMD_AGENT_HOME/internal-bin"
UV="$VMD_AGENT_HOME/uv/uv"

if [ ! -x "$UV" ]; then
  say "Step 1 of 3: fetching uv into $VMD_AGENT_HOME/uv (a small tool that manages Python for you)"
  curl -LsSf https://astral.sh/uv/install.sh | sh || die "could not fetch uv. See https://docs.astral.sh/uv/getting-started/installation/ and run this again."
fi
[ -x "$UV" ] || die "uv was fetched but is not at $UV. Please report this."

say "Step 2 of 3: installing vmd-agent into $VMD_AGENT_HOME (downloads Python and packages; can take a few minutes)"
"$UV" tool install --python "$PYTHON" --force "vmd-agent[server] @ $SOURCE" \
  || die "installing vmd-agent failed (see the message above). Check your internet connection and try again."

# A launcher that always sets the folder, so settings and downloads stay inside it.
RUN="$VMD_AGENT_HOME/bin/vmd-agent"
{
  printf '#!/bin/sh\n'
  printf 'VMD_AGENT_HOME="%s"; export VMD_AGENT_HOME\n' "$VMD_AGENT_HOME"
  printf 'exec "%s/internal-bin/vmd-agent" "$@"\n' "$VMD_AGENT_HOME"
} > "$RUN"
chmod +x "$RUN"

say "Step 3 of 3: setup"
if (: < /dev/tty) 2>/dev/null; then       # a real terminal is attached (a readable /dev/tty file is not enough)
  # the script itself came through a pipe, so give the setup the keyboard explicitly
  "$RUN" setup < /dev/tty || true
else
  printf 'Installed. Now run:  %s setup\n' "$RUN"
fi

printf '\nDone. Next time run:  %s\n' "$RUN"
printf 'To remove everything, just delete this folder: %s\n' "$VMD_AGENT_HOME"
