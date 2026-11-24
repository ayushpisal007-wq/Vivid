import { el, pad, reducedMotion, FILTER } from "./util.js";

const SPEED = 26; // px per second
const WAVE = 2600; // wavelength in px
const FRAMES = 12;

function filmCell({ photo, style, out }, n) {
  const cell = el("div", { class: "film-cell" },
    el("div", { class: "film-edge top" },
      el("span", { class: "l" }, "VIVID 400"), el("span", { class: "r" }, style.name.toUpperCase())),
    el("div", { class: "film-frame" },
      el("div", { class: "film-flip" },
        el("img", { src: out.thumb, alt: "", draggable: "false" }),
        el("img", { src: photo.original.thumb, alt: "", draggable: "false" }))),
    el("div", { class: "film-edge bottom" },
      el("span", { class: "l" }, pad(n)), el("span", { class: "r" }, `${pad(n)} ▸ ${n}A`)));
  cell.addEventListener("click", () => cell.classList.toggle("flipped")); // touch has no hover
  cell.style.transformOrigin = "0 0";
  return cell;
}

/** The wavy, drifting film strip. Each cell is skewed to follow the wave, so neighbours always join. */
export function heroFilm(root, data) {
  const photos = data.photos.filter((p) => p.kind === "example");
  const styles = data.styles.filter((s) => s.id !== FILTER);
  // Walk photos and styles together so neighbouring frames differ in both.
  const frames = Array.from({ length: FRAMES }, (_, i) => {
    const photo = photos[i % photos.length];
    const style = styles[i % styles.length];
    return { photo, style, out: photo.outputs[style.id] };
  });

  let offset = 0, last = 0, running = false, hovering = false, w = 286, amp = 22;

  const layout = () => {
    const cs = getComputedStyle(root);
    w = parseFloat(cs.getPropertyValue("--cell"));
    amp = parseFloat(cs.getPropertyValue("--amp"));
    const need = Math.max(FRAMES, Math.ceil(root.clientWidth / w) + 2); // cover the screen, hide the wrap
    while (root.children.length < need) {
      const i = root.children.length;
      root.append(filmCell(frames[i % FRAMES], i + 1));
    }
  };
  const y = (x, t) => amp * Math.sin((x / WAVE) * Math.PI * 2 + t);
  const draw = (t) => {
    const total = root.children.length * w;
    [...root.children].forEach((cell, i) => {
      const x = (((i * w - offset) % total) + total) % total - w;
      const a = y(x, t), b = y(x + w, t);
      cell.style.transform = `translate3d(${x}px,${a}px,0) skewY(${Math.atan2(b - a, w)}rad)`;
    });
  };
  const tick = (now) => {
    if (!running) return;
    if (!hovering) offset += SPEED * Math.min(0.1, (now - last) / 1000);
    last = now;
    draw(now / 4200);
    requestAnimationFrame(tick);
  };
  const start = () => {
    if (running || reducedMotion.matches) return;
    running = true;
    last = performance.now();
    requestAnimationFrame(tick);
  };

  root.addEventListener("pointerenter", (e) => { hovering = e.pointerType === "mouse"; });
  root.addEventListener("pointerleave", () => { hovering = false; });
  new ResizeObserver(() => { layout(); draw(performance.now() / 4200); }).observe(root);
  new IntersectionObserver(([e]) => { if (e.isIntersecting) start(); else running = false; }).observe(root);
}

export function filmBands() {
  for (const band of document.querySelectorAll(".film-band")) {
    for (let i = 1; i <= 24; i++) band.append(el("span", {}, i % 2 ? "VIVID 400" : `${pad(i)} ▸ ${i}A`));
  }
}
