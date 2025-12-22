// =====================================================
//   MODULE 2 — DOM.JS (CLEAN PRODUCTION)
//   Références DOM centralisées
// =====================================================

import { formatPseudo } from "./utils.js";

// Login
export const loginDiv     = document.getElementById("login");
export const appDiv       = document.getElementById("app");
export const pseudoInput  = document.getElementById("pseudo");
export const langSelect   = document.getElementById("lang");
export const enterBtn     = document.getElementById("enter");

// Salons
export const channelListEl = document.getElementById("channel-list");
export const tabsEl        = document.getElementById("tabs");
export const roomTitleEl   = document.getElementById("room-title");
export const messagesEl    = document.getElementById("messages");
export const userListEl    = document.getElementById("user-list");

// Message input
export const msgInput  = document.getElementById("message");
export const sendBtn   = document.getElementById("send");
export const errorBox  = document.getElementById("error-box");

// Create room
export const newRoomInput   = document.getElementById("new-room-name");
export const createRoomBtn  = document.getElementById("create-room-btn");

// Thème
export const themeBtn = document.getElementById("theme-toggle");


// =====================================================
//   USER LIST RENDERING (🛡️ admin / ⭐ modo)
// =====================================================

export function renderUserList(users) {
  if (!userListEl) return;

  userListEl.innerHTML = "";

  if (!Array.isArray(users)) return;

  users.forEach((u) => {
    if (!u || !u.pseudo) return;

    const div = document.createElement("div");
    div.className = "user";

    div.textContent = formatPseudo(
      u.pseudo,
      u.is_admin === true,
      u.is_mod === true
    );

    userListEl.appendChild(div);
  });
}
