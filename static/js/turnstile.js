// =====================================================
//   TURNSTILE.JS — Lexyo Clean Module
//   Cloudflare Turnstile (Invisible)
//   NO side effects — safe ES module
// =====================================================

let resolvers = [];
let timer = null;

window.onTurnstileSuccess = function (token) {
  if (!token) return;

  resolvers.forEach(r => r(token));
  resolvers = [];

  if (timer) {
    clearTimeout(timer);
    timer = null;
  }
};

export function runTurnstile() {
  return new Promise((resolve, reject) => {
    timer = setTimeout(() => {
      resolvers = [];
      reject("turnstile_timeout");
    }, 8000);

    resolvers.push(token => {
      clearTimeout(timer);
      timer = null;
      resolve(token);
    });
  });
}
