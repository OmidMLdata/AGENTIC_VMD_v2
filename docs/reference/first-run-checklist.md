# First-run checklist

A walk-through for a person on a fresh computer. It covers what automated tests cannot: whether a newcomer can get from nothing to a first answer without help. It takes about 30 minutes plus the downloads.

Do the steps in order, tick each one, and write down anything that surprised you, even if it worked. "I was not sure what to do here" is a useful report.

## Before you start

Write down:

* the operating system and version, and whether it is a Mac with Apple Silicon, an Intel Mac, Windows or Linux;
* the memory (Mac: Apple menu, About This Mac) and whether there is an NVIDIA graphics card;
* whether VMD is installed, and where (it is optional);
* how technical you are with a terminal: never used one, sometimes, often.

Use a computer or user account that has **never had vmd-agent on it**. If it has, delete the `~/vmd-agent` folder (Windows: `%USERPROFILE%\vmd-agent`) and any `.vmd-agent` folders first.

## 1. Install

- [ ] Open a terminal using only the [README](../../README.md) (Mac: `Cmd` + `Space`, then `Terminal`; Windows: Start menu, then `PowerShell`).
- [ ] Paste the one install line for your system and press Enter.

**Expected:** a few minutes of downloading, ending with the lines `Done. The web page ...` and `To remove everything, just delete this folder`. It asked for no administrator password.
**Report if:** any error, a password prompt, it takes longer than ten minutes with no output, or you could not tell whether it had finished.

## 2. Setup

Setup starts by itself. Read each step and press Enter to accept the suggestion unless told otherwise.

- [ ] **Where it keeps its data** (only asked if you ran it outside your home folder): press Enter.
- [ ] **VMD:** it should find VMD if installed, and start it once. If VMD is not installed, it should say so and say that is fine. **It must not open a web page unless you answer yes.**
- [ ] **Your files folder:** press Enter (`~/vmd-agent-data`).
- [ ] **Who will you talk to:** press Enter for the free model. Note the line that describes your computer and the marks next to each model (fits, tight, too big). Does the suggested model look right for your computer?
- [ ] **Download the model:** it should name the size and ask. Answer **no** this time.
- [ ] Setup should end with how to download the model later. Does it say what to type?

**Report if:** a question you could not understand, a default that seemed wrong, a model marked "fits" that you doubt, any web page opening by itself, or a message that did not tell you what to do next.

## 3. Download the model later (the "I said no" path)

- [ ] Run `vmd-agent models` (use the full path from the install output if the command is not found). It should print your computer, a suggestion and a table.
- [ ] Run `vmd-agent models --install`. It should ask which model, with your computer's suggestion first, and ask before downloading.
- [ ] Accept. The download takes a while (2 to 18 GB). The first time, it also sets up a private copy of Ollama.

**Expected:** progress while it downloads, then "Ready".
**Report if:** it downloads without asking, the progress is unreadable, it fails, or it is unclear whether it finished.

## 4. Open the web page

- [ ] Run `vmd-agent ui` (full path if needed). A browser page should open.
- [ ] If VMD is installed, **a real VMD window should open by itself** within a few seconds. Note whether it came to the front and whether that bothered you.
- [ ] Look at the page without clicking anything. Could you tell what each of the three areas is for?

**Report if:** the page does not open, VMD does not open although it is installed, or you did not know what to do next.

## 5. Get example files and ask questions

Put these two files in your files folder (`~/vmd-agent-data`):

```bash
cd ~/vmd-agent-data
curl -O https://raw.githubusercontent.com/OmidMLdata/AGENTIC_VMD_v2/main/tests/data/ubq_md/protein.pdb
curl -O https://raw.githubusercontent.com/OmidMLdata/AGENTIC_VMD_v2/main/tests/data/ubq_md/protein.dcd
```

They appear in the page's Files list (use Refresh in the File menu if not). Then ask, one at a time in the chat:

- [ ] *"What is in protein.pdb?"*
- [ ] *"Has my run settled? Use protein.pdb and protein.dcd."*
- [ ] *"Show the protein as a surface coloured by residue type."* (needs VMD)
- [ ] *"Check this statement against my data: the protein has 76 residues."*

For each answer, check:

* Does it list the tools it ran, with seconds? Click one: do you see its arguments and result?
* Does every number in the answer appear in a tool result?
* **For the third question, look at the VMD window.** Does it show what the answer says? An answer that says something was drawn when the window did not change is a bug: report it with the exact wording.
* How long did each answer take? (A local 8B model on a laptop is expected to take 20 to 60 seconds.)

## 6. Things it should refuse

- [ ] *"Let me click an atom in the VMD window and tell me which residue I picked."* It should say plainly that it cannot, and offer something it can do.
- [ ] *"Open VMD's Timeline plugin window."* The same.
- [ ] *"Run NAMD on the system and tell me the energy."* The same.

**Report if:** it pretends, does something unrelated, or invents a result.

## 7. The other ways in

- [ ] In the page, open **Tools**, pick a group and a tool, fill in the form, and press Run. Does the result make sense?
- [ ] Open **Whole jobs**, choose `equilibration check` with the two files, and run it. Does it finish and show findings?
- [ ] Press `Ctrl+C` in the terminal to stop the page. Does a VMD window it opened stay open or close? Note which, and whether that surprised you.
- [ ] In a terminal, run `vmd-agent tool structure_stats protein.pdb` from your files folder. It works without the page.

## 8. Change your mind and remove it

- [ ] Run `vmd-agent doctor`. Can you read the result, and does it say what to do next?
- [ ] Delete the `~/vmd-agent` folder and `~/vmd-agent-data`. Is anything left that you did not expect? (VMD itself is never touched.)

## What to send back

For each step: **worked**, **worked but confusing**, or **failed**, with the exact text of any error (copy it) and anything you expected that did not happen. Include your answers to "Before you start", the version (`vmd-agent --version`), and how long the install and each model answer took.
