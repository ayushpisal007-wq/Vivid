"""Jury content: no placeholders left, and the batch metrics compare matching pictures."""
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import metrics  # noqa: E402
import registry  # noqa: E402

PAGES = [ROOT / "README.md", ROOT / "portfolio.py", ROOT / "templates" / "portfolio_template.html",
         ROOT / "frontend" / "index.html", *(ROOT / "frontend" / "js").glob("*.js")]


def test_no_placeholder_text_left():
    for page in PAGES:
        text = page.read_text(encoding="utf-8")
        assert not re.search(r"placeholder|fill in before presenting|lorem ipsum", text, re.I), page.name


def test_commentary_covers_every_sample_photo():
    site = (ROOT / "frontend" / "js" / "commentary.js").read_text(encoding="utf-8")
    import portfolio

    for photo in (ROOT / "inputs").glob("sample_*.jpg"):
        assert f"{photo.stem}:" in site
        assert photo.name in portfolio.PHOTO_NOTES


def test_commentary_picks_are_real_styles():
    site = (ROOT / "frontend" / "js" / "commentary.js").read_text(encoding="utf-8")
    assert set(re.findall(r'pick: "(\w+)"', site)) <= {s.id for s in registry.STYLES}


def test_square_crop_is_scored_against_the_same_crop():
    # What face2paint does: centre-crop to a square, then resize. With no stylization the scores must be perfect.
    photo = Image.open(ROOT / "inputs" / "sample_landscape.jpg").convert("RGB")
    w, h = photo.size
    square = photo.crop(((w - h) // 2, 0, (w - h) // 2 + h, h))
    aligned = metrics.compute_ssim(metrics.crop_like(photo, square), square)
    assert aligned > 0.999
    assert metrics.compute_ssim(photo, square) < 0.6  # the squashed comparison this replaced


def test_crop_like_keeps_matching_images_whole():
    photo = Image.fromarray(np.zeros((40, 60, 3), np.uint8))
    assert metrics.crop_like(photo, photo).size == photo.size
