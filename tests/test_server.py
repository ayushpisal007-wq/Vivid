"""API smoke tests with a real sample photo and the real models."""
import base64
import io
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import server  # noqa: E402

METRIC_KEYS = {"ssim", "hist_shift", "edge_density_change_pct", "inference_ms"}


def encode(image: Image.Image, fmt: str) -> bytes:
    buf = io.BytesIO()
    image.save(buf, fmt)
    return buf.getvalue()


def open_data_url(url: str) -> Image.Image:
    header, _, payload = url.partition(",")
    assert header.startswith("data:image/")
    return Image.open(io.BytesIO(base64.b64decode(payload)))


PHOTO = (ROOT / "inputs" / "sample_portrait.jpg").read_bytes()
SMALL = encode(Image.open(io.BytesIO(PHOTO)).resize((280, 360)), "PNG")


@pytest.fixture(scope="module")
def client():
    with TestClient(server.app) as c:
        yield c


def post(client, data=PHOTO, name="photo.jpg", **form):
    form = {"style": "classic_filter", "max_side": 256} | form
    return client.post("/api/cartoonize", files={"image": (name, data)}, data=form)


# ------------------------------------------------ GET endpoints

def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["styles"] == body["total_styles"] == 11
    assert body["ai_styles"] == 10
    assert body["unavailable"] == []


def test_styles(client):
    body = client.get("/api/styles").json()
    assert len(body) == 11
    assert {s["family"] for s in body} == {"AnimeGAN", "CartoonGAN", "Filter"}
    assert all(s["id"] and s["name"] and s["description"] and s["source"] for s in body)
    assert any(s["name"] == "Classic Filter (no AI)" for s in body)


def test_examples_exist_and_load(client):
    body = client.get("/api/examples").json()
    assert len(body) >= 3
    for e in body:
        r = client.get(e["url"])
        assert r.status_code == 200
        Image.open(io.BytesIO(r.content)).verify()


def test_frontend_is_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "Vivid" in r.text


def test_static_mount_does_not_leak_source(client):
    for path in ("/server.py", "/examples/../server.py", "/examples/%2e%2e/server.py", "/.git/config"):
        assert client.get(path).status_code == 404


def test_unknown_api_path_is_json(client):
    r = client.get("/api/nope")
    assert r.status_code == 404 and isinstance(r.json()["detail"], str)


# ------------------------------------------------ POST /api/cartoonize

@pytest.mark.parametrize("style", ["face_paint_v2", "hayao_v3", "cartoongan_shinkai", "classic_filter"])
def test_cartoonize_each_family(client, style):
    r = post(client, style=style)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["style"]["id"] == style
    assert set(body["metrics"]) == METRIC_KEYS
    out, original = open_data_url(body["image"]), open_data_url(body["original"])
    assert out.format == "PNG"
    assert out.size == original.size == (body["width"], body["height"])


@pytest.mark.parametrize("fmt", ["JPEG", "PNG", "WEBP"])
def test_cartoonize_accepts_formats(client, fmt):
    data = encode(Image.open(io.BytesIO(SMALL)), fmt)
    assert post(client, data=data, name="x.bin").status_code == 200  # content decides, not the name


def test_intensity_zero_returns_the_original(client):
    body = post(client, intensity=0).json()
    assert body["metrics"]["ssim"] == 1.0


def test_color_pop_changes_the_result(client):
    assert post(client).json()["image"] != post(client, color_pop="true").json()["image"]


def test_slider_moves_are_served_from_cache(client):
    post(client, style="paprika")
    body = post(client, style="paprika", intensity=40).json()
    assert body["cached"] is True


# ------------------------------------------------ validation

@pytest.mark.parametrize(
    "data, status",
    [
        (b"", 400),
        (b"this is not an image", 415),
        (encode(Image.new("RGB", (32, 32)), "GIF"), 415),
        (encode(Image.new("RGB", (32, 32)), "BMP"), 415),
        (b"<svg xmlns='http://www.w3.org/2000/svg'/>", 415),
        (PHOTO[: len(PHOTO) // 3], 400),  # truncated JPEG
        (PHOTO + b"\0" * (server.MAX_UPLOAD - len(PHOTO) + 1), 413),  # just over, passes the header check
        (PHOTO + b"\0" * server.MAX_UPLOAD, 413),
        (encode(Image.new("L", (8000, 7000)), "PNG"), 413),  # tiny file, 56 megapixels
    ],
    ids=["empty", "text", "gif", "bmp", "svg", "truncated", "just-over-10MB", "way-over-10MB", "pixel-bomb"],
)
@pytest.mark.parametrize("path", ["/api/cartoonize", "/api/compare"])
def test_bad_uploads_get_friendly_errors(client, path, data, status):
    r = client.post(path, files={"image": ("photo.jpg", data, "image/jpeg")}, data={"style": "classic_filter"})
    assert r.status_code == status, r.text
    detail = r.json()["detail"]
    assert isinstance(detail, str) and detail.endswith(".") and "Error" not in detail


@pytest.mark.parametrize(
    "form",
    [{"intensity": "abc"}, {"intensity": "101"}, {"intensity": "-1"}, {"intensity": "nan"}, {"intensity": "inf"},
     {"color_pop": "maybe"}, {"max_side": "100"}, {"max_side": "9999"}],
)
def test_bad_options(client, form):
    r = post(client, **form)
    assert r.status_code == 422 and isinstance(r.json()["detail"], str)


def test_unknown_style(client):
    r = post(client, style="mona_lisa")
    assert r.status_code == 400 and "mona_lisa" in r.json()["detail"]


def test_missing_photo(client):
    r = client.post("/api/cartoonize", data={"style": "paprika"})
    assert r.status_code == 422 and r.json()["detail"] == "Please add a photo first."


def test_chunked_upload_without_length_is_refused(client):
    r = client.post("/api/cartoonize", content=iter([b"x" * 1000]), headers={"content-type": "multipart/form-data; boundary=x"})
    assert r.status_code == 411


def test_crash_is_a_friendly_500(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("secret internal detail")

    with TestClient(server.app, raise_server_exceptions=False) as c:
        monkeypatch.setattr(server.app.state.registry, "run", boom)
        r = post(c)
    assert r.status_code == 500 and "secret" not in r.text


# ------------------------------------------------ POST /api/compare

def test_compare_returns_every_style(client):
    r = client.post("/api/compare", files={"image": ("photo.png", SMALL)})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["failed"] == []
    assert [x["style"]["id"] for x in body["results"]] == [s["id"] for s in client.get("/api/styles").json()]
    size = open_data_url(body["original"]).size
    for x in body["results"]:
        assert set(x["metrics"]) == METRIC_KEYS
        assert open_data_url(x["image"]).size == size  # same size, so the grid lines up


def test_compare_survives_one_broken_style(client, monkeypatch):
    real = server.app.state.registry.run

    def flaky(photo, style, *a, **k):
        if style == "paprika":
            raise RuntimeError("boom")
        return real(photo, style, *a, **k)

    monkeypatch.setattr(server.app.state.registry, "run", flaky)
    body = client.post("/api/compare", files={"image": ("photo.png", SMALL)}).json()
    assert body["failed"] == ["paprika"] and len(body["results"]) == 10


# ------------------------------------------------ responsiveness

def test_health_answers_while_inference_runs(client):
    photo = encode(Image.effect_noise((512, 512), 80), "PNG")  # new image, so it can't come from the cache
    worker = threading.Thread(target=lambda: post(client, data=photo, style="face_paint_v1", max_side=512))
    worker.start()
    time.sleep(0.5)
    start = time.perf_counter()
    assert client.get("/api/health").status_code == 200
    took = time.perf_counter() - start
    assert worker.is_alive(), "inference finished too early to prove anything"
    assert took < 1.5
    worker.join()


def test_closing_the_tab_stops_a_compare(monkeypatch):
    """Needs a real server: the in-process test client never disconnects."""
    live = uvicorn.Server(uvicorn.Config(server.app, port=0, log_level="error"))
    thread = threading.Thread(target=live.run)
    thread.start()
    try:
        while not live.started:
            assert thread.is_alive()
            time.sleep(0.1)
        calls = []
        real = server.app.state.registry.run

        def slow(photo, style, *a, **k):
            calls.append(style)
            time.sleep(0.5)
            return real(photo, "classic_filter", *a, **k)

        monkeypatch.setattr(server.app.state.registry, "run", slow)
        port = live.servers[0].sockets[0].getsockname()[1]
        with pytest.raises(httpx.ReadTimeout):
            httpx.post(f"http://127.0.0.1:{port}/api/compare", files={"image": ("p.png", SMALL)}, timeout=1.2)
        time.sleep(4)
        assert 1 <= len(calls) <= 5, calls
    finally:
        live.should_exit = True
        thread.join()
