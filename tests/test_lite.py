"""The lite deployment (Render free plan): no PyTorch, three styles, called from another site."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

SCRIPT = """
import sys
sys.modules["torch"] = None  # as if PyTorch were not installed
import io, json
from fastapi.testclient import TestClient
from PIL import Image
import server

photo = open("inputs/sample_portrait.jpg", "rb").read()
big = io.BytesIO(); Image.effect_noise((4000, 3000), 60).convert("RGB").save(big, "JPEG")
site = {"Origin": "https://vivid-demo.vercel.app"}
out = {}
with TestClient(server.app, raise_server_exceptions=False) as c:
    out["health"] = c.get("/api/health", headers=site).json()
    out["styles"] = [s["id"] for s in c.get("/api/styles", headers=site).json()]
    def post(data, style):
        r = c.post("/api/cartoonize", files={"image": ("p.jpg", data)}, data={"style": style}, headers=site)
        return [r.status_code, r.headers.get("access-control-allow-origin"), r.json().get("width"), r.json().get("height")]
    out["hayao"] = post(photo, "hayao_v3")
    out["filter"] = post(photo, "classic_filter")
    out["big"] = post(big.getvalue(), "classic_filter")
    out["torch_style"] = post(photo, "paprika")
    out["too_big"] = post(photo + bytes(11 * 1024 * 1024), "classic_filter")
    out["example"] = c.get("/examples/sample_portrait.jpg", headers=site).headers.get("access-control-allow-origin")
    server.app.state.registry.run = lambda *a, **k: 1 / 0
    out["crash"] = post(photo, "classic_filter")
print("RESULT" + json.dumps(out))
"""


@pytest.fixture(scope="module")
def lite():
    env = os.environ | {
        "VIVID_STYLES": "hayao_v3,shinkai_v3,classic_filter", "VIVID_MAX_SIDE": "512", "VIVID_MAX_PIXELS": "25000000",
        "VIVID_CORS_ORIGINS": "*", "CPU_CORES": "1", "PYTHONPATH": str(ROOT),
    }
    r = subprocess.run([sys.executable, "-c", SCRIPT], cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
    assert "RESULT" in r.stdout, r.stderr[-2000:]
    return json.loads(r.stdout.rsplit("RESULT", 1)[1])


def test_lite_runs_only_the_small_styles(lite):
    assert lite["styles"] == ["hayao_v3", "shinkai_v3", "classic_filter"]
    assert lite["health"]["styles"] == 3 and lite["health"]["total_styles"] == 11
    assert lite["health"]["max_side"] == 512


def test_lite_cartoonizes_for_another_site(lite):
    assert lite["hayao"] == [200, "*", 384, 512]
    assert lite["filter"][:2] == [200, "*"]


def test_lite_takes_a_big_phone_photo(lite):
    assert lite["big"][0] == 200 and max(lite["big"][2:]) == 512


def test_every_error_is_readable_from_the_other_site(lite):
    assert lite["torch_style"][:2] == [400, "*"]
    assert lite["too_big"][:2] == [413, "*"]
    assert lite["crash"][:2] == [500, "*"]
    assert lite["example"] == "*"
