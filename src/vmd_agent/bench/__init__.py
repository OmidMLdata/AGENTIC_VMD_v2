"""Generated test structures with known answers.

``truth``   ground truth read from a structure file (no model involved)
``synth``   procedural novel structures with validated truth: the protein, trajectory and maps of the tool test set (``vmd-agent bench tools``) are made from these
"""
from vmd_agent.bench import synth
from vmd_agent.bench.truth import classify_fold, ground_truth

__all__ = ["ground_truth", "classify_fold", "synth"]
