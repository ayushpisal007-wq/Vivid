#!/usr/bin/env python
"""Generate every image and number the website shows, using the real models.

Writes frontend/gallery/*.webp and frontend/gallery/showcase.json. Takes several minutes on CPU.
Re-run after changing models, or after adding photos to inputs/ or failure_cases/inputs/.

Usage:
    python tools/build_showcase.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from registry import FILTER_STYLE, MAX_SIDE, Registry, preprocess  # noqa: E402

OUT = ROOT / "frontend" / "gallery"
THUMB = 420
NAMES = {
    "sample_portrait": "Portrait",
    "sample_landscape": "Fjord",
    "sample_street": "Lioness",
    "face_closeup": "Face close-up",
    "busy_background": "Busy background",
}
EXTS = {".jpg", ".jpeg", ".png", ".webp"}
FLICKER_PHOTO = "sample_landscape"
FLICKER_STYLES = ("hayao_v3", "face_paint_v2")
FLICKER_SHIFT = 5  # pixels the "camera" moves between the two frames


def save(image: Image.Image, name: str) -> dict:
    image.save(OUT / f"{name}.webp", quality=84, method=6)
    thumb = image.copy()
    thumb.thumbnail((THUMB, THUMB), Image.LANCZOS)
    thumb.save(OUT / f"{name}.thumb.webp", quality=80, method=6)
    return {"src": f"gallery/{name}.webp", "thumb": f"gallery/{name}.thumb.webp", "w": image.width, "h": image.height}


def flicker(registry: Registry, photo: Image.Image, style: str) -> dict:
    """Two crops of one photo a few pixels apart, like consecutive video frames.

    Once lined up again the two inputs are identical, so any difference left between the two
    outputs was introduced by the model.
    """
    s = FLICKER_SHIFT
    w, h = 640, 448
    frames = [photo.crop((x, 40, x + w, 40 + h)) for x in (100, 100 + s)]
    outs = [registry.stylize(f, style)[0] for f in frames]
    a = outs[0].crop((s, 0, w, h))
    b = outs[1].crop((0, 0, w - s, h))
    m = 24  # ignore the borders, where the two crops really do see different pixels
    a, b = (im.crop((m, m, im.width - m, im.height - m)) for im in (a, b))
    diff = np.abs(np.asarray(a, float) - np.asarray(b, float)).mean(2)
    heat = Image.fromarray((diff * 4).clip(0, 255).astype(np.uint8)).convert("RGB")
    return {
        "style": style,
        "shift": s,
        "mean_diff": round(float(diff.mean()), 2),
        "changed_pct": round(float((diff > 8).mean() * 100), 1),
        "a": save(a, f"flicker__{style}__a"),
        "b": save(b, f"flicker__{style}__b"),
        "diff": save(heat, f"flicker__{style}__diff"),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    registry = Registry()
    photos, opened = [], {}
    for kind, folder in (("example", ROOT / "inputs"), ("stress", ROOT / "failure_cases" / "inputs")):
        for path in sorted(folder.iterdir()):
            if path.suffix.lower() not in EXTS:
                continue
            with Image.open(path) as im:
                im.load()
                image = im.copy()
                image.info = im.info
            original = preprocess(image)
            opened[path.stem] = original
            entry = {
                "id": path.stem,
                "name": NAMES.get(path.stem, path.stem.replace("_", " ").title()),
                "kind": kind,
                "original": save(original, f"{path.stem}__original"),
                "outputs": {},
            }
            for style in registry.styles:
                r = registry.run(image, style)
                # CartoonGAN runs smaller; scale back so before and after line up exactly.
                out = r.image if r.image.size == original.size else r.image.resize(original.size, Image.LANCZOS)
                entry["outputs"][style] = save(out, f"{path.stem}__{style}") | {"metrics": r.metrics}
                print(f"{path.stem:18s} {style:20s} {r.metrics['inference_ms']:8.0f} ms", flush=True)
            photos.append(entry)

    ai = [s for s in registry.styles if s != FILTER_STYLE]
    ms = [p["outputs"][s]["metrics"]["inference_ms"] for p in photos if p["kind"] == "example" for s in ai]
    data = {
        "styles": [s.info() | {"max_side": s.max_side} for s in registry.styles.values()],
        "photos": photos,
        "flicker": [flicker(registry, opened[FLICKER_PHOTO], s) for s in FLICKER_STYLES if s in registry.styles],
        "stats": {
            "styles": len(registry.styles),
            "ai_styles": len(ai),
            "avg_inference_ms": round(sum(ms) / len(ms)),
            "runs": len(ms),
            "max_side": MAX_SIDE,
            "device": str(registry.device),
        },
    }
    (OUT / "showcase.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
    print(json.dumps(data["stats"]), [(f["style"], f["mean_diff"], f["changed_pct"]) for f in data["flicker"]])


if __name__ == "__main__":
    main()
