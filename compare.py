#!/usr/bin/env python
"""Vivid -- contact sheet + objective metrics generator.

For every input photo, builds a single labeled contact sheet (original +
each model's output side by side) and computes SSIM / color-histogram
shift / edge-density change between the original and each output.

Reuses cached outputs from outputs/{model}/{filename} if present (i.e.
run cartoonize.py first); otherwise generates them on the fly.

Usage:
    python compare.py
    python compare.py --input inputs/photo.jpg --models paprika,face_paint_v2
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from metrics import compute_all, crop_like
from models import MODEL_VARIANTS, get_device, load_models

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
PANEL_W = 380
LABEL_H = 36


def _font(size: int = 18) -> ImageFont.ImageFont:
    for candidate in ("arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _panel(img: Image.Image, label: str, width: int = PANEL_W) -> Image.Image:
    w, h = img.size
    new_h = max(1, int(h * (width / w)))
    resized = img.resize((width, new_h))
    canvas = Image.new("RGB", (width, new_h + LABEL_H), "white")
    canvas.paste(resized, (0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([0, new_h, width, new_h + LABEL_H], fill=(25, 25, 25))
    draw.text((10, new_h + 8), label, fill="white", font=_font(16))
    return canvas


def build_contact_sheet(original_path: Path, model_outputs: dict, out_path: Path) -> None:
    original = Image.open(original_path).convert("RGB")
    panels = [_panel(original, "Original")]
    for name, out_img in model_outputs.items():
        panels.append(_panel(out_img, name))

    pad = 12
    title_h = 40
    total_w = sum(p.width for p in panels) + pad * (len(panels) + 1)
    max_h = max(p.height for p in panels)
    sheet = Image.new("RGB", (total_w, max_h + title_h + pad * 2), "white")
    draw = ImageDraw.Draw(sheet)
    draw.text((pad, pad // 2), original_path.name, fill="black", font=_font(22))

    x, y = pad, title_h + pad
    for p in panels:
        sheet.paste(p, (x, y))
        x += p.width + pad

    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path)


def main():
    parser = argparse.ArgumentParser(description="Build before/after contact sheets and objective metrics.")
    parser.add_argument("--input", default="inputs")
    parser.add_argument("--outputs", default="outputs", help="Root of cartoonize.py outputs (reused if present)")
    parser.add_argument("--contact-sheets", default="contact_sheets")
    parser.add_argument("--models", default="all")
    parser.add_argument("--device", default="auto")
    parser.add_argument("--size", type=int, default=512)
    args = parser.parse_args()

    model_names = list(MODEL_VARIANTS) if args.models == "all" else [m.strip() for m in args.models.split(",")]

    input_path = Path(args.input)
    images = (
        sorted(p for p in input_path.iterdir() if p.suffix.lower() in IMAGE_EXTS)
        if input_path.is_dir()
        else [input_path]
    )
    if not images:
        parser.error(f"No images found at {input_path}")

    output_root = Path(args.outputs)
    sheets_root = Path(args.contact_sheets)
    sheets_root.mkdir(parents=True, exist_ok=True)

    models_loaded = None  # lazy: only load models if some cached output is missing
    metrics_rows = []

    for image_path in images:
        model_outputs = {}
        for name in model_names:
            cached = output_root / name / image_path.name
            if cached.exists():
                model_outputs[name] = Image.open(cached).convert("RGB")
            else:
                if models_loaded is None:
                    device = get_device(args.device)
                    print("Some outputs missing from outputs/ -- loading models to generate on the fly...")
                    models_loaded = load_models(model_names, device, size=args.size)
                img = Image.open(image_path).convert("RGB")
                out_img = models_loaded[name].run(img)
                out_dir = output_root / name
                out_dir.mkdir(parents=True, exist_ok=True)
                out_img.save(out_dir / image_path.name)
                model_outputs[name] = out_img

        sheet_path = sheets_root / f"{image_path.stem}_contact.png"
        build_contact_sheet(image_path, model_outputs, sheet_path)
        print(f"Contact sheet: {sheet_path}")

        original = Image.open(image_path).convert("RGB")
        for name, out_img in model_outputs.items():
            m = compute_all(crop_like(original, out_img), out_img)
            m.update(image=image_path.name, model=name)
            metrics_rows.append(m)
            print(
                f"  {image_path.name:28s} {name:16s} "
                f"ssim={m['ssim']:.3f} hist_shift={m['hist_shift']:.3f} "
                f"edge_change={m['edge_density_change_pct']:+.1f}%"
            )

    metrics_path = output_root / "metrics.csv"
    output_root.mkdir(parents=True, exist_ok=True)
    with open(metrics_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["image", "model", "ssim", "hist_shift", "edge_density_change_pct"])
        writer.writeheader()
        writer.writerows(metrics_rows)
    print(f"\nMetrics written to {metrics_path}")


if __name__ == "__main__":
    main()
