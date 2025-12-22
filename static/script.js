// =====================================================
//   SCRIPT.JS — Lexyo PROD STABLE
// =====================================================

import "./js/state.js";
import "./js/dom.js";
import "./js/utils.js";
import "./js/media.js";
import "./js/tabs.js";
import "./js/messages.js";
import "./js/mp.js";
import { runTurnstile } from "./js/turnstile.js";
import { createMediaObserver } from "./js/media.js";
import { messagesEl } from "./js/dom.js";

createMediaObserver(messagesEl);

// =====================================================
//   AUTO-RESIZE TEXTAREA MESSAGE
// =====================================================
const msgField = document.getElementById("message");

if (msgField) {
    msgField.addEventListener("input", () => {
        if (!msgField.value.trim()) {
            msgField.style.height = "36px";
            return;
        }
        msgField.style.height = "auto";
        msgField.style.height = msgField.scrollHeight + "px";
    });
}

// =====================================================
//   TURNSTILE SOCKET EMIT WRAPPER (GLOBAL)
// =====================================================

/**
 * Emit a socket event protected by a fresh Turnstile token.
 * Usage:
 *   emitWithCaptcha(socket, "set_pseudo", { pseudo })
 */
window.emitWithCaptcha = function (socket, event, payload = {}) {
    runTurnstile()
        .then(token => {
            socket.emit(event, {
                ...payload,
                captcha: token
            });
        })
        .catch(() => {
            // silent fail, retry will trigger a new token
        });
};
