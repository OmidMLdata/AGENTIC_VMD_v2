# Models, and how the chat keeps one honest

## Free models (as of 2026-10-06)

These are the open-source models this toolkit suggests. On **2026-10-06**, while writing the code, each was checked against
the public [Ollama library](https://ollama.com/library): the name exists, the download size is what the registry reported,
the licence is what it serves, and the library page marks it as able to call tools (which this toolkit needs). Names move
quickly, so `vmd-agent models --check` asks the library again, and setup does that before it downloads anything.

| Model | Download | Licence | Suits | Note |
|---|---|---|---|---|
| `granite4.1:3b` | 2.1 GB | Apache 2.0 | 8 GB of memory | small and fast |
| `granite4.1:8b` | 5.35 GB | Apache 2.0 | 16 GB of memory, or a graphics card | **default** |
| `gemma4:e4b` | 6.58 GB | Apache 2.0 | 16 GB of memory, or a graphics card | alternative |
| `lfm2.5:8b` | 5.16 GB | LFM Open License v1.0 (not Apache; read it) | 16 GB of memory | fast on a plain CPU |
| `gemma4:12b` | 8.02 GB | Apache 2.0 | 32 GB of memory, or a good graphics card | larger |
| `gpt-oss:20b` | 13.79 GB | Apache 2.0 | 32 GB of memory, or a 16 GB graphics card | larger |
| `qwen3.8:27b` | 17.74 GB | Apache 2.0 | 48 GB of memory, or a 24 GB graphics card | largest listed |

**Read this before trusting it:** the sizes, names and licences were checked on that date, and the "suits" column is a rough
guide, not a measurement. **Only `granite4.1:8b` and `granite4.1:3b` were run with this toolkit** (on a Mac, 2026-10-06, a few dozen
questions about local files, trajectories and system building; this is not a benchmark). The 8B chose the right tools and reported
their numbers correctly in the questions tried, though it sometimes fills arguments badly. The 3B chose tools but often misread what
they returned, which is why the chat flags any number a tool did not return; **start with the 8B or larger**. The others are
unverified. Any other Ollama model, or any online OpenAI-compatible service, can be used instead. `vmd-agent tool verify_claims` checks any
statement against the data.

### Which one suits this computer, and downloading later

`vmd-agent models` reads this computer (memory, any NVIDIA graphics card and its memory; on Apple Silicon the memory is shared with the graphics, so all of it counts) and marks each model
**fits**, **tight** (it may run slowly, or fail when other programs are open) or **too big**, names the one it suggests, and shows which are already downloaded. Setup and the web page's
Model window show the same marks. The mark is a rough guide from the "suits" column, not a measurement.

Saying no in setup is never final. The choice is saved, and you can download any time:

* `vmd-agent models --install` asks which model (this computer's suggestion first) and sets up the private Ollama first if there is none; `vmd-agent models --install granite4.1:8b` names it;
* or open **Model** in the web page, then **Download a model**: pick one, tick the box that says how much will be downloaded, and it downloads with progress and switches the chat to it.

Nothing large is fetched without that yes: the Ollama program and each model are confirmed separately, with their sizes.

### How the chat keeps a model honest

Language models guess; these checks stop a guess from passing as a measurement.

* **A data question needs a tool.** If a model answers a question about your files from memory, the chat sends it back once and
  requires a tool call.
* **Numbers are checked.** After the answer, every number the model wrote is compared with what the tools returned (the numbers you wrote in your question count as given). A numbered answer with a number no tool returned is
  **sent back once** ("use only what the tools returned; if the question cannot be answered with them, say so"); if it still has such a number, or if the answer was already shown piece by piece
  (the terminal chat and the web page stream), the number is listed under the answer ("check these numbers yourself").
* **Arguments are put right when there is only one way to read them.** A number written as text, a list written as one word, `RMSD` for `rmsd`, `traj` for `trajectory`, a file name without its
  folder, a file that does not exist but has a companion of the same name (`protein.psf` when only `protein.pdb` is there), the trajectory given as the topology, a required file left out when the folder
  holds exactly one that fits: each is corrected and the result says so (`note_on_arguments`). Anything
  ambiguous is left for the tool to refuse, and `repair=False` turns this off.
* **The model reads a sentence, not only fields.** The results that were most often misread (`detect_system`, `structure_stats`) start with a plain `summary` sentence, and parameters whose names do
  not say what they do (`align`, `step`, `solvate`, ...) and choices with fixed values are described to the model.
* **A list of statements to judge is pointed at `verify_claims`**, and a question that names a whole job (has my run settled, prepare a simulation) at the workflow that does it; the model still makes the call.
* **Only the tools that fit are offered** with `--tools auto` ([details](tools.md#does-the-model-see-all-of-them-at-once)); the model can ask for more with `offer_tools`.
* **Inputs are protected.** No tool writes over a file the same call reads, and a trajectory that does not match its topology is an
  error, not an empty result.
* **Invented settings are ignored.** Models are not shown the `vmd_path` parameter (they invent paths); the toolkit finds VMD itself.
* **The context is big enough.** The private Ollama runs with a 16384-token context (Ollama's default of 4096 cuts off the model's own
  instructions and tools). With your own Ollama, set `OLLAMA_CONTEXT_LENGTH=16384`.
* **Answers are capped** (3000 tokens), so a rambling model is cut off instead of waited for.

`vmd-agent chat` options: `--model NAME`, `--base-url ADDRESS`, `--api-key KEY`, `--roots FOLDER ...` (what the AI may see),
`--tools all|core|vmd|auto`, `--max-turns N`, `--temperature T`, `--no-stream`, `--no-check`.
