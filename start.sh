#!/bin/sh
# vmd-agent: one command. Starts a local open-source model and opens the chat.
#
#   ./start.sh                 start everything and open the chat
#   ./start.sh "question"      ask once and exit
#   ./start.sh down            stop it
#
# You need Docker, and that is all. Put your files in ./data (the agent can only see that
# folder). First run downloads the model (several GB) and builds the image: be patient.
#
# Optional: VMD renders. VMD cannot be redistributed, so download the LINUX build of VMD
# from https://www.ks.uiuc.edu/Research/vmd/ (after accepting its licence), put the
# vmd-*.tar.gz in docker/vmd-dist/, and run this again. Without it, figures are drawn
# with the built-in matplotlib renderer. (A Mac or Windows VMD cannot run in Docker.)
#
# Settings (environment variables): MODEL (default granite4.1:8b), DATA_DIR (default ./data),
# DOCKER (default docker).
#
# STATUS: NEVER RUN. Docker was not available where this was written; no model, Ollama
# or VMD was run with it. Its syntax and the compose files' structure are checked by the
# tests, nothing more.
set -eu

cd "$(dirname "$0")"
DOCKER="${DOCKER:-docker}"
MODEL="${MODEL:-granite4.1:8b}"
DATA_DIR="${DATA_DIR:-$PWD/data}"
export MODEL DATA_DIR

die() { echo "vmd-agent: $*" >&2; exit 1; }

command -v "$DOCKER" >/dev/null 2>&1 ||
  die "Docker is not installed. Install Docker Desktop (Mac/Windows) or Docker Engine (Linux): https://docs.docker.com/get-docker/ then run this again."
"$DOCKER" info >/dev/null 2>&1 ||
  die "Docker is installed but not running. Start Docker Desktop (or the docker service), then run this again."
"$DOCKER" compose version >/dev/null 2>&1 ||
  die "Docker Compose v2 is needed (it comes with Docker Desktop). See https://docs.docker.com/compose/install/"

FILES="-f docker/chat.compose.yml"
compose() { "$DOCKER" compose $FILES "$@"; }

if [ "${1:-}" = "down" ]; then
  compose down
  exit 0
fi

mkdir -p "$DATA_DIR"

# VMD: only if the user supplied the Linux tarball
if ls docker/vmd-dist/vmd*.tar.gz docker/vmd-dist/vmd*.tgz >/dev/null 2>&1; then
  VMD_TARGET=with-vmd
  echo "VMD tarball found: building the image with VMD (this image must not be shared)."
else
  VMD_TARGET=runtime
  echo "No VMD tarball in docker/vmd-dist/: using the built-in renderer. See the top of this script for VMD."
fi
export VMD_TARGET

# NVIDIA GPU, if there is one (Docker Desktop on a Mac cannot use the Mac's GPU)
if command -v nvidia-smi >/dev/null 2>&1 && "$DOCKER" info 2>/dev/null | grep -qi nvidia; then
  FILES="$FILES -f docker/chat.gpu.yml"
  echo "NVIDIA GPU found: the model will use it."
else
  echo "No GPU available to Docker: the model runs on the CPU (slower, especially on a Mac)."
fi

echo "Starting the model server..."
compose up -d ollama

if compose exec -T ollama ollama list 2>/dev/null | grep -q "^$MODEL"; then
  echo "Model $MODEL is already downloaded."
else
  echo "Downloading model $MODEL (several GB, first time only)..."
  compose exec -T ollama ollama pull "$MODEL"
fi

echo "Building the vmd-agent image (first time only)..."
compose build vmd-agent

echo
echo "Ready. Your files go in: $DATA_DIR"
compose run --rm vmd-agent chat "$@"
