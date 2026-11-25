import { $, el, pad, FILTER, beforeAfter, renderMetrics, scrollToEl, seconds, signed, skeleton } from "./util.js";
import { cartoonize, fetchExample, getJSON } from "./api.js";
import { REMOTE } from "./config.js";

const MAX_BYTES = 10 * 1024 * 1024;
const TYPES = ["image/jpeg", "image/png", "image/webp"];
const FAMILIES = ["AnimeGAN", "CartoonGAN", "Filter"];
const COMPARE_SIDE = 512;
const HISTORY_MAX = 12;
const DEFAULT_STYLE = "hayao_v3";

export function studio(styles, showcaseData) {
  let photo = null; // { file, url, ar }
  let result = null; // the one on screen
  let history = [];
  let shot = 0; // running frame number for the history strip
  let job = null; // AbortController of the running cartoonize
  let compareJob = null;
  let retune = 0; // debounce timer
  let vsToken = 0;
  let examples = null, exampleIndex = 0;
  let available = new Set(styles.map((s) => s.id));

  const byId = (id) => styles.find((s) => s.id === id);
  const style = () => $("style-picker").querySelector("input:checked")?.value;
  const options = () => ({ intensity: +$("intensity").value, pop: $("pop").checked });
  const isAbort = (e) => e.name === "AbortError";

  /* ---------- errors ---------- */
  function fail(message) {
    $("error").textContent = message;
    $("error").hidden = !message;
    if (message) $("error").scrollIntoView({ block: "nearest" });
  }

  /* ---------- style picker ---------- */
  for (const family of FAMILIES) {
    const group = styles.filter((s) => s.family === family);
    if (!group.length) continue;
    $("style-picker").append(el("div", { class: "style-group" },
      el("span", { class: "mono" }, family),
      el("div", { class: "pills" }, ...group.map((s) =>
        el("label", { class: "pill" },
          el("input", { type: "radio", name: "style", value: s.id, onchange: describe }),
          el("span", {}, s.name))))));
  }
  function describe() {
    const s = byId(style());
    $("style-desc").textContent = s ? s.description : "No styles are available right now.";
  }
  function selectStyle(id) {
    const input = $("style-picker").querySelector(`input[value="${CSS.escape(id)}"]`);
    if (input && !input.disabled) input.checked = true;
    describe();
  }
  /** Grey out styles this server doesn't run. Their results are still in the Portfolio. */
  function setAvailable(ids) {
    available = new Set(ids);
    for (const input of $("style-picker").querySelectorAll("input")) {
      input.disabled = !available.has(input.value);
      input.parentElement.title = input.disabled ? "Runs in the full version" : "";
      if (input.disabled && input.checked) input.checked = false;
    }
    if (!style()) selectStyle(available.has(DEFAULT_STYLE) ? DEFAULT_STYLE : ids[0]);
    const limited = available.size < styles.length;
    $("style-limit").hidden = !limited;
    $("style-limit").textContent = limited
      ? `This small server runs ${available.size} of ${styles.length} styles. The rest need more memory: see their results in the Portfolio, or run the full version locally.`
      : "";
  }
  selectStyle(byId(DEFAULT_STYLE) ? DEFAULT_STYLE : styles[0]?.id ?? "");
  if (!styles.length) for (const id of ["go", "compare-btn", "example"]) $(id).disabled = true;

  /* ---------- photo input ---------- */
  async function setPhoto(file) {
    fail("");
    if (!file) return false;
    if (!TYPES.includes(file.type)) {
      fail("Please choose a JPG, PNG or WebP photo. Other formats, such as HEIC or GIF, aren't supported.");
      return false;
    }
    if (file.size > MAX_BYTES) {
      fail("That photo is larger than 10 MB. Please choose a smaller one.");
      return false;
    }
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.src = url;
    try {
      await img.decode();
    } catch {
      URL.revokeObjectURL(url);
      fail("That file couldn't be read as an image. It may be damaged; please try another photo.");
      return false;
    }
    if (photo) URL.revokeObjectURL(photo.url);
    photo = { file, url, ar: img.naturalWidth / img.naturalHeight };
    $("preview").src = url;
    $("drop").classList.add("filled");
    document.querySelector(".drop-preview").hidden = false;
    return true;
  }

  $("file").addEventListener("change", (e) => {
    setPhoto(e.target.files[0]);
    e.target.value = ""; // so choosing the same file again still fires
  });
  const drop = $("drop");
  let depth = 0;
  drop.addEventListener("dragenter", (e) => { e.preventDefault(); depth++; drop.classList.add("over"); });
  drop.addEventListener("dragover", (e) => e.preventDefault());
  drop.addEventListener("dragleave", () => { if (--depth <= 0) { depth = 0; drop.classList.remove("over"); } });
  drop.addEventListener("drop", (e) => {
    e.preventDefault();
    depth = 0;
    drop.classList.remove("over");
    setPhoto(e.dataTransfer.files[0]);
  });
  // A photo dropped beside the box would otherwise make the browser leave the page.
  for (const type of ["dragover", "drop"]) addEventListener(type, (e) => e.preventDefault());
  document.addEventListener("paste", (e) => {
    const file = [...(e.clipboardData?.files ?? [])].find((f) => f.type.startsWith("image/"));
    if (!file) return;
    e.preventDefault();
    setPhoto(file).then((ok) => ok && scrollToEl($("studio")));
  });

  /* ---------- webcam ---------- */
  const modal = $("cam-modal"), video = $("cam-video");
  let stream = null;
  const stopCam = () => {
    stream?.getTracks().forEach((t) => t.stop());
    stream = null;
    video.srcObject = null;
    $("cam-shoot").disabled = true;
  };
  $("webcam").addEventListener("click", async () => {
    $("cam-error").hidden = true;
    modal.showModal();
    try {
      if (!navigator.mediaDevices) throw new DOMException("", "Insecure");
      const s = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 1280 }, facingMode: "user" } });
      if (!modal.open) return s.getTracks().forEach((t) => t.stop()); // closed while the prompt was up
      stream = s;
      video.srcObject = s;
      await video.play();
      $("cam-shoot").disabled = false;
    } catch (e) {
      const messages = {
        NotAllowedError: "Camera access was blocked. Allow it in the browser's address bar, then try again.",
        NotFoundError: "No camera was found on this device.",
        NotReadableError: "The camera is being used by another app. Close it and try again.",
        Insecure: "The browser only allows the camera on localhost or HTTPS.",
      };
      if (!modal.open) return;
      $("cam-error").textContent = messages[e.name] ?? "The camera couldn't be started.";
      $("cam-error").hidden = false;
    }
  });
  $("cam-close").addEventListener("click", () => modal.close());
  modal.addEventListener("close", stopCam);
  $("cam-shoot").addEventListener("click", () => {
    const c = el("canvas", { width: video.videoWidth, height: video.videoHeight });
    const g = c.getContext("2d");
    g.translate(c.width, 0);
    g.scale(-1, 1); // keep it mirrored, like the preview
    g.drawImage(video, 0, 0);
    c.toBlob((blob) => {
      modal.close();
      if (blob) setPhoto(new File([blob], "webcam.jpg", { type: "image/jpeg" }));
    }, "image/jpeg", 0.92);
  });

  /* ---------- cartoonize ---------- */
  function estimate(id) {
    // The timings were measured on the laptop, so only quote them there.
    if (!["localhost", "127.0.0.1"].includes(location.hostname)) return REMOTE ? "small free server, this can take a minute or two" : "";
    const runs = showcaseData?.photos
      .filter((p) => p.kind === "example" && p.outputs[id])
      .map((p) => p.outputs[id].metrics.inference_ms) ?? [];
    return runs.length ? `usually about ${seconds(runs.reduce((a, b) => a + b) / runs.length)}` : "";
  }

  async function run() {
    if (!photo) return fail("Add a photo first, or press Try an example.");
    stopCompare();
    job?.abort();
    clearTimeout(retune);
    const mine = (job = new AbortController());
    const used = { photo, style: style(), ...options() };
    fail("");
    $("compare").hidden = true;
    $("results").hidden = false;
    $("results").classList.add("loading");
    $("res-family").textContent = byId(used.style).family;
    $("res-name").textContent = byId(used.style).name;
    $("metrics").replaceChildren();
    $("vs-panel").hidden = true;
    $("download").disabled = true;
    $("stage").replaceChildren(skeleton(photo.ar, estimate(used.style)));
    scrollToEl($("results"));
    try {
      const data = await cartoonize(used.photo.file, { ...used, signal: mine.signal });
      if (job !== mine) return;
      addToHistory({ ...used, data });
    } catch (e) {
      if (isAbort(e) || job !== mine) return;
      $("stage").replaceChildren();
      if (result) show(result);
      else $("results").hidden = true;
      fail(e.message);
      scrollToEl($("form"));
    } finally {
      if (job === mine) job = null;
    }
  }

  /** Show a finished result. */
  function show(r) {
    result = r;
    const { data } = r;
    $("results").hidden = false;
    $("results").classList.remove("loading");
    $("res-family").textContent = `${data.style.family} / ${data.style.source}`;
    $("res-name").textContent = data.style.name;
    $("stage").replaceChildren(beforeAfter({
      before: data.original, after: data.image, width: data.width, height: data.height, label: data.style.name,
    }));
    renderMetrics($("metrics"), data.metrics);
    $("download").disabled = false;
    $("vs").disabled = r.style === FILTER;
    $("vs-wrap").title = r.style === FILTER ? "Pick an AI style to compare it with the filter." : "";
    updateVs();
    renderHistory();
  }

  /* Intensity and color pop re-blend the cached model output, so they update live. */
  function tuned() {
    $("intensity-out").textContent = `${$("intensity").value}%`;
    $("intensity").style.setProperty("--fill", `${$("intensity").value}%`);
    clearTimeout(retune);
    if (!result || job || compareJob || result.photo !== photo || result.style !== style()) return;
    retune = setTimeout(async () => {
      const target = result;
      const mine = (job = new AbortController());
      const opts = options();
      const ba = $("stage").querySelector(".ba");
      ba?.classList.add("busy");
      try {
        const data = await cartoonize(target.photo.file, { style: target.style, ...opts, signal: mine.signal });
        if (job !== mine) return;
        Object.assign(target, opts, { data });
        if (result === target) {
          ba?.setAfter(data.image);
          renderMetrics($("metrics"), data.metrics);
          updateVs();
        }
        renderHistory();
      } catch (e) {
        if (!isAbort(e)) fail(e.message);
      } finally {
        ba?.classList.remove("busy");
        if (job === mine) {
          job = null;
          const now = options();
          if (now.intensity !== opts.intensity || now.pop !== opts.pop) tuned(); // moved again meanwhile
        }
      }
    }, 220);
  }
  $("intensity").addEventListener("input", tuned);
  $("pop").addEventListener("change", tuned);

  /* ---------- AI vs filter ---------- */
  async function updateVs() {
    const r = result;
    const on = $("vs").checked && r && r.style !== FILTER;
    $("vs-panel").hidden = !on;
    const mine = ++vsToken;
    if (!on) return;
    const { data } = r;
    const side = (src, title, m) => el("figure", {},
      el("img", { src, alt: title }),
      el("figcaption", {}, title, el("span", { class: "mono" },
        `SSIM ${m.ssim.toFixed(3)} / HIST ${m.hist_shift.toFixed(3)} / EDGE ${signed(m.edge_density_change_pct)} / ${Math.round(m.inference_ms)} ms`)));
    const ai = side(data.image, `${data.style.name} (AI)`, data.metrics);
    $("vs-pair").replaceChildren(ai, el("figure", {}, skeleton(data.width / data.height)));
    try {
      const f = await cartoonize(r.photo.file, {
        style: FILTER, intensity: r.intensity, pop: r.pop, maxSide: Math.max(data.width, data.height),
      });
      if (mine === vsToken) $("vs-pair").replaceChildren(ai, side(f.image, f.style.name, f.metrics));
    } catch (e) {
      if (mine === vsToken) $("vs-pair").replaceChildren(ai, el("p", { class: "error" }, e.message));
    }
  }
  $("vs").addEventListener("change", updateVs);

  /* ---------- download ---------- */
  $("download").addEventListener("click", async () => {
    if (!result) return;
    const blob = await (await fetch(result.data.image)).blob();
    const url = URL.createObjectURL(blob);
    el("a", { href: url, download: `vivid-${result.style.replaceAll("_", "-")}.png` }).click();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
  });

  /* ---------- session history ---------- */
  function addToHistory(r) {
    r.n = ++shot;
    history = [r, ...history].slice(0, HISTORY_MAX);
    show(r);
  }
  function renderHistory() {
    $("history").hidden = !history.length;
    $("history-strip").replaceChildren(...history.map((r) =>
      el("button", {
        type: "button",
        "aria-current": r === result && "true",
        "aria-label": `Frame ${r.n}: ${r.data.style.name}`,
        onclick: () => { reload(r); },
      },
        el("span", { class: "fr" }, el("span", {}, "VIVID 400"), el("span", {}, `${pad(r.n)} ▸ ${r.n}A`)),
        el("img", { src: r.data.image, alt: "" }),
        el("span", { class: "fr" }, r.data.style.name))));
  }
  function reload(r) {
    job?.abort();
    job = null;
    stopCompare();
    $("compare").hidden = true;
    photo = r.photo;
    // The photo's preview URL may have been released when a newer photo replaced it.
    URL.revokeObjectURL(photo.url);
    photo.url = URL.createObjectURL(photo.file);
    $("preview").src = photo.url;
    selectStyle(r.style);
    $("intensity").value = r.intensity;
    $("pop").checked = r.pop;
    $("intensity-out").textContent = `${r.intensity}%`;
    $("intensity").style.setProperty("--fill", `${r.intensity}%`);
    show(r);
    scrollToEl($("results"));
  }

  /* ---------- compare all ---------- */
  function stopCompare() {
    compareJob?.abort();
    compareJob = null;
  }
  async function compareAll() {
    if (!photo) return fail("Add a photo first, or press Try an example.");
    fail("");
    job?.abort();
    job = null;
    stopCompare();
    const mine = (compareJob = new AbortController());
    const used = photo;
    const opts = options();
    // One request per style, so frames appear as they finish. The instant filter goes first.
    const order = styles.filter((s) => available.has(s.id)).sort((a, b) => (b.id === FILTER) - (a.id === FILTER));
    const cards = new Map(order.map((s) => [s.id, card(s)]));
    $("results").hidden = true;
    $("compare").hidden = false;
    $("cmp-stop").hidden = false;
    $("cmp-grid").style.setProperty("--ar", used.ar);
    $("cmp-grid").replaceChildren(
      el("div", { class: "card" },
        el("div", { class: "card-img" }, el("img", { src: used.url, alt: "Original" })),
        el("div", { class: "card-name" }, "Original")),
      ...[...cards.values()].map((c) => c.node));
    let done = 0;
    const progress = (text) => { $("cmp-progress").textContent = text ?? `${pad(done)} / ${pad(order.length)} developed, ${COMPARE_SIDE} px`; };
    progress();
    scrollToEl($("compare"));

    for (const s of order) {
      const c = cards.get(s.id);
      c.working();
      try {
        const data = await cartoonize(used.file, { style: s.id, ...opts, maxSide: COMPARE_SIDE, signal: mine.signal });
        done++;
        c.ready(data, () => addFromCompare(used, s.id, opts, data));
        progress();
      } catch (e) {
        if (isAbort(e)) break;
        c.failed(e.message);
      }
    }
    if (compareJob !== mine && !mine.signal.aborted) return;
    if (mine.signal.aborted) {
      for (const c of cards.values()) c.stopped();
      progress(`Stopped at ${pad(done)} / ${pad(order.length)}`);
    } else {
      compareJob = null;
      progress(done === order.length ? `${pad(done)} / ${pad(done)} developed. Click a frame to open it.` : `${pad(done)} / ${pad(order.length)} developed`);
    }
    $("cmp-stop").hidden = true;
  }

  function addFromCompare(used, styleId, opts, data) {
    stopCompare();
    photo = used;
    selectStyle(styleId);
    addToHistory({ photo: used, style: styleId, ...opts, data });
    scrollToEl($("results"));
  }

  function card(s) {
    const img = el("div", { class: "card-img waiting" }, el("span", { class: "mono" }, "Waiting"));
    const meta = el("span", { class: "mono" }, "");
    const more = el("span", { class: "mono card-meta" }, s.family);
    let node = el("div", { class: "card" }, img, el("div", { class: "card-name" }, el("span", {}, s.name), meta), more);
    let finished = false;
    const message = (text) => { img.className = "card-img waiting"; img.replaceChildren(el("span", { class: "mono" }, text)); };
    return {
      node,
      working() { img.className = "card-img"; img.replaceChildren(skeleton(1)); },
      ready(data, onclick) {
        finished = true;
        img.className = "card-img";
        img.replaceChildren(el("img", { src: data.image, alt: s.name }));
        meta.textContent = `${Math.round(data.metrics.inference_ms).toLocaleString("en")} ms`;
        more.textContent = `SSIM ${data.metrics.ssim.toFixed(2)} / HIST ${data.metrics.hist_shift.toFixed(2)} / EDGE ${signed(data.metrics.edge_density_change_pct)}`;
        const button = el("button", { class: "card", type: "button", onclick }, ...node.childNodes);
        node.replaceWith(button);
        node = button;
      },
      failed(text) { finished = true; message(text); },
      stopped() { if (!finished) message("Not developed"); },
    };
  }

  /* ---------- buttons ---------- */
  $("form").addEventListener("submit", (e) => { e.preventDefault(); run(); });
  $("compare-btn").addEventListener("click", compareAll);
  $("cmp-stop").addEventListener("click", stopCompare);

  async function loadExample(id) {
    examples ??= await getJSON("/api/examples");
    const found = examples.findIndex((x) => x.id === id);
    const example = examples[found >= 0 ? found : exampleIndex++ % examples.length];
    return setPhoto(await fetchExample(example));
  }
  $("example").addEventListener("click", async () => {
    try {
      if (await loadExample()) run();
    } catch (e) {
      fail(e.message);
    }
  });

  /** From the Q&A section: make sure the AI-vs-Filter panel ends up on screen. */
  async function demoVsFilter() {
    try {
      if (!photo && !(await loadExample("sample_landscape"))) return;
      if (style() === FILTER) selectStyle(DEFAULT_STYLE);
      $("vs").disabled = false;
      $("vs").checked = true;
      if (result && result.photo === photo && result.style === style()) {
        $("compare").hidden = true;
        show(result);
        scrollToEl($("vs-panel"));
      } else {
        await run();
        if (!$("vs-panel").hidden) scrollToEl($("vs-panel"));
      }
    } catch (e) {
      fail(e.message);
    }
  }

  return { selectStyle, setAvailable, demoVsFilter };
}
