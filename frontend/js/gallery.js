import { $, el, beforeAfter, renderMetrics, reveal, seconds, signed } from "./util.js";
import { PHOTO_NOTES, LIMITS, averageNotes } from "./commentary.js";

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
    const note = PHOTO_NOTES[photo.id];
    const pick = note && data.styles.find((s) => s.id === note.pick && photo.outputs[s.id]);
    $("pf-note").hidden = !note;
    if (note) {
      $("pf-note").replaceChildren(
        el("p", {}, note.look),
        el("p", {}, note.but),
        pick && el("p", { class: "pf-pick" }, el("span", { class: "label" }, "Our pick"),
          el("button", { type: "button", class: "btn btn-line btn-small", onclick: () => openLightbox(photo, pick) }, pick.name)));
    }
    grid.replaceChildren(
      tile(photo.original, ar, "Original", "photo"),
      ...data.styles.filter((s) => photo.outputs[s.id]).map((s) => {
        const out = photo.outputs[s.id];
        return tile(out, ar, s.name, `SSIM ${out.metrics.ssim.toFixed(2)}`, () => openLightbox(photo, s));
      }));
  }
  show(photos[0]);
  averages(data, photos);
}

function averages(data, photos) {
  const rows = data.styles.map((style) => {
    const m = photos.filter((p) => p.outputs[style.id]).map((p) => p.outputs[style.id].metrics);
    const avg = (key) => m.reduce((sum, x) => sum + x[key], 0) / m.length;
    return { style, ssim: avg("ssim"), hist: avg("hist_shift"), edge: avg("edge_density_change_pct"), ms: avg("inference_ms") };
  });
  const bar = (v) => el("td", { class: "mono" }, v.toFixed(2),
    el("span", { class: "bar" }, el("i", { style: { width: `${Math.min(100, v * 100)}%` } })));
  $("avg-basis").textContent = `Average of ${photos.length} photos: ${photos.map((p) => p.name).join(", ")}`;
  $("avg-table").replaceChildren(
    el("thead", {}, el("tr", {}, ...["Style", "Family", "SSIM", "Hist shift", "Edge Δ", "Time"].map((h) => el("th", { scope: "col" }, h)))),
    el("tbody", {}, ...rows.map((r) => el("tr", {},
      el("th", { scope: "row" }, r.style.name),
      el("td", { class: "mono" }, r.style.family),
      bar(r.ssim), bar(r.hist),
      el("td", { class: "mono" }, signed(r.edge)),
      el("td", { class: "mono" }, seconds(r.ms))))));
  $("avg-notes").replaceChildren(...averageNotes(rows).map((n) => el("div", {}, el("h4", {}, n.title), el("p", {}, n.text))));
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
      text: [LIMITS.faces.what, LIMITS.faces.why],
      media: [
        slider("sample_portrait", "paprika", "Paprika invents cracks on smooth, brightly lit skin."),
        slider("face_closeup", "face_paint_v2", "A 128 px close-up. Portrait makes up the missing detail."),
      ],
    },
    {
      n: "07 ▸ 7A",
      title: "Fine detail",
      text: [LIMITS.detail.what, LIMITS.detail.why],
      media: [
        slider("busy_background", "face_paint_v1", "Portrait Classic: the forest becomes haze."),
        slider("busy_background", "celeba_distill", "Cel Shade: leaves become a dotted pattern."),
      ],
    },
    f && {
      n: "08 ▸ 8A",
      title: "Temporal flicker",
      text: [
        `Here the same photo moved ${f.shift} pixels, like two video frames. Lined up again, the inputs are identical, but ${f.changed_pct}% of the output pixels still differ by more than 3%. In a video, that is flicker.`,
        LIMITS.flicker.why,
      ],
      media: [still(f.a, "Frame 1"), still(f.b, `Frame 2, moved ${f.shift} px`), still(f.diff, "Difference, brightened ×4")],
      three: true,
    },
  ].filter(Boolean);

  for (const it of items) {
    const row = el("article", { class: "limit reveal" },
      el("div", {}, el("p", { class: "mono" }, it.n), el("h3", {}, it.title), ...it.text.map((t) => el("p", {}, t))),
      el("div", { class: it.three ? "limit-media three" : "limit-media" }, ...it.media.filter(Boolean)));
    $("limit-list").append(row);
    reveal(row);
  }
}

export function stats(data) {
  $("st-styles").textContent = data.stats.styles;
  const [n, unit] = seconds(data.stats.avg_inference_ms).split(" ");
  $("st-ms").replaceChildren(n, el("small", {}, unit));
  $("st-res").replaceChildren(String(data.stats.max_side), el("small", {}, "px"));
}
