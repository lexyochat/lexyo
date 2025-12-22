// =====================================================
//   MODULE 7 — MESSAGES.JS (CLEAN 2026 EDITION)
//   Gestion complète des messages (public, privé, action, système, code)
//   Version synchronisée avec utils.js (scroll intelligent + forced scroll)
// =====================================================

import {
  myPseudo,
  roomMessages,
  currentRoom,
  ensureRoomArray,
  joinedRooms,
  addJoinedRoom,
  setMpPeer,            // 🔥 MP-02J
} from "./state.js";

import { messagesEl } from "./dom.js";

import {
  renderHTMLMessage,
  scrollToBottom,
  updateScrollState,
  forceScrollToBottom,
  escapeHTML as escapeHTMLSafe,
} from "./utils.js";

import { initMediaLoadFix } from "./media.js";
import { startTabBlink, renderTabs } from "./tabs.js";


// =====================================================
//   HELPERS INTERNES
// =====================================================

function _legacyEscapeHTML(str = "") {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function renderCodeHTML(pseudo, lang, content, timestamp = null, isSelf = false) {
  const ts = timestamp || Math.floor(Date.now() / 1000);
  const d = new Date(ts * 1000);

  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  const time = `[${hh}:${mm}]`;

  const safeCode = escapeHTMLSafe(content || "");
  const safeLang = (lang || "txt").toLowerCase();

  return `
    <div class="msg msg-code ${isSelf ? "self" : ""}">
      <div class="msg-line">
        <span class="msg-time">${time}</span>
        <span class="msg-user">${pseudo}</span>
        <span class="msg-sep">:</span>
        <span class="msg-lang">[${safeLang}]</span>
      </div>
      <pre class="msg-code-block"><code>${safeCode}</code></pre>
    </div>
  `;
}


// =====================================================
//   ANTI-DOUBLON (PUBLIC) — buffer de messages locaux
//   But: éviter double affichage quand pseudo change côté serveur (ex admin)
//   IMPORTANT: ne s'applique PAS aux MP (isPrivate)
// =====================================================

const LOCAL_ECHO_BUFFER = [];
const LOCAL_ECHO_MAX = 25;          // nombre max d'entrées
const LOCAL_ECHO_TTL_MS = 5000;     // fenêtre de déduplication (5s)

function _nowMs() {
  return Date.now();
}

function _normalizeText(t) {
  return String(t ?? "").trim();
}

function rememberLocalEcho(room, text) {
  const entry = {
    room: room || "",
    text: _normalizeText(text),
    ts: _nowMs(),
  };

  LOCAL_ECHO_BUFFER.push(entry);

  // purge taille
  if (LOCAL_ECHO_BUFFER.length > LOCAL_ECHO_MAX) {
    LOCAL_ECHO_BUFFER.splice(0, LOCAL_ECHO_BUFFER.length - LOCAL_ECHO_MAX);
  }

  // purge TTL
  const cutoff = _nowMs() - LOCAL_ECHO_TTL_MS;
  while (LOCAL_ECHO_BUFFER.length && LOCAL_ECHO_BUFFER[0].ts < cutoff) {
    LOCAL_ECHO_BUFFER.shift();
  }
}

function isServerEchoDuplicate(room, data) {
  const r = room || "";
  const incomingText = _normalizeText(data?.original ?? data?.translated ?? "");

  if (!incomingText) return false;

  const cutoff = _nowMs() - LOCAL_ECHO_TTL_MS;

  // purge TTL avant check
  while (LOCAL_ECHO_BUFFER.length && LOCAL_ECHO_BUFFER[0].ts < cutoff) {
    LOCAL_ECHO_BUFFER.shift();
  }

  // On cherche un match exact room + texte dans la fenêtre TTL
  for (let i = LOCAL_ECHO_BUFFER.length - 1; i >= 0; i--) {
    const e = LOCAL_ECHO_BUFFER[i];
    if (e.room === r && e.text === incomingText) {
      // Consomme l'entrée (évite de bloquer un second msg identique)
      LOCAL_ECHO_BUFFER.splice(i, 1);
      return true;
    }
  }

  return false;
}


// =====================================================
//   INIT SCROLL TRACKING
// =====================================================

if (messagesEl) {
  messagesEl.addEventListener("scroll", () => updateScrollState(messagesEl));
}


// =====================================================
//   MESSAGE SELF (PUBLIC UNIQUEMENT)
// =====================================================

export function appendLocalMessage(
  room,
  pseudo,
  text,
  isSelf = false,
  original = null,
  translated = null
) {
  const shown = translated || text;
  const senderColor = pseudo === myPseudo ? window.myUserColor : null;
  const timestamp = Math.floor(Date.now() / 1000);

  // 🔥 Anti-doublon: mémoriser le message local (public)
  // On mémorise le "texte original" (celui que le serveur renvoie dans data.original)
  rememberLocalEcho(room, original ?? text);

  const html = renderHTMLMessage(
    pseudo,
    shown,
    original ?? text,
    senderColor,
    timestamp,
    isSelf,
    window.myIsAdmin === true,
    window.myIsMod === true
  );

  const arr = ensureRoomArray(room);
  arr.push(html);

  if (room === currentRoom) {
    messagesEl.insertAdjacentHTML("beforeend", html);
    scrollToBottom(messagesEl);
    initMediaLoadFix(messagesEl);
  }
}


// =====================================================
//   MESSAGE SYSTEM
// =====================================================

export function appendSystemMessage(room, msg) {
  const div = document.createElement("div");
  div.className = "system";
  div.textContent = msg;

  const html = div.outerHTML;
  const arr = ensureRoomArray(room);
  arr.push(html);

  if (room === currentRoom) {
    messagesEl.insertAdjacentHTML("beforeend", html);
    scrollToBottom(messagesEl);
  }
}


// =====================================================
//   MESSAGE ACTION (/me)
// =====================================================

export function appendActionMessage(room, author, content) {
  const div = document.createElement("div");
  div.className = "msg-action";
  div.textContent = `* ${author} ${content}`;

  const html = div.outerHTML;
  const arr = ensureRoomArray(room);
  arr.push(html);

  if (room === currentRoom) {
    messagesEl.insertAdjacentHTML("beforeend", html);
    scrollToBottom(messagesEl);
  }
}


// =====================================================
//   MESSAGE CODE (/code) — PATCH SCROLL FINAL
// =====================================================

export function appendCodeMessage(
  room,
  pseudo,
  lang,
  content,
  timestamp = null,
  isSelf = false
) {
  const html = renderCodeHTML(pseudo, lang, content, timestamp, isSelf);

  const arr = ensureRoomArray(room);
  arr.push(html);

  if (room === currentRoom) {
    messagesEl.insertAdjacentHTML("beforeend", html);

    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        forceScrollToBottom(messagesEl);
      });
    });
  }
}


// =====================================================
//   MESSAGE INCOMING (PUBLIC + MP)
// =====================================================

export function handleIncomingMessage(data) {
  const room = data.room || currentRoom || "#general";

  const isPrivate =
    data.is_private === true || (room && room.startsWith("@"));

  // 🔥 MP-02J:
  // Enregistrer le peer côté receiver si MP
  if (isPrivate && data.with && room) {
    setMpPeer(room, data.with);
  }

  // MP-02G:
  // Ne JAMAIS ignorer un message privé même si on est l'émetteur.
  // MAIS pour les salons publics, on dédoublonne via buffer local.
  if (!isPrivate) {
    // 1) ancien garde-fou (utile quand pseudo synchro)
    if (data.pseudo === myPseudo) return;

    // 2) nouveau garde-fou robuste (utile quand pseudo change côté serveur, ex admin)
    if (isServerEchoDuplicate(room, data)) return;
  }

  if (isPrivate) {
    if (!joinedRooms.includes(room)) addJoinedRoom(room);

    renderTabs();

    if (room !== currentRoom) {
      startTabBlink(room);
    }
  }

  const html = renderHTMLMessage(
    data.pseudo,
    data.translated,
    data.original,
    data.color,
    data.timestamp,
    false,
    data.is_admin === true,
    data.is_mod === true
  );

  const arr = ensureRoomArray(room);
  arr.push(html);

  if (room === currentRoom) {
    messagesEl.insertAdjacentHTML("beforeend", html);
    scrollToBottom(messagesEl);
    initMediaLoadFix(messagesEl);
  }

  renderTabs();
}


// =====================================================
//   HISTORIQUE
// =====================================================

export function loadRoomHistory(room, messages) {
  const list = messages.map((m) => {
    const type = m.type || "text";

    if (type === "action") {
      const div = document.createElement("div");
      div.className = "msg-action";
      div.textContent = `* ${m.pseudo || "Anonymous"} ${m.content || ""}`;
      return div.outerHTML;
    }

    if (type === "code") {
      return renderCodeHTML(
        m.pseudo || "Anonymous",
        m.lang || "txt",
        m.content || "",
        m.timestamp,
        false
      );
    }

    return renderHTMLMessage(
      m.pseudo,
      m.translated,
      m.original,
      m.color,
      m.timestamp,
      false,
      m.is_admin === true,
      m.is_mod === true
    );
  });

  roomMessages[room] = list;

  if (room === currentRoom) {
    messagesEl.innerHTML = list.join("");
    scrollToBottom(messagesEl);
    initMediaLoadFix(messagesEl);
  }
}
