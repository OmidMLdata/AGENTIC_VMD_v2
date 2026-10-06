"""Prepare and verify rendered media so the agent can interpret it.

Interpretation itself is a model capability, not a script: this module does the
mechanical half. It probes an encoded video for real metadata, proves the file
actually decodes, pulls stills at known timestamps, runs quality control over
those stills (blank / frozen / uniform frames), maps every sampled still back to
a source trajectory frame, and writes a machine-readable manifest.

The contract with the agent is deliberate. Nothing here claims to have "watched"
a video. :func:`interpret_video` returns evidence -- verified metadata plus
stills at stated timestamps -- and the agent must view those stills with
``view_image`` before writing any interpretation. ``verification`` in the
returned package records exactly what was mechanically checked so the agent can
state the extent of verification honestly.

Encoded video is rendered *visual evidence*, never a molecular trajectory: VMD
cannot load an MP4 as coordinates, and :func:`probe_video` is the entry point
for that kind of input.
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import tempfile
import time
from typing import Optional, Sequence

# Containers we treat as rendered evidence rather than loadable coordinates.
_VIDEO_EXT = {".mp4", ".avi", ".mkv", ".mov", ".webm", ".gif", ".m4v",
              ".mpg", ".mpeg", ".ogv", ".wmv"}

# A frame whose grayscale spread is below this is effectively featureless.
_BLANK_STD = 2.0
# Side length of the grayscale fingerprint used for duplicate detection.
_FP_SIZE = 32
# Mean per-cell fingerprint difference below which two stills are called
# identical. Calibrated against real renders: consecutive frames of an
# equilibrating solvated protein -- where motion is genuinely subtle -- differ
# by ~0.9-2.2, while frames held frozen through the same H.264 encode differ by
# 0.000-0.008. 0.05 sits in that gap with a wide margin either side, so normal
# MD motion is never mistaken for a stalled encode.
_FROZEN_TOL = 0.05


def is_video(path: str) -> bool:
    """True when the extension names an encoded video/animation container."""
    return os.path.splitext(path)[1].lower() in _VIDEO_EXT


# ------------------------------------------------------------------ probing
def _rational(text) -> Optional[float]:
    """Parse an ffprobe rational such as ``'24/1'`` into a float."""
    if text in (None, "", "N/A"):
        return None
    try:
        s = str(text)
        if "/" in s:
            num, den = s.split("/", 1)
            den = float(den)
            return float(num) / den if den else None
        return float(s)
    except (TypeError, ValueError):
        return None


def _as_int(text) -> Optional[int]:
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def validate_decode(path: str, timeout: int = 300) -> dict:
    """Decode the whole stream to null and report any decoder complaints.

    Metadata can look perfectly healthy on a truncated or corrupt file, so a
    real decode pass is the only honest proof the video plays end to end.
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return {"checked": False, "reason": "ffmpeg not found"}
    try:
        proc = subprocess.run([ffmpeg, "-v", "error", "-i", path, "-f", "null", "-"],
                              capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"checked": True, "decodes": False, "errors": "decode timed out"}
    errs = (proc.stderr or "").strip()
    return {"checked": True, "decodes": proc.returncode == 0 and not errs,
            "returncode": proc.returncode,
            "errors": errs[-2000:] if errs else ""}


def probe_video(path: str, count_frames: bool = False,
                verify_decode: bool = True) -> dict:
    """Report real container/codec/geometry/timing metadata for a video.

    ``count_frames`` forces an exact frame count by decoding (slower); without
    it the container's declared ``nb_frames`` is used when present and a
    duration*fps estimate otherwise. ``n_frames_exact`` says which you got.
    """
    path = os.path.abspath(path)
    if not os.path.exists(path):
        return {"ok": False, "path": path, "exists": False,
                "error": f"video not found: {path}"}
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return {"ok": False, "path": path, "exists": True,
                "error": "ffprobe not found; cannot read video metadata."}

    try:
        proc = subprocess.run(
            [ffprobe, "-v", "error", "-print_format", "json",
             "-show_format", "-show_streams", path],
            capture_output=True, text=True, timeout=120)
        meta = json.loads(proc.stdout or "{}")
    except Exception as e:
        return {"ok": False, "path": path, "exists": True,
                "error": f"ffprobe failed: {e}"}

    streams = meta.get("streams") or []
    vs = next((s for s in streams if s.get("codec_type") == "video"), None)
    if vs is None:
        return {"ok": False, "path": path, "exists": True,
                "error": "no video stream found in file."}
    fmt = meta.get("format") or {}

    fps = _rational(vs.get("avg_frame_rate")) or _rational(vs.get("r_frame_rate"))
    duration = _rational(vs.get("duration")) or _rational(fmt.get("duration"))
    n_frames = _as_int(vs.get("nb_frames"))
    exact = n_frames is not None

    if count_frames or n_frames is None:
        counted = _count_frames(path)
        if counted is not None:
            n_frames, exact = counted, True
    if n_frames is None and fps and duration:
        n_frames, exact = int(round(fps * duration)), False

    info = {
        "ok": True, "path": path, "exists": True,
        "container": fmt.get("format_name"),
        "codec": vs.get("codec_name"),
        "profile": vs.get("profile"),
        "pix_fmt": vs.get("pix_fmt"),
        "width": _as_int(vs.get("width")),
        "height": _as_int(vs.get("height")),
        "fps": round(fps, 6) if fps else None,
        "duration_s": round(duration, 4) if duration else None,
        "n_frames": n_frames,
        "n_frames_exact": exact,
        "bitrate_kbps": (round(float(fmt["bit_rate"]) / 1000.0, 1)
                         if fmt.get("bit_rate") else None),
        "size_bytes": _as_int(fmt.get("size")),
        "n_audio_streams": sum(1 for s in streams
                               if s.get("codec_type") == "audio"),
    }
    if verify_decode:
        info["decode_check"] = validate_decode(path)
    return info


def _count_frames(path: str, timeout: int = 600) -> Optional[int]:
    """Exact frame count by decoding. Only used when the container is vague."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        proc = subprocess.run(
            [ffprobe, "-v", "error", "-count_frames", "-select_streams", "v:0",
             "-show_entries", "stream=nb_read_frames",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=timeout)
        return _as_int((proc.stdout or "").strip())
    except Exception:
        return None


# ------------------------------------------------------- frame fingerprints
def _frame_stats(png: str) -> dict:
    """Grayscale mean/spread plus a coarse fingerprint for duplicate detection.

    Returns ``{}`` when Pillow is unavailable so quality control degrades to
    "not checked" instead of guessing.
    """
    try:
        from PIL import Image
    except ImportError:
        return {}
    try:
        with Image.open(png) as im:
            g = im.convert("L")
            small = g.resize((_FP_SIZE, _FP_SIZE))
            px = list(small.tobytes())          # 'L' mode: one byte per pixel
        n = len(px)
        mean = sum(px) / n
        var = sum((p - mean) ** 2 for p in px) / n
        return {"mean": round(mean, 2), "std": round(var ** 0.5, 3),
                "fingerprint": px}
    except Exception:
        return {}


def _fingerprint_distance(a: Sequence[int], b: Sequence[int]) -> Optional[float]:
    if not a or not b or len(a) != len(b):
        return None
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)


def qc_frames(frames: Sequence[dict]) -> dict:
    """Flag blank and frozen stills among an ordered list of sampled frames.

    ``frames`` entries must carry ``index``, ``path`` and (optionally) ``stats``.
    A blank frame is near-uniform; a frozen run is consecutive stills that are
    visually identical, which usually means the encode stalled or the
    trajectory stopped advancing.
    """
    blank, frozen, checked = [], [], 0
    prev_fp, run_start = None, None
    for f in frames:
        st = f.get("stats") or {}
        fp = st.get("fingerprint")
        if not st:
            prev_fp = None
            continue
        checked += 1
        if st.get("std", 99) < _BLANK_STD:
            blank.append(f["index"])
        d = _fingerprint_distance(prev_fp, fp) if prev_fp else None
        if d is not None and d < _FROZEN_TOL:
            if run_start is None:
                run_start = f["index"] - 1
            frozen.append(f["index"])
        else:
            run_start = None
        prev_fp = fp

    issues = []
    if blank:
        issues.append(f"{len(blank)} blank/near-uniform frame(s) at index {blank}")
    if frozen:
        issues.append(f"{len(frozen)} frame(s) identical to the one before "
                      f"at index {frozen}")
    return {"checked_frames": checked,
            "blank_frame_indices": blank,
            "frozen_frame_indices": frozen,
            "all_frames_distinct": not frozen,
            "issues": issues,
            "passed": not blank and not frozen,
            "note": ("Quality control skipped: Pillow unavailable."
                     if checked == 0 else
                     "Mechanical checks only -- they cannot tell whether the "
                     "intended scientific event is present. View the stills.")}


# --------------------------------------------------------------- extraction
def _grab(video: str, t: float, out: str, ffmpeg: str,
          duration: Optional[float] = None,
          fps: Optional[float] = None) -> Optional[str]:
    """Pull the single frame nearest video time ``t``; return the method used.

    A plain forward seek can land past the final packet and silently produce
    nothing, which would drop the last frame -- the one most likely to show
    whether the run completed. Fall back to an exact output-side seek, then to
    a backwards seek from EOF.

    The EOF tail is sized in *frames*, not seconds: a fixed offset that is
    reasonable for a minute-long movie is several frames deep in a
    sub-second one, which would return an earlier frame masquerading as the
    last. Combined with ``-update`` (rather than ``-frames:v 1``) every frame
    in the tail is written in turn, so the file left behind is the true final
    frame.
    """
    t = max(float(t), 0.0)
    attempts = [("fast_seek",
                 ["-accurate_seek", "-ss", f"{t:.4f}", "-i", video],
                 ["-frames:v", "1"]),
                ("exact_seek",
                 ["-i", video, "-ss", f"{t:.4f}"],
                 ["-frames:v", "1"])]
    near_end = duration is None or t >= duration - 1.0
    if near_end:
        tail = max(2.5 / fps, 0.05) if fps else 0.35
        attempts.append(("seek_from_end",
                         ["-sseof", f"-{tail:.4f}", "-i", video],
                         ["-update", "1"]))
    for method, pre, post in attempts:
        if os.path.exists(out):
            os.remove(out)
        proc = subprocess.run([ffmpeg, "-y", *pre, *post, out],
                              capture_output=True, text=True)
        if (proc.returncode == 0 and os.path.exists(out)
                and os.path.getsize(out) > 0):
            return method
    return None


def _extract_by_index(video: str, indices: Sequence[int], out_dir: str,
                      ffmpeg: str) -> dict:
    """Extract exact frame numbers in a single decode pass.

    Timestamp seeking is unreliable near the end of a stream -- a forward seek
    can fall past the final packet and a backwards seek can land on an earlier
    frame -- which silently yields duplicate stills. Selecting by frame number
    is exact, and one pass covers every frame we want, so it is also cheaper
    than one seek per still. Returns ``{frame_index: png_path}``.
    """
    uniq = sorted({int(k) for k in indices})
    if not uniq:
        return {}
    # No shell is involved, so the filtergraph parser sees our quoting directly.
    # Single quotes protect the commas inside eq(n,k); the escaped form is the
    # equivalent unquoted spelling. Try both, and both ffmpeg flag spellings
    # (`-fps_mode` replaced `-vsync` in ffmpeg 5.1), so every build works.
    quoted = "select='" + "+".join(f"eq(n,{k})" for k in uniq) + "'"
    escaped = "select=" + "+".join(f"eq(n\\,{k})" for k in uniq)
    pattern = os.path.join(out_dir, "_sel_%04d.png")
    proc = None
    for vf in (quoted, escaped):
        for sync_flags in (["-fps_mode", "passthrough"], ["-vsync", "0"]):
            for stale in glob.glob(os.path.join(out_dir, "_sel_*.png")):
                os.remove(stale)
            proc = subprocess.run(
                [ffmpeg, "-y", "-i", video, "-vf", vf, *sync_flags, pattern],
                capture_output=True, text=True)
            n_out = len(glob.glob(os.path.join(out_dir, "_sel_*.png")))
            if proc.returncode == 0 and n_out == len(uniq):
                break
        else:
            continue
        break
    produced = sorted(glob.glob(os.path.join(out_dir, "_sel_*.png")))
    if proc.returncode != 0 or len(produced) != len(uniq):
        for f in produced:
            os.remove(f)
        return {}
    # ffmpeg writes the selected frames in ascending order.
    return dict(zip(uniq, produced))


def sample_frames(video: str, n: int = 9, out_dir: Optional[str] = None,
                  timestamps: Optional[Sequence[float]] = None,
                  include_endpoints: bool = True,
                  probe: Optional[dict] = None) -> dict:
    """Extract stills at known timestamps and fingerprint each one.

    By default the sample spans the full video and pins the true first and last
    frames, so the beginning and end are always inspected (the spec's
    begin/middle/end rule). Pass ``timestamps`` to target specific events.
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return {"ok": False, "error": "ffmpeg not found."}
    if not os.path.exists(video):
        return {"ok": False, "error": f"video not found: {video}"}

    info = probe or probe_video(video, verify_decode=False)
    if not info.get("ok"):
        return {"ok": False, "error": info.get("error", "probe failed"),
                "probe": info}
    dur = info.get("duration_s")
    fps = info.get("fps")
    out_dir = os.path.abspath(out_dir or tempfile.mkdtemp(prefix="vmd_frames_"))
    os.makedirs(out_dir, exist_ok=True)

    if timestamps is not None:
        times = [float(t) for t in timestamps]
    elif dur and dur > 0:
        n = max(int(n), 1)
        if include_endpoints and n >= 2:
            # Land inside the last frame rather than exactly at the end, where
            # a seek can fall past the final packet and return nothing.
            last = max(dur - (0.5 / fps if fps else 0.01), 0.0)
            times = [i * last / (n - 1) for i in range(n)]
        else:
            times = [dur * (i + 0.5) / n for i in range(n)]
    else:
        times = []

    n_total = info.get("n_frames")

    # Preferred path: turn each requested time into an exact frame number and
    # pull them all in one decode pass. Only when the container will not tell
    # us fps/frame-count do we fall back to per-timestamp seeking.
    if fps and n_total:
        wanted = []
        for t in times:
            k = int(max(float(t), 0.0) * fps)
            wanted.append(max(0, min(k, n_total - 1)))
        got = _extract_by_index(video, wanted, out_dir, ffmpeg)
        if got:
            frames, dropped = [], []
            for i, (t, k) in enumerate(zip(times, wanted)):
                src = got.get(k)
                if not src:
                    dropped.append({"index": i, "requested_time_s": round(t, 4)})
                    continue
                out = os.path.join(out_dir, f"frame_{len(frames):03d}.png")
                shutil.copyfile(src, out)
                entry = {"index": len(frames), "path": out,
                         "video_frame": k,
                         "video_time_s": round(k / fps, 4),
                         "extraction": "exact_frame_index"}
                if abs(entry["video_time_s"] - round(t, 4)) > 1e-6:
                    entry["requested_time_s"] = round(t, 4)
                entry["stats"] = _frame_stats(out)
                frames.append(entry)
            for f in got.values():
                if os.path.exists(f):
                    os.remove(f)
            if frames:
                return {"ok": True, "n_frames": len(frames), "frames": frames,
                        "n_requested": len(times), "dropped_frames": dropped,
                        "out_dir": out_dir, "probe": info}

    frames, dropped = [], []
    for i, t in enumerate(times):
        out = os.path.join(out_dir, f"frame_{i:03d}.png")
        method = _grab(video, t, out, ffmpeg, duration=dur, fps=fps)
        if method is None:
            dropped.append({"index": i, "requested_time_s": round(t, 4)})
            continue
        entry = {"index": len(frames), "path": out,
                 "video_time_s": round(t, 4)}
        if fps:
            # Frame k covers [k/fps, (k+1)/fps), so floor -- not round -- names
            # the frame a timestamp falls inside. Clamp because a request at or
            # past the end must map to the last real frame, never past it.
            vf = int(t * fps)
            if n_total:
                vf = min(vf, n_total - 1)
            entry["video_frame"] = max(vf, 0)
        if method != "fast_seek":
            entry["seek_method"] = method
        if method == "seek_from_end":
            # We landed on the final frame, wherever the caller aimed; report
            # where we actually are rather than the requested time.
            entry["requested_time_s"] = round(t, 4)
            entry["video_time_approximate"] = True
            if fps and n_total:
                entry["video_frame"] = n_total - 1
                entry["video_time_s"] = round((n_total - 1) / fps, 4)
        entry["stats"] = _frame_stats(out)
        frames.append(entry)

    if not frames:
        return {"ok": False, "error": "no frames could be extracted.",
                "probe": info, "out_dir": out_dir}
    return {"ok": True, "n_frames": len(frames), "frames": frames,
            "n_requested": len(times), "dropped_frames": dropped,
            "out_dir": out_dir, "probe": info}


def extract_frames(video: str, n: int = 9,
                   out_dir: Optional[str] = None) -> dict:
    """Extract ``n`` evenly-spaced frames from a video/GIF.

    Kept for the original ``extract_video_frames`` contract: returns plain PNG
    paths. :func:`interpret_video` is the richer entry point.
    """
    r = sample_frames(video, n=n, out_dir=out_dir)
    if not r.get("ok"):
        return {"ok": False, "error": r.get("error"), "n_frames": 0,
                "frames": [], "out_dir": r.get("out_dir")}
    return {"ok": True, "n_frames": r["n_frames"],
            "frames": [f["path"] for f in r["frames"]],
            "timestamps_s": [f["video_time_s"] for f in r["frames"]],
            "out_dir": r["out_dir"], "video_info": r["probe"],
            "note": "Hand these stills to the agent for visual interpretation; "
                    "do not over-claim dynamics from single frames."}


# ---------------------------------------------------------------- mapping
def map_to_source(frames: Sequence[dict], fps: Optional[float],
                  stride: int = 1, first_frame: int = 0,
                  time_per_frame: Optional[float] = None,
                  time_unit: str = "ns") -> dict:
    """Annotate each still with the source trajectory frame it came from.

    ``stride``/``first_frame`` describe how the movie sampled the trajectory;
    ``time_per_frame`` is simulation time per *saved trajectory frame*. Without
    it only frame indices are mapped, never invented times.
    """
    mapped = 0
    for f in frames:
        vf = f.get("video_frame")
        if vf is None and fps:
            vf = int(round(f.get("video_time_s", 0.0) * fps))
        if vf is None:
            continue
        src = first_frame + vf * max(int(stride), 1)
        f["source_frame"] = src
        if time_per_frame is not None:
            f["sim_time"] = round(src * float(time_per_frame), 6)
            f["sim_time_unit"] = time_unit
        mapped += 1
    return {"mapped_frames": mapped, "fps": fps, "stride": stride,
            "first_frame": first_frame,
            "time_per_frame": time_per_frame,
            "time_unit": time_unit if time_per_frame is not None else None,
            "relation": ("source_frame = first_frame + video_frame * stride"
                         if mapped else "no mapping available (fps unknown)")}


# ------------------------------------------------------------- validation
def validate_video(video: str, expect_width: Optional[int] = None,
                   expect_height: Optional[int] = None,
                   expect_fps: Optional[float] = None,
                   expect_n_frames: Optional[int] = None,
                   expect_min_duration_s: Optional[float] = None,
                   fps_tolerance: float = 0.51) -> dict:
    """Check an encoded video decodes and matches what was asked for.

    Every expectation left as ``None`` is reported as "not checked" rather than
    silently passing, so a thin check can never look like a thorough one.
    """
    info = probe_video(video, verify_decode=True)
    if not info.get("ok"):
        return {"ok": False, "error": info.get("error"), "probe": info}

    checks, failures = {}, []

    def record(name, expected, actual, passed):
        checks[name] = {"expected": expected, "actual": actual,
                        "checked": expected is not None,
                        "passed": None if expected is None else passed}
        if expected is not None and not passed:
            failures.append(f"{name}: expected {expected}, got {actual}")

    dec = info.get("decode_check") or {}
    decodes = dec.get("decodes")
    checks["decodes"] = {"expected": True, "actual": decodes,
                         "checked": bool(dec.get("checked")),
                         "passed": bool(decodes)}
    if dec.get("checked") and not decodes:
        failures.append(f"stream does not decode cleanly: {dec.get('errors','')[:200]}")

    record("width", expect_width, info.get("width"),
           info.get("width") == expect_width)
    record("height", expect_height, info.get("height"),
           info.get("height") == expect_height)
    record("fps", expect_fps, info.get("fps"),
           info.get("fps") is not None and expect_fps is not None
           and abs(info["fps"] - expect_fps) <= fps_tolerance)
    record("n_frames", expect_n_frames, info.get("n_frames"),
           info.get("n_frames") == expect_n_frames)
    record("min_duration_s", expect_min_duration_s, info.get("duration_s"),
           info.get("duration_s") is not None
           and expect_min_duration_s is not None
           and info["duration_s"] >= expect_min_duration_s)

    return {"ok": not failures, "video": info["path"], "probe": info,
            "checks": checks, "failures": failures,
            "summary": ("all requested checks passed" if not failures
                        else f"{len(failures)} check(s) failed")}


# ---------------------------------------------------------------- manifest
def write_manifest(out_path: str, payload: dict) -> str:
    """Write the machine-readable run manifest next to the outputs."""
    out_path = os.path.abspath(out_path)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w") as fh:
        json.dump(payload, fh, indent=2, default=str)
    return out_path


_WHAT_TO_LOOK_FOR = [
    "Is the molecular system present and correctly bonded in every still, or "
    "do atoms/bonds vanish between frames?",
    "Do parts of the system jump across the box between consecutive stills "
    "(periodic-boundary artefacts that wrapping/unwrapping would fix)?",
    "Is the scientific event of interest actually visible, and between which "
    "timestamps does it occur?",
    "Is the framing stable -- no clipping, occlusion, or drift that hides the "
    "event -- and are colours and labels consistent throughout?",
    "Do representations or selections change unexpectedly partway through?",
]


def interpret_video(video: str, n_frames: int = 9,
                    out_dir: Optional[str] = None,
                    timestamps: Optional[Sequence[float]] = None,
                    stride: int = 1, first_frame: int = 0,
                    time_per_frame: Optional[float] = None,
                    time_unit: str = "ns",
                    source_topology: Optional[str] = None,
                    source_trajectory: Optional[str] = None,
                    count_frames: bool = False,
                    manifest_path: Optional[str] = None) -> dict:
    """Turn an encoded video into inspectable, verified visual evidence.

    Probes the file, proves it decodes, samples stills at known timestamps,
    runs quality control, maps each still back to a source trajectory frame,
    and writes a manifest. Returns the evidence package -- the agent must then
    view each still with ``view_image`` before interpreting anything.
    """
    video = os.path.abspath(video)
    if not os.path.exists(video):
        return {"ok": False, "stage": "input",
                "error": f"video not found: {video}"}
    if not is_video(video):
        return {"ok": False, "stage": "input",
                "error": f"not a recognised video container: {video}",
                "hint": "Supported: " + ", ".join(sorted(_VIDEO_EXT))}

    info = probe_video(video, count_frames=count_frames, verify_decode=True)
    if not info.get("ok"):
        return {"ok": False, "stage": "probe", "error": info.get("error"),
                "probe": info}

    out_dir = os.path.abspath(out_dir or tempfile.mkdtemp(prefix="vmd_video_"))
    samp = sample_frames(video, n=n_frames, out_dir=os.path.join(out_dir, "frames"),
                         timestamps=timestamps, probe=info)
    if not samp.get("ok"):
        return {"ok": False, "stage": "extraction",
                "error": samp.get("error"), "probe": info}

    frames = samp["frames"]
    qc = qc_frames(frames)
    mapping = map_to_source(frames, info.get("fps"), stride=stride,
                            first_frame=first_frame,
                            time_per_frame=time_per_frame, time_unit=time_unit)

    dec = info.get("decode_check") or {}
    verification = {
        "metadata_read": True,
        "decode_verified": bool(dec.get("checked")),
        "decodes_cleanly": dec.get("decodes"),
        "frames_extracted_from_encoded_output": len(frames),
        "frames_span": ([frames[0]["video_time_s"], frames[-1]["video_time_s"]]
                        if frames else None),
        "quality_control_run": qc["checked_frames"] > 0,
        "frames_visually_inspected_by_agent": False,
        "statement": (
            f"{len(frames)} still(s) were decoded from the encoded output itself "
            f"and mechanically checked. No frame has been seen by the agent yet: "
            f"call view_image on each path before interpreting, and describe only "
            f"what those stills show."),
    }

    package = {
        "ok": True,
        "video": video,
        "probe": info,
        "verification": verification,
        "quality_control": qc,
        "frame_to_source_mapping": mapping,
        "frames": frames,
        "out_dir": out_dir,
        "source_topology": source_topology,
        "source_trajectory": source_trajectory,
        "what_to_look_for": _WHAT_TO_LOOK_FOR,
        "interpretation_instructions": (
            "Call view_image on every path in `frames`. Report events with the "
            "still's video_time_s and, when frame_to_source_mapping supplies "
            "them, its source_frame / sim_time. Keep three things apart: what "
            "is visibly in the stills, what was measured from the source "
            "trajectory by analyze_trajectory, and any mechanistic hypothesis. "
            "Stills are discrete samples -- an event between two of them is "
            "unobserved, not absent -- and never infer energies, barriers, "
            "rates, or significance from appearance. Store the result with "
            "record_visual_interpretation(kind='video')."),
    }

    manifest = {
        "tool": "vmd_agent.media.interpret_video",
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "inputs": {"video": video, "source_topology": source_topology,
                   "source_trajectory": source_trajectory},
        "video_metadata": {k: v for k, v in info.items() if k != "decode_check"},
        "decode_check": dec,
        "sampling": {"n_requested": n_frames, "n_extracted": len(frames),
                     "explicit_timestamps": list(timestamps) if timestamps else None,
                     "timestamps_s": [f["video_time_s"] for f in frames]},
        "frame_to_source_mapping": mapping,
        "quality_control": qc,
        "verification": verification,
        "outputs": {"out_dir": out_dir,
                    "frames": [f["path"] for f in frames]},
        "software": {"ffmpeg": shutil.which("ffmpeg"),
                     "ffprobe": shutil.which("ffprobe")},
    }
    package["manifest_path"] = write_manifest(
        manifest_path or os.path.join(out_dir, "video_manifest.json"), manifest)
    return package
