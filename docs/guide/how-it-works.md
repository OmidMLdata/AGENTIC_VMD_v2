# How it works

This page explains what happens between your question and the answer, in the order it happens.

## The loop

```
your question
  → routing: choose the tools that fit the question
  → the model picks a tool and its arguments
  → argument repair: put right a slip when there is only one way to read it
  → the tool runs (VMD, the analysis code, ffmpeg, or the network)
  → the result goes back to the model, with a one-line summary where models misread
  → the model writes the answer from what the tool returned
  → the number check flags any number no tool returned
```

One module runs the model, the tools and the checks, and every front end sits on top of it, so the chat, the web page and the benchmark behave alike. Every model call and every tool call shows how long it took.

* **Routing.** By default (`--tools auto`) the model is offered only the tools that fit your question, plus a way to ask for more. All 57 descriptions together take most of a small model's context window, so offering a few works better.
  `--tools all` offers everything. [Which tools a model sees](tools.md#does-the-model-see-all-of-them-at-once).
* **Argument repair.** A number written as text, `RMSD` instead of `rmsd`, a file name without its folder, a trajectory given as the topology: each is put right when there is only one sensible reading, and the result says so.
* **Plain results.** The results models misread most start with a one-sentence summary, and parameters whose names do not say what they do are described to the model.
* **The guard.** A data question answered without a tool is sent back once. An answer containing a number no tool returned is sent back once, then flagged. Requests that cannot be answered are declined, not guessed. The guard also checks what an answer claims *happened*: a statement that something is shown in the VMD window needs a tool that actually changed the window, and a statement that a file was written needs a tool result that names it. A tool that draws in the window reports whether anything changed (`changed`), and says so when it did not.
* **Things it cannot do are refused up front.** Asking for mouse picking of atoms, VMD's own Tk plugin windows (Timeline and the others) or running NAMD gets a fixed, plain refusal that names what it can do instead, without asking the model, so a small model cannot quietly do the nearest thing and imply it did what you asked.

The model never computes. It chooses tools and reads what they return.

## Two ways VMD is used

| | Headless VMD | The VMD window |
|---|---|---|
| What it is | VMD in the background with no window, started for one job | One VMD with its window, which stays open |
| For | Numbers, files, builds, pictures for a report | Looking at a system and working with it while you talk to the agent |
| Tools | `measure_with_vmd`, `render_image`, `build_system` and the rest | The `window_*` tools, and `show_in_window` on many others |

Each tool that runs VMD saves the exact Tcl it used, so you can repeat it in your own VMD. The window link is described in [Your VMD window](window.md).

## Tools and whole jobs

A **tool** does one thing. There are 57, in eleven groups, and every one is available to the chat, to MCP clients and to `vmd-agent tool NAME`. [The tool library](tools.md).

A **workflow** runs several tools in a fixed order, grades what it finds (ok, note, warning, problem), gives a verdict and writes `report.md` and `report.html` with the figures, every caveat the tools raised, the methods, the
SHA-256 of each input and the Tcl of each VMD step. The agent reaches all eleven through one call, `run_workflow`; from a terminal it is `vmd-agent workflow NAME FILE ...`. [Whole jobs](workflows.md).

## Ways in

The web page, the numbered menu, the terminal chat and the command line all use the same tools. [Ways to work](using.md). The same tools are also an MCP server for Claude Code, Claude Desktop or any other client: [MCP clients](mcp.md).

## Where to read next

* How the code fits together: [Architecture](../reference/architecture.md#the-agent-and-what-surrounds-the-model)
* How each measurement is computed: [Methods](../reference/methods.md)
* What is protected and how: [Security](../reference/security.md)
* Which model to use, and how to compare them: [Models](models.md)
