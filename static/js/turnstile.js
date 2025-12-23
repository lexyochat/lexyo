// =====================================================
//   TURNSTILE.JS — Lexyo Clean Module (PATCHED)
//   Cloudflare Turnstile (Invisible, Explicit Render)
//   Stable with ES modules, no race condition
// =====================================================

let resolvers = [];
let timer = null;
let widgetId = null;

// -----------------------------------------------------
// Global callback required by Cloudflare Turnstile
// -----------------------------------------------------
if (!window.onTurnstileSuccess) {
  window.onTurnstileSuccess = function (token) {
    if (!token) return;

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
    resolvers.push(resolve);

    timer = setTimeout(() => {
      resolvers = [];
      reject("turnstile_timeout");
    }, 8000);

    executeTurnstile();
  });
}
