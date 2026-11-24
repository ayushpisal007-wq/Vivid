"""Pretrained weight catalogue and downloader for Vivid.

Every checkpoint the web app can use is listed here with its source, licence and SHA-256.
`ensure(name)` returns a verified local path, downloading to weights/ on first use. A file
whose hash doesn't match is never returned, so a half-finished or tampered download cannot
turn into a broken style in the UI.
"""
from __future__ import annotations

import hashlib
import os
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

WEIGHTS_DIR = Path(__file__).parent / "weights"
CHUNK = 1 << 20  # 1 MiB
WORKERS = 16  # GitHub throttles each connection, so many small ranges are far faster than one stream
RETRIES = 8
TIMEOUT = 60

_ANIMEGAN2 = "https://raw.githubusercontent.com/bryandlee/animegan2-pytorch/main/weights"
_ANIMEGAN3 = "https://github.com/TachibanaYoshino/AnimeGANv3/releases/download/v1.1.0"
_CARTOONGAN = (
    "https://raw.githubusercontent.com/maciej3031/comixify/"
    "821c46106b09a2a892e8a887e2bfe31d45f331d2/CartoonGAN/pretrained_model"
)


@dataclass(frozen=True)
class Weight:
    filename: str
    url: str
    sha256: str


WEIGHTS: dict[str, Weight] = {
    w.filename: w
    for w in (
        Weight("face_paint_512_v2.pt", f"{_ANIMEGAN2}/face_paint_512_v2.pt",
               "06b88a204eb230889444ad868ee5608f4fce5d4ff7b7738acaa4209c2b8fdca7"),
        Weight("face_paint_512_v1.pt", f"{_ANIMEGAN2}/face_paint_512_v1.pt",
               "f27b45d17c6f4d027753026aeb7e0a558bb95cff5d03a207ac06ca0a372d5316"),
        Weight("paprika.pt", f"{_ANIMEGAN2}/paprika.pt",
               "3eaba1b6d01e88ea32b16a6006b04eb3f60327c1dcc841de640d3196898da344"),
        Weight("celeba_distill.pt", f"{_ANIMEGAN2}/celeba_distill.pt",
               "a3740d98f99efe2ee6c332de2b800f542ddbb2d15e835c07e9bf667c29cef8a7"),
        Weight("AnimeGANv3_Hayao_36.onnx", f"{_ANIMEGAN3}/AnimeGANv3_Hayao_36.onnx",
               "95ba7b219073fd5b12f569bc38056ffd3019cf4caf15b1feb9f73d1286c9f69d"),
        Weight("AnimeGANv3_Shinkai_37.onnx", f"{_ANIMEGAN3}/AnimeGANv3_Shinkai_37.onnx",
               "8dc4d789c44db472447806583c56809e155280225b991bd79f9e2cb20793dcb9"),
        Weight("Hayao_net_G_float.pth", f"{_CARTOONGAN}/Hayao_net_G_float.pth",
               "8ab0e492efb3b705487db38679e363dc8b1f016692913bbe100587d695a9e2b5"),
        Weight("Hosoda_net_G_float.pth", f"{_CARTOONGAN}/Hosoda_net_G_float.pth",
               "c666eea7700864d5972765cc43e926d900174648297bfef494006dc230fd1bf0"),
        Weight("Shinkai_net_G_float.pth", f"{_CARTOONGAN}/Shinkai_net_G_float.pth",
               "c3547f611e780e79aebde7f7bc2b6c278555d701620f125583d666351044c486"),
        Weight("Paprika_net_G_float.pth", f"{_CARTOONGAN}/Paprika_net_G_float.pth",
               "0629352a54838e56a2ad7fca3e6e51e6889d4338c37469f9ddb43e5929ef9475"),
    )
}


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(CHUNK):
            h.update(block)
    return h.hexdigest()


def _open(url: str, headers: dict[str, str] | None = None):
    return urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=TIMEOUT)


def _size_if_ranged(url: str) -> int | None:
    """Total size if the server honours Range requests, else None."""
    with _open(url, {"Range": "bytes=0-0"}) as r:
        content_range = r.headers.get("Content-Range", "")
        return int(content_range.rsplit("/", 1)[1]) if r.status == 206 and "/" in content_range else None


def _retry(fn, *args):
    for attempt in range(RETRIES):
        try:
            return fn(*args)
        except OSError:  # URLError, timeouts and resets are all OSError
            if attempt == RETRIES - 1:
                raise
            time.sleep(1 + attempt)


def _fetch_range(url: str, start: int, end: int) -> bytes:
    with _open(url, {"Range": f"bytes={start}-{end}"}) as r:
        data = r.read()
    if len(data) != end - start + 1:
        raise OSError(f"short read: {len(data)} of {end - start + 1} bytes")
    return data


def _download(url: str, dest: Path, log=print) -> None:
    """Download into `dest`, resuming chunk by chunk from a previous attempt if there was one."""
    size = _retry(_size_if_ranged, url)
    if size is None:
        with _open(url) as r, open(dest, "wb") as f:
            while block := r.read(CHUNK):
                f.write(block)
        return

    parts_dir = dest.with_suffix(dest.suffix + ".parts")
    parts_dir.mkdir(parents=True, exist_ok=True)
    starts = range(0, size, CHUNK)

    def chunk(start: int) -> None:
        end = min(start + CHUNK, size) - 1
        part = parts_dir / f"{start:012d}"
        if part.exists() and part.stat().st_size == end - start + 1:
            return
        tmp = part.with_suffix(".tmp")
        tmp.write_bytes(_retry(_fetch_range, url, start, end))
        os.replace(tmp, part)

    done = 0
    with ThreadPoolExecutor(WORKERS) as pool:
        for _ in pool.map(chunk, starts):
            done += 1
            if done % 10 == 0 or done == len(starts):
                log(f"  {dest.name}: {done}/{len(starts)} MiB")
    with open(dest, "wb") as f:
        for start in starts:
            f.write((parts_dir / f"{start:012d}").read_bytes())
    for part in parts_dir.iterdir():
        part.unlink()
    parts_dir.rmdir()


def ensure(filename: str, log=print) -> Path:
    """Return the verified local path of a checkpoint, downloading it if needed."""
    w = WEIGHTS[filename]
    path = WEIGHTS_DIR / filename
    if path.exists() and sha256_of(path) == w.sha256:
        return path
    WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    log(f"Downloading {filename} ...")
    tmp = path.with_suffix(path.suffix + ".download")
    _download(w.url, tmp, log)
    digest = sha256_of(tmp)
    if digest != w.sha256:
        tmp.unlink()
        raise RuntimeError(f"{filename}: SHA-256 mismatch (got {digest})")
    os.replace(tmp, path)
    return path
