# Your VMD window

vmd-agent does not draw molecules itself. When you want to *see* something, it drives a **real VMD**: the one you would open yourself. The agent, the page, the command line and
an MCP client all send the same small set of commands to that VMD window, and everything you see is VMD's own drawing: its NewCartoon, QuickSurf, materials, lighting and
animation. If VMD can draw it, you can ask for it; if it cannot, vmd-agent cannot either.

There are two ways VMD is used, and they do different jobs:

| | Headless VMD | The VMD window |
|---|---|---|
| What it is | VMD run in the background with no window, once per question | one VMD with its window, which stays open |
| Tools | `measure_with_vmd`, `render_image`, `build_system`, ... | the `window_*` tools |
| Good for | numbers, files, renders for a report | looking at a system, changing how it is drawn, working with it while you talk to the agent |

## The tools

Thirteen tools in the group **Control your VMD window** (see [the library](tools.md)). They need a VMD with a window (or, for tests and servers, one without; see below).

| Tool | What it does |
|---|---|
| `window_open` | open a VMD window, or reuse the one that is open |
| `window_load` | load a structure (and trajectory), add frames to a molecule, or load a density map |
| `window_molecules` | list, make top, show, hide, rename, delete |
| `window_representation` | list, add, change, delete or replace (`only`) the representations of a molecule: selection, drawing method, colour, material |
| `window_display` | projection, depth cueing, background, axes, shadows, ambient occlusion, culling, antialiasing |
| `window_view` | reset, rotate, zoom, move, centre on a selection, save and restore a view |
| `window_animate` | go to a frame, play, pause, set the style and speed |
| `window_query` | what a selection holds (atoms, residues, chains, centre, extent, radius of gyration), a bond, angle, dihedral or SASA |
| `window_snapshot` | a picture of the window (VMD's own picture, or its built-in ray tracer with `--quality tachyon`) |
| `window_scene` | set up a whole scene at once from the same description `render_image` takes |
| `window_visualize` | draw a system the way the recipe would (what it holds, each part drawn to suit) and say what the colours mean |
| `window_movie` | a movie of the window: the trajectory played, or a turntable, drawn by VMD and encoded with ffmpeg |
| `window_save` | save the window's state as a `.vmd` file that VMD opens again |

```bash
vmd-agent tool window_load run.pdb run.dcd
vmd-agent tool window_representation --action only --selection protein --style NewCartoon --color Structure
vmd-agent tool window_representation --action add --selection "resname LIG" --style Licorice --color Name
vmd-agent tool window_view --action center --selection "resname LIG"
vmd-agent tool window_snapshot --out view.png
```

Each of those is a separate command, and they act on the same window: vmd-agent remembers it (in `live/link.json` inside vmd-agent's data folder, readable only by you; with a `.vmd-agent` working folder that is `.vmd-agent/live/link.json`).

## Everything else the toolkit does, in your VMD window

The window is not a separate feature: the tools that find something worth looking at can show it. Add `show_in_window` (`--show-in-window` on the command line, a check box in the page's forms) and the tool does what it always
did and then draws the result in VMD, opening it if needed. The result gains a `window` entry saying what was drawn.

| What the toolkit does | In the VMD window |
|---|---|
| `visualize_and_interpret`, `generate_visualization_recipe` | `window_visualize` draws the recipe's own choices (a cartoon for the protein, licorice for a ligand, spheres for ions, ...) with the legend; `visualize_and_interpret --show-in-window` does it as well as writing the images |
| `render_image` (scene), `export_session` | `window_scene`, and `--show-in-window` on either; `window_snapshot` is the picture, `window_save` the state file |
| `render_movie` | `window_movie` (the trajectory played, or a turntable) |
| `find_interactions` | the residues of the most persistent hydrogen bonds, salt bridges or contacts drawn as licorice (with VMD's H-bond drawing for hydrogen bonds) |
| `backbone_torsions` | the Ramachandran outliers in red, on the frame that was checked |
| `check_structure`, `secondary_structure` | the structure, on the frame checked; secondary structure as a cartoon coloured by VMD's own assignment |
| `select_keyframes` | the window goes to the first informative frame and the list is returned to step through |
| `align_structures` | the reference and the superposed structure, in two colours |
| `fit_to_map`, `make_map`, `combine_maps`, `inspect_map` | the map as an isosurface (at the map's mean plus three standard deviations unless you say), with the fitted model inside it |
| `build_system`, `mutate_residue`, `merge_structures`, `build_membrane`, `build_nanotube` | the built system, loaded and drawn |
| `run_workflow` | the outcome of the whole job: the structure with its outliers or interactions, the two runs side by side, the fitted model in its map, the built system |

Not drawn, because there is nothing to see: the numbers of `analyze_trajectory`, `measure_with_vmd` and `periodic_box` (use `window_query` for what the window itself can measure), the claim checks and records, the video
tools (a movie of the window is one `window_movie` away), `convert_trajectory` and `write_structure` (load the file they wrote with `window_load`).

## From the page, the chat and the agent

* **The web page** (`vmd-agent ui`) is a remote for the window. Its display shows VMD's snapshots; dragging the picture rotates the real VMD view, the wheel zooms it, a double click resets it. The molecule
  list, the Representations window, the animation bar, the menus and the console all send the commands above and then read VMD's state back. Changes made in VMD's own window show up in the page within a few
  seconds. Nothing on the page is drawn by the page.
* **The page's forms and the Whole jobs tab** have the check box *show in my VMD window*; the display updates when a job finishes.
* **The chat** can use the same tools: *"Show the ligand as licorice and the protein as a cartoon coloured by secondary structure"*, *"How many atoms does chain A have?"*, *"Go to frame 20"*, *"Zoom in on residue 25"*.
  The model cannot see the window; it reads what the tools return (the representations, the counts, the frame) and says what it did. Ask for a snapshot when you want a picture.
* **Without VMD installed** the page says so and the other tools still draw built-in pictures; the window tools need VMD.

## How it is kept safe

The window runs a small program (`vmdkit/live_bridge.tcl`) inside VMD that listens on `127.0.0.1` on a random port. Only a request that carries a one-time token can talk to it; the token is generated for each
window and kept in a file only you can read.

* A request is a **command name and arguments**. The names are a fixed list of 21; there is no command that runs Tcl, runs a program or reads a file, and VMD's `quit` is not among them.
* Every argument is checked **twice**, once in Python and again inside VMD: numbers are numbers, a molecule is one VMD has, a drawing method, colour or material is from VMD's own lists, a file is an absolute path inside
  the folders vmd-agent may use, and a selection contains only the characters VMD's selection language needs (no `$`, `[`, `]`, `;`, quotes or braces).
* A request is taken apart as a Tcl **list** and never evaluated, so text such as `[exit]` inside an argument is just text.
* VMD parses a selection before it is used, so an invalid one is an error you can read ("VMD cannot read that selection"), not a representation that silently draws nothing.

The tests send hostile requests straight to the socket (a wrong token, an unknown command, `eval`, `[exit]` in a selection, a relative path, a path with a brace) and check that VMD answers each with a refusal and
is still running afterwards. Security note: another program running as you on the same computer could read the token file; the window is as private as your user account.

## Limits to know

* Started with `vmd-agent tool window_open`, the page's **Open VMD window** button, or by the first command that needs it. On Linux a display is needed; on a server use `--headless` through the Python API or
  `VMD_AGENT_WINDOW_HEADLESS=1`, which runs the same commands with no window (pictures then come from VMD's built-in ray tracer).
* Picking an atom with the mouse, VMD's Tk windows (Timeline, Hydrogen Bonds, the plugin windows), labels, clipping planes are not exposed: do those in VMD itself.
* Where VMD closes the window, the link is gone; the next command says so and `window_open` starts a new one.
* Written and run on macOS (VMD 1.9.4a57, Apple Silicon). The window is started with `sh` and `tail`, so Linux uses the same path; Windows starts VMD directly, and neither has been run here.
