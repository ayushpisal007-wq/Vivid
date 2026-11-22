"""Model loading and inference wrappers for Vivid.

Wraps pretrained AnimeGAN2 (bryandlee/animegan2-pytorch) generator
checkpoints behind a small, consistent interface so the rest of the
pipeline doesn't need to know about torch.hub or face2paint internals.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import torch
from PIL import Image

# No tagged releases on the upstream repo, so we pin to a branch ref.
# torch.hub caches the checkout under ~/.cache/torch/hub after first use.
HUB_REPO = "bryandlee/animegan2-pytorch:main"

# name -> (torch.hub pretrained weight key, human-readable description)
# These are the actual checkpoint names published by the repo. They are
# NOT literally named "Hayao"/"Shinkai" (those are the original TensorFlow
# AnimeGANv2 checkpoints) -- see README "How it works" for the distinction.
MODEL_VARIANTS = {
    "face_paint_v2": (
        "face_paint_512_v2",
        "General-purpose portrait/scene stylization, best all-round quality",
    ),
    "paprika": (
        "paprika",
        "Bolder, more graphic style inspired by Satoshi Kon's film 'Paprika'",
    ),
    "celeba_distill": (
        "celeba_distill",
        "Lighter distilled checkpoint, softer and subtler stylization",
    ),
}


def get_device(requested: str = "auto") -> torch.device:
    if requested != "auto":
        return torch.device(requested)
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


class CartoonModel:
    """One loaded AnimeGAN2 generator plus its face2paint pre/post-processor."""

    def __init__(self, name: str, device: torch.device, size: int = 512):
        if name not in MODEL_VARIANTS:
            raise ValueError(f"Unknown model '{name}'. Choices: {', '.join(MODEL_VARIANTS)}")
        weight_key, description = MODEL_VARIANTS[name]
        self.name = name
        self.description = description
        self.device = device

        self.generator = torch.hub.load(
            HUB_REPO, "generator", pretrained=weight_key, device=str(device), trust_repo=True
        ).eval()
        self.face2paint = torch.hub.load(
            HUB_REPO, "face2paint", size=size, device=str(device), trust_repo=True
        )

    @torch.inference_mode()
    def run(self, image: Image.Image) -> Image.Image:
        return self.face2paint(self.generator, image)


def load_models(names: list[str], device: torch.device, size: int = 512) -> dict[str, CartoonModel]:
    return {name: CartoonModel(name, device, size=size) for name in names}


# AnimeGANv3 film-style checkpoints (the real "Hayao"/"Shinkai" styles), published by the
# original author as ONNX files only -- kept separate from MODEL_VARIANTS so the batch
# scripts (cartoonize.py, compare.py, ...) are unaffected. Used by app.py.
ONNX_RELEASE = "https://github.com/TachibanaYoshino/AnimeGANv3/releases/download/v1.1.0"
ONNX_VARIANTS = {
    "hayao_v3": ("AnimeGANv3_Hayao_36.onnx", "Miyazaki/Ghibli-inspired film look, bold lines and painted skies"),
    "shinkai_v3": ("AnimeGANv3_Shinkai_37.onnx", "Makoto Shinkai-inspired look, vivid light and saturated colour"),
}
WEIGHTS_DIR = Path(__file__).parent / "weights"


class OnnxCartoonModel:
    """One AnimeGANv3 ONNX generator, downloaded to weights/ on first use."""

    def __init__(self, name: str):
        import onnxruntime as ort

        filename, self.description = ONNX_VARIANTS[name]
        self.name = name
        path = WEIGHTS_DIR / filename
        if not path.exists():
            WEIGHTS_DIR.mkdir(exist_ok=True)
            torch.hub.download_url_to_file(f"{ONNX_RELEASE}/{filename}", str(path))
        self.session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name

    def run(self, image: Image.Image) -> Image.Image:
        # Same pre/post-processing as the upstream test_by_onnx.py: NHWC in [-1, 1], sides multiple of 8.
        w, h = image.size
        x = np.asarray(image.convert("RGB").resize((w - w % 8, h - h % 8)), dtype=np.float32) / 127.5 - 1
        out = self.session.run(None, {self.input_name: x[None]})[0][0]
        return Image.fromarray(((out + 1) * 127.5).clip(0, 255).astype(np.uint8))
