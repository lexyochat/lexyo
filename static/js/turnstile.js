// =====================================================
//   TURNSTILE.JS — Lexyo Clean Module
//   Cloudflare Turnstile (Invisible)
//   NO side effects — safe ES module
// =====================================================

let resolvers = [];
let timer = null;

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

function executeTurnstile() {
  if (!window.turnstile) return;
  try {
    window.turnstile.reset();
    window.turnstile.execute();
  } catch (_) {}
}

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
