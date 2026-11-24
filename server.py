#!/usr/bin/env python
"""Vivid web server: JSON API plus the static frontend.

Usage:
    python server.py            # http://127.0.0.1:7860
    PORT=8000 HOST=0.0.0.0 python server.py
"""
from __future__ import annotations

import base64
import io
import logging
import mimetypes
import os
from contextlib import asynccontextmanager
from pathlib import Path

import anyio
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException as StarletteHTTPException

from registry import FILTER_STYLE, MAX_SIDE, STYLES, Registry, Result, preprocess

log = logging.getLogger("vivid.server")

# Windows can report blank or wrong types for these (it reads them from the registry), and browsers
# refuse to run a module script that isn't served as JavaScript.
for ext, mime in ((".js", "text/javascript"), (".css", "text/css"), (".webp", "image/webp"), (".woff2", "font/woff2")):
    mimetypes.add_type(mime, ext)

ROOT = Path(__file__).parent
FRONTEND_DIR = ROOT / "frontend"
EXAMPLES_DIR = ROOT / "inputs"
EXAMPLE_NAMES = {"sample_portrait": "Portrait", "sample_landscape": "Fjord", "sample_street": "Lioness"}

MAX_UPLOAD = 10 * 1024 * 1024
MULTIPART_OVERHEAD = 64 * 1024  # form fields and boundaries around the file itself
MAX_PIXELS = 50_000_000         # a small file can still decode to a huge bitmap
ALLOWED_FORMATS = ("JPEG", "PNG", "WEBP")
COMPARE_SIDE = 512              # all styles at full size would take over a minute on a laptop CPU

TOO_BIG = "That photo is larger than 10 MB. Please choose a smaller one."
BAD_TYPE = "Please upload a JPG, PNG or WebP photo. Other formats, such as HEIC or GIF, aren't supported."
BAD_IMAGE = "That file couldn't be read as an image. It may be damaged; please try another photo."


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Loading models (first run downloads about 220 MB of weights)...", flush=True)
    app.state.registry = await anyio.to_thread.run_sync(Registry)
    # Separate, small thread budget: queued inference can't starve the rest of the server.
    app.state.limiter = anyio.CapacityLimiter(2)
    print(f"Ready: {len(app.state.registry.styles)} styles online.", flush=True)
    yield


app = FastAPI(title="Vivid", lifespan=lifespan)


# ---------------------------------------------------------------- errors: always {"detail": "<sentence>"}

@app.exception_handler(StarletteHTTPException)
async def on_http_error(request: Request, exc: StarletteHTTPException):
    detail = exc.detail
    if detail in ("Not Found", "Method Not Allowed"):
        detail = "There's nothing at this address."
    return JSONResponse({"detail": detail}, exc.status_code, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def on_invalid_request(request: Request, exc: RequestValidationError):
    field = str(exc.errors()[0]["loc"][-1]) if exc.errors() else ""
    messages = {
        "image": "Please add a photo first.",
        "style": "Please choose a style.",
        "intensity": "Intensity must be a number from 0 to 100.",
        "color_pop": "Color pop must be on or off.",
        "max_side": f"max_side must be a whole number from 256 to {MAX_SIDE}.",
    }
    return JSONResponse({"detail": messages.get(field, "That request wasn't valid.")}, 422)


@app.exception_handler(Exception)
async def on_crash(request: Request, exc: Exception):
    log.exception("Unhandled error on %s", request.url.path)
    return JSONResponse({"detail": "Something went wrong on our side. Please try again."}, 500)


class BodyTooLarge(Exception):
    pass


class RejectOversizedUploads:
    """Stops a huge upload early, whether or not it announces its size, so it never fills the disk.

    Some proxies and HTTP versions leave Content-Length out, so the bytes are counted as well.
    Plain ASGI on purpose: the @app.middleware decorator hides client disconnects from endpoints,
    and /api/compare relies on those to stop work for a closed tab.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST":
            return await self.app(scope, receive, send)

        limit = MAX_UPLOAD + MULTIPART_OVERHEAD
        too_big = JSONResponse({"detail": TOO_BIG}, 413, headers={"connection": "close"})
        length = Headers(scope=scope).get("content-length", "")
        if length.isdigit() and int(length) > limit:
            return await too_big(scope, receive, send)

        received, exceeded = 0, False

        async def counted_receive():
            nonlocal received, exceeded
            message = await receive()
            received += len(message.get("body", b""))
            if received > limit:
                exceeded = True
                raise BodyTooLarge
            return message

        async def guarded_send(message):
            if not exceeded:  # drop the generic parsing error the app would answer with
                await send(message)

        try:
            await self.app(scope, counted_receive, guarded_send)
        except BodyTooLarge:
            pass
        if exceeded:
            await too_big(scope, receive, send)


app.add_middleware(RejectOversizedUploads)


# ---------------------------------------------------------------- helpers

def decode(data: bytes) -> Image.Image:
    """Validate by content, not by file name or the browser's claimed type."""
    if not data:
        raise HTTPException(400, "That file is empty. Please choose another photo.")
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, TOO_BIG)
    try:
        image = Image.open(io.BytesIO(data), formats=ALLOWED_FORMATS)
    except Image.DecompressionBombError:
        raise HTTPException(413, "That photo has too many pixels. Please resize it and try again.")
    except Exception:
        raise HTTPException(415, BAD_TYPE)
    if image.width * image.height > MAX_PIXELS:
        raise HTTPException(413, "That photo has too many pixels. Please resize it and try again.")
    try:
        image.load()
    except Exception:
        raise HTTPException(400, BAD_IMAGE)
    return image


def data_url(image: Image.Image, fmt: str) -> str:
    buf = io.BytesIO()
    image.save(buf, fmt, **({"quality": 90} if fmt == "JPEG" else {"compress_level": 3}))
    return f"data:image/{fmt.lower()};base64,{base64.b64encode(buf.getvalue()).decode()}"


def result_json(registry: Registry, r: Result, fmt: str) -> dict:
    return {
        "style": registry.styles[r.style].info(),
        "image": data_url(r.image, fmt),
        "width": r.image.width,
        "height": r.image.height,
        "cached": r.cached,
        "metrics": r.metrics,
    }


async def in_thread(fn, *args):
    return await anyio.to_thread.run_sync(fn, *args, limiter=app.state.limiter)


# ---------------------------------------------------------------- API

@app.get("/api/health")
async def health():
    registry: Registry = app.state.registry
    return {
        "status": "ok",
        "styles": len(registry.styles),
        "ai_styles": sum(s != FILTER_STYLE for s in registry.styles),
        "total_styles": len(STYLES),
        "unavailable": list(registry.unavailable),
        "device": str(registry.device),
        "max_side": MAX_SIDE,
    }


@app.get("/api/styles")
async def styles():
    return [s.info() | {"max_side": s.max_side} for s in app.state.registry.styles.values()]


@app.get("/api/examples")
async def examples():
    return [
        {
            "id": p.stem,
            "name": EXAMPLE_NAMES.get(p.stem, p.stem.replace("_", " ").replace("-", " ").title()),
            "url": f"/examples/{p.name}",
        }
        for p in sorted(EXAMPLES_DIR.iterdir())
        if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
    ]


@app.post("/api/cartoonize")
async def cartoonize(
    image: UploadFile = File(...),
    style: str = Form(...),
    intensity: float = Form(100, ge=0, le=100, allow_inf_nan=False),
    color_pop: bool = Form(False),
    max_side: int = Form(MAX_SIDE, ge=256, le=MAX_SIDE),
):
    registry: Registry = app.state.registry
    if style not in registry.styles:
        raise HTTPException(400, f"There's no style called '{style[:40]}'. Please pick one from the list.")
    data = await image.read()

    def work() -> dict:
        r = registry.run(decode(data), style, intensity, color_pop, max_side)
        return result_json(registry, r, "PNG") | {"original": data_url(r.original, "JPEG")}

    return await in_thread(work)


@app.post("/api/compare")
async def compare(request: Request, image: UploadFile = File(...)):
    registry: Registry = app.state.registry
    data = await image.read()
    photo = await in_thread(decode, data)

    def one(style: str) -> dict:
        return result_json(registry, registry.run(photo, style, max_side=COMPARE_SIDE), "JPEG")

    results, failed = [], []
    for style in registry.styles:
        if await request.is_disconnected():  # don't keep computing for a closed tab
            raise HTTPException(499, "The comparison was cancelled.")
        try:
            results.append(await in_thread(one, style))
        except Exception:
            log.exception("compare: %s failed", style)
            failed.append(style)
    original = await in_thread(lambda: data_url(preprocess(photo, COMPARE_SIDE), "JPEG"))
    return {"original": original, "results": results, "failed": failed}


# ---------------------------------------------------------------- static files (mounted last: "/" matches everything)

app.mount("/examples", StaticFiles(directory=EXAMPLES_DIR), name="examples")
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    uvicorn.run(app, host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "7860")))
