import { $, reveal } from "./util.js";
import { getJSON } from "./api.js";
import { heroFilm, filmBands } from "./film.js";
import { showcase } from "./showcase.js";
import { portfolio, limits, stats } from "./gallery.js";
import { studio } from "./studio.js";
import { REMOTE } from "./config.js";

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
let app = null;
let known = false; // have we learned which styles this server runs?
let checking = false;
const box = $("status");
const statusText = box.querySelector(".status-text");
function setStatus(on, message) {
  box.classList.toggle("on", on);
  if (statusText.textContent !== message) statusText.textContent = message;
}

async function checkServer() {
  if (checking) return; // a sleeping free server can take a minute to answer
  checking = true;
  const waking = REMOTE && !known && setTimeout(() => setStatus(false, "Waking the models up, about a minute…"), 2500);
  try {
    const h = await getJSON("/api/health");
    setStatus(true, `Models online · ${h.styles === h.total_styles ? "" : `${h.styles} of `}${h.total_styles} styles`);
    if (!known) {
      const styles = await getJSON("/api/styles");
      app.setAvailable(styles.map((s) => s.id));
      known = true;
    }
  } catch {
    setStatus(false, "Models offline");
  } finally {
    clearTimeout(waking);
    checking = false;
  }
}

/* ---------- start ---------- */
reveal(...document.querySelectorAll(".reveal"));
filmBands();

// The page itself never waits for the models.
const data = await getJSON("gallery/showcase.json").catch(() => null);
app = studio(data?.styles ?? (await getJSON("/api/styles").catch(() => [])), data);
if (data) {
  heroFilm($("hero-film"), data);
  showcase(data, app.selectStyle);
  portfolio(data);
  limits(data);
  stats(data);
}
document.querySelector("[data-demo=vs]").addEventListener("click", (e) => {
  e.preventDefault();
  app.demoVsFilter();
});
checkServer();
setInterval(checkServer, 30000);
