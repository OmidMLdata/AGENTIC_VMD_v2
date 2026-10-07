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

* **Your files** (left): everything in your files folder, with a drop zone to add more. Click a structure, trajectory or video to look at it
  (`inspect files`, `detect system`, `structure stats`, `probe video`, each with the seconds it took), to see an image or play a video, or to ask the chat about it.
* **Chat** (middle): the model's text as it is written, and every tool it calls as a card with its arguments, a progress bar when the tool
  reports progress, any pictures it made, and **the seconds it took**. Each model call is timed too, and a line under every answer says where the time
  went. The numbers in the answer are checked against the tools' results exactly as in the terminal chat ([How the chat keeps a model honest](models.md#how-the-chat-keeps-a-model-honest)).
* **Whole jobs** (second tab): pick a [workflow](workflows.md), pick the files, run it, and read the verdict, the graded findings, the step table with
  seconds and the figures, with a link to the report. No model is needed for this tab.

It runs **only on this computer**: it listens on 127.0.0.1, answers only requests addressed to it by that name, and wants the one-time key that is part
of the address it prints (kept in a cookie), so no other web page you have open can use it. It can read and write only inside your files folder, never
overwrites an uploaded file, and runs one job at a time. It needs nothing beyond what vmd-agent already installs.

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
Options: `--model NAME`, `--base-url ADDRESS`, `--api-key KEY`, `--roots FOLDER ...`, `--tools all|core|vmd`, `--max-turns N`, `--temperature T`,
`--no-stream`, `--no-check`.

Things to ask (examples of what to type, not results): *"What is in 1ubq.pdb?"*, *"Draw it from the front and the side and tell me what each colour means."*,
*"Has my run settled? Use run.psf and run.dcd."*, *"Which salt bridges persist?"*, *"Build a solvated, neutral system from 1ubq.pdb."*, *"Does this structure
really have a ligand and a disulfide bond?"*

The answer appears as the model writes it (`--no-stream` to wait for the whole thing); each tool call is shown with its progress ("frame 20 of 50",
"adding a water box", "ray tracing 72 frames"). The `vmd` and `workflow` commands print the same progress on the error stream (`--quiet` hides it), so the
result on standard output stays clean to pipe.
