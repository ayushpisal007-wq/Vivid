/** Where the API lives. On Vercel only the pages are hosted, so the API is on Render; locally it's the same server. */
const RENDER_API = "https://vivid-gan-api.onrender.com";

export const REMOTE = location.hostname.endsWith(".vercel.app");
export const API = REMOTE ? RENDER_API : "";
