"""Classical cartoon filter: no neural network, no learned weights.

The baseline Vivid uses to answer "how is this different from a photo filter?". It applies the
same three fixed steps to every photo, whatever is in it:
  1. bilateral filter       smooth textures, keep strong edges
  2. colour quantization    snap colours to a small palette
  3. adaptive threshold     draw dark outlines where brightness changes
"""
from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

PALETTE_SIZE = 16
HUE_WEIGHT = 2.5
KMEANS_SAMPLES = 20_000


def _smooth(rgb: np.ndarray) -> np.ndarray:
    # Filter at half size (several small passes beat one big one), then scale back up.
    h, w = rgb.shape[:2]
    small = cv2.resize(rgb, (max(1, w // 2), max(1, h // 2)), interpolation=cv2.INTER_AREA)
    for _ in range(5):
        small = cv2.bilateralFilter(small, d=9, sigmaColor=35, sigmaSpace=7)
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)


def _to_lab(rgb: np.ndarray) -> np.ndarray:
    lab = cv2.cvtColor(rgb.reshape(-1, 1, 3), cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float32)
    return lab * (1, HUE_WEIGHT, HUE_WEIGHT)


def _quantize(rgb: np.ndarray) -> np.ndarray:
    # k-means palette on a seeded sample, so the same photo always gives the same result. Clustering
    # weights hue over brightness, so small vivid areas (lips, signs) keep a colour of their own.
    pixels = rgb.reshape(-1, 3)
    n = min(KMEANS_SAMPLES, len(pixels))
    sample = pixels[np.random.default_rng(0).choice(len(pixels), n, replace=False)]
    cv2.setRNGSeed(0)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    k = min(PALETTE_SIZE, n)
    _, labels, centers = cv2.kmeans(_to_lab(sample).astype(np.float32), k, None, criteria, 2, cv2.KMEANS_PP_CENTERS)
    labels = labels.ravel()
    palette = np.stack([sample[labels == i].mean(0) if (labels == i).any() else np.zeros(3) for i in range(k)])
    # Nearest cluster per 5-bit RGB cell, then a lookup: much cheaper than per-pixel distances.
    levels = np.arange(32, dtype=np.uint8) * 8 + 4
    cells = np.stack(np.meshgrid(levels, levels, levels, indexing="ij"), -1).reshape(-1, 3)
    nearest = ((_to_lab(cells)[:, None] - centers[None]) ** 2).sum(-1).argmin(1)
    lut = palette.round().clip(0, 255).astype(np.uint8)[nearest]
    q = (pixels >> 3).astype(np.int32)
    return lut[(q[:, 0] << 10) | (q[:, 1] << 5) | q[:, 2]].reshape(rgb.shape)


def _edges(rgb: np.ndarray) -> np.ndarray:
    gray = cv2.medianBlur(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY), 7)
    return cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, blockSize=9, C=3)


def classic_cartoon(image: Image.Image) -> Image.Image:
    rgb = np.asarray(image.convert("RGB"))
    flat = _quantize(_smooth(rgb))
    return Image.fromarray(cv2.bitwise_and(flat, flat, mask=_edges(rgb)))
