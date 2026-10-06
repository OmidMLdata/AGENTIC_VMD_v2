"""Benchmarks.

``bench.agent`` is the primary study: end-to-end VMD-automation tasks for LLM
agents (see ``docs/PAPER.md#5-the-automation-benchmark``). The modules below implement the
secondary grounded-interpretation component study.

Research question: does structured grounding (a visual legend, colour keys and
measured statistics) make a model's reading of a molecular visualization more
accurate, better calibrated and less prone to hallucination?

Pieces
------
``truth``        ground truth from the structure file (no model involved)
``questions``    questions with answers and the sources able to answer them
``conditions``   the grounding ladder, including adversarial conditions
``models``       offline baselines and an Anthropic API adapter
``scorer``       accuracy, hallucination, abstention, calibration, bootstrap CIs
``runner``       end-to-end evaluation of a model on a set of structures
``sampling``     uniform vs event-aware frame-selection simulation study (AR(1))
``events``       the same comparison on *real* MD noise with injected events
``synth``        procedural novel structures (contamination-free) with validated truth
``rating_study`` blinded expert-rating instrument for the representation policy
"""
from vmd_agent.bench.truth import ground_truth, classify_fold
from vmd_agent.bench.questions import build_questions
from vmd_agent.bench.conditions import (
    CONDITIONS, DEFAULT_CONDITIONS, build_context,
)
from vmd_agent.bench.scorer import summarize, paired_difference, parse_response
from vmd_agent.bench.runner import run_benchmark, plan_benchmark
from vmd_agent.bench import models, sampling, rating_study, synth, events
from vmd_agent.bench import agent

__all__ = ["ground_truth", "classify_fold", "build_questions", "CONDITIONS",
           "DEFAULT_CONDITIONS", "build_context", "summarize",
           "paired_difference", "parse_response", "run_benchmark",
           "plan_benchmark", "synth", "events", "models",
           "sampling", "rating_study", "agent"]
