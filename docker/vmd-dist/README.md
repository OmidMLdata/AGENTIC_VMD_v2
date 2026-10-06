# VMD drop-folder (intentionally empty)

VMD cannot be redistributed with this project (UIUC license, see `../../NOTICE.md`).

To build the optional `with-vmd` image **for your own use**:

1. Download the Linux binary distribution from
   <https://www.ks.uiuc.edu/Research/vmd/> after accepting the license.
2. Put the `vmd-*.tar.gz` file in this directory.
3. From the repository root:
   `docker build -f docker/Dockerfile --target with-vmd -t vmd-agent:vmd-local .`

Tarballs here are git-ignored. **Do not push an image built this way.**
Prefer the `vmd-libs` image with your VMD mounted read-only; see `../docs/TECHNICAL.md#docker`.
