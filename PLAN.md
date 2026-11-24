# Vivid: build plan

Goal: turn Vivid into a full web app for the final Gen AI jury (Topic 128: Cartoonize
Photos with AnimeGAN/CartoonGAN). Existing pipeline scripts must keep working.

Rules

- Work through the phases in order. After each one: verify it actually works (run it, call
  the endpoints, open the page), then git commit with a clear message.
- Commits show only the project owner as author.
- If something can't be made to work in about 15 minutes, use the stated fallback, note it
  here, and move on.
- Run one phase at a time; check in before starting Phase 2 and onwards (added 24 Nov 2026).

The design spec lives in [DESIGN.md](DESIGN.md).

## Task list

- [x] Phase 0: Repo cleanup
- [x] Phase 1: Model registry
- [x] Phase 2: API
- [x] Phase 3: Frontend
- [x] Phase 4: Jury content
- [x] Final pass: test every style via the UI, screenshots, summary

## Phase 0: Repo cleanup

- venv/ is committed to GitHub. Remove it from tracking (`git rm -r --cached venv`) without
  deleting the local venv. Make sure .gitignore covers venv/, __pycache__/, outputs/,
  contact_sheets/, uploads/ and caches.
- Retire Gradio (it crashes with a huggingface_hub HfFolder import error). Remove it from
  requirements; the new app is FastAPI + a custom frontend.

## Phase 1: Model registry

Build one registry that loads every model ONCE at startup, with one interface:
`run(image, style) -> image + inference_ms`.

- a) AnimeGANv2 via torch.hub bryandlee/animegan2-pytorch: face_paint_v2, face_paint_v1,
  paprika, celeba_distill.
- b) Classic anime-film styles, Hayao (Ghibli-like) and Shinkai: use AnimeGANv3 or AnimeGANv2
  ONNX checkpoints (TachibanaYoshino GitHub releases or the Hugging Face Hub) via
  onnxruntime. Verify each URL downloads before wiring it in.
- c) CartoonGAN: a working pretrained CartoonGAN (Hayao/Hosoda/Shinkai/Paprika PyTorch
  weights) or a White-box Cartoonization ONNX model. Verify the download first.
- d) Classical filter baseline (OpenCV bilateral filter + adaptive-threshold edges + color
  quantization), labeled "Classic Filter (no AI)". This must always exist; it's the live
  answer to "how is this different from a photo filter?"

Fallback: if (b) or (c) can't be obtained, ship what works and list what's missing in this
file. Never ship a broken option.

- Preprocessing: fix EXIF rotation, keep aspect ratio where the model allows (resize to
  multiples of 32 instead of square cropping), cap the long side at 1024px for CPU speed.
- Postprocessing (toggleable): intensity (blend 0-100% with the original) and color pop
  (saturation/contrast boost).
- Per-result metrics using the existing metrics.py: SSIM, histogram shift, edge-density
  change, inference time.
- tools/download_weights.py that pre-fetches all weights (the Docker build will use it later).

## Phase 2: API (FastAPI, server.py)

- POST /api/cartoonize (image, style, intensity, color_pop) -> result image + metrics JSON
- POST /api/compare (image) -> every style's output + metrics, for a side-by-side grid
- GET /api/styles (name, family: AnimeGAN / CartoonGAN / Filter, short description),
  GET /api/examples, GET /api/health
- Validation: jpg/png/webp only, 10 MB max, friendly error messages. Run inference in a
  threadpool so the server doesn't freeze.
- Serve the built frontend as static files. Port from env PORT, default 7860.
- Write pytest smoke tests for every endpoint using a sample image, and run them.

## Phase 3: Frontend

Plain HTML/CSS/JS or Vite, but it must build to static files that FastAPI serves. Follow
DESIGN.md exactly.

## Phase 4: Jury content

- Port the existing portfolio (before/after grids, averaged metrics table, failure cases)
  into the site's Portfolio and Limits sections, using real generated images.
- Replace EVERY "Placeholder" commentary with real commentary based on README.md's "How it
  works" and "Known limitations", in simple language that can be said out loud.
- Update README: run locally (python server.py), architecture overview, model list with
  sources and licenses, and a placeholder for the live link.

## Final pass

Run the server, test every style through the UI with a portrait and a landscape, fix
anything broken or ugly, save screenshots of each section to docs/screenshots, and give a
short summary of what works and what fell back.

## Notes and fallbacks

- Phase 0: app.py (the Gradio app) was removed; it stays in git history (commit 5de8351).
- Local environments: use `.venv312` (Python 3.12). The old `venv/` is a Python 3.14
  environment with mismatched packages; it is untracked now but left on disk.

### Phase 1 (done, no fallback needed)

All 11 styles load and pass tests: 4 AnimeGANv2, 2 AnimeGANv3, 4 CartoonGAN, 1 classic filter.

- Files: registry.py (the registry), weight_store.py (URLs, SHA-256 pins, resumable parallel
  downloads), cartoongan.py, classic_filter.py, tools/download_weights.py, tests/test_registry.py.
- Weights live in weights/ (gitignored, about 220 MB). AnimeGANv2 and CartoonGAN files were
  checked against GitHub's published blob hashes; every file is SHA-256 pinned. The two
  AnimeGANv3 files have no published hash to check against, so their pins record what the
  official GitHub release served.
- CartoonGAN: the original host (vllab1.ucmerced.edu) is down, so the weights come from the
  maciej3031/comixify mirror, pinned to a commit. The Hayao port closely reproduces three
  published sample outputs of Yijunmaverick/CartoonGAN-Test-Pytorch-Torch, which also confirmed
  BGR input order. Hosoda, Shinkai and Paprika share the code path but were not compared.
- CartoonGAN colour shifts (brown or green skies, tinted skin) appear on our samples. Hayao
  matching its published outputs says they come from the checkpoints, not from this port.
  Paprika's cracked skin is also in the old 512px outputs. Good material for Limits.
- Speed on the Ryzen 5 3500U, sample photos (long side 896): AnimeGANv2 about 9-10 s, AnimeGANv3
  5-6 s, CartoonGAN about 7 s (capped at 512px, close to its reference size), filter 0.3 s.
  ONNX Runtime was tried for AnimeGANv2 and is slower here than PyTorch.
- Phase 2: Compare-all at full size takes over a minute, so use the registry's max_side (e.g. 512).
- Phase 4: README says "a few hundred ms" on a laptop CPU. That is wrong on this machine (about
  5 s at 512x512) and must be corrected. inputs/sample_street.jpg is actually a lioness.
- Licences to state in README: animegan2-pytorch is MIT; AnimeGANv3 is non-commercial/academic;
  comixify is CC BY-NC 4.0. Fine for a jury project, not for commercial use.

### Phase 2 (done)

- server.py: the API plus static files from frontend/ (a placeholder page until Phase 3). HOST
  defaults to 127.0.0.1; the Docker image must set HOST=0.0.0.0.
- Images come back as data URLs inside the JSON: PNG for cartoonize, JPEG for compare. Every error
  is {"detail": "<plain sentence>"}.
- Added beyond the spec: the registry caches raw model outputs, so intensity and color-pop changes
  take under a second, and /api/cartoonize accepts max_side (256-1024).
- /api/compare runs at 512px and takes about 50 s here (CartoonGAN is about 30 s of that). It stops
  when the client disconnects. For Phase 3, call /api/cartoonize once per style with max_side=512
  so the grid fills in as results arrive instead of showing nothing for 50 s.
- One inference runs at a time, so a request made during a compare waits for the current style.

### Phase 3 (done)

- frontend/: plain HTML, CSS and ES modules, no build step. Fonts are self-hosted (Anton, Inter
  Tight, JetBrains Mono, all SIL OFL), so the site needs no internet.
- tools/build_showcase.py generates frontend/gallery/ (real outputs, metrics, flicker test). Run it
  with nothing else busy: its timings feed the stats band (7.3 s average over 30 runs here).
- Checked in headless Chrome: every control, error paths, 320 / 390 / 820 / 1366 / 1920 px wide,
  reduced motion. Webcam was tested with Chrome's fake camera only.
- Deviations from DESIGN.md: small secondary text uses #6b6b6b on paper, because #8A8A8A is too
  faint there (about 3:1); #8A8A8A stays for frame and family labels. At 1366x768 the status line
  sits just below the fold.
- The compare grid calls /api/cartoonize per style, so frames appear as they finish; the UI does
  not use /api/compare.
- Portfolio, Limits and Q&A exist with real images and short copy. Phase 4 still owes the averaged
  metrics table, the full commentary and the README.
- For Phase 4: README credits the edge-promoting loss to AnimeGAN, but CartoonGAN introduced it.
  The site already says CartoonGAN. The style loss is AnimeGAN's addition.
- Edge change can look extreme on smooth photos (Hayao on the portrait: +1206%) because the original
  has almost no edges. Worth a sentence in the commentary.

### Phase 4 and final pass (done)

- Portfolio: commentary per photo, averaged metrics table, reading guide and recommendation. Limits:
  what happened and why, per case. Text lives in frontend/js/commentary.js; numbers come from
  showcase.json. The offline portfolio (portfolio.py) has real commentary too. A test fails if any
  placeholder text comes back.
- Fixed in the batch scripts: compare.py and failure_cases.py scored a square-cropped output against
  the whole photo squashed into a square, so SSIM was too low (Paprika portrait 0.63, now 0.78).
- Corrected claims: celeba_distill is not "lighter" and not trained like AnimeGAN (renamed Cel
  Shade); the edge-promoting loss is CartoonGAN's; CPU speed is seconds, not milliseconds.
- CartoonGAN Hosoda was also compared with published samples and matches closely.
- Every style was run through the UI on the portrait and the landscape: 22 of 22 fine. The app also
  starts with the network blocked, so the demo works offline.
- Nothing fell back: all planned model families are in. The CartoonGAN weights come from a mirror.
- Not done: no Dockerfile or deployment, so the README's live link is still a placeholder to fill in.
- Screenshots are JPEG in docs/screenshots (4 MB instead of 14 MB as PNG).

### Public link and deployment

- Hugging Face now needs a PRO account for Docker Spaces, so the Space was not created. The Docker
  and Space files are ready; the image build itself has not been run (no Docker on this laptop).
- start_public.bat starts Vivid and a free Cloudflare quick tunnel, and prints both addresses. The
  public address changes every time. If the tunnel fails, the local site keeps working.
- The upload limit counts bytes as they arrive, because some HTTP versions and proxies leave out
  Content-Length.
