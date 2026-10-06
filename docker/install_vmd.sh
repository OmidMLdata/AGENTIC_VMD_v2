#!/bin/sh
# Install a user-supplied VMD *binary* distribution into DEST.
#
#   install_vmd.sh [SRC_DIR=/tmp/vmd-dist] [DEST=/opt/vmd]
#
# STATUS: UNTESTED. The Dockerfile that calls this was written without access to
# Docker or a VMD tarball. It follows VMD's documented binary install
# (./configure; cd src; make install) but VMD's configure script layout varies
# between releases. It fails loudly instead of guessing; if it fails, use the
# `vmd-libs` image and mount a VMD you installed on the host (docs/TECHNICAL.md#docker).
set -eu
SRC="${1:-/tmp/vmd-dist}"
DEST="${2:-/opt/vmd}"

tarball=""
for f in "$SRC"/vmd*.tar.gz "$SRC"/vmd*.tgz "$SRC"/vmd*.tar.Z; do
  if [ -f "$f" ]; then tarball="$f"; break; fi
done
if [ -z "$tarball" ]; then
  echo "ERROR: no VMD tarball (vmd*.tar.gz) found in $SRC." >&2
  echo "Download the Linux binary from https://www.ks.uiuc.edu/Research/vmd/ after" >&2
  echo "accepting its license, put it in docker/vmd-dist/, and rebuild." >&2
  exit 1
fi

work="$(mktemp -d)"
tar -xzf "$tarball" -C "$work"
dir="$(find "$work" -maxdepth 1 -mindepth 1 -type d | head -n 1)"
[ -n "$dir" ] || { echo "ERROR: unexpected tarball layout" >&2; exit 1; }
cd "$dir"

mkdir -p "$DEST/bin" "$DEST/lib"
if ! grep -q 'install_bin_dir' configure; then
  echo "ERROR: this VMD release's configure script has no install_bin_dir;" >&2
  echo "install VMD on the host and mount it instead (docs/TECHNICAL.md#docker)." >&2
  exit 1
fi
sed -i.bak -E "s|^(\\\$?install_bin_dir)[[:space:]]*=.*|\\1=\"$DEST/bin\";|" configure
sed -i.bak -E "s|^(\\\$?install_library_dir)[[:space:]]*=.*|\\1=\"$DEST/lib/vmd\";|" configure
rm -f configure.bak
./configure
( cd src && make install )

if [ ! -x "$DEST/bin/vmd" ]; then
  echo "ERROR: VMD launcher not found at $DEST/bin/vmd after install." >&2
  exit 1
fi
chmod -R a+rX "$DEST"
rm -rf "$work"
echo "VMD installed at $DEST/bin/vmd"
