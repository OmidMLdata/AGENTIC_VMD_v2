# Third-party software and licenses

This repository's own code is MIT licensed (see `LICENSE`). It interoperates
with, but **does not contain or redistribute**, the software below.

## VMD and Tachyon (not included)

VMD (Visual Molecular Dynamics) is developed by the Theoretical and
Computational Biophysics Group at the University of Illinois at
Urbana-Champaign and is distributed under the UIUC VMD license
(<https://www.ks.uiuc.edu/Research/vmd/current/LICENSE.html>). As of this
writing that license:

* permits you to create complementary works that interoperate with VMD and to
  direct users to obtain VMD from the TCBG server;
* restricts redistribution of VMD itself beyond narrow terms;
* requires a commercial license for commercial use.

For these reasons **no VMD binary, source or derived code is shipped in this
repository, in the Python package, or in the published Docker image.** The
published image is the open-source "base" image; VMD users either mount their own
installation or build the optional `with-vmd` image locally from a tarball they
downloaded after accepting the license themselves (see `docs/TECHNICAL.md#docker`).

The Tachyon ray tracer bundled inside VMD distributions is covered by its own
license; the same rule applies.

If you intend to redistribute a VMD-bearing image, or to use this toolkit
commercially with VMD, contact <vmd@ks.uiuc.edu>. This note is not legal advice.

## Python dependencies

| Package | License |
|---|---|
| MDAnalysis | GPL-3.0-or-later (imported as a library; see its terms if you redistribute a combined work) |
| NumPy, SciPy, pandas, networkx | BSD-3-Clause |
| Matplotlib | Matplotlib (PSF-style) |
| Pillow | HPND |
| mcp (optional) | MIT |
| freesasa (optional) | MIT |
| anthropic (optional) | MIT |

> **Note on MDAnalysis.** MDAnalysis is licensed GPL-3.0-or-later. This project
> depends on it as an imported library. If you redistribute a container that
> bundles MDAnalysis, you are redistributing GPL software and must satisfy its
> terms (source availability, license text). Review this with your institution
> before publishing an image.
