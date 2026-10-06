#!/bin/sh
# No arguments            -> run the MCP server on stdio.
# vmd-agent <subcommand>  -> the CLI.   (also accepts a bare subcommand)
set -e
case "${1:-}" in
  "")                                exec vmd-agent-server ;;
  vmd-agent|vmd-agent-server|python|python3|pytest|sh|bash) exec "$@" ;;
  -*)                                exec vmd-agent-server "$@" ;;
  *)                                 exec vmd-agent "$@" ;;
esac
