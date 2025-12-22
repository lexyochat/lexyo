// =====================================================
//   SOCKETS.JS — LEXYO CLEAN PRO EDITION (2026)
//   Version CLEAN + Turnstile Invisible Integration
// =====================================================

if (!window.socket) window.socket = io();
export const socket = window.socket;

// -----------------------------------------------------
//  IMPORTS
// -----------------------------------------------------
import {
  myPseudo,
  setMyPseudo,
  setMyLang,
  userId,
  setChannelData,
  setRoomCounts,
  addJoinedRoom,
  joinedRooms,
  channelData,
  roomCounts,
  currentRoom,
  getMpPeer, // ✅ MP-02: resolve peer for @mp_<hash>
  cleanupMpRoom,
} from "./state.js";

import {
  pseudoInput,
  langSelect,
  enterBtn,
  errorBox,
  loginDiv,
  appDiv,
  channelListEl,
  userListEl,
  newRoomInput,
  createRoomBtn,
  msgInput,
  sendBtn,
} from "./dom.js";

import { renderTabs, switchTo, startTabBlink } from "./tabs.js";

import {
  appendLocalMessage,
  appendSystemMessage,
  appendActionMessage,
  appendCodeMessage,
  handleIncomingMessage,
  loadRoomHistory,
} from "./messages.js";

import {
  handleMpCommand,
  openPrivateConversation,
  onOpenPrivateRoom,
} from "./mp.js";

import { runTurnstile } from "./turnstile.js";

import { formatPseudo } from "./utils.js";

// =====================================================
//   UTIL — RESET TEXTAREA
// =====================================================
function resetTextarea() {
  if (!msgInput) return;
  msgInput.value = "";
  msgInput.style.height = "36px";
}

// =====================================================
//   LOGIN (MODIFIÉ POUR TURNSTILE INVISIBLE)
// =====================================================

enterBtn.addEventListener("click", async () => {
  let pseudo = pseudoInput.value.trim();

  if (!pseudo) {
    const rand = Math.floor(1000 + Math.random() * 9000);
    pseudo = "Anonymous" + rand;
  }

  setMyPseudo(pseudo);
  setMyLang(langSelect.value);

  errorBox.style.display = "none";

  // -------------------------
  //  RUN CLOUDFLARE TURNSTILE
  // -------------------------
  let token = null;
  try {
    token = await runTurnstile();
    if (!token) throw new Error("Captcha failed");
  } catch (err) {
    errorBox.textContent = "Captcha error. Please try again.";
    errorBox.style.display = "block";
    return;
  }

  // -------------------------
  //  SEND REGISTER WITH TOKEN
  // -------------------------
  socket.emit("register", {
    pseudo,
    lang: langSelect.value,
    user_id: userId,
    captcha_token: token,
  });
});

pseudoInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") enterBtn.click();
});

socket.on("pseudo_taken", ({ msg }) => {
  errorBox.textContent = msg;
  errorBox.style.display = "block";
});

// =====================================================
//   JOINED_ROOM
// =====================================================
socket.on("joined_room", ({ color, room }) => {
  if (color && !loginDiv.classList.contains("hidden")) {
    window.myUserColor = color;

    loginDiv.classList.add("hidden");
    appDiv.classList.remove("hidden");

    const footer = document.getElementById("footer-donate");
    if (footer) footer.style.display = "none";

    msgInput.focus();
  }

  if (room) {
    if (!joinedRooms.includes(room)) addJoinedRoom(room);
    switchTo(room);
    renderTabs();
  }
});

// =====================================================
//   SWITCHED_ROOM
// =====================================================
socket.on("switched_room", ({ room }) => {
  if (!joinedRooms.includes(room)) {
    // If server switches to a MP room that is no longer valid client-side,
    // do NOT keep a ghost tab.
    if (room && room.startsWith("@")) {
      cleanupMpRoom(room);
      renderTabs();
      return;
    }
    addJoinedRoom(room);
  }
  switchTo(room);
  renderTabs();
});

// =====================================================
//   USER KICKED
// =====================================================
socket.on("user_kicked", ({ room, reason }) => {
  appendSystemMessage(room, reason || "You were kicked.");

  const idx = joinedRooms.indexOf(room);
  if (idx !== -1) joinedRooms.splice(idx, 1);

  if (currentRoom === room) {
    switchTo("#general");
    socket.emit("join", { room: "#general" });
  }

  renderTabs();
});

// =====================================================
//   CHANNELS LIST + COUNTS
// =====================================================
socket.on("channel_list", ({ channels }) => {
  setChannelData(channels);
  renderChannels();
});

socket.on("room_counts", (counts) => {
  setRoomCounts(counts);
  renderChannels();
});

function renderChannels() {
  if (!channelListEl) return;

  channelListEl.innerHTML = "";
  const channels = channelData;
  const counts = roomCounts;

  channels.forEach((room) => {
    if (room.startsWith("@")) return;

    const count = counts[room] || 0;

    const li = document.createElement("li");
    li.innerHTML = `
      <div class="channel-item">
        <span class="chan-name">${room}</span>
        <span class="chan-right">
          <span class="chan-dot ${count > 0 ? "dot-green" : "dot-red"}">•</span>
          <span class="chan-count">${count}</span>
        </span>
      </div>
    `;

    li.addEventListener("click", () => socket.emit("join", { room }));
    channelListEl.appendChild(li);
  });
}

// =====================================================
//   HISTORY
// =====================================================
socket.on("room_history", ({ room, messages }) => {
  loadRoomHistory(room, messages);
});

// =====================================================
//   SYSTEM MESSAGE
// =====================================================
socket.on("system_message", ({ room, msg }) => {
  appendSystemMessage(room || "#general", msg);

  // If server indicates MP room is gone, cleanup UI deterministically
  if (
    room &&
    room.startsWith("@") &&
    typeof msg === "string" &&
    msg.toLowerCase().includes("no longer exists")
  ) {
    cleanupMpRoom(room);
    renderTabs();
    switchTo("#general");
    socket.emit("join", { room: "#general" });
  }
});

// =====================================================
//   ACTION MESSAGE /me
// =====================================================
socket.on("action_message", ({ room, author, content }) => {
  appendActionMessage(room || currentRoom, author, content);
});

// =====================================================
//   CODE MESSAGE /code
// =====================================================
socket.on("code_message", ({ room, pseudo, lang, content, timestamp }) => {
  appendCodeMessage(
    room || currentRoom,
    pseudo,
    lang,
    content,
    timestamp,
    pseudo === myPseudo
  );
});

// =====================================================
//   IDENTITY UPDATE (admin / future roles)
// =====================================================
socket.on("identity_update", (data) => {
  if (!data || !data.pseudo) return;

  console.log("[identity_update]", data);

  // Update local identity immediately (fixes /admin pseudo desync)
  setMyPseudo(data.pseudo);

  if (data.color) {
    window.myUserColor = data.color;
  }
});

// =====================================================
//   ROOM DELETED
// =====================================================
socket.on("room_deleted", ({ room }) => {
  const i = joinedRooms.indexOf(room);
  if (i !== -1) joinedRooms.splice(i, 1);

  const ci = channelData.indexOf(room);
  if (ci !== -1) channelData.splice(ci, 1);

  if (currentRoom === room) {
    switchTo("#general");
    socket.emit("join", { room: "#general" });
  }

  renderChannels();
  renderTabs();
});

// =====================================================
//   CREATE ROOM
// =====================================================
if (createRoomBtn && newRoomInput) {
  createRoomBtn.addEventListener("click", () => {
    const raw = newRoomInput.value.trim();
    if (!raw) return;

    socket.emit("create_room", { name: raw, user_id: userId });
    newRoomInput.value = "";
  });

  newRoomInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") createRoomBtn.click();
  });
}

// =====================================================
//   CREATE ROOM — ERROR HANDLER
// =====================================================
socket.on("room_create_error", ({ error }) => {
  appendSystemMessage(currentRoom, error);
  console.warn("ROOM CREATE ERROR:", error);
});

// =====================================================
//   MESSAGE SENDER
// =====================================================
sendBtn.addEventListener("click", sendMessage);

msgInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

function sendMessage() {
  if (!msgInput) return;

  const raw = msgInput.value;
  const msg = raw.trim();

  if (!msg) {
    resetTextarea();
    return;
  }

  const room = currentRoom || "#general";

  // ----------- /mp command -----------
  if (msg.startsWith("/mp ")) {
    handleMpCommand(msg, socket, room);
    resetTextarea();
    return;
  }

  // ----------- PRIVATE ROOM (@xxx) -----------
  if (room.startsWith("@")) {
    // ✅ MP-02 FIX: resolve target from map (set by mp.js on open_private_room)
    const target = getMpPeer(room);

    if (!target) {
      appendSystemMessage(room, "This private conversation is no longer available.");
      cleanupMpRoom(room);
      renderTabs();
      switchTo("#general");
      socket.emit("join", { room: "#general" });
      resetTextarea();
      return;
    }

    // IMPORTANT:
    // On n'append plus localement ici (sinon doublons),
    // car messages.js affiche maintenant aussi les MP émis
    // via receive_message.
    socket.emit("private_message", { to: target, msg });

    resetTextarea();
    return;
  }

  // ----------- PUBLIC ROOM -----------
  appendLocalMessage(room, myPseudo, msg, true, msg, msg);
  socket.emit("send_message", { msg });

  resetTextarea();
}

// =====================================================
//   INCOMING MESSAGE
// =====================================================
socket.on("receive_message", (data) => handleIncomingMessage(data));

// =====================================================
//   PRIVATE ROOM (receiver side)
// =====================================================
socket.on("open_private_room", (data) => {
  onOpenPrivateRoom(data, socket, startTabBlink);
});

// =====================================================
//   ROOM USERS
// =====================================================
socket.on("room_users", ({ room, users }) => {
  // ---------------------------------------------------
  //  SYNC myPseudo AFTER SERVER-SIDE IDENTITY CHANGE
  //  Example: /admin -> pseudo becomes "Lexyo"
  //  We key off userId (stable), NOT pseudo (mutable).
  // ---------------------------------------------------
  try {
    const me = users.find((u) => u.user_id === userId);
    if (me && me.pseudo && me.pseudo !== myPseudo) {
      console.log("[sync] myPseudo updated:", myPseudo, "→", me.pseudo);
      setMyPseudo(me.pseudo);
    }
  } catch (e) {
    // no-op, do not break rendering
  }

  if (room !== currentRoom) return;

  userListEl.innerHTML = "";

  users.forEach((u) => {
    const li = document.createElement("li");
    li.classList.add("user-item");

    if (u.pseudo === myPseudo) {
      window.myUserColor = u.color || null;
      window.myIsAdmin = u.is_admin === true;
      window.myIsMod = u.is_mod === true;
    }

    li.innerHTML = `
      <span class="pseudo" style="color:${u.color || "inherit"}">
        ${formatPseudo(u.pseudo, u.is_admin, u.is_mod)}
      </span>

      <span class="lang-badge">[${u.lang.toUpperCase()}]</span>
    `;

    li.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (u.pseudo === myPseudo) return;
      openPrivateConversation(socket, u.pseudo);
    });

    userListEl.appendChild(li);
  });
});

// =====================================================
//   FORCE DISCONNECT (Kick / Ban / Perma)
// =====================================================
socket.on("force_disconnect", (data) => {
  console.log("Disconnected by server:", data);

  const reason = data?.reason || "disconnected";

  // Petit message propre
  let message = "";
  if (reason === "spam_kick") message = "You were kicked for spam.";
  else if (reason === "spam_ban") message = "You were banned for 10 minutes (spam).";
  else if (reason === "spam_perma") message = "You were permanently banned for spam.";
  else message = "You were disconnected by the server.";

  alert(message);

  // Déconnexion socket propre
  socket.disconnect();

  // Reset interface
  document.getElementById("app").classList.add("hidden");
  document.getElementById("login").classList.remove("hidden");

  // Optionnel: reset textarea et autres
  if (msgInput) {
    msgInput.value = "";
    msgInput.style.height = "36px";
  }
});
