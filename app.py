#!/usr/bin/env python
"""Vivid -- live Gradio demo.

Loads the pretrained AnimeGAN2 checkpoints used by cartoonize.py (via
models.py) plus the AnimeGANv3 Hayao/Shinkai ONNX checkpoints once at
startup, then serves a one-page upload -> pick style -> generate UI for a
live jury demo.

Usage:
    python app.py
Then open the local URL it prints (typically http://127.0.0.1:7860).
"""
from __future__ import annotations

import base64
import io
import random
import tempfile
from pathlib import Path

import gradio as gr
from PIL import Image, ImageEnhance

from models import MODEL_VARIANTS, ONNX_VARIANTS, OnnxCartoonModel, get_device, load_models

SIZE = 512
COMPARE_ALL = "compare_all"
HISTORY_LEN = 8
EXAMPLES = sorted(p for p in (Path(__file__).parent / "inputs").iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})

# Ordered softest -> boldest so the picker reads as a spectrum.
STYLE_LABELS = {
    "face_paint_v2": "Portrait",
    "paprika": "Paprika",
    "celeba_distill": "Cel Shade",
    "hayao_v3": "Hayao",
    "shinkai_v3": "Shinkai",
}

print("Loading models once at startup (reusing the torch.hub cache)...")
DEVICE = get_device("auto")
MODELS = {
    **load_models(list(MODEL_VARIANTS), DEVICE, size=SIZE),
    **{name: OnnxCartoonModel(name) for name in ONNX_VARIANTS},
}
MODELS = {name: MODELS[name] for name in STYLE_LABELS}
print(f"Loaded {len(MODELS)} model(s) on {DEVICE}. Ready.")


def square_crop(image: Image.Image) -> Image.Image:
    # Same centre crop face2paint applies, so the original lines up pixel-for-pixel with every output.
    w, h = image.size
    s = min(w, h)
    return image.crop(((w - s) // 2, (h - s) // 2, (w + s) // 2, (h + s) // 2)).resize((SIZE, SIZE), Image.LANCZOS)


def stylize(base: Image.Image, name: str, intensity: float, enhance: bool) -> Image.Image:
    out = MODELS[name].run(base).resize(base.size)
    if enhance:
        out = ImageEnhance.Contrast(ImageEnhance.Color(out).enhance(1.3)).enhance(1.12)
    return Image.blend(base, out, intensity / 100)


def to_data_uri(image: Image.Image) -> str:
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=90)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def slider_html(before: Image.Image, after: Image.Image, label: str) -> str:
    return f"""
<div class="ba" style="--pos:50%">
  <img src="{to_data_uri(after)}" alt="Stylized">
  <div class="ba-before"><img src="{to_data_uri(before)}" alt="Original"></div>
  <div class="ba-line"><span>⇆</span></div>
  <span class="ba-tag ba-tag-l">Original</span><span class="ba-tag ba-tag-r">{label}</span>
  <input type="range" min="0" max="100" value="50" aria-label="Drag to compare before and after"
         oninput="this.parentElement.style.setProperty('--pos', this.value + '%')">
</div>"""


EMPTY_HTML = """
<div class="ba-empty"><div class="ba-empty-icon">✦</div>
<p>Your before / after comparison appears here.</p><span>Upload a photo or try an example, then hit Generate.</span></div>"""

LOADING_HTML = """
<div class="ba-skeleton"><div class="spinner"></div><p>Painting your photo…</p>
<span>Running the AnimeGAN model on CPU, this takes a few seconds per style.</span></div>"""


def save_png(image: Image.Image) -> str:
    path = tempfile.NamedTemporaryFile(prefix="vivid_", suffix=".png", delete=False).name
    image.save(path)
    return path


def generate(image, style, intensity, enhance, history):
    if image is None:
        raise gr.Error("Upload a photo or click “Try an example” first.")

    yield LOADING_HTML, gr.DownloadButton(visible=False), gr.Gallery(visible=False), gr.Button(interactive=False), history, history_items(history)

    base = square_crop(image.convert("RGB"))
    names = list(MODELS) if style == COMPARE_ALL else [style]
    outputs = [(stylize(base, name, intensity, enhance), STYLE_LABELS[name]) for name in names]

    first, label = outputs[0]
    history = ([{"base": base, "out": out, "label": lbl} for out, lbl in outputs] + history)[:HISTORY_LEN]
    yield (
        slider_html(base, first, label),
        gr.DownloadButton(f"Download {label}", value=save_png(first), visible=True),
        gr.Gallery(value=[(base, "Original")] + outputs, visible=len(outputs) > 1),
        gr.Button(interactive=True),
        history,
        history_items(history),
    )


def history_items(history):
    return [(h["out"], h["label"]) for h in history]


def reload_from_history(history, evt: gr.SelectData):
    h = history[evt.index]
    return slider_html(h["base"], h["out"], h["label"]), gr.DownloadButton(f"Download {h['label']}", value=save_png(h["out"]), visible=True)


CSS = """
:root, .dark {
  --v-bg: #0a0a12;
  --v-surface: #13131d;
  --v-surface-2: #1b1b28;
  --v-border: #262636;
  --v-text: #f4f4fa;
  --v-text-2: #a3a3b8;
  --v-text-3: #6e6e85;
  --v-primary: #8b5cf6;
  --v-primary-hover: #9d74ff;
  --v-grad: linear-gradient(135deg, #a855f7 0%, #6366f1 50%, #14b8a6 100%);
  --v-radius: 12px;
  --v-shadow: 0 1px 0 rgba(255,255,255,.04) inset, 0 12px 40px -12px rgba(0,0,0,.6);
  --body-background-fill: var(--v-bg);
  --background-fill-primary: var(--v-surface);
  --background-fill-secondary: var(--v-surface-2);
  --block-background-fill: transparent;
  --block-border-width: 0px;
  --border-color-primary: var(--v-border);
  --body-text-color: var(--v-text);
  --block-label-text-color: var(--v-text-2);
  --color-accent: var(--v-primary);
  --slider-color: var(--v-primary);
  --checkbox-background-color-selected: var(--v-primary);
  --checkbox-border-color-selected: var(--v-primary);
}
body, gradio-app, .gradio-container { background: var(--v-bg) !important; color: var(--v-text); }
.gradio-container { max-width: 1440px !important; margin: 0 auto !important; padding: 0 32px 64px !important; }
footer { display: none !important; }

/* Hero */
#hero { text-align: center; padding: 64px 0 40px; position: relative; }
#hero::before { content: ""; position: absolute; inset: 0 20% auto; height: 260px; z-index: -1;
  background: radial-gradient(closest-side, rgba(139,92,246,.28), transparent); filter: blur(30px); }
#hero .pill { display: table; margin: 0 auto; padding: 6px 14px; border-radius: 999px; font-size: 13px; font-weight: 600;
  color: var(--v-text-2); border: 1px solid var(--v-border); background: var(--v-surface); margin-bottom: 20px; }
#hero h1 { display: inline-block; padding: 0 .06em .08em; font-size: clamp(56px, 8vw, 104px); font-weight: 800; letter-spacing: -0.045em; margin: 0; line-height: 1;
  background-image: var(--v-grad) !important; -webkit-background-clip: text; background-clip: text; color: transparent; -webkit-text-fill-color: transparent; }
#hero p { color: var(--v-text-2); font-size: clamp(17px, 1.4vw, 21px); margin: 18px 0 0; }

/* Cards */
.v-card { background: var(--v-surface) !important; border: 1px solid var(--v-border) !important;
  border-radius: 20px !important; padding: 24px !important; box-shadow: var(--v-shadow); gap: 16px !important; }
.v-step { display: flex; align-items: center; gap: 10px; margin: 0; color: var(--v-text); font-size: 16px; font-weight: 650; }
.v-step b { display: inline-grid; place-items: center; width: 26px; height: 26px; border-radius: 8px; font-size: 13px;
  background: var(--v-surface-2); border: 1px solid var(--v-border); color: var(--v-text-2); }
.v-hint { color: var(--v-text-3); font-size: 13px; margin: -8px 0 0; }
#section-results { margin-top: 28px; }

/* Upload */
#upload { border-radius: 14px !important; overflow: hidden; background: var(--v-surface-2) !important;
  border: 1.5px dashed #3a3a52 !important; min-height: 380px; transition: border-color .2s; }
#upload:hover { border-color: var(--v-primary) !important; }

/* Style picker as segmented chips */
#style-picker .wrap { gap: 8px !important; }
#style-picker label { border-radius: 10px !important; padding: 10px 16px !important; cursor: pointer;
  border: 1px solid var(--v-border) !important; background: var(--v-surface-2) !important; color: var(--v-text-2) !important;
  transition: all .15s; font-weight: 600; }
#style-picker label:hover { border-color: #4a4a66 !important; color: var(--v-text) !important; }
#style-picker label.selected { background: rgba(139,92,246,.16) !important; border-color: var(--v-primary) !important; color: #fff !important; }
#style-picker input { display: none; }

/* Buttons */
button.v-primary { background: var(--v-primary) !important; border: none !important; color: #fff !important;
  font-size: 17px !important; font-weight: 700 !important; border-radius: 12px !important; padding: 15px 20px !important;
  box-shadow: 0 8px 24px -8px rgba(139,92,246,.7); transition: background .15s, transform .1s, box-shadow .15s; }
button.v-primary:hover { background: var(--v-primary-hover) !important; box-shadow: 0 10px 30px -8px rgba(139,92,246,.9); }
button.v-primary:active { transform: translateY(1px); }
button.v-primary:disabled { opacity: .55; cursor: progress; }
button.v-ghost { background: transparent !important; border: 1px solid var(--v-border) !important; color: var(--v-text) !important;
  font-weight: 600 !important; border-radius: 10px !important; transition: background .15s, border-color .15s; }
button.v-ghost:hover { background: var(--v-surface-2) !important; border-color: #4a4a66 !important; }

/* Before/after slider */
.ba { position: relative; width: 100%; max-width: 720px; margin: 0 auto; aspect-ratio: 1; border-radius: 16px;
  overflow: hidden; user-select: none; background: var(--v-surface-2); box-shadow: 0 20px 60px -20px rgba(0,0,0,.8); }
.ba img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; display: block; }
.ba-before { position: absolute; inset: 0; clip-path: inset(0 calc(100% - var(--pos)) 0 0); }
.ba-line { position: absolute; top: 0; bottom: 0; left: var(--pos); width: 3px; margin-left: -1.5px; background: #fff;
  pointer-events: none; box-shadow: 0 0 12px rgba(0,0,0,.5); }
.ba-line span { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); width: 44px; height: 44px;
  border-radius: 50%; background: #fff; color: #222; display: grid; place-items: center; font-size: 20px; font-weight: 700;
  box-shadow: 0 4px 16px rgba(0,0,0,.4); }
.ba-tag { position: absolute; top: 14px; padding: 6px 12px; border-radius: 8px; font-size: 13px; font-weight: 700;
  background: rgba(10,10,18,.7); backdrop-filter: blur(6px); color: #fff; pointer-events: none; }
.ba-tag-l { left: 14px; } .ba-tag-r { right: 14px; }
.ba input[type=range] { position: absolute; inset: 0; width: 100%; height: 100%; margin: 0; opacity: 0; cursor: ew-resize; }

.ba-empty, .ba-skeleton { max-width: 720px; margin: 0 auto; aspect-ratio: 1; border-radius: 16px; display: flex;
  flex-direction: column; align-items: center; justify-content: center; text-align: center; padding: 24px;
  background: var(--v-surface-2); border: 1px solid var(--v-border); }
.ba-empty p, .ba-skeleton p { color: var(--v-text); font-size: 18px; font-weight: 650; margin: 14px 0 6px; }
.ba-empty span, .ba-skeleton span { color: var(--v-text-3); font-size: 14px; }
.ba-empty-icon { font-size: 40px; color: var(--v-primary); }
.ba-skeleton { background: linear-gradient(110deg, var(--v-surface-2) 30%, #262638 50%, var(--v-surface-2) 70%);
  background-size: 250% 100%; animation: shimmer 1.6s linear infinite; }
.spinner { width: 46px; height: 46px; border-radius: 50%; border: 4px solid rgba(255,255,255,.1);
  border-top-color: var(--v-primary); animation: spin .8s linear infinite; }
@keyframes shimmer { to { background-position: -150% 0; } }
@keyframes spin { to { transform: rotate(360deg); } }

#compare-grid, #history { border-radius: 14px; }
#compare-grid *, #history * { scrollbar-color: #3a3a52 transparent; }
#history .thumbnail-item { border-radius: 10px !important; }
"""

THEME = gr.themes.Base(
    primary_hue="violet", neutral_hue="slate", radius_size="lg", font=[gr.themes.GoogleFont("Inter"), "sans-serif"]
)

# Force dark mode regardless of the viewer's OS setting.
FORCE_DARK = "() => { document.body.classList.add('dark'); }"


with gr.Blocks(title="Vivid", css=CSS, theme=THEME, js=FORCE_DARK) as demo:
    history_state = gr.State([])

    gr.HTML(
        "<div id='hero'><span class='pill'>AnimeGAN · 5 styles · runs locally</span>"
        "<h1>Vivid</h1><p>Turn any photo into anime-style art in seconds.</p></div>"
    )

    with gr.Row(equal_height=True):
        with gr.Column(scale=3, elem_classes="v-card"):
            gr.HTML("<p class='v-step'><b>1</b>Upload a photo</p>")
            image_in = gr.Image(type="pil", show_label=False, sources=["upload", "clipboard"], elem_id="upload")
            example_btn = gr.Button("🎲  Try an example", elem_classes="v-ghost")
        with gr.Column(scale=2, elem_classes="v-card"):
            gr.HTML("<p class='v-step'><b>2</b>Pick a style</p>")
            style_in = gr.Radio(
                choices=[(label, name) for name, label in STYLE_LABELS.items()] + [("Compare all", COMPARE_ALL)],
                value="face_paint_v2",
                show_label=False,
                elem_id="style-picker",
            )
            gr.HTML("<p class='v-hint'>Ordered from clean anime portrait (Portrait) to bold film-style line art (Hayao, Shinkai).</p>")
            gr.HTML("<p class='v-step'><b>3</b>Fine-tune</p>")
            intensity_in = gr.Slider(0, 100, value=100, step=5, label="Style intensity (%)")
            enhance_in = gr.Checkbox(value=True, label="Vivid boost: extra saturation & contrast")
            generate_btn = gr.Button("✨  Generate", elem_classes="v-primary")

    with gr.Column(elem_classes="v-card", elem_id="section-results"):
        with gr.Row():
            gr.HTML("<p class='v-step'><b>✦</b>Result: drag the handle to compare</p>")
            download_btn = gr.DownloadButton("Download", visible=False, elem_classes="v-ghost", scale=0, min_width=200)
        result_view = gr.HTML(EMPTY_HTML)
        compare_grid = gr.Gallery(
            show_label=False, columns=6, rows=1, height=240, object_fit="cover", visible=False, elem_id="compare-grid", allow_preview=False
        )
        gr.HTML("<p class='v-step' style='margin-top:12px'><b>⟲</b>Recent generations: click to reload</p>")
        history_out = gr.Gallery(
            show_label=False, columns=8, rows=1, height=190, object_fit="cover", elem_id="history", allow_preview=False
        )

    gen_inputs = [image_in, style_in, intensity_in, enhance_in, history_state]
    gen_outputs = [result_view, download_btn, compare_grid, generate_btn, history_state, history_out]

    generate_btn.click(generate, gen_inputs, gen_outputs, show_progress="hidden")
    # One click for the jury: load a random sample photo and generate straight away.
    example_btn.click(lambda: str(random.choice(EXAMPLES)), None, image_in).then(
        generate, gen_inputs, gen_outputs, show_progress="hidden"
    )
    history_out.select(reload_from_history, history_state, [result_view, download_btn])


if __name__ == "__main__":
    demo.launch(share=False)
