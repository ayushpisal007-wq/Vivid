"""Objective before/after metrics for cartoonization outputs.

These are sanity/talking-point numbers for a jury demo, not a quality
benchmark -- a *good* cartoonization is expected to score low on SSIM
and high on histogram shift, since the whole point of the model is to
change local structure, texture and palette.
"""
from __future__ import annotations

import cv2
import numpy as np
from PIL import Image
from skimage.metrics import structural_similarity as ssim


def compute_ssim(original: Image.Image, output: Image.Image) -> float:
    """Structural similarity between original and stylized output (grayscale)."""
    o = np.array(original.convert("L").resize(output.size))
    p = np.array(output.convert("L"))
    score, _ = ssim(o, p, full=True)
    return float(score)


def compute_hist_shift(original: Image.Image, output: Image.Image) -> float:
    """Color histogram shift: 0 = identical palette, 1 = fully disjoint.

    Bhattacharyya distance between 3D RGB histograms -- captures the
    palette flattening / saturation boost cartoonization models are
    known for.
    """
    o = cv2.cvtColor(np.array(original.convert("RGB").resize(output.size)), cv2.COLOR_RGB2BGR)
    p = cv2.cvtColor(np.array(output.convert("RGB")), cv2.COLOR_RGB2BGR)
    bins = [8, 8, 8]
    ranges = [0, 256, 0, 256, 0, 256]
    hist_o = cv2.calcHist([o], [0, 1, 2], None, bins, ranges)
    hist_p = cv2.calcHist([p], [0, 1, 2], None, bins, ranges)
    cv2.normalize(hist_o, hist_o)
    cv2.normalize(hist_p, hist_p)
    return float(cv2.compareHist(hist_o, hist_p, cv2.HISTCMP_BHATTACHARYYA))


def compute_edge_density(img: Image.Image) -> float:
    """Fraction of pixels Canny marks as edges -- a proxy for fine detail."""
    gray = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 100, 200)
    return float(np.count_nonzero(edges)) / edges.size


def compute_edge_density_change(original: Image.Image, output: Image.Image) -> float:
    """Relative change in edge density (negative = smoother/flatter output)."""
    o_density = compute_edge_density(original.resize(output.size))
    p_density = compute_edge_density(output)
    if o_density == 0:
        return 0.0
    return (p_density - o_density) / o_density


def compute_all(original: Image.Image, output: Image.Image) -> dict:
    return {
        "ssim": round(compute_ssim(original, output), 4),
        "hist_shift": round(compute_hist_shift(original, output), 4),
        "edge_density_change_pct": round(compute_edge_density_change(original, output) * 100, 2),
    }
