import { $, el, pad } from "./util.js";

/** Which photo shows each style best on a wide screen. Tall screens always use the portrait. */
const WIDE = {
  face_paint_v2: "sample_street",
  face_paint_v1: "sample_landscape",
  paprika: "sample_street",
  celeba_distill: "sample_landscape",
  hayao_v3: "sample_landscape",
  shinkai_v3: "sample_street",
  cartoongan_hayao: "sample_street",
  cartoongan_hosoda: "sample_street",
  cartoongan_shinkai: "sample_landscape",
  cartoongan_paprika: "sample_street",
  classic_filter: "sample_landscape",
};
const TALL = "sample_portrait";
const tall = matchMedia("(max-aspect-ratio: 1/1)");

export function showcase(data, onTry) {
  const root = $("styles");
  const stage = root.querySelector(".showcase-stage");
  const examples = data.photos.filter((p) => p.kind === "example");
  const slides = data.styles
    .filter((style) => examples.some((p) => p.outputs[style.id]))
    .map((style) => ({
      style,
      get out() {
        const want = tall.matches ? TALL : WIDE[style.id];
        const photo = examples.find((p) => p.id === want && p.outputs[style.id])
          ?? examples.find((p) => p.outputs[style.id]);
        return photo.outputs[style.id];
      },
    }));
  if (!slides.length) return;

  const layers = [el("img", { alt: "" }), el("img", { alt: "" })];
  stage.append(...layers);
  let index = 0, front = 0, token = 0;

  function show(i) {
    index = (i + slides.length) % slides.length;
    const { style, out } = slides[index];
    const next = slides[(index + 1) % slides.length];
    const mine = ++token;
    const back = layers[1 - front];
    back.src = out.src;
    const swap = () => {
      if (mine !== token) return; // the viewer already moved on
      back.classList.add("on");
      layers[front].classList.remove("on");
      front = 1 - front;
    };
    back.decode().then(swap, swap);
    $("sc-index").textContent = pad(index + 1);
    $("sc-total").textContent = pad(slides.length);
    $("sc-name").textContent = style.name;
    $("sc-sub").textContent = `${style.family} / ${style.source}`;
    $("sc-next-img").src = next.out.thumb;
    $("sc-next-name").textContent = next.style.name;
  }

  $("sc-next").addEventListener("click", () => show(index + 1));
  $("sc-prev").addEventListener("click", () => show(index - 1));
  $("sc-try").addEventListener("click", () => onTry(slides[index].style.id));
  root.addEventListener("keydown", (e) => {
    if (e.key === "ArrowRight") show(index + 1);
    else if (e.key === "ArrowLeft") show(index - 1);
  });
  let startX = null;
  root.addEventListener("pointerdown", (e) => { startX = e.pointerType === "mouse" ? null : e.clientX; });
  root.addEventListener("pointerup", (e) => {
    if (startX === null) return;
    const dx = e.clientX - startX;
    startX = null;
    if (Math.abs(dx) > 50) show(index + (dx < 0 ? 1 : -1));
  });
  tall.addEventListener("change", () => show(index));
  show(0);
}
