// =====================================================
//   TURNSTILE.JS — Lexyo Clean Module (STABLE PROD FIX)
//   Cloudflare Turnstile Invisible — RACE CONDITION FIX
// =====================================================

let resolvers = [];
let timer = null;
let widgetId = null;

// 🔒 Stocke le dernier token reçu (évite race condition)
let lastToken = null;

// -----------------------------------------------------
// Global callback required by Cloudflare Turnstile
// -----------------------------------------------------
if (!window.onTurnstileSuccess) {
  window.onTurnstileSuccess = function (token) {
    if (!token) return;

    // Stocker le token au cas où runTurnstile n'écoute pas encore
    lastToken = token;

    const list = resolvers.slice();
    resolvers = [];

    if (timer) {
      clearTimeout(timer);
      timer = null;
    }

    list.forEach(r => r(token));
  };
}

// -----------------------------------------------------
// Ensure the invisible widget is rendered exactly once
// -----------------------------------------------------
function ensureWidget() {
  if (widgetId !== null) return;
  if (!window.turnstile) return;

  const el = document.querySelector(".cf-turnstile");
  if (!el) return;

  try {
    widgetId = window.turnstile.render(el, {
      sitekey: el.dataset.sitekey,
      callback: window.onTurnstileSuccess,
      size: "invisible"
    });
  } catch (_) {
    widgetId = null;
  }
}

// -----------------------------------------------------
// Execute Turnstile challenge
// -----------------------------------------------------
function executeTurnstile() {
  if (!window.turnstile) return;

  ensureWidget();
  if (widgetId === null) return;

  try {
    window.turnstile.reset(widgetId);
    window.turnstile.execute(widgetId);
  } catch (_) {}
}

// -----------------------------------------------------
// Public API
// -----------------------------------------------------
export function runTurnstile() {
  return new Promise((resolve, reject) => {

    // ✅ Si un token est déjà disponible, on le consomme immédiatement
    if (lastToken) {
      const token = lastToken;
      lastToken = null;
      resolve(token);
      return;
    }

    if (!window.turnstile) {
      reject("turnstile_not_loaded");
      return;
    }

    resolvers.push(resolve);

    timer = setTimeout(() => {
      resolvers = [];
      reject("turnstile_timeout");
    }, 8000);

    executeTurnstile();
  });
}
