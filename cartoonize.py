#!/usr/bin/env python
"""Vivid -- batch photo cartoonization CLI.

Runs every input photo through each loaded AnimeGAN2 model variant and
saves results to outputs/{model_name}/{filename}. Prints per-image,
per-model timing and writes it to outputs/timing_stats.csv.

Usage:
    python cartoonize.py                              # inputs/ -> outputs/, all models
    python cartoonize.py --input inputs/photo.jpg
    python cartoonize.py --models face_paint_v2,paprika
    python cartoonize.py --device cuda
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from PIL import Image
from tqdm import tqdm

from models import MODEL_VARIANTS, get_device, load_models

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def collect_images(input_path: Path) -> list[Path]:
    if input_path.is_file():
        return [input_path]
    return sorted(p for p in input_path.iterdir() if p.suffix.lower() in IMAGE_EXTS)


def main():
    parser = argparse.ArgumentParser(description="Cartoonize photos with pretrained AnimeGAN2 variants.")
    parser.add_argument("--input", default="inputs", help="Image file or folder of images (default: inputs/)")
    parser.add_argument("--output", default="outputs", help="Output root folder (default: outputs/)")
    parser.add_argument("--models", default="all", help="Comma-separated model names, or 'all' (default: all)")
    parser.add_argument("--size", type=int, default=512, help="Processing resolution (default: 512)")
    parser.add_argument("--device", default="auto", help="cpu | cuda | auto (default: auto)")
    args = parser.parse_args()

    model_names = list(MODEL_VARIANTS) if args.models == "all" else [m.strip() for m in args.models.split(",")]
    for name in model_names:
        if name not in MODEL_VARIANTS:
            parser.error(f"Unknown model '{name}'. Choices: {', '.join(MODEL_VARIANTS)}")

    device = get_device(args.device)
    input_path = Path(args.input)
    images = collect_images(input_path)
    if not images:
        parser.error(f"No images found at {input_path}")

    print(f"Device: {device}")
    print(f"Models: {', '.join(model_names)}")
    print(f"Images: {len(images)}")
    print("Loading model weights (first run downloads via torch.hub, then caches locally)...")
    models = load_models(model_names, device, size=args.size)

    output_root = Path(args.output)
    rows = []  # (image_name, model_name, elapsed_seconds)
    for image_path in tqdm(images, desc="Images"):
        img = Image.open(image_path).convert("RGB")
        for name, model in models.items():
            out_dir = output_root / name
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / image_path.name

            start = time.perf_counter()
            result = model.run(img)
            elapsed = time.perf_counter() - start

            result.save(out_path)
            rows.append((image_path.name, name, elapsed))
            tqdm.write(f"  {image_path.name:30s} -> {name:16s} {elapsed * 1000:8.1f} ms  ({out_path})")

    print("\nSummary (ms per image):")
    header = f"{'image':30s} " + " ".join(f"{n:>16s}" for n in model_names)
    print(header)
    by_image: dict[str, dict[str, float]] = {}
    for image_name, model_name, elapsed in rows:
        by_image.setdefault(image_name, {})[model_name] = elapsed * 1000
    for image_name, times in by_image.items():
        print(f"{image_name:30s} " + " ".join(f"{times.get(n, float('nan')):16.1f}" for n in model_names))

    stats_path = output_root / "timing_stats.csv"
    output_root.mkdir(parents=True, exist_ok=True)
    with open(stats_path, "w", encoding="utf-8") as f:
        f.write("image,model,ms\n")
        for image_name, model_name, elapsed in rows:
            f.write(f"{image_name},{model_name},{elapsed * 1000:.2f}\n")
    print(f"\nTiming stats written to {stats_path}")


if __name__ == "__main__":
    main()
