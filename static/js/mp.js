// =====================================================
//   MODULE 6 — MP.JS (CLEAN PRODUCTION 2026)
//   Private messages: /mp command, user click, receiver
//   Version ALIGNÉE MP-02 (backend authoritative)
// =====================================================

import {
  myPseudo,
  addJoinedRoom,
  joinedRooms,
  currentRoom,
  setMpPeer,          // 🔥 NOUVEAU
} from "./state.js";

import { switchTo, renderTabs } from "./tabs.js";
import { appendSystemMessage } from "./messages.js";


// =====================================================
//   /mp username message
// =====================================================
export function handleMpCommand(cmd, socket, currentRoomValue) {
  const parts = cmd.trim().split(" ");
  if (parts.length < 3) {
    appendSystemMessage(
      currentRoomValue || "#general",
      "Usage: /mp username message"
    );
    return;
  }

  const target = parts[1];
  const text = cmd.slice(cmd.indexOf(target) + target.length).trim();

  if (!target || !text) return;

  // MP-02:
  // - Le frontend NE crée JAMAIS la room
  // - Le serveur est la seule source de vérité
  socket.emit("open_private", { with: target });
  socket.emit("private_message", { to: target, msg: text });
}


// =====================================================
//   Open MP from sidebar user click
// =====================================================
export function openPrivateConversation(socket, targetPseudo) {
  if (!targetPseudo || targetPseudo === myPseudo) return;

  // MP-02:
  // - Ne pas inventer la room
  // - Le serveur renverra open_private_room
  socket.emit("open_private", { with: targetPseudo });
}


// =====================================================
//   "open_private_room" event (server authoritative)
// =====================================================
// data = { room: "@mp_xxx", with: "otherPseudo" }
export function onOpenPrivateRoom(data, socket, startTabBlink) {
  const room = data.room;
  const peer = data.with;

  if (!room) return;

  // 🔥 MP-02 FIX:
  // On enregistre le vrai destinataire associé à cette room
  if (peer) {
    setMpPeer(room, peer);
  }

  // Créer l’onglet si nécessaire
  if (!joinedRooms.includes(room)) {
    addJoinedRoom(room);
  }

  // Rendre les tabs
  renderTabs();

  // 🔥 IMPORTANT:
  // On switch TOUJOURS vers la room MP dès son ouverture,
  // même si elle est déjà active.
  // Cela garantit l’émission de "switch_private".
  switchTo(room);
}
