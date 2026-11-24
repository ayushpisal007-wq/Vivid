export const $ = (id) => document.getElementById(id);
export const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
export const pad = (n) => String(n).padStart(2, "0");
export const FILTER = "classic_filter";

/** el("div", {class: "x", onclick: fn}, child, "text"). Text is never parsed as HTML. */
export function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (v === undefined || v === null || v === false) continue;
    if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else if (k === "style") for (const [p, val] of Object.entries(v)) node.style.setProperty(p, val);
    else node.setAttribute(k, v === true ? "" : v);
  }
  node.append(...children.filter((c) => c !== undefined && c !== null && c !== false));
  return node;
}

export const seconds = (ms) => (ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)} s`);
export const signed = (n) => `${n > 0 ? "+" : n < 0 ? "−" : ""}${Math.abs(n).toFixed(0)}%`;

/** The four numbers shown for every result. */
export function renderMetrics(dl, m) {
  const rows = [
    ["SSIM", m.ssim.toFixed(3), "1 means the structure is unchanged"],
    ["Hist shift", m.hist_shift.toFixed(3), "0 means the same palette"],
    ["Edge Δ", signed(m.edge_density_change_pct), "more or fewer edges than the photo"],
    ["ms", Math.round(m.inference_ms).toLocaleString("en"), "time the model took"],
  ];
  dl.replaceChildren(...rows.map(([k, v, note]) => el("div", {}, el("dt", {}, k), el("dd", {}, v, el("small", {}, note)))));
}

/** Draggable before/after reveal. Works with mouse, touch and arrow keys. */
export function beforeAfter({ before, after, width, height, label, beforeLabel = "Original", lazy = false }) {
  const loading = lazy ? "lazy" : undefined;
  const range = el("input", { type: "range", min: 0, max: 100, value: 50, "aria-label": `Reveal: ${beforeLabel} versus ${label}` });
  const root = el("div", { class: "ba", style: { "--ar": `${width / height}` } },
    el("img", { class: "after", src: after, alt: label, loading, draggable: "false" }),
    el("img", { class: "before", src: before, alt: beforeLabel, loading, draggable: "false" }),
    el("span", { class: "ba-line" }),
    el("span", { class: "ba-tag l" }, beforeLabel),
    el("span", { class: "ba-tag r" }, label),
    range);
  const set = (pct) => {
    const p = Math.min(100, Math.max(0, pct));
    root.style.setProperty("--pos", `${p}%`);
    range.value = p;
  };
  const move = (e) => {
    const box = root.getBoundingClientRect();
    set(((e.clientX - box.left) / box.width) * 100);
  };
  root.addEventListener("pointerdown", (e) => {
    if (e.button) return;
    root.setPointerCapture(e.pointerId);
    move(e);
  });
  root.addEventListener("pointermove", (e) => root.hasPointerCapture(e.pointerId) && move(e));
  range.addEventListener("input", () => set(+range.value));
  root.setAfter = (src) => { root.querySelector(".after").src = src; };
  return root;
}

export function skeleton(ar, hint) {
  const timer = el("span", { class: "mono" }, hint ?? "");
  const node = el("div", { class: "skeleton", style: { "--ar": `${ar}` } }, el("p", {}, "Developing your frame…", timer));
  const start = performance.now();
  const id = setInterval(() => {
    if (!node.isConnected) return clearInterval(id);
    const s = Math.floor((performance.now() - start) / 1000);
    timer.textContent = `${pad(Math.floor(s / 60))}:${pad(s % 60)}${hint ? ` / ${hint}` : ""}`;
  }, 1000);
  return node;
}

const observer = new IntersectionObserver((entries) => {
  for (const e of entries) {
    if (!e.isIntersecting) continue;
    e.target.classList.add("in");
    observer.unobserve(e.target);
  }
}, { rootMargin: "0px 0px -8% 0px" });

/** Fade and slide up once, when scrolled into view. */
export const reveal = (...nodes) => nodes.forEach((n) => observer.observe(n));

export function scrollToEl(node) {
  node.scrollIntoView({ behavior: reducedMotion.matches ? "auto" : "smooth", block: "start" });
}
