# Vivid — Before/After Cartoonization Portfolio

A small pipeline that runs pretrained AnimeGAN2 checkpoints over your own
photos, compares the variants with objective metrics, deliberately
highlights where the models break, and packages everything into one HTML
page you can screen-share to a jury.

## Quick start

```bash
cd Vivid
python -m venv venv                 # already created if you're reading this from the repo
venv\Scripts\activate                # Windows PowerShell/cmd
# source venv/Scripts/activate       # Git Bash

pip install -r requirements.txt

python cartoonize.py                 # inputs/  -> outputs/{model}/{filename}, timing stats
python compare.py                    # contact sheets + SSIM/hist/edge metrics
python failure_cases.py              # deliberate face-closeup + busy-background stress test
python portfolio.py                  # builds portfolio/index.html

# or, all four stages in one go:
python run_all.py
```

Then open `portfolio/index.html` in a browser (or screen-share the tab).

Drop your own photos into `inputs/` before running — a few free-license
placeholder photos are already there so the scripts are verifiable
immediately. `failure_cases/inputs/` similarly ships a placeholder face
close-up and busy-background photo; swap in your own for a stronger demo.

The first run of `cartoonize.py` (or any script that loads models)
downloads the pretrained weights via `torch.hub` from the
[`bryandlee/animegan2-pytorch`](https://github.com/bryandlee/animegan2-pytorch)
repo and caches them under `~/.cache/torch/hub` — no manual weight
hunting, but it does need an internet connection the first time.

### A note on cropping

`face2paint` (the pre/post-processing wrapper these checkpoints ship with)
center-crops every input to a square before resizing to 512×512. Wide
landscape photos lose their left/right edges in the output — that's why
originals in the portfolio grid are rectangular but every stylized output
is square. This is expected behavior for this model family, not a bug.

### Per-stage options

Every script takes `--models` (comma-separated, default `all`), `--device`
(`cpu`/`cuda`/`auto`), and an `--input`/`--output` pair — run any script
with `--help` for the full list. Model names: `face_paint_v2`, `paprika`,
`celeba_distill` (see `models.py`).

## What's in here

| File | Purpose |
|---|---|
| `models.py` | Loads the three pretrained AnimeGAN2 checkpoints via `torch.hub` |
| `cartoonize.py` | Batch CLI: photo(s) → each model → `outputs/{model}/{filename}`, with timing |
| `metrics.py` | SSIM, color-histogram shift, edge-density change between original and output |
| `compare.py` | Builds a labeled contact sheet per photo + writes `outputs/metrics.csv` |
| `failure_cases.py` | Runs all models on a face close-up and a busy-background photo, with annotated callouts |
| `portfolio.py` + `templates/` | Renders everything into one HTML page |
| `run_all.py` | Runs the four stages above in sequence |

## How it works

Vivid uses **AnimeGAN2**, a convolutional generator trained adversarially
to translate ordinary photos into an anime/cartoon visual style. A few
concepts worth being able to explain to the jury:

**Encoder–decoder generator.** The generator is a single feed-forward CNN:
an *encoder* downsamples the input photo through strided convolutions into
a compact feature representation, a stack of residual blocks processes
that representation, and a *decoder* upsamples it back to a full-resolution
RGB image. Unlike a segmentation network, the output isn't a mask or a
label map — it's a complete re-synthesized image, produced in a single
forward pass (a few hundred milliseconds on CPU, real-time-ish on GPU).

**Adversarial loss.** A separate *discriminator* network is trained
alongside the generator to distinguish "real anime frames" from "generator
outputs." The generator is trained to fool it. This is what pushes results
toward genuine cartoon-style texture statistics — flat color regions, bold
clean edges — rather than just a global color/contrast shift.

**Content and style losses.** Adversarial loss alone doesn't guarantee the
output still looks like *your photo* — it only rewards looking cartoon-ish.
So training also includes a **content loss** (comparing input and output
in a pretrained VGG feature space, to preserve structure/semantics — what's
in the image and roughly where) and **style losses** (comparing grayscale
VGG features and a blurred/desaturated color signal against real cartoon
images, to transfer palette and shading style). AnimeGAN's specific
contribution is an *edge-promoting adversarial loss*: the discriminator is
also shown edge-smoothed versions of real cartoon frames, which specifically
penalizes muddy or blurry edges relative to real hand-drawn line art.

**Unpaired image-to-image translation.** There is no dataset of "this exact
photo, hand-drawn as its cartoon equivalent" — that pairing doesn't exist
at any scale. Training instead uses two *unrelated* collections: a large
set of real photos and a large set of real anime/cartoon frames, with no
correspondence between them. The loss functions above are specifically
designed so a mapping between the two domains can be learned from these
independent sets alone (the same family of idea as CycleGAN). This is what
makes the whole approach practical — collecting matched photo/cartoon pairs
by hand would be a non-starter at the scale GANs need.

## Model variants used

All three checkpoints share the same generator/discriminator architecture
and training recipe — they differ only in the dataset/distillation used:

- **`face_paint_v2`** — general-purpose portrait/scene stylization, the
  best all-round default.
- **`paprika`** — bolder, more graphic style, tuned toward Satoshi Kon's
  film *Paprika*.
- **`celeba_distill`** — a lighter, distilled checkpoint with softer,
  subtler stylization.

Note on naming: these are the actual published checkpoint names from
`bryandlee/animegan2-pytorch`. They are **not** the original "Hayao" /
"Shinkai" TensorFlow AnimeGANv2 checkpoints (those reference Studio
Ghibli's Hayao Miyazaki and Makoto Shinkai's visual styles specifically);
this repo's checkpoints are portrait-oriented distillations of that same
line of work, chosen here because they load cleanly through `torch.hub`
with no manual conversion. Say this plainly if a jury member who knows the
original AnimeGANv2 project asks — it's a fair question and the honest
answer is more credible than glossing over it.

## Known limitations

- **Face distortion.** The face-oriented checkpoints were trained at a
  fixed 512×512 resolution on a particular face-crop distribution. Faces
  outside that distribution — extreme close-ups, unusual angles, strong
  lighting, glasses/accessories — commonly come out with warped eyes,
  waxy/plastic-looking skin, or subtle left-right asymmetry. See
  `failure_cases.py`'s face close-up output for a deliberate example.

- **Loss of fine texture and detail.** The adversarial and style losses
  explicitly reward flat, bold regions, because that's what real cartoon
  frames look like. High-frequency detail — individual hair strands,
  foliage, fabric weave — gets smeared or flattened into blotches rather
  than stylized crisply. This is a direct, by-design consequence of the
  training objective, not a bug to patch. See the busy-background failure
  case.

- **Temporal instability.** The model processes every image independently
  with no notion of "the previous frame." There is no temporal-consistency
  loss or mechanism at all. Run it on consecutive video frames and you'll
  see visible flicker: small changes in the input can flip local
  stylization decisions (exact edge placement, which way a color patch
  splits) frame to frame. Fine for single photos; a real problem the
  moment this is applied to video without additional smoothing.

- **This is not a hand-tuned Instagram-style filter.** A conventional
  photo filter is a fixed, global pixel-wise transform — the same
  saturation curve / color LUT / convolution kernel applied identically to
  every pixel of every image, tuned once by a designer and fully
  deterministic. AnimeGAN2 is a **learned nonlinear function of the whole
  image's content**: the network makes different local decisions depending
  on what it infers a region *is* (sky vs. foliage vs. skin vs. hard edge),
  producing spatially-varying, content-aware stylization that a fixed
  filter is architecturally incapable of. The tradeoff runs the other way,
  too — a filter is perfectly predictable and never distorts geometry; a
  learned model occasionally makes content-dependent mistakes (see the two
  limitations above) that a filter simply cannot make, because a filter
  never "looks at" what's in the image in the first place.

## Requirements / environment notes

- Built and tested against **Python 3.12** — PyTorch wheel support tends
  to lag brand-new Python releases, so if you have multiple Pythons
  installed, prefer 3.12 over anything newer when creating the venv
  (`py -3.12 -m venv venv`).
- `requirements.txt` pins CPU-only `torch`/`torchvision` builds — fast to
  install and enough for a demo (a few hundred ms/image on a laptop CPU,
  per the timing stats `cartoonize.py` prints). If you have a CUDA GPU,
  install matching `torch`/`torchvision` CUDA wheels instead and pass
  `--device cuda`.
