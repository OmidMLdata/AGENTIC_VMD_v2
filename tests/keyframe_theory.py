"""How a frame selection is scored against known events, and how likely evenly spaced frames are to catch an event: the yardstick the keyframe tests measure the selector with.

It lives with the tests because only they use it: the selector itself (``vmd_agent.dynamics.keyframes``) does not need to know where the events were."""
from typing import Sequence

import numpy as np


def evaluate_sampling(selected: Sequence[int], events: Sequence[dict],
                      tolerance: int = 0) -> dict:
    """Score a frame selection against labelled events.

    ``events`` are ``{"start": int, "end": int}`` in frame units. For each:

    * **hit**: a selected frame lies inside ``[start - tol, end + tol]``;
    * **bracketed**: frames exist at or before ``start`` *and* at or after
      ``end`` (the before/after states are both visible);
    * **localisation error**: distance in frames from the event centre to the
      nearest selected frame.
    """
    sel = np.sort(np.asarray(list(selected), dtype=int))
    hits = brk = 0
    errs = []
    per = []
    for ev in events:
        s, e = int(ev["start"]), int(ev["end"])
        hit = bool(np.any((sel >= s - tolerance) & (sel <= e + tolerance)))
        bracket = bool(np.any(sel <= s) and np.any(sel >= e))
        centre = (s + e) / 2
        err = float(np.min(np.abs(sel - centre))) if len(sel) else float("inf")
        hits += hit
        brk += bracket
        errs.append(err)
        per.append({"start": s, "end": e, "hit": hit, "bracketed": bracket,
                    "localisation_error_frames": err})
    n = max(len(events), 1)
    return {"n_events": len(events), "n_selected": int(len(sel)),
            "recall_hit": hits / n, "recall_bracketed": brk / n,
            "mean_localisation_error": float(np.mean(errs)) if errs else None,
            "per_event": per}


# ------------------------------------------- uniform-sampling sufficiency
def hit_probability_uniform(n_frames: int, k: int, event_len: int) -> float:
    """P(an event of ``event_len`` frames at a random position contains >=1
    of ``k`` evenly spaced samples).

    For spacing ``s = (n-1)/(k-1)`` an event window of length ``L`` is
    missed only if it fits entirely between two samples, giving
    ``P = min(1, (L + 1) / s)`` for a continuous placement.
    """
    if k <= 1 or n_frames <= 1:
        return 1.0 if event_len >= n_frames else 0.0
    s = (n_frames - 1) / (k - 1)
    return float(min(1.0, (event_len + 1) / s))


def frames_needed_uniform(n_frames: int, event_len: int,
                          p: float = 0.95) -> int:
    """Smallest ``k`` giving hit probability >= ``p`` with uniform sampling."""
    if event_len + 1 >= n_frames:
        return 1
    # P = (L+1)(k-1)/(n-1) >= p  =>  k >= 1 + p (n-1)/(L+1)
    return int(np.ceil(1 + p * (n_frames - 1) / (event_len + 1)))
