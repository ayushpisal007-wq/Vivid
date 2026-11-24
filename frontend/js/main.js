import { $, reveal } from "./util.js";
import { getJSON } from "./api.js";
import { heroFilm, filmBands } from "./film.js";
import { showcase } from "./showcase.js";
import { portfolio, limits, stats } from "./gallery.js";
import { studio } from "./studio.js";

/* ---------- nav ---------- */
const burger = document.querySelector(".nav-burger");
const menu = $("nav-menu");
function setMenu(open) {
  menu.classList.toggle("open", open);
  burger.setAttribute("aria-expanded", String(open));
  document.body.style.overflow = open ? "hidden" : "";
}
burger.addEventListener("click", () => setMenu(!menu.classList.contains("open")));
menu.addEventListener("click", (e) => { if (e.target.closest("a")) setMenu(false); });
addEventListener("keydown", (e) => {
  if (e.key !== "Escape" || !menu.classList.contains("open")) return;
  setMenu(false);
  burger.focus();
});
matchMedia("(min-width: 901px)").addEventListener("change", (e) => { if (e.matches) setMenu(false); });

const nav = document.querySelector(".nav");
addEventListener("scroll", () => nav.classList.toggle("stuck", scrollY > 8), { passive: true });

const links = [...menu.querySelectorAll("a:not(.btn)")];
const spy = new IntersectionObserver((entries) => {
  for (const e of entries) {
    const link = links.find((a) => a.hash === `#${e.target.id}`);
    if (e.isIntersecting) link.setAttribute("aria-current", "true");
    else link.removeAttribute("aria-current");
  }
}, { rootMargin: "-45% 0px -50% 0px" });
links.forEach((a) => spy.observe(document.querySelector(a.hash)));

/* ---------- live status ---------- */
async function health() {
  const box = $("status");
  const text = box.querySelector(".status-text");
  const set = (on, message) => {
    box.classList.toggle("on", on);
    if (text.textContent !== message) text.textContent = message;
  };
  try {
    const h = await getJSON("/api/health");
    set(true, `Models online · ${h.styles} styles`);
    return h;
  } catch {
    set(false, "Models offline");
    return null;
  }
}

/* ---------- start ---------- */
reveal(...document.querySelectorAll(".reveal"));
filmBands();

const [data, h, styles] = await Promise.all([
  getJSON("gallery/showcase.json").catch(() => null),
  health(),
  getJSON("/api/styles").catch(() => null),
]);

const app = studio(styles ?? data?.styles ?? [], data);
if (data) {
  heroFilm($("hero-film"), data);
  showcase(data, app.selectStyle);
  portfolio(data);
  limits(data);
  stats(data, h);
}
document.querySelector("[data-demo=vs]").addEventListener("click", (e) => {
  e.preventDefault();
  app.demoVsFilter();
});
setInterval(health, 30000);
