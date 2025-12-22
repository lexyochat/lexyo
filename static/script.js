// =====================================================
//   SCRIPT.JS — Lexyo 2026 ULTRA CLEAN EDITION
//   Turnstile Invisible Captcha (Stable, No Warnings)
// =====================================================

import "./js/state.js";
import "./js/dom.js";
import "./js/utils.js";
import "./js/media.js";
import "./js/tabs.js";
import "./js/messages.js";
import "./js/mp.js";
import "./js/turnstile.js";
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
