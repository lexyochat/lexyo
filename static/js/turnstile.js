// =====================================================
//   TURNSTILE.JS — Lexyo Clean Module
//   Cloudflare Turnstile (Invisible)
//   NO side effects — safe ES module
// =====================================================

// Stocke le token reçu par la callback définie dans index.html
window.turnstileToken = null;

// Attendre que turnstile soit disponible
function waitForTurnstile() {
  return new Promise((resolve, reject) => {
    let tries = 0;
    const interval = setInterval(() => {
      if (window.turnstile && typeof window.turnstile.reset === "function") {
        clearInterval(interval);
        resolve();
      }
      if (tries++ > 50) {
        clearInterval(interval);
        reject("Turnstile not loaded");
      }
    }, 100);
  });
}

// Déclencher un défi propre (reset + execute)
export async function runTurnstile() {
  await waitForTurnstile();

  window.turnstileToken = null;

  try {
    window.turnstile.reset(".cf-turnstile");
    window.turnstile.execute(".cf-turnstile");
  } catch (err) {
    return Promise.reject("Turnstile execution error");
  }

  return new Promise((resolve, reject) => {
    let tries = 0;
    const interval = setInterval(() => {
      if (window.turnstileToken) {
        clearInterval(interval);
        resolve(window.turnstileToken);
      }
      if (tries++ > 50) {
        clearInterval(interval);
        reject("Turnstile timeout");
      }
    }, 100);
  });
}
