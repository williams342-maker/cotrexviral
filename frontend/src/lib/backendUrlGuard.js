/* ------------------------------------------------------------------
   Backend URL safety guard
   ------------------------------------------------------------------

   Detects the "I deployed to a custom domain but `REACT_APP_BACKEND_URL`
   is still pointing at the preview environment" failure mode — the
   exact bug that took cortexviral.com login down. Two protections:

   1. **Visible loud banner** at the top of the viewport so the bug
      surfaces in seconds, not after user reports.
   2. **Auto-rewrite axios requests** that match a known-bad host so
      the app keeps functioning while the deploy env is fixed.

   Heuristics intentionally conservative:
   - Only fires when the page origin is a "real production" domain
     (custom domain or *.emergent.host) AND the env URL is a preview.
   - Rewrites only target the preview backend host → page origin
     (same-origin assumption). For multi-service prod splits we'd need
     a smarter rule, but the platform default is same-origin.

   This file has zero React deps so it can run before React mounts.
   ------------------------------------------------------------------ */

import axios from "axios";

const PREVIEW_HOST_RE = /\.preview\.emergentagent\.com$/i;
const DEV_HOST_RE     = /^(localhost|127\.0\.0\.1)$/i;

function isPreviewUrl(url) {
  try {
    return PREVIEW_HOST_RE.test(new URL(url).hostname);
  } catch {
    return false;
  }
}

function isLikelyProductionOrigin(originHost) {
  // Localhost / dev → no guard. Preview-domain page → no guard
  // (it's correctly using a preview backend). Anything else =
  // production (a custom domain, *.emergent.host, etc.).
  if (DEV_HOST_RE.test(originHost)) return false;
  if (PREVIEW_HOST_RE.test(originHost)) return false;
  return true;
}

function showBanner(message) {
  if (typeof document === "undefined") return;
  if (document.getElementById("cv-backend-url-mismatch-banner")) return;
  const el = document.createElement("div");
  el.id = "cv-backend-url-mismatch-banner";
  el.setAttribute("role", "alert");
  el.style.cssText = `
    position: fixed; top: 0; left: 0; right: 0; z-index: 2147483647;
    padding: 10px 16px; background: #b91c1c; color: #fff;
    font: 600 13px/1.4 -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, sans-serif;
    text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.3);
    letter-spacing: 0.01em;
  `;
  el.textContent = message;
  // If body isn't ready yet (script runs in <head>), wait one tick.
  if (document.body) document.body.appendChild(el);
  else document.addEventListener("DOMContentLoaded", () => document.body.appendChild(el));
}

export function installBackendUrlGuard() {
  // CRA inlines this at build time, so we read it once.
  const envUrl = process.env.REACT_APP_BACKEND_URL || "";
  if (typeof window === "undefined") return;
  const pageOrigin     = window.location.origin;
  const pageHost       = window.location.hostname;

  // Only act on a real preview-vs-prod mismatch.
  if (!isLikelyProductionOrigin(pageHost)) return;
  if (!isPreviewUrl(envUrl))               return;

  // Same-origin fallback: rewrite all preview-host requests → page origin.
  const badHost = new URL(envUrl).host;
  const fallbackOrigin = pageOrigin;

  axios.interceptors.request.use((config) => {
    try {
      const url = config.url || "";
      if (url.includes(badHost)) {
        config.url = url.split(badHost).join(new URL(fallbackOrigin).host);
        // Re-anchor protocol too if needed.
        const u = new URL(config.url, fallbackOrigin);
        config.url = u.toString();
      }
      if (config.baseURL && config.baseURL.includes(badHost)) {
        config.baseURL = fallbackOrigin;
      }
    } catch (_e) { /* never block a request from the guard */ }
    return config;
  });

  // eslint-disable-next-line no-console
  console.error(
    `[CortexViral] REACT_APP_BACKEND_URL is pointing at a preview environment ` +
    `(${envUrl}) but the page is loaded from ${pageOrigin}. ` +
    `API requests will be auto-rewritten to ${fallbackOrigin} to keep the app ` +
    `working — but you must update the Emergent deploy variable ` +
    `REACT_APP_BACKEND_URL to fix this permanently.`
  );

  showBanner(
    `Misconfigured deploy: REACT_APP_BACKEND_URL points to a preview server. ` +
    `Set it to ${pageOrigin} in your Emergent deploy variables, then redeploy.`
  );
}
