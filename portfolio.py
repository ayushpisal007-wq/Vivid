#!/usr/bin/env python
"""Vivid -- builds a single polished HTML portfolio page from pipeline outputs.

Run after cartoonize.py and compare.py (and, ideally, failure_cases.py).
Produces portfolio/index.html: intro, before/after grid per photo, model
comparison table, failure-case section, and placeholder commentary blocks
you fill in before presenting.

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

# failure_cases/inputs/{key}.jpg -> (display title, jury talking-point note)
# kept in sync with failure_cases.py's CASES dict
FAILURE_CASE_META = {
    "face_closeup": (
        "Face close-up",
        "Watch the eyes, mouth corners and skin shading. These models were "
        "trained mostly on faces, but at close range you'll often see waxy "
        "skin, shifted eye shape, or asymmetric warping the source photo "
        "doesn't have.",
    ),
    "busy_background": (
        "Busy / fine-detail background",
        "Watch foliage, hair strands and repeated textures. The generator "
        "tends to flatten or smear high-frequency detail into blotchy "
        "regions instead of preserving individual leaves or strands.",
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
        for key, (title, note) in FAILURE_CASE_META.items():
            sheet = failure_dir / f"{key}_failure_sheet.png"
            if sheet.exists():
                failure_cases.append({"title": title, "note": note, "sheet_src": rel(sheet, out_dir)})

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
