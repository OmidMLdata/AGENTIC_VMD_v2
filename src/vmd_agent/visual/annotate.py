"""Draw the colour key and structure statistics onto a rendered image.

A VMD render on its own does not say what its colours mean or how many bonds
are in the picture. This module composites a legend panel onto the image so
the figure is self-describing: colour swatches with labels, and a stats block
with atom/bond/link counts.

Uses Pillow when available and falls back to matplotlib, so it works in either
environment.
"""
from __future__ import annotations

import os
from typing import Optional, Sequence

_PANEL_BG = (255, 255, 255)
_TEXT = (25, 25, 25)
_MUTED = (110, 110, 110)


def _hex_to_rgb(h: str):
    h = (h or "#888888").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return (136, 136, 136)


def _font(size: int):
    from PIL import ImageFont
    candidates = []
    try:                                   # matplotlib bundles DejaVu on every OS
        import matplotlib
        candidates.append(os.path.join(matplotlib.get_data_path(), "fonts",
                                       "ttf", "DejaVuSans.ttf"))
    except Exception:
        pass
    for path in candidates + [
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                 "/System/Library/Fonts/Helvetica.ttc",
                 "C:/Windows/Fonts/arial.ttf"]:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def annotate_image(image_path: str,
                   color_keys: Sequence[dict] = (),
                   stats_lines: Sequence[str] = (),
                   legend_lines: Sequence[str] = (),
                   title: str = "",
                   out_path: Optional[str] = None,
                   panel_side: str = "right") -> dict:
    """Composite a colour key + statistics panel onto a rendered image.

    Parameters
    ----------
    color_keys : sequence of dicts from :func:`colorkey.color_key`
        Each has ``method``, ``description`` and ``entries`` (label/colour/hex).
    stats_lines : sequence of str
        Output of :func:`stats.stats_caption`.
    legend_lines : sequence of str
        Which representation is which component (the visual legend).
    panel_side : ``"right"`` (default) or ``"left"``
        Which side of the image the panel is attached to.
    """
    if panel_side not in ("right", "left"):
        return {"ok": False, "error": "panel_side must be 'right' or 'left', "
                                      f"got {panel_side!r}"}
    if not os.path.exists(image_path):
        return {"ok": False, "error": f"image not found: {image_path}"}
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return _annotate_matplotlib(image_path, color_keys, stats_lines,
                                    legend_lines, title, out_path)

    img = Image.open(image_path).convert("RGB")
    W, H = img.size
    panel_w = max(360, int(W * 0.42))
    f_title = _font(max(15, panel_w // 24))
    f_head = _font(max(13, panel_w // 30))
    f_body = _font(max(11, panel_w // 34))

    # ---- measure required height (wrap first, then count real lines) -------
    pad, sw = 16, int(f_body.size * 1.1)
    line_h = int(f_body.size * 1.55)
    from PIL import ImageDraw as _ID
    probe = _ID.Draw(Image.new("RGB", (10, 10)))
    avail = panel_w - 2 * pad

    def _wrap(text, font, width, drawer=probe):
        words, lines, cur = str(text).split(), [], ""
        for w in words:
            t = (cur + " " + w).strip()
            if drawer.textlength(t, font=font) <= width:
                cur = t
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines or [""]

    need = pad * 2
    if title:
        need += len(_wrap(title, f_title, avail)) * int(f_title.size * 1.4) + 6
    if legend_lines:
        need += int(f_head.size * 1.8)
        for ln in legend_lines:
            need += len(_wrap("• " + str(ln).replace("**", ""),
                              f_body, avail)) * line_h
        need += 8
    for ck in color_keys:
        need += int(f_head.size * 1.8)
        if ck.get("description"):
            need += len(_wrap(ck["description"], f_body, avail)) * line_h
        need += max(len(ck.get("entries", [])), 0) * line_h + 8
    if stats_lines:
        need += int(f_head.size * 1.8)
        for ln in stats_lines:
            need += len(_wrap(ln, f_body, avail)) * line_h
    need += pad

    panel_h = max(H, need)
    canvas = Image.new("RGB", (W + panel_w, panel_h), _PANEL_BG)
    left = panel_side == "left"
    canvas.paste(img, (panel_w if left else 0, (panel_h - H) // 2))
    d = ImageDraw.Draw(canvas)
    x0, y = (pad if left else W + pad), pad

    def wrap(text, font, width):
        words, lines, cur = str(text).split(), [], ""
        for w in words:
            t = (cur + " " + w).strip()
            if d.textlength(t, font=font) <= width:
                cur = t
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines

    if title:
        for ln in wrap(title, f_title, panel_w - 2 * pad):
            d.text((x0, y), ln, font=f_title, fill=_TEXT); y += int(f_title.size * 1.4)
        y += 6

    if legend_lines:
        d.text((x0, y), "WHAT YOU ARE LOOKING AT", font=f_head, fill=_TEXT)
        y += int(f_head.size * 1.8)
        for ln in legend_lines:
            for w in wrap("• " + str(ln).replace("**", ""), f_body,
                          panel_w - 2 * pad):
                d.text((x0, y), w, font=f_body, fill=_TEXT); y += line_h
        y += 8

    for ck in color_keys:
        d.text((x0, y), f"COLOUR KEY — {ck.get('method', '')}",
               font=f_head, fill=_TEXT)
        y += int(f_head.size * 1.8)
        if ck.get("description"):
            for w in wrap(ck["description"], f_body, panel_w - 2 * pad):
                d.text((x0, y), w, font=f_body, fill=_MUTED); y += line_h
        for e in ck.get("entries", []):
            rgb = _hex_to_rgb(e.get("hex"))
            d.rectangle([x0, y + 3, x0 + sw, y + 3 + sw], fill=rgb,
                        outline=(60, 60, 60))
            d.text((x0 + sw + 8, y), f"{e.get('label')}  ({e.get('color')})",
                   font=f_body, fill=_TEXT)
            y += line_h
        y += 8

    if stats_lines:
        d.text((x0, y), "STRUCTURE STATISTICS", font=f_head, fill=_TEXT)
        y += int(f_head.size * 1.8)
        for ln in stats_lines:
            for w in wrap(ln, f_body, panel_w - 2 * pad):
                d.text((x0, y), w, font=f_body, fill=_TEXT); y += line_h

    out_path = out_path or _annotated_name(image_path)
    canvas.save(out_path)
    return {"ok": True, "annotated_image": os.path.abspath(out_path),
            "source_image": os.path.abspath(image_path),
            "size": canvas.size}


def _annotated_name(path: str) -> str:
    base, ext = os.path.splitext(path)
    return f"{base}_annotated{ext or '.png'}"


def _annotate_matplotlib(image_path, color_keys, stats_lines, legend_lines,
                         title, out_path):
    """Fallback panel renderer when Pillow is unavailable."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.image as mpimg
    from matplotlib.patches import Rectangle

    img = mpimg.imread(image_path)
    fig, (ax, axl) = plt.subplots(1, 2, figsize=(14, 7), dpi=150,
                                  gridspec_kw={"width_ratios": [1.5, 1]})
    ax.imshow(img); ax.axis("off")
    if title:
        ax.set_title(title, fontsize=11)
    axl.axis("off")
    y = 1.0
    if legend_lines:
        axl.text(0, y, "WHAT YOU ARE LOOKING AT", fontsize=9, weight="bold")
        y -= 0.05
        for ln in legend_lines:
            axl.text(0, y, "• " + str(ln).replace("**", "")[:70], fontsize=7)
            y -= 0.035
        y -= 0.02
    for ck in color_keys:
        axl.text(0, y, f"COLOUR KEY — {ck.get('method','')}", fontsize=9,
                 weight="bold"); y -= 0.045
        for e in ck.get("entries", []):
            axl.add_patch(Rectangle((0, y - 0.012), 0.035, 0.025,
                                    facecolor=e.get("hex", "#888"),
                                    edgecolor="k", lw=0.5,
                                    transform=axl.transAxes))
            axl.text(0.05, y, f"{e.get('label')} ({e.get('color')})", fontsize=7)
            y -= 0.035
        y -= 0.02
    if stats_lines:
        axl.text(0, y, "STRUCTURE STATISTICS", fontsize=9, weight="bold")
        y -= 0.045
        for ln in stats_lines:
            axl.text(0, y, str(ln)[:70], fontsize=7); y -= 0.033
    out_path = out_path or _annotated_name(image_path)
    fig.tight_layout(); fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    return {"ok": True, "annotated_image": os.path.abspath(out_path),
            "source_image": os.path.abspath(image_path),
            "renderer": "matplotlib"}
