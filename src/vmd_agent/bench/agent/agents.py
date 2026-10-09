"""Agents the benchmark can run.

Scripted agents need no model and no network. They have two jobs:

1. **Prove the benchmark measures what it says.** ``OracleAgent`` knows the
   answers (must score 100 %); ``SloppyAgent`` makes the mistakes an unreviewed
   analysis makes (must score low and show *silent* errors).
2. **Check that the tasks are solvable with the toolkit's own tools.**
   ``ReferenceAgent`` solves each task through the ``vmd_agent`` arm's tools
   the way a careful user would. A task it fails is a gap in the toolkit, and
   is reported as such rather than hidden.

``LLMAgent`` runs a real model through a tool-use loop in the Anthropic Messages
tool-use protocol. The client is an argument (a real ``anthropic.Anthropic()``).
Its live test (``requires_api``) has **never been run** by the author.

Scripted agents are written against the task *kind*. They receive the full
task; an LLM agent receives only the public view (no kind, no truth).
"""
from __future__ import annotations

import os
import re
import time
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

import numpy as np

from vmd_agent.bench.agent import suite as S
from vmd_agent.bench.agent.tools import Environment, StepLimit

SYSTEM_PROMPT = (
    "You are an analyst automating molecular-visualization and trajectory "
    "analysis on files in a workspace. Use the tools provided. Check your "
    "data before trusting a number: if a file is damaged or a result cannot "
    "be trusted, say so in `issues` instead of reporting it as fine. If you "
    "cannot answer reliably, set abstain to true rather than guess. Finish "
    "with submit_answer and the JSON object the task asks for.")


def _ok(r) -> bool:
    return isinstance(r, dict) and not r.get("error")


class _Scripted(ABC):
    scripted = True

    def run(self, task: dict, env: Environment) -> dict:
        try:
            ans = self.solve(task, env)
        except StepLimit:
            ans = None
        except Exception as e:                       # a bug in the script
            env.log.append({"tool": "_agent_error", "args": {},
                            "error": f"{type(e).__name__}: {e}"})
            ans = None
        if ans is not None:
            env.call("submit_answer", {"answer": ans})
        return {"tokens_in": 0, "tokens_out": 0}

    @abstractmethod
    def solve(self, task, env):
        """Return the answer object for ``task`` (or None to submit nothing)."""


# ------------------------------------------------------------------ oracle
class OracleAgent(_Scripted):
    """Knows the truth. Scoring this must give 100 %: a ceiling and a check on
    the scorers."""
    name = "oracle"

    def __init__(self, truth: Dict[str, dict]):
        self.truth = truth

    def solve(self, task, env):
        t = self.truth[task["id"]]
        fam = task["family"]
        base = {"issues": [], "confidence": 1.0}
        if fam == "measure":
            return {"value": t["value"], **base}
        if fam == "event":
            ev = t["event"]
            return {"onset_frame": None if ev is None else ev["start"],
                    **base}
        if fam == "diagnosis":
            return {"value": t["value"], "issue": t["issue"], **base,
                    "issues": [] if t["issue"] == "none" else [t["issue"]]}
        if fam == "selection":
            return {"selection": "index " + " ".join(map(str, t["atoms"])),
                    **base}
        if fam == "keyframes":
            ev = t["event"]
            frames = [ev["start"] + 2, ev["end"], ev["end"] + 3][: t["k"]]
            from vmd_agent.visual.renderers import get_renderer
            f = task["files"]
            r = get_renderer("matplotlib").render_frames(
                f["topology"], f["trajectory"], frames,
                out_dir=os.path.join(task["workdir"], "oracle_frames"),
                width=320, height=240)
            imgs = [i["path"] for i in r.get("images", [])]
            return {"frames": frames, "images": imgs, **base}
        if fam == "report":
            from vmd_agent.bench import truth as bt
            g = bt.ground_truth(task["files"]["topology"])
            s = []
            if g.get("has_protein"):
                n = g["n_protein_chains"]
                s.append(f"It has {n} protein chain{'s' * (n != 1)}")
            s.append("It contains a ligand" if g.get("has_ligand")
                     else "It has no ligand")
            return {"report": s, **base}
        return None


# ------------------------------------------------------------------ sloppy
class SloppyAgent(_Scripted):
    """The mistakes of an unreviewed analysis: wrong selection, trusts the file
    header, never checks the data, always finds an event, never flags a
    problem. It reports every answer with full confidence."""
    name = "sloppy"

    def solve(self, task, env):
        f, kind, fam = task["files"], task["kind"], task["family"]
        top, trj = f["topology"], f.get("trajectory")
        base = {"issues": [], "confidence": 0.95}
        if fam == "measure":
            r = env.call("analyze_trajectory", {
                "topology": top, "trajectory": trj,
                "analyses": ["rmsd", "rgyr"], "selection": "protein"})
            if not _ok(r):
                return {"value": 0.0, **base}
            res = r["results"]
            if kind == "rmsd_last":
                return {"value": res["rmsd"]["summary"]["last"], **base}
            if kind == "rg_mean":
                return {"value": res["rgyr"]["summary"]["last"], **base}
            if kind == "cog_distance":
                return {"value": res["rgyr"]["summary"]["mean"], **base}
            ta = r["time_axis"]                      # trusts the file header
            return {"value": (r["n_frames"] - 1) * (ta.get("dt_ps") or 1.0)
                    / 1000.0, **base}
        if fam == "event":
            r = env.call("select_keyframes", {"topology": top,
                                              "trajectory": trj, "k": 3})
            fr = r.get("frames") or [0]
            return {"onset_frame": int(fr[len(fr) // 2]), **base}
        if fam == "diagnosis":
            r = env.call("analyze_trajectory", {
                "topology": top, "trajectory": trj, "analyses": ["rmsd"],
                "selection": "name CA"})
            v = (r.get("results", {}).get("rmsd", {}).get("summary", {})
                 .get("last") if _ok(r) else 0.0)
            return {"value": v, "issue": "none", **base}
        if fam == "selection":
            if kind == "near_residue":
                rid, _chain = _target_residue(task["prompt"])
                return {"selection": f"around {S.NEAR_CUTOFF} resid {rid}",
                        **base}
            if kind == "sidechain_range":
                lo, hi = re.search(r"residues (\d+) to (\d+)",
                                   task["prompt"]).groups()
                return {"selection": f"resid {lo}:{hi} and sidechain",
                        **base}
            return {"selection": "protein and around 5.0 protein", **base}
        if fam == "keyframes":
            r = env.call("select_keyframes", {
                "topology": top, "trajectory": trj, "k": 4, "render": True,
                "renderer": "matplotlib"})
            imgs = [p for _f, p in _rendered_pairs(r)]
            n = len(imgs)
            return {"frames": [int(x) for x in np.linspace(0, 119, n)],
                    "images": imgs, **base}
        if fam == "report":
            return {"report": ["It is a single-chain protein",
                               "It contains a ligand",
                               "The protein is mostly helical"], **base}
        return None


def _rendered_pairs(r: dict) -> List[tuple]:
    """``[(frame, image path)]`` from a ``select_keyframes(render=True)`` result."""
    rend = (r or {}).get("rendered") or {}
    return [(int(i["frame"]), i["path"]) for i in rend.get("images") or []
            if isinstance(i, dict) and "frame" in i and "path" in i]


def _target_residue(prompt: str):
    m = re.search(r"residue (\d+)(?: of chain (\S+))? itself", prompt)
    return m.group(1), m.group(2)


# --------------------------------------------------------------- reference
class ReferenceAgent(_Scripted):
    """A careful user of the toolkit. Reads notes and warnings, passes the
    right selection and the stated time step, flags damaged data, and checks
    its own write-up with ``verify_claims``."""
    name = "reference"

    def solve(self, task, env):
        f, kind, fam = task["files"], task["kind"], task["family"]
        top, trj = f["topology"], f.get("trajectory")
        base = {"issues": [], "confidence": 0.9}
        if fam == "measure":
            return self._measure(task, env, top, trj, kind, base)
        if fam == "event":
            return self._event(env, top, trj, base)
        if fam == "diagnosis":
            return self._diagnosis(env, top, trj, base)
        if fam == "selection":
            return self._selection(task, env, top, kind, base)
        if fam == "keyframes":
            r = env.call("select_keyframes", {
                "topology": top, "trajectory": trj, "k": 4, "render": True,
                "renderer": "matplotlib"})
            pairs = _rendered_pairs(r)
            if not _ok(r) or not pairs:
                return {"abstain": True, "issues": ["could not render frames"]}
            return {"frames": [f for f, _ in pairs],
                    "images": [p for _, p in pairs], **base}
        if fam == "report":
            return self._report(env, top, base)
        return None

    # ---- measure
    def _measure(self, task, env, top, trj, kind, base):
        if kind == "rmsd_last":
            r = env.call("analyze_trajectory", {
                "topology": top, "trajectory": trj, "analyses": ["rmsd"],
                "selection": "name CA"})
            return {"value": r["results"]["rmsd"]["summary"]["last"], **base}
        if kind == "rg_mean":
            r = env.call("analyze_trajectory", {
                "topology": top, "trajectory": trj, "analyses": ["rgyr"]})
            return {"value": r["results"]["rgyr"]["summary"]["mean"], **base}
        if kind == "cog_distance":
            a0, a1, b0, b1 = map(int, re.search(
                r"residues (\d+)-(\d+) and that of residues (\d+)-(\d+)",
                task["prompt"]).groups())
            r = env.call("analyze_trajectory", {
                "topology": top, "trajectory": trj, "analyses": ["distance"],
                "selection": f"protein and resid {a0}:{a1}",
                "sel2": f"protein and resid {b0}:{b1}"})
            return {"value": r["results"]["distance"]["summary"]["last"],
                    **base}
        r = env.call("analyze_trajectory", {
            "topology": top, "trajectory": trj, "analyses": ["rgyr"],
            "dt_ps": 400.0})
        return {"value": (r["n_frames"] - 1) * 0.4, **base}

    # ---- event
    def _event(self, env, top, trj, base):
        r = env.call("select_keyframes", {"topology": top, "trajectory": trj,
                                          "k": 4})
        cps = [c for c in (r.get("change_points") or []) if c["z"] >= 6.0]
        if not _ok(r):
            return {"abstain": True, "issues": [r.get("error", "failed")]}
        if not cps:
            return {"onset_frame": None, **base}
        best = max(cps, key=lambda c: c["z"])        # the strongest change
        return {"onset_frame": int(best["frame"]), **base}

    # ---- diagnosis
    def _diagnosis(self, env, top, trj, base):
        det = env.call("detect_system", {"topology": top, "trajectory": trj})
        r = env.call("analyze_trajectory", {
            "topology": top, "trajectory": trj, "analyses": ["rmsd"],
            "selection": "name CA"})
        text = " ".join([str(det.get("error", "")), str(r.get("error", "")),
                         " ".join(map(str, r.get("notes", []))),
                         str((r.get("pbc") or {}).get("warning", "")),
                         " ".join(map(str, det.get("warnings", []) or []))]
                        ).lower()
        if "non-finite" in text or "nan" in text:
            issue = "nonfinite_coordinates"
        elif "split across periodic" in text or "half the box" in text:
            issue = "pbc_broken"
        elif "atoms" in text and ("mismatch" in text or "differ" in text
                                  or "could not load" in text
                                  or "natoms" in text):
            issue = "atom_count_mismatch"
        else:
            issue = "none"
        if issue != "none":
            return {"value": None, "issue": issue, "issues": [issue],
                    "confidence": 0.9}
        return {"value": r["results"]["rmsd"]["summary"]["last"],
                "issue": "none", **base}

    # ---- selection (the toolkit has no selection builder: written by hand)
    def _selection(self, task, env, top, kind, base):
        p = task["prompt"]
        if kind == "near_residue":
            rid, ch = _target_residue(p)
            tgt = f"protein and resid {rid}" + (
                f" and chainID {ch}" if ch else "")
            return {"selection": f"protein and byres (around "
                                 f"{S.NEAR_CUTOFF} ({tgt})) and not ({tgt})",
                    **base}
        if kind == "sidechain_range":
            lo, hi = re.search(r"residues (\d+) to (\d+)", p).groups()
            return {"selection": f"protein and resid {lo}:{hi} and not "
                                 "name N CA C O and not name H*", **base}
        a, c = re.search(r"of chain (\S+) that are within [\d.]+ A of any "
                         r"protein atom of chain (\S+)\.", p).groups()
        return {"selection": f"protein and chainID {a} and around "
                             f"{S.INTERFACE_CUTOFF} (protein and chainID "
                             f"{c})", **base}

    # ---- report
    def _report(self, env, top, base):
        from vmd_agent.bench import truth as bt
        g = bt.ground_truth(top)
        cand = []
        if g.get("has_protein"):
            n = g["n_protein_chains"]
            cand.append(f"It has {n} protein chain{'s' * (n != 1)}")
        cand.append("It contains a ligand" if g.get("has_ligand")
                    else "It has no ligand")
        cand.append("It contains a nucleic acid" if g.get("has_nucleic")
                    else "It has no nucleic acid")
        v = env.call("verify_claims", {"topology": top, "claims": cand})
        keep = [x["claim"] if isinstance(x.get("claim"), str) else
                x.get("text", "") for x in v.get("results", [])
                if x.get("verdict") == "supported"]
        keep = [k for k in keep if k] or cand[:1]
        return {"report": keep, **base}


# --------------------------------------------------------------- LLM agent
class LLMAgent:
    """A model driven through the Anthropic tool-use protocol.

    ``client`` must provide ``client.messages.create(model=, max_tokens=,
    system=, tools=, messages=)``. Not run against a live API in this
    repository; its live test is opt-in (`VMD_AGENT_LIVE_TESTS=1`).
    """
    scripted = False

    def __init__(self, client, model: str, max_tokens: int = 2048,
                 max_turns: int = 30, temperature: float = 0.0,
                 system: str = SYSTEM_PROMPT):
        self.client, self.model = client, model
        self.max_tokens, self.max_turns = max_tokens, max_turns
        self.temperature, self.system = temperature, system
        self.name = f"llm:{model}"

    def run(self, task: dict, env: Environment) -> dict:
        from vmd_agent.bench.agent.tools import render_result
        msgs = [{"role": "user", "content": task["prompt"]}]
        t_in = t_out = 0
        model_s, model_calls = 0.0, 0
        for _ in range(self.max_turns):
            t0 = time.time()
            resp = self.client.messages.create(
                model=self.model, max_tokens=self.max_tokens,
                temperature=self.temperature, system=self.system,
                tools=env.tool_specs(), messages=msgs)
            model_s += time.time() - t0
            model_calls += 1
            use = getattr(resp, "usage", None)
            t_in += getattr(use, "input_tokens", 0) or 0
            t_out += getattr(use, "output_tokens", 0) or 0
            msgs.append({"role": "assistant", "content": resp.content})
            calls = [b for b in resp.content
                     if getattr(b, "type", None) == "tool_use"]
            if not calls:
                break
            results = []
            for c in calls:
                try:
                    out = env.call(c.name, dict(c.input or {}))
                except StepLimit as e:
                    out = {"error": str(e)}
                results.append({"type": "tool_result", "tool_use_id": c.id,
                                "content": render_result(out)})
            msgs.append({"role": "user", "content": results})
            if env.submitted is not None or len(env.log) >= env.max_steps:
                break
        return {"tokens_in": t_in, "tokens_out": t_out, "model_s": round(model_s, 2), "model_calls": model_calls}


class OpenAICompatAgent:
    """A model driven through the OpenAI-style chat API with tool calling.

    Covers open-source models served by Ollama, llama.cpp, vLLM or LM Studio, and
    hosted services with that API, through :mod:`vmd_agent.llm_client`. The model
    must finish by calling the ``submit_answer`` tool, exactly as for the Anthropic
    agent; a reply that never submits is scored as no answer. Its only test is a
    live one (``requires_llm``), which the author has never run: no model server was
    available.
    """
    scripted = False

    def __init__(self, base_url: str, model: str, api_key: Optional[str] = None,
                 max_turns: int = 30, temperature: float = 0.0,
                 system: str = SYSTEM_PROMPT, timeout: float = 900.0):
        self.base_url, self.model, self.api_key = base_url, model, api_key
        self.max_turns, self.temperature = max_turns, temperature
        self.system, self.timeout = system, timeout
        self.name = f"openai:{model}"

    def run(self, task: dict, env: Environment) -> dict:
        from vmd_agent.llm_client import (
            assistant_message, chat_completion, parse_choice, render_result,
            to_openai_tools, tool_message)
        specs = env.tool_specs()
        tools, names = to_openai_tools(specs), [s["name"] for s in specs]
        msgs = [{"role": "system", "content": self.system},
                {"role": "user", "content": task["prompt"]}]
        t_in = t_out = 0
        model_s, model_calls = 0.0, 0
        for _ in range(self.max_turns):
            t0 = time.time()
            resp = chat_completion(self.base_url, self.model, msgs, tools=tools,
                                   api_key=self.api_key,
                                   temperature=self.temperature,
                                   timeout=self.timeout)
            model_s += time.time() - t0
            model_calls += 1
            parsed = parse_choice(resp, names)
            t_in += parsed["usage"]["input_tokens"]
            t_out += parsed["usage"]["output_tokens"]
            msgs.append(assistant_message(parsed))
            if not parsed["tool_calls"]:
                break
            for c in parsed["tool_calls"]:
                if c["arguments_error"]:
                    out = {"error": c["arguments_error"]}
                else:
                    try:
                        out = env.call(c["name"], c["arguments"])
                    except StepLimit as e:
                        out = {"error": str(e)}
                msgs.append(tool_message(c["id"], c["name"],
                                         render_result(out)))
            if env.submitted is not None or len(env.log) >= env.max_steps:
                break
        return {"tokens_in": t_in, "tokens_out": t_out, "model_s": round(model_s, 2), "model_calls": model_calls}

