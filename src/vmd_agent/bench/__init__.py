"""Generated test structures with known answers.

``truth``   ground truth read from a structure file (no model involved)
``synth``   procedural novel structures with validated truth: the protein, trajectory and maps of the tool test set (``vmd-agent bench tools``) are made from these

An earlier study (end-to-end automation tasks for language-model agents, a grounded-interpretation benchmark and a paper about them) lived here; it is kept
in the Git tag ``archive/research-benchmark``, not in the product.
"""
from vmd_agent.bench import synth
from vmd_agent.bench.truth import classify_fold, ground_truth

__all__ = ["ground_truth", "classify_fold", "synth"]
