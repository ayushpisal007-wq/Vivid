#!/usr/bin/env python
"""Vivid -- deliberate failure-case demo for jury Q&A.

Runs every model on a close-up face photo and a fine-detail/busy-background
photo, and builds annotated contact sheets calling out exactly where and
why the stylization breaks down. These are expected weaknesses to have
ready talking points for, not bugs to fix.

Usage:
    python failure_cases.py
    python failure_cases.py --models paprika
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw

from compare import _font, build_contact_sheet
from metrics import compute_all
from models import MODEL_VARIANTS, get_device, load_models

# filename in failure_cases/inputs/ -> (display title, jury talking-point note)
CASES = {
    "face_closeup.jpg": (
        "Face close-up",
        "Watch the eyes, mouth corners and skin shading. These models were "
        "trained mostly on faces, but at close range you'll often see waxy "
        "skin, shifted eye shape, or asymmetric warping the source photo "
        "doesn't have.",
    ),
    "busy_background.jpg": (
        "Busy / fine-detail background",
        "Watch foliage, hair strands and repeated textures. The generator "
        "tends to flatten or smear high-frequency detail into blotchy "
        "regions instead of preserving individual leaves or strands.",
    ),
}


def _annotate(sheet_path: Path, title: str, note: str) -> None:
    sheet = Image.open(sheet_path).convert("RGB")
    band_h = 96
    canvas = Image.new("RGB", (sheet.width, sheet.height + band_h), "white")
    canvas.paste(sheet, (0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([0, sheet.height, sheet.width, sheet.height + band_h], fill=(255, 247, 214))
    draw.text((14, sheet.height + 8), f"Failure case: {title}", fill=(120, 60, 0), font=_font(20))
    draw.multiline_text((14, sheet.height + 36), _wrap(note, 100), fill=(60, 40, 0), font=_font(14), spacing=4)
    canvas.save(sheet_path)


def _wrap(text: str, width: int) -> str:
    import textwrap

    return "\n".join(textwrap.wrap(text, width))


def main():
    parser = argparse.ArgumentParser(description="Generate deliberate failure-case examples for jury Q&A.")
    parser.add_argument("--input", default="failure_cases/inputs")
    parser.add_argument("--output", default="failure_cases/outputs")
    parser.add_argument("--models", default="all")
    parser.add_argument("--device", default="auto")
    parser.add_argument("--size", type=int, default=512)
    args = parser.parse_args()

    model_names = list(MODEL_VARIANTS) if args.models == "all" else [m.strip() for m in args.models.split(",")]
    device = get_device(args.device)

    input_dir = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    available = {f: meta for f, meta in CASES.items() if (input_dir / f).exists()}
    if not available:
        raise SystemExit(f"No failure-case inputs found in {input_dir} (expected: {', '.join(CASES)})")

    print("Loading model weights...")
    models = load_models(model_names, device, size=args.size)

    for filename, (title, note) in available.items():
        image_path = input_dir / filename
        img = Image.open(image_path).convert("RGB")

        model_outputs = {}
        for name, model in models.items():
            out_img = model.run(img)
            out_dir = output_dir / name
            out_dir.mkdir(parents=True, exist_ok=True)
            out_img.save(out_dir / filename)
            model_outputs[name] = out_img

        sheet_path = output_dir / f"{image_path.stem}_failure_sheet.png"
        build_contact_sheet(image_path, model_outputs, sheet_path)
        _annotate(sheet_path, title, note)

        print(f"\n{title} ({filename})")
        for name, out_img in model_outputs.items():
            m = compute_all(img, out_img)
            print(
                f"  {name:16s} ssim={m['ssim']:.3f} hist_shift={m['hist_shift']:.3f} "
                f"edge_change={m['edge_density_change_pct']:+.1f}%"
            )
        print(f"  -> {sheet_path}")


if __name__ == "__main__":
    main()
