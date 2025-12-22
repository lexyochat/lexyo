// =====================================================
//   TURNSTILE.JS — Lexyo Clean Module (PROD)
//   Cloudflare Turnstile (Invisible)
//   One-shot token, socket-safe
// =====================================================

let widgetId = null;
let pendingResolvers = [];
let timeoutHandle = null;

/**
 * Internal success callback called by Cloudflare
 */
window.onTurnstileSuccess = function (token) {
    if (!token) return;

    const resolvers = [...pendingResolvers];
    pendingResolvers = [];

    resolvers.forEach(resolve => resolve(token));

    if (timeoutHandle) {
        clearTimeout(timeoutHandle);
        timeoutHandle = null;
    }
};

/**
 * Ensure Turnstile widget exists and is executed
 */
function ensureTurnstile() {
    if (widgetId === null) {
        widgetId = turnstile.render("#turnstile", {
            sitekey: TURNSTILE_SITE_KEY,
            callback: window.onTurnstileSuccess,
            "error-callback": resetTurnstile,
            "expired-callback": resetTurnstile
        });
    }

    turnstile.reset(widgetId);
    turnstile.execute(widgetId);
}

/**
 * Reset internal state and force a fresh token
 */
function resetTurnstile() {
    pendingResolvers = [];

    if (timeoutHandle) {
        clearTimeout(timeoutHandle);
        timeoutHandle = null;
    }

    if (widgetId !== null) {
        turnstile.reset(widgetId);
    }
}

/**
 * Public API
 * Returns a Promise that resolves with a FRESH Turnstile token
 */
export function runTurnstile() {
    return new Promise((resolve, reject) => {
        pendingResolvers.push(resolve);

        timeoutHandle = setTimeout(() => {
            pendingResolvers = [];
            timeoutHandle = null;
            reject("turnstile_timeout");
        }, 8000);

        ensureTurnstile();
    });
}
