"""Vivid model registry: every style behind one interface.

    registry = Registry()                         # loads each model once
    result = registry.run(image, "hayao_v3")      # -> Result(image, inference_ms, metrics, ...)

A style that can't be downloaded or fails its load-time smoke test is left out of
`registry.styles` and listed in `registry.unavailable`, so the UI never offers a broken option.
The batch scripts (cartoonize.py etc.) keep using models.py directly and don't touch this file.
"""
from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageEnhance, ImageOps

import metrics
from classic_filter import classic_cartoon
from models import HUB_REPO, ONNX_VARIANTS, OnnxCartoonModel, get_device
from weight_store import ensure

try:
    import torch
except ImportError:  # lite deployments run only the ONNX styles and the filter
    torch = None

log = logging.getLogger("vivid.registry")

MAX_SIDE = int(os.environ.get("VIVID_MAX_SIDE", "1024"))  # cap for CPU speed
MIN_SIDE = 512   # these networks see almost nothing in tiny inputs, so upscale the long side to this
CARTOONGAN_SIDE = 512  # upstream runs it at ~450px; at 896px it is ~3x slower
MULTIPLE = 32
FILTER_STYLE = "classic_filter"
CACHE_SIZE = 32  # raw model outputs kept, so moving the intensity slider never re-runs a network

Runner = Callable[[Image.Image], Image.Image]


def cpu_budget() -> int:
    """CPUs this process may really use. Inside a container os.cpu_count() can report the whole host."""
    count = os.cpu_count() or 4
    try:
        quota, period = open("/sys/fs/cgroup/cpu.max").read().split()
        if quota != "max":
            count = min(count, max(1, round(int(quota) / int(period))))
    except (OSError, ValueError):
        pass  # not Linux, or no limit set
    cores = os.environ.get("CPU_CORES", "")  # set by Hugging Face Spaces
    return min(count, max(1, int(cores))) if cores.isdigit() else count


def no_grad():
    return torch.inference_mode() if torch else nullcontext()


# ---------------------------------------------------------------- loaders

def _to_tensor(image: Image.Image, device: torch.device) -> torch.Tensor:
    x = torch.from_numpy(np.array(image, dtype=np.float32)) / 127.5 - 1
    return x.permute(2, 0, 1)[None].to(device, memory_format=torch.channels_last)


def _to_image(y: torch.Tensor) -> Image.Image:
    y = ((y[0].float().cpu().permute(1, 2, 0) + 1) * 127.5).round().clamp(0, 255)
    return Image.fromarray(y.numpy().astype(np.uint8))


def load_hub_generator() -> torch.nn.Module:
    """AnimeGANv2 network definition from torch.hub, without weights."""
    return torch.hub.load(HUB_REPO, "generator", pretrained=False, trust_repo=True, skip_validation=True, verbose=False)


def _animegan2(filename: str) -> Callable[[torch.device], Runner]:
    def load(device):
        net = load_hub_generator()
        net.load_state_dict(torch.load(ensure(filename), map_location="cpu", weights_only=True))
        net = net.to(device, memory_format=torch.channels_last).eval()
        return lambda image: _to_image(net(_to_tensor(image, device)))
    return load


def _animegan3(name: str) -> Callable[[torch.device], Runner]:
    def load(device):
        ensure(ONNX_VARIANTS[name][0])
        limit = cpu_budget()
        return OnnxCartoonModel(name, threads=limit if limit < (os.cpu_count() or 4) else 0).run
    return load


def _cartoongan(filename: str) -> Callable[[torch.device], Runner]:
    def load(device):
        from cartoongan import load_cartoongan

        net = load_cartoongan(ensure(filename), device).to(memory_format=torch.channels_last)
        # The released weights expect BGR channel order.
        return lambda image: _to_image(net(_to_tensor(image, device).flip(1)).flip(1))
    return load


# ---------------------------------------------------------------- style catalogue

@dataclass(frozen=True)
class Style:
    id: str
    name: str
    family: str  # AnimeGAN | CartoonGAN | Filter
    source: str
    description: str
    load: Callable[[torch.device], Runner]
    max_side: int = MAX_SIDE

    def info(self) -> dict:
        return {k: getattr(self, k) for k in ("id", "name", "family", "source", "description")}


_V2, _V3, _CG = "AnimeGANv2 (bryandlee, PyTorch)", "AnimeGANv3 (TachibanaYoshino, ONNX)", "CartoonGAN (CVPR 2018)"

STYLES = (
    Style("face_paint_v2", "Portrait", "AnimeGAN", _V2,
          "Clean anime portrait look, the best all-rounder for faces.", _animegan2("face_paint_512_v2.pt")),
    Style("face_paint_v1", "Portrait Classic", "AnimeGAN", _V2,
          "Earlier portrait checkpoint with a stronger, more graphic repaint.", _animegan2("face_paint_512_v1.pt")),
    Style("paprika", "Paprika", "AnimeGAN", _V2,
          "Bold, graphic look inspired by Satoshi Kon's film Paprika.", _animegan2("paprika.pt")),
    Style("celeba_distill", "Cel Shade", "AnimeGAN", _V2,
          "Webtoon-like shading: flat skin, bold outlines, heavy black shadows.", _animegan2("celeba_distill.pt")),
    Style("hayao_v3", "Hayao", "AnimeGAN", _V3,
          "Ghibli-like film look with bold lines and painted skies.", _animegan3("hayao_v3")),
    Style("shinkai_v3", "Shinkai", "AnimeGAN", _V3,
          "Makoto Shinkai-like look with vivid light and saturated colour.", _animegan3("shinkai_v3")),
    Style("cartoongan_hayao", "CartoonGAN Hayao", "CartoonGAN", _CG,
          "The original CartoonGAN trained on Miyazaki film frames.", _cartoongan("Hayao_net_G_float.pth"), CARTOONGAN_SIDE),
    Style("cartoongan_hosoda", "CartoonGAN Hosoda", "CartoonGAN", _CG,
          "CartoonGAN trained on Mamoru Hosoda film frames.", _cartoongan("Hosoda_net_G_float.pth"), CARTOONGAN_SIDE),
    Style("cartoongan_shinkai", "CartoonGAN Shinkai", "CartoonGAN", _CG,
          "CartoonGAN trained on Makoto Shinkai film frames.", _cartoongan("Shinkai_net_G_float.pth"), CARTOONGAN_SIDE),
    Style("cartoongan_paprika", "CartoonGAN Paprika", "CartoonGAN", _CG,
          "CartoonGAN trained on frames from Paprika.", _cartoongan("Paprika_net_G_float.pth"), CARTOONGAN_SIDE),
    Style(FILTER_STYLE, "Classic Filter (no AI)", "Filter", "OpenCV",
          "Fixed recipe: smooth, reduce colours, trace edges. No learning involved.",
          lambda device: classic_cartoon),
)


# ---------------------------------------------------------------- pre / post processing

def preprocess(image: Image.Image, max_side: int = MAX_SIDE) -> Image.Image:
    """Upright RGB, aspect ratio kept, sides multiples of 32, long side between 512 and max_side."""
    image = ImageOps.exif_transpose(image)
    if image.mode in ("RGBA", "LA", "PA") or "transparency" in image.info:
        image = image.convert("RGBA")
        image = Image.alpha_composite(Image.new("RGBA", image.size, "white"), image)
    image = image.convert("RGB")

    long_side = max(image.size)
    scale = min(max_side, max(MIN_SIDE, long_side)) / long_side
    size = tuple(max(MULTIPLE, round(s * scale / MULTIPLE) * MULTIPLE) for s in image.size)
    return image if size == image.size else image.resize(size, Image.LANCZOS)


def color_pop_filter(image: Image.Image) -> Image.Image:
    return ImageEnhance.Contrast(ImageEnhance.Color(image).enhance(1.3)).enhance(1.12)


def postprocess(original: Image.Image, output: Image.Image, intensity: float = 100, color_pop: bool = False) -> Image.Image:
    if color_pop:
        output = color_pop_filter(output)
    alpha = min(100.0, max(0.0, float(intensity))) / 100
    return output if alpha == 1 else Image.blend(original, output, alpha)


# ---------------------------------------------------------------- registry

@dataclass
class Result:
    style: str
    original: Image.Image  # preprocessed input, same size as `image`
    image: Image.Image
    inference_ms: float  # time the network took, even when this result came from the cache
    cached: bool
    metrics: dict


class Registry:
    def __init__(self, device: str = "auto", only: list[str] | None = None):
        unknown = set(only or ()) - {s.id for s in STYLES}
        if unknown:
            raise ValueError(f"Unknown styles: {', '.join(sorted(unknown))}")
        self.device = get_device(device)
        if torch:
            torch.set_num_threads(cpu_budget())  # hyperthreads + channels_last: ~20% faster on CPU here
        self.styles: dict[str, Style] = {}
        self.unavailable: dict[str, str] = {}
        self._runners: dict[str, Runner] = {}
        self._lock = threading.Lock()  # one inference at a time keeps timings honest and memory bounded
        self._cache: OrderedDict[tuple, tuple[Image.Image, float]] = OrderedDict()
        for style in STYLES:
            if only is None or style.id in only:
                self._load(style)

    def _load(self, style: Style) -> None:
        try:
            runner = style.load(self.device)
            probe = Image.effect_noise((64, 96), 60).convert("RGB")
            with no_grad():
                out = runner(probe)
            if out.size != probe.size or np.asarray(out).std() < 1:
                raise RuntimeError(f"smoke test produced a bad image ({out.size})")
        except Exception as e:  # any failure means the style must not be offered
            log.warning("Style %s unavailable: %s", style.id, e)
            self.unavailable[style.id] = str(e)
            return
        self.styles[style.id] = style
        self._runners[style.id] = runner

    def stylize(self, image: Image.Image, style: str) -> tuple[Image.Image, float, bool]:
        """Raw model output for an already preprocessed image, inference time in ms, and cache hit."""
        if style not in self._runners:
            raise KeyError(f"Unknown style '{style}'")
        key = (style, image.size, hashlib.sha256(image.tobytes()).digest())
        with self._lock, no_grad():
            if key in self._cache:
                self._cache.move_to_end(key)
                return *self._cache[key], True
            start = time.perf_counter()
            out = self._runners[style](image)
            ms = (time.perf_counter() - start) * 1000
            if out.size != image.size:
                out = out.resize(image.size, Image.LANCZOS)
            self._cache[key] = (out, ms)
            if len(self._cache) > CACHE_SIZE:
                self._cache.popitem(last=False)
        return out, ms, False

    def run(
        self,
        image: Image.Image,
        style: str,
        intensity: float = 100,
        color_pop: bool = False,
        max_side: int = MAX_SIDE,
    ) -> Result:
        if style not in self.styles:
            raise KeyError(f"Unknown style '{style}'")
        original = preprocess(image, min(max_side, self.styles[style].max_side))
        out, ms, cached = self.stylize(original, style)
        out = postprocess(original, out, intensity, color_pop)
        # Metrics describe the image the user sees, after intensity and color pop.
        scores = metrics.compute_all(original, out) | {"inference_ms": round(ms, 1)}
        return Result(style, original, out, ms, cached, scores)
