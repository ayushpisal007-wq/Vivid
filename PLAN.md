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
- [ ] Phase 1: Model registry
- [ ] Phase 2: API
- [ ] Phase 3: Frontend
- [ ] Phase 4: Jury content
- [ ] Final pass: test every style via the UI, screenshots, summary

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
