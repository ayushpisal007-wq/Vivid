"""Registry tests. The full every-style run is slow on CPU, so it uses a small input size."""
import io
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import registry as reg  # noqa: E402
import weight_store  # noqa: E402

PORTRAIT = ROOT / "inputs" / "sample_portrait.jpg"
METRIC_KEYS = {"ssim", "hist_shift", "edge_density_change_pct", "inference_ms"}


@pytest.fixture(scope="module")
def registry():
    return reg.Registry()


def test_every_style_loads(registry):
    assert registry.unavailable == {}
    assert list(registry.styles) == [s.id for s in reg.STYLES]


@pytest.mark.parametrize("style", [s.id for s in reg.STYLES])
def test_every_style_stylizes(registry, style):
    with Image.open(PORTRAIT) as im:
        r = registry.run(im, style, max_side=256)
    assert r.image.size == r.original.size
    assert r.image.mode == "RGB"
    assert np.asarray(r.image).std() > 5  # not a blank frame
    assert np.abs(np.asarray(r.image, float) - np.asarray(r.original, float)).mean() > 3  # actually changed
    assert r.inference_ms > 0
    assert set(r.metrics) == METRIC_KEYS


def test_cartoongan_runs_at_its_reference_size(registry):
    with Image.open(PORTRAIT) as im:
        assert max(registry.run(im, "cartoongan_hayao").image.size) == reg.CARTOONGAN_SIDE


def test_unknown_style(registry):
    with pytest.raises(KeyError):
        registry.run(Image.new("RGB", (64, 64)), "nope")


def test_broken_style_is_hidden_not_shipped(monkeypatch):
    def boom(filename, log=print):
        raise RuntimeError("no network")

    monkeypatch.setattr(reg, "ensure", boom)
    r = reg.Registry(only=["paprika", reg.FILTER_STYLE])
    assert list(r.styles) == [reg.FILTER_STYLE]  # the filter needs no weights, so it always survives
    assert "paprika" in r.unavailable


@pytest.mark.parametrize(
    "size, expected",
    [((4000, 3000), (1024, 768)), ((900, 600), (896, 608)), ((128, 128), (512, 512)), ((5000, 100), (1024, 32))],
)
def test_preprocess_sizes(size, expected):
    assert reg.preprocess(Image.new("RGB", size)).size == expected


def test_preprocess_fixes_exif_rotation():
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90
    buf = io.BytesIO()
    Image.new("RGB", (800, 400)).save(buf, "JPEG", exif=exif)
    w, h = reg.preprocess(Image.open(buf)).size
    assert h > w


def test_preprocess_flattens_transparency():
    assert reg.preprocess(Image.new("RGBA", (512, 512), (0, 0, 0, 0))).getpixel((0, 0)) == (255, 255, 255)


def test_postprocess_intensity_and_pop():
    a, b = Image.new("RGB", (4, 4), (0, 0, 0)), Image.new("RGB", (4, 4), (200, 100, 50))
    assert reg.postprocess(a, b, 0).getpixel((0, 0)) == (0, 0, 0)
    assert reg.postprocess(a, b, 50).getpixel((0, 0)) == (100, 50, 25)
    assert reg.postprocess(a, b, 100).getpixel((0, 0)) == (200, 100, 50)
    assert reg.postprocess(a, b, 100, color_pop=True).getpixel((0, 0)) != (200, 100, 50)


def test_corrupt_weight_is_refetched(tmp_path, monkeypatch):
    good = b"good weights"
    w = weight_store.Weight("x.pt", "https://example.invalid/x.pt", weight_store.hashlib.sha256(good).hexdigest())
    monkeypatch.setattr(weight_store, "WEIGHTS_DIR", tmp_path)
    monkeypatch.setitem(weight_store.WEIGHTS, "x.pt", w)
    monkeypatch.setattr(weight_store, "_download", lambda url, dest, log: dest.write_bytes(good))
    (tmp_path / "x.pt").write_bytes(b"truncated")
    assert weight_store.ensure("x.pt", log=lambda m: None).read_bytes() == good


def test_tampered_download_is_rejected(tmp_path, monkeypatch):
    w = weight_store.Weight("x.pt", "https://example.invalid/x.pt", "0" * 64)
    monkeypatch.setattr(weight_store, "WEIGHTS_DIR", tmp_path)
    monkeypatch.setitem(weight_store.WEIGHTS, "x.pt", w)
    monkeypatch.setattr(weight_store, "_download", lambda url, dest, log: dest.write_bytes(b"evil"))
    with pytest.raises(RuntimeError):
        weight_store.ensure("x.pt", log=lambda m: None)
    assert list(tmp_path.iterdir()) == []
