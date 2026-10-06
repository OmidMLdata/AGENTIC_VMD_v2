#!/bin/sh
# Run the VMD-automation benchmark in a container with YOUR VMD.
#
#   docker/bench.sh <command> [args...]
#
#   check-vmd            sanity-check the VMD you point at (no Docker needed)
#   preflight [args]     bench agent-preflight inside the container
#   suite [args]         bench agent-suite     (write tasks under /data)
#   plan [args]          bench agent-plan      (cost estimate; calls no model)
#   run [args]           bench agent-run       (--model needs ANTHROPIC_API_KEY)
#   shell                an interactive shell in the container
#
# Choose how VMD is supplied with MODE (default: plain):
#   MODE=hostvmd   mount a Linux VMD install:  VMD_HOME=/path/to/vmd  docker/bench.sh ...
#   MODE=withvmd   VMD built into a LOCAL image from docker/vmd-dist/*.tar.gz (never push it)
#   MODE=plain     no VMD (matplotlib renderer; the plain-VMD arm is unavailable)
#
# Other variables: DATA_DIR (default ./data, mounted at /data), VMD_PLATFORM
# (default linux/amd64; the VMD build must match), BENCH_MEM (default 8g).
#
# STATUS: UNTESTED against Docker or a real VMD (neither was available where
# this was written). `sh -n` syntax and the compose file's structure are checked
# by the test suite; everything else is what `preflight` is for. Run it first.
set -eu

HERE="$(cd "$(dirname "$0")" && pwd)"
COMPOSE="docker compose -f $HERE/docker-compose.yml"
MODE="${MODE:-plain}"
cmd="${1:-}"
[ $# -gt 0 ] && shift

case "$MODE" in
  plain)   SERVICE=bench;          PROFILE=bench ;;
  hostvmd) SERVICE=bench-hostvmd;  PROFILE=bench-hostvmd ;;
  withvmd) SERVICE=bench-withvmd;  PROFILE=bench-withvmd ;;
  *) echo "MODE must be plain, hostvmd or withvmd (got '$MODE')" >&2; exit 2 ;;
esac

check_vmd() {
  home="${VMD_HOME:-}"
  [ -n "$home" ] || { echo "set VMD_HOME to your VMD install directory" >&2; return 2; }
  exe=""
  for c in "$home/bin/vmd" "$home/vmd"; do
    [ -f "$c" ] && { exe="$c"; break; }
  done
  [ -n "$exe" ] || { echo "no vmd launcher in $home (looked for bin/vmd and vmd)" >&2; return 1; }
  if command -v file >/dev/null 2>&1; then
    kind="$(file -L "$exe" 2>/dev/null || true)"
    case "$kind" in
      *Mach-O*)
        echo "$exe is a macOS binary. A Linux container cannot run it." >&2
        echo "Use MODE=withvmd with the Linux tarball in docker/vmd-dist/, or run natively:" >&2
        echo "  vmd-agent bench agent-preflight --vmd <path-to-your-mac-vmd> ..." >&2
        return 1 ;;
    esac
  fi
  echo "found $exe"
  [ "$(uname -s)" = "Linux" ] || echo "note: host is $(uname -s); the mounted VMD must still be a Linux build matching VMD_PLATFORM=${VMD_PLATFORM:-linux/amd64}" >&2
}

run_in() {   # run_in <vmd-agent args...>
  if [ "$MODE" = hostvmd ]; then check_vmd >/dev/null || { check_vmd; exit 1; }; fi
  mkdir -p "${DATA_DIR:-$HERE/../data}"
  $COMPOSE --profile "$PROFILE" run --rm "$SERVICE" "$@"
}

case "$cmd" in
  check-vmd)  check_vmd ;;
  preflight)  run_in bench agent-preflight "$@" ;;
  suite)      run_in bench agent-suite "$@" ;;
  plan)       run_in bench agent-plan "$@" ;;
  run)        run_in bench agent-run "$@" ;;
  shell)      run_in sh ;;
  *) sed -n '2,24p' "$0"; exit 2 ;;
esac
