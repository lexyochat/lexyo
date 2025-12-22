// =====================================================
//   MODULE 5 — TABS.JS (CLEAN PRODUCTION — ENGLISH)
//   Tab rendering + room switching system (+ MP sync)
//   MP-03: MP tabs have UI labels + can be closed (UI only)
// =====================================================

import {
  currentRoom,
  setCurrentRoom,
  joinedRooms,
  roomMessages,
  myPseudo,
  getMpPeer,
} from "./state.js";

import {
  tabsEl,
  roomTitleEl,
  messagesEl,
  msgInput,
} from "./dom.js";

import { scrollToBottom } from "./utils.js";
import { initMediaLoadFix } from "./media.js";
import { socket } from "./sockets.js";


// =====================================================
//   RENDER ALL TABS
// =====================================================

export function renderTabs() {
  if (!tabsEl) return;

  tabsEl.innerHTML = "";

  joinedRooms.forEach((roomName) => {
    const tab = document.createElement("button");
    tab.dataset.room = roomName;

    // ---------------------------------
    // Label (UI)
    // ---------------------------------
    let label = roomName;

    if (roomName.startsWith("@mp_")) {
      const peer = getMpPeer(roomName);
      if (peer) {
        label = `@${myPseudo}_${peer}`;
      }
    }

    // ---------------------------------
    // Inner HTML
    // ---------------------------------
    if (roomName === "#general") {
      tab.textContent = label;
    } else {
      tab.innerHTML = `
        ${label}
        <span class="tab-close" data-room="${roomName}">&times;</span>
      `;
    }

    tab.className = "tab" + (roomName === currentRoom ? " active" : "");

    // =================================================
    // CLICK → SWITCH ROOM
    // =================================================
    tab.addEventListener("click", () => {
      tab.classList.remove("blink");

      if (roomName === currentRoom) return;

      if (roomName.startsWith("@")) {
        switchTo(roomName);
        return;
      }

      switchTo(roomName);
      socket.emit("join", { room: roomName });
    });

    // =================================================
    // CLOSE BUTTON (UI ONLY)
    // =================================================
    const closeBtn = tab.querySelector(".tab-close");

    if (closeBtn) {
      if (roomName === "#general") {
        closeBtn.style.display = "none";
      } else {
        closeBtn.addEventListener("click", (e) => {
          e.stopPropagation();

          const roomToClose = closeBtn.dataset.room;
          const idx = joinedRooms.indexOf(roomToClose);

          if (idx !== -1) {
            joinedRooms.splice(idx, 1);
          }

          if (currentRoom === roomToClose) {
            switchTo("#general");
            socket.emit("join", { room: "#general" });
          } else {
            renderTabs();
          }
        });
      }
    }

    tabsEl.appendChild(tab);
  });
}


// =====================================================
//   BLINKING TABS (Unread notifications)
// =====================================================

export function startTabBlink(room) {
  setTimeout(() => {
    const tabs = document.querySelectorAll(".tab");
    tabs.forEach((t) => {
      if (t.dataset.room === room) {
        t.classList.add("blink");
      }
    });
  }, 80);
}


// =====================================================
//   SWITCH ROOM (UI + sync serveur pour MP)
// =====================================================

export function switchTo(room) {
  setCurrentRoom(room);

  if (roomTitleEl) {
    roomTitleEl.textContent = room;
  }

  if (msgInput) {
    msgInput.placeholder = room.startsWith("@")
      ? "Write a private message..."
      : `Write a message to ${room}...`;
  }

  const list = roomMessages[room] || [];
  messagesEl.innerHTML = list.join("");

  // ---------------------------------
  // Initial scroll (logical)
  // ---------------------------------
  scrollToBottom(messagesEl);

  // Init media load fix (images / videos)
  initMediaLoadFix(messagesEl);

  // ---------------------------------
  // 🔒 FINAL SAFETY SCROLL
  // Ensures scroll is at bottom AFTER:
  // - DOM paint
  // - images / embeds layout
  // ---------------------------------
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      messagesEl.scrollTop = messagesEl.scrollHeight;
    });
  });

  // Notify server ONLY for private rooms
  if (room.startsWith("@")) {
    socket.emit("switch_private", { room });
  }

  renderTabs();
}
