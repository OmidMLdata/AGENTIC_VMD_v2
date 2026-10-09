# (No `# syntax=` line: it makes the build fetch a frontend image from Docker Hub first, which fails whenever the Hub is slow, and nothing here needs it.)
#
# vmd-agent container images.   VMD IS NOT INCLUDED (UIUC license), see
# README.md (Docker section) and ../docs/NOTICE.md.
#
#   docker build -f docker/Dockerfile -t vmd-agent .                           # default: open-source
#   docker build -f docker/Dockerfile --target vmd-libs -t vmd-agent:hostvmd .  # + libs, mount your VMD
#   docker build -f docker/Dockerfile --target with-vmd -t vmd-agent:vmd .      # build in YOUR tarball
#
# Benchmark runs with a real VMD: `vmd-agent bench docker` (see the Docker section of README.md).
# VMD is a Linux binary: it must match the image CPU architecture (see
# VMD_PLATFORM in docker/docker-compose.yml).
#
# Build context is the repository root.
ARG PYTHON_VERSION=3.11
# Where the base image comes from: Docker Hub by default; CI uses a mirror of the same official image, because Docker Hub rate-limits shared runners.
ARG PYTHON_REGISTRY=docker.io/library

# ------------------------------------------------------------------ base ----
# Everything except VMD. The matplotlib renderer works here, so the toolkit is
# fully usable (inspection, detection, analysis, claims, keyframes, benchmark,
# figures) with only open-source software.
FROM ${PYTHON_REGISTRY}/python:${PYTHON_VERSION}-slim AS base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    MPLBACKEND=Agg \
    MPLCONFIGDIR=/tmp/mpl \
    HOME=/home/vmdagent \
    VMD_AGENT_ALLOWED_ROOTS=/data
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
 && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home --uid 10001 vmdagent \
 && mkdir -p /data /opt/vmd \
 && chown vmdagent:vmdagent /data
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
# [bench] adds the Anthropic SDK so `vmd-agent bench agent-run --model anthropic:...`
# works in the image. The key is never baked in: pass ANTHROPIC_API_KEY at run time.
RUN pip install ".[server,bench]" \
 && (pip install freesasa || echo "freesasa unavailable on this platform; SASA analysis disabled")
COPY docker/entrypoint.sh docker/install_vmd.sh /app/docker/
RUN chmod 0755 /app/docker/*.sh
LABEL org.opencontainers.image.title="vmd-agent" \
      org.opencontainers.image.description="Agentic molecular-visualization toolkit (MCP server + CLI). VMD not included." \
      org.opencontainers.image.licenses="MIT"

# -------------------------------------------------------------- vmd-libs ----
# Adds the shared libraries a VMD binary needs, but no VMD. Use it with a host
# installation mounted at /opt/vmd:  -v /path/to/vmd:/opt/vmd:ro  -e VMD_BIN=/opt/vmd/bin/vmd
FROM base AS vmd-libs
USER root
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libgl1 libglu1-mesa libx11-6 libxi6 libxinerama1 libxft2 \
      libfontconfig1 libxext6 libxrender1 tcsh \
 && rm -rf /var/lib/apt/lists/*

# -------------------------------------------------------------- with-vmd ----
# Installs a VMD tarball YOU placed in docker/vmd-dist/ after accepting UIUC's
# license. The result contains VMD: do NOT push or redistribute this image.
FROM vmd-libs AS with-vmd
COPY docker/vmd-dist/ /tmp/vmd-dist/
RUN /app/docker/install_vmd.sh /tmp/vmd-dist /opt/vmd && rm -rf /tmp/vmd-dist
ENV VMD_BIN=/opt/vmd/bin/vmd
LABEL vmd-agent.contains-vmd="true" \
      vmd-agent.redistributable="false"
USER vmdagent
WORKDIR /data
ENTRYPOINT ["/app/docker/entrypoint.sh"]

# ---------------------------------------------------------------- runtime ----
# LAST stage = what a plain `docker build .` produces: the open-source image.
FROM base AS runtime
USER vmdagent
WORKDIR /data
ENTRYPOINT ["/app/docker/entrypoint.sh"]
