# Ways to work

Four ways in. They all call the same [tools](tools.md), so a number does not depend on how you asked for it.

| Way | For whom | How |
|---|---|---|
| **The web page** | you want everything in one window: files, chat, whole jobs, pictures | `vmd-agent ui` |
| **The menu** | you would rather not learn commands | type `vmd-agent`, pick a number |
| **Chat** | you want to ask in plain words, in the terminal | `vmd-agent chat` (or `vmd-agent chat "your question"` for a single answer) |
| **Commands** | scripts, batches, no AI | `vmd-agent <command> ...`, listed in the [command reference](commands.md) |

## The web page (`vmd-agent ui`)

```bash
vmd-agent ui                    # opens your browser; Ctrl+C in the terminal stops it
vmd-agent ui --data-dir ~/my-project --port 8765 --no-browser
```

A workbench laid out like VMD's own windows: a **Molecules** list (VMD's Main window) and your files on the left, the **Display** in the middle (its Graphics window), the assistant on the right,
and a **console** along the bottom (its Tk console), with a menu bar on top (File, Molecule, Graphics, Display, Mouse, Animation, Extensions, Help) and a status bar under it. Every action is in
the menus, in the command palette (**Ctrl/⌘ K** searches all of them), on a keyboard shortcut (press **?**), or in the console. The three splitters resize the columns and the console (they are
remembered; double-click one to restore it), and the light/dark/automatic theme button is in the menu bar.

* **Molecules.** A table as in VMD: ID, **T** (top molecule), **D** (drawn), name, atoms, frames. Load several and show or hide each. Below it, everything in your files folder, with a drop zone and
  folders that open. Click a file for its details and read-only looks (`inspect files`, `detect system`, `structure stats`, `probe video`, each with its seconds); double-click a structure to draw it
  as a new molecule, or a trajectory to load it into the top molecule.
* **Representations** (Graphics menu, **Ctrl/⌘ R**). Each molecule has any number of representations, each with a selection, a drawing method (`Lines`, `Licorice`, `CPK`, `VDW`, `Points`, `Trace`,
  `Tube`) and a colouring method (`Name`, `Chain`, `ResType`, `Resid`, `Index`, `Mono`, `ColorID`). Selections use VMD's own language: `protein`, `water`, `backbone`, `sidechain`, `name CA`,
  `resname ALA GLY`, `chain A`, `resid 10 to 40`, `within 5 of resname LIG`, `same residue as ...`, combined with `and`, `or`, `not` and parentheses; a mistake is explained under the box.
* **Display.** Rotate, Move, Zoom and **Query** (click an atom to see what it is) mouse modes as in VMD's Mouse menu, perspective or orthographic projection, depth cueing, axes and background
  colour, and the animation bar (first, previous, play, next, last, reverse, a frame box, speed, and the loop, once and rock styles). **Save picture** keeps the view as a PNG. Images and videos that
  tools make open in the same place, and every figure is kept in a strip under the display. A system of more than 40,000 atoms opens as its backbone and non-solvent atoms only, and the caption says so.
* **Console.** VMD's commands for what the page shows: `mol new`, `mol addfile`, `mol addrep`, `mol modselect`, `mol modstyle`, `mol modcolor`, `mol delrep`, `mol top`, `mol delete`, `animate goto`, `animate forward`,
  `display projection`, `display depthcue`, `axes location`, `color Display Background`, `rotate`, `scale`, plus `ask ...` (send a question to the assistant), `look TOOL FILE`, `workflow NAME FILES` and `help`.
  Arrow keys recall earlier commands. It also logs every tool and model call with its seconds and progress, and the totals of the session.
* **Assistant, Chat.** The model's answer is written as Markdown (headings, lists, tables, code; never raw HTML), every tool call is a collapsible card with its arguments, result, a progress bar and
  **the seconds it took**, each model call is timed, and a line under every answer says where the time went. The numbers in an answer are checked against the tools' results exactly as in the terminal
  chat ([How the chat keeps a model honest](models.md#how-the-chat-keeps-a-model-honest)).
* **Assistant, Whole jobs.** Pick a [workflow](workflows.md), pick the files, run it, and read the verdict, the graded findings, the step table with seconds and the figures, with a link to the
  report. No model is needed for this tab.
* **Status bar.** Whether the model answers, VMD's version, ffmpeg, the mouse mode, and a **chat tools** menu: `all`, `core` or `vmd` (see [Does the model see all 53 at once?](tools.md#does-the-model-see-all-53-at-once)).
  On a narrow window the columns stack.

It runs **only on this computer**: it listens on 127.0.0.1, answers only requests addressed to it by that name, and wants the one-time key that is part of the address it prints (kept in a
cookie), so no other web page you have open can use it. It can read and write only inside your files folder, never overwrites an uploaded file, and runs one job at a time. It needs nothing
beyond what vmd-agent already installs. The drawing is vmd-agent's own and is a convenient look at a structure, not a replacement for VMD's: no surfaces, no secondary-structure
cartoons; for those, [drive VMD itself](vmd.md#6-drive-vmd-itself).

## Wall-clock time of every execution

Every model call and every tool call is timed, wherever you work:

* **Terminal chat:** each tool call prints its seconds; after each answer a line says `took 8.4 s (model 6.9 s in 2 calls; tools 1.3 s in 1 call, first words after 3.1 s)`;
  `/time` shows the whole conversation's totals and the slowest tools.
* **Web page:** the same, as cards, per-call lines and a chip under each answer.
* **Workflows:** every step of a report has its seconds.
* **The benchmark:** every run's record has `wall_s` (the whole run), `model_s` and `model_calls` (time inside the model's calls) and `tool_s` (time inside the tools);
  the summary has their means per arm, so a model's speed can be compared as well as its accuracy.
* **The tool test set:** the seconds of every case.

These are plain stopwatch times on your computer, including the model server's own work: they depend on your hardware and your model, and
nothing in the repository records any.

## Chat commands

Inside `vmd-agent chat`: `/tools` lists the tools, `/time` says where the time went, `/reset` starts over, `/help` shows this, `/quit` leaves.
Options: `--model NAME`, `--base-url ADDRESS`, `--api-key KEY`, `--roots FOLDER ...`, `--tools all|core|vmd|auto`, `--max-turns N`, `--temperature T`,
`--no-stream`, `--no-check`.

Things to ask (examples of what to type, not results): *"What is in 1ubq.pdb?"*, *"Draw it from the front and the side and tell me what each colour means."*,
*"Has my run settled? Use run.psf and run.dcd."*, *"Which salt bridges persist?"*, *"Build a solvated, neutral system from 1ubq.pdb."*, *"Does this structure
really have a ligand and a disulfide bond?"*

The answer appears as the model writes it (`--no-stream` to wait for the whole thing); each tool call is shown with its progress ("frame 20 of 50",
"adding a water box", "ray tracing 72 frames"). The `vmd` and `workflow` commands print the same progress on the error stream (`--quiet` hides it), so the
result on standard output stays clean to pipe.
