import { $, el, beforeAfter, renderMetrics, reveal, seconds } from "./util.js";

function openLightbox(photo, style) {
  const out = photo.outputs[style.id];
  $("lb-family").textContent = `${style.family} / ${photo.name}`;
  $("lb-name").textContent = style.name;
  $("lb-stage").replaceChildren(beforeAfter({
    before: photo.original.src,
    after: out.src,
    width: photo.original.w,
    height: photo.original.h,
    label: style.name,
  }));
  renderMetrics($("lb-metrics"), out.metrics);
  $("lightbox").showModal();
}

export function portfolio(data) {
  const box = $("lightbox");
  $("lb-close").addEventListener("click", () => box.close());
  box.addEventListener("click", (e) => { if (e.target === box) box.close(); });

  const photos = data.photos.filter((p) => p.kind === "example");
  const grid = $("pf-grid");
  const tabs = photos.map((photo) => el("button", { type: "button", onclick: () => show(photo) }, photo.name));
  $("pf-tabs").append(...tabs);

  function tile(img, ar, name, meta, onclick) {
    return el(onclick ? "button" : "div", { class: "card", type: onclick && "button", onclick },
      el("div", { class: "card-img", style: { "--ar": ar } }, el("img", { src: img.src, alt: name, loading: "lazy" })),
      el("div", { class: "card-name" }, el("span", {}, name), el("span", { class: "mono" }, meta)));
  }

  function show(photo) {
    tabs.forEach((t, i) => t.setAttribute("aria-pressed", String(photos[i] === photo)));
    const ar = `${photo.original.w / photo.original.h}`;
    grid.replaceChildren(
      tile(photo.original, ar, "Original", "photo"),
      ...data.styles.filter((s) => photo.outputs[s.id]).map((s) => {
        const out = photo.outputs[s.id];
        return tile(out, ar, s.name, `SSIM ${out.metrics.ssim.toFixed(2)}`, () => openLightbox(photo, s));
      }));
  }
  show(photos[0]);
}

export function limits(data) {
  const styleName = (id) => data.styles.find((s) => s.id === id)?.name ?? id;
  const slider = (photoId, styleId, caption) => {
    const p = data.photos.find((x) => x.id === photoId);
    if (!p?.outputs[styleId]) return null;
    return el("figure", {},
      beforeAfter({
        before: p.original.src,
        after: p.outputs[styleId].src,
        width: p.original.w,
        height: p.original.h,
        label: styleName(styleId),
        lazy: true,
      }),
      el("figcaption", {}, caption));
  };
  const still = (img, caption) =>
    el("figure", {}, el("img", { src: img.src, alt: caption, loading: "lazy" }), el("figcaption", {}, caption));
  const f = data.flicker[0];

  const items = [
    {
      n: "06 ▸ 6A",
      title: "Faces",
      text: "Skin can crack, eyes can warp and tones can drift. These models learned from a narrow range of faces, so close-ups and hard light push them outside what they know.",
      media: [
        slider("sample_portrait", "paprika", "Paprika invents cracks on smooth, brightly lit skin."),
        slider("face_closeup", "face_paint_v2", "A tiny 128 px close-up. Detail that isn't there gets made up."),
      ],
    },
    {
      n: "07 ▸ 7A",
      title: "Fine detail",
      text: "Cartoons are flat shapes with clean lines, so training rewards exactly that. Leaves, hair and texture get smeared into blotches. It is a side effect of the goal, not a bug.",
      media: [
        slider("busy_background", "face_paint_v1", "Busy texture, Portrait Classic."),
        slider("busy_background", "celeba_distill", "Busy texture, Soft Distill."),
      ],
    },
    f && {
      n: "08 ▸ 8A",
      title: "Temporal flicker",
      text: `Every image is drawn from scratch, with no memory of the last one. Here the same photo moved ${f.shift} pixels, like two video frames. Lined up again, ${f.changed_pct}% of pixels still differ by more than 3%. In a video, that is flicker.`,
      media: [still(f.a, "Frame 1"), still(f.b, `Frame 2, moved ${f.shift} px`), still(f.diff, "Difference, brightened ×4")],
      three: true,
    },
  ].filter(Boolean);

  for (const it of items) {
    const row = el("article", { class: "limit reveal" },
      el("div", {}, el("p", { class: "mono" }, it.n), el("h3", {}, it.title), el("p", {}, it.text)),
      el("div", { class: it.three ? "limit-media three" : "limit-media" }, ...it.media.filter(Boolean)));
    $("limit-list").append(row);
    reveal(row);
  }
}

export function stats(data, health) {
  $("st-styles").textContent = health?.styles ?? data.stats.styles;
  const [n, unit] = seconds(data.stats.avg_inference_ms).split(" ");
  $("st-ms").replaceChildren(n, el("small", {}, unit));
  $("st-res").replaceChildren(String(health?.max_side ?? data.stats.max_side), el("small", {}, "px"));
}
