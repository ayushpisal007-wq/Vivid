async function request(url, options) {
  let response;
  try {
    response = await fetch(url, options);
  } catch (e) {
    if (e.name === "AbortError") throw e;
    throw new Error("Can't reach the Vivid server. Check that it's running, then try again.");
  }
  let body = null;
  try {
    body = await response.json();
  } catch (e) {
    if (e.name === "AbortError") throw e;
  }
  if (!response.ok) throw new Error(body?.detail ?? "Something went wrong. Please try again.");
  if (!body) throw new Error("The server sent an answer we couldn't read. Please try again.");
  return body;
}

export const getJSON = (url) => request(url);

export function cartoonize(file, { style, intensity = 100, pop = false, maxSide, signal }) {
  const form = new FormData();
  form.append("image", file, file.name || "photo.jpg");
  form.append("style", style);
  form.append("intensity", intensity);
  form.append("color_pop", pop);
  if (maxSide) form.append("max_side", maxSide);
  return request("/api/cartoonize", { method: "POST", body: form, signal });
}

export async function fetchExample(example) {
  const response = await fetch(example.url).catch(() => null);
  if (!response?.ok) throw new Error("That example couldn't be loaded.");
  const blob = await response.blob();
  return new File([blob], example.url.split("/").pop(), { type: blob.type || "image/jpeg" });
}
