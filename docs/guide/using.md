# Ways to work

Four ways in. They all call the same [tools](tools.md), so a number does not depend on how you asked for it.

| Way | For whom | How |
|---|---|---|
| **The web page** | you want everything in one window: files, chat, whole jobs, pictures | `vmd-agent ui` |
| **The menu** | you would rather not learn commands | type `vmd-agent`, pick a number |
| **Chat** | you want to ask in plain words, in the terminal | `vmd-agent chat` (or `vmd-agent chat "your question"` for a single answer) |
| **The command line** | scripts, batches, no AI | `vmd-agent tool NAME ...` for one tool, `vmd-agent workflow ...` for a whole job: [the command line](commands.md) |

## The web page (`vmd-agent ui`)

```bash
vmd-agent ui                    # opens your browser; Ctrl+C in the terminal stops it
vmd-agent ui --data-dir ~/my-project --port 8765 --no-browser
```

A workbench laid out like VMD's own windows, **in front of a real VMD**: a **Molecules** list and your files on the left, the **Display** in the middle, the assistant on the right, and a **console** along the bottom,
with a menu bar on top (File, Molecule, Graphics, Display, Mouse, Animation, Extensions, Help) and a status bar under it. Every action is in the menus, in the command palette (**Ctrl/⌘ K** searches all of them), on a
keyboard shortcut (press **?**), or in the console. The three splitters resize the columns and the console (they are remembered; double-click one to restore it), and the light/dark/automatic theme button is in the status bar.

**Nothing on the page is drawn by the page.** The display shows snapshots of a real VMD window, and every button sends a command to that VMD ([Your VMD window](window.md)). Opening a structure starts VMD for you if it is not
running; the window then sits on your screen, and you can use VMD's own mouse and menus in it as well: the page notices within a few seconds.

* **Molecules.** VMD's own list: ID, **T** (top molecule), **D** (drawn), name, atoms, frames, read from VMD. Load several and show or hide each. Below it, everything in your files folder, with a drop zone and
  folders that open. Click a file for its details and read-only looks (`inspect files`, `detect system`, `structure stats`, `probe video`, each with its seconds); double-click a structure to load it into VMD,
  or a trajectory to add its frames to the top molecule.
* **Representations** (Graphics menu, **Ctrl/⌘ R**). VMD's Graphical Representations: each molecule has any number of representations, each with a selection (VMD's own language, which VMD parses: an invalid one is
  reported under the box), any of VMD's drawing methods (`NewCartoon`, `QuickSurf`, `Licorice`, `CPK`, `VDW`, `Tube`, `Surf`, `MSMS`, ...), any colouring method (`Name`, `ResType`, `Structure`, `Chain`, `Beta`,
  `ColorID`, ...) and a material.
* **Display.** Rotate, Move and Zoom mouse modes act on VMD's view (drag the picture; Shift-drag moves in any mode; the wheel zooms; a double click resets). Perspective or orthographic projection, depth cueing, axes,
  shadows and background colour are VMD's settings. The animation bar steps and plays the frames **inside VMD** (first, previous, play, next, last, reverse, a frame box, speed, and the loop, once and rock styles).
  **Refresh** takes a new snapshot; **live** keeps taking them. **Save picture** has VMD's ray tracer draw the window as a PNG. Images and videos that tools make open in the same place, and every figure is kept in a
  strip under the display.
* **Console.** VMD's commands, sent to VMD: `mol new`, `mol addfile`, `mol addrep`, `mol modselect`, `mol modstyle`, `mol modcolor`, `mol delrep`, `mol top`, `mol delete`, `animate goto`, `animate forward`,
  `display projection`, `display depthcue`, `axes location`, `color Display Background`, `rotate`, `scale by`, plus `ask ...` (send a question to the assistant), `look TOOL FILE`, `workflow NAME FILES` and `help`.
  Arrow keys recall earlier commands. It also logs every tool and model call with its seconds and progress, and the totals of the session.
* **Assistant, Chat.** The model can drive the VMD window too (*"show the ligand as licorice"*, *"go to frame 20"*); the page updates when it does. The model's answer is written as Markdown (headings, lists, tables, code; never raw HTML), every tool call is a collapsible card with its arguments, result, a progress bar and
  **the seconds it took**, each model call is timed, and a line under every answer says where the time went. The numbers in an answer are checked against the tools' results exactly as in the terminal
  chat ([How the chat keeps a model honest](models.md#how-the-chat-keeps-a-model-honest)).
* **Assistant, Tools.** Every tool of the [library](tools.md) as a form, for people who prefer to click: pick a group and a tool, then fill in drop-downs (your files, filtered by kind: structures, trajectories, maps, videos, images;
  fixed choices such as `kind` or `fmt`), check boxes (`analyses`, yes/no options), number and text boxes (with the default shown), and a box for a scene's JSON (with a drop-down to load one from your files). The result is
  shown as a summary, the facts, the pictures and the files it made, with **the same command for a terminal** to copy.
* **Terminal.** The console also takes the real command line, for developers: `tools`, `tool NAME --flags`, `tool NAME --help`, `workflow` (a leading `vmd-agent` is accepted), run in your files folder, next to VMD's
  own viewer commands (`mol new`, `animate goto`).
* **Assistant, Whole jobs.** Pick a [workflow](workflows.md), pick the files, run it, and read the verdict, the graded findings, the step table with seconds and the figures, with a link to the
  report. No model is needed for this tab.
* **Model.** The page is connected to the model that setup chose. If none answers (the server is not running, or it lacks the model), a note says which of the two it is, with buttons to start the local
  model server, to choose another model (**Extensions, Model…**: the free local one, or any server with the common chat interface such as an online service, Ollama, LM Studio or vLLM) and to check again; a question
  asked meanwhile gets a plain explanation instead of an error, and the files, the look buttons, the whole jobs and the VMD window itself keep working. The page checks again every 15 seconds.
* **Status bar.** Whether the model answers, VMD's version, ffmpeg, the mouse mode, and a **chat tools** menu: `all` or `auto` (see [Does the model see all of them at once?](tools.md#does-the-model-see-all-of-them-at-once)).
  On a narrow window the columns stack.

It runs **only on this computer**: it listens on 127.0.0.1, answers only requests addressed to it by that name, and wants the one-time key that is part of the address it prints (kept in a
cookie), so no other web page you have open can use it. It can read and write only inside your files folder, never overwrites an uploaded file, and runs one job at a time. It needs nothing
beyond what vmd-agent already installs. The picture in the middle is always VMD's own: the page is a remote for a real VMD window ([the window](window.md)), so surfaces, cartoons and every
other style VMD has are available.

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
Options: `--model NAME`, `--base-url ADDRESS`, `--api-key KEY`, `--roots FOLDER ...`, `--tools all|auto`, `--max-turns N`, `--temperature T`,
`--no-stream`, `--no-check`.

Things to ask (examples of what to type, not results): *"What is in 1ubq.pdb?"*, *"Draw it from the front and the side and tell me what each colour means."*,
*"Has my run settled? Use run.psf and run.dcd."*, *"Which salt bridges persist?"*, *"Build a solvated, neutral system from 1ubq.pdb."*, *"Does this structure
really have a ligand and a disulfide bond?"*

The answer appears as the model writes it (`--no-stream` to wait for the whole thing); each tool call is shown with its progress ("frame 20 of 50",
"adding a water box", "ray tracing 72 frames"). The `tool` and `workflow` commands print the same progress on the error stream (`--quiet` hides it), so the
result on standard output stays clean to pipe.
