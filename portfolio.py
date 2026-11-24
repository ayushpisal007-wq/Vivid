#!/usr/bin/env python
"""Vivid -- builds a single polished HTML portfolio page from pipeline outputs.

Run after cartoonize.py and compare.py (and, ideally, failure_cases.py).
Produces portfolio/index.html: intro, before/after grid per photo, model
comparison table, failure-case section, and commentary.

The website (python server.py) is the main demo; this page is the offline version.

Usage:
    python portfolio.py
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
from collections import defaultdict
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from models import MODEL_VARIANTS

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

# failure_cases/inputs/{key}.jpg -> (display title, what to watch, what happened and why)
FAILURE_CASE_META = {
    "face_closeup": (
        "Face close-up",
        "Watch the eyes, brows and skin.",
        "face_paint_v2 sharpens eyes and brows that were never sharp in this 128 px photo, so "
        "the person changes a little. paprika adds cracks and hard shadows. celeba_distill irons "
        "the skin flat. Why: the models only know faces like the ones they were trained on. "
        "Low resolution and close range push them outside that, so they fill the gap with "
        "what they learned.",
    ),
    "busy_background": (
        "Busy / fine-detail background",
        "Watch the trees.",
        "face_paint_v2 smears leaves into soft blobs and celeba_distill fills them with a repeating "
        "pattern. Why: cartoons are flat shapes with clean lines, so the adversarial and style "
        "losses reward exactly that. Leaves don't fit, so they get flattened. It is a side "
        "effect of the goal, not a bug.",
    ),
}

# input filename -> spoken commentary; photos without an entry simply show no commentary block
PHOTO_NOTES = {
    "sample_landscape.jpg": (
        "paprika stays closest to the photo and mostly shifts the colours. face_paint_v2 turns the "
        "rock into brush strokes and the water to teal. celeba_distill gives the strongest drawn "
        "look, with black outlines, but scribbles over the fine rock texture. Our pick here is "
        "celeba_distill for style, or paprika if the scene must stay recognisable."
    ),
    "sample_portrait.jpg": (
        "face_paint_v2 is the clear pick: it was trained on faces, redraws the eyes cleanly and "
        "brightens the skin. celeba_distill goes full comic with heavy shadows. paprika fails here: "
        "it draws cracks across the bright forehead, and we keep that result in on purpose."
    ),
    "sample_street.jpg": (
        "A lioness, so a subject none of the face models expected. face_paint_v2 handles it best and "
        "paints the fur as soft shapes. paprika mainly cools the colours. celeba_distill pushes the "
        "shadows to black and scribbles on the fur."
    ),
}


def rel(path: Path, start: Path) -> str:
    return Path(os.path.relpath(path, start)).as_posix()


def load_metrics(path: Path) -> dict:
    metrics = {}
    if not path.exists():
        return metrics
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            metrics[(row["image"], row["model"])] = row
    return metrics


def main():
    parser = argparse.ArgumentParser(description="Build the Vivid HTML portfolio page.")
    parser.add_argument("--inputs", default="inputs")
    parser.add_argument("--outputs", default="outputs")
    parser.add_argument("--contact-sheets", default="contact_sheets")
    parser.add_argument("--failure-cases", default="failure_cases/outputs")
    parser.add_argument("--out", default="portfolio/index.html")
    args = parser.parse_args()

    inputs_dir = Path(args.inputs)
    outputs_dir = Path(args.outputs)
    sheets_dir = Path(args.contact_sheets)
    failure_dir = Path(args.failure_cases)
    out_path = Path(args.out)
    out_dir = out_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    metrics = load_metrics(outputs_dir / "metrics.csv")
    model_names = [n for n in MODEL_VARIANTS if (outputs_dir / n).is_dir()] or list(MODEL_VARIANTS)

    # --- before/after photo grid -------------------------------------------------
    photos = []
    if inputs_dir.is_dir():
        for image_path in sorted(inputs_dir.iterdir()):
            if image_path.suffix.lower() not in IMAGE_EXTS:
                continue
            per_model = []
            for name in model_names:
                out_img = outputs_dir / name / image_path.name
                if not out_img.exists():
                    continue
                m = metrics.get((image_path.name, name), {})
                per_model.append(
                    {
                        "name": name,
                        "description": MODEL_VARIANTS[name][1],
                        "src": rel(out_img, out_dir),
                        "ssim": m.get("ssim", "--"),
                        "hist_shift": m.get("hist_shift", "--"),
                        "edge_change": m.get("edge_density_change_pct", "--"),
                    }
                )
            if not per_model:
                continue
            sheet = sheets_dir / f"{image_path.stem}_contact.png"
            photos.append(
                {
                    "filename": image_path.name,
                    "original_src": rel(image_path, out_dir),
                    "sheet_src": rel(sheet, out_dir) if sheet.exists() else None,
                    "models": per_model,
                    "note": PHOTO_NOTES.get(image_path.name),
                }
            )

    # --- aggregated per-model averages -------------------------------------------
    sums = defaultdict(lambda: {"ssim": 0.0, "hist_shift": 0.0, "edge_change": 0.0, "n": 0})
    for (_, name), m in metrics.items():
        try:
            sums[name]["ssim"] += float(m["ssim"])
            sums[name]["hist_shift"] += float(m["hist_shift"])
            sums[name]["edge_change"] += float(m["edge_density_change_pct"])
            sums[name]["n"] += 1
        except (KeyError, ValueError):
            continue
    model_averages = []
    for name in model_names:
        s = sums.get(name)
        if s and s["n"]:
            model_averages.append(
                {
                    "name": name,
                    "description": MODEL_VARIANTS[name][1],
                    "ssim": round(s["ssim"] / s["n"], 3),
                    "hist_shift": round(s["hist_shift"] / s["n"], 3),
                    "edge_change": round(s["edge_change"] / s["n"], 2),
                    "n": s["n"],
                }
            )

    # --- failure cases -------------------------------------------------------------
    failure_cases = []
    if failure_dir.is_dir():
        for key, (title, note, why) in FAILURE_CASE_META.items():
            sheet = failure_dir / f"{key}_failure_sheet.png"
            if sheet.exists():
                failure_cases.append({"title": title, "note": note, "why": why, "sheet_src": rel(sheet, out_dir)})

    env = Environment(loader=FileSystemLoader(str(Path(__file__).parent / "templates")))
    template = env.get_template("portfolio_template.html")
    html = template.render(
        title="Vivid — Before/After Cartoonization Portfolio",
        generated_at=dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        models=[{"name": n, "description": MODEL_VARIANTS[n][1]} for n in model_names],
        photos=photos,
        model_averages=model_averages,
        failure_cases=failure_cases,
    )
    out_path.write_text(html, encoding="utf-8")
    print(f"Portfolio written to {out_path.resolve()}")
    print("Open it directly in a browser, or screen-share the tab for the jury.")
    if not photos:
        print("Warning: no photo outputs found -- run cartoonize.py and compare.py first.")


if __name__ == "__main__":
    main()
