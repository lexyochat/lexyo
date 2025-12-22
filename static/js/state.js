// =====================================================
//   MODULE 1 — STATE.JS (CLEAN PRODUCTION)
//   États globaux & helpers simples
// =====================================================

// ----------------------------------------
// UUID utilisateur (stocké dans localStorage)
// ----------------------------------------
export function generateUUID() {
  return "xxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

let userId = localStorage.getItem("user_id");
if (!userId) {
  userId = generateUUID();
  localStorage.setItem("user_id", userId);
}
export { userId };

// ----------------------------------------
// États principaux
// ----------------------------------------
export let myPseudo = "";
export let myLang = "fr";
export let joinedRooms = [];
export let currentRoom = null;
export let roomMessages = {};    // { room: [HTML strings] }
export let roomCounts = {};
export let channelData = [];
export let userMenu = null;

// ----------------------------------------
// MP (rooms hashées @mp_<hash>)
// ----------------------------------------
// Permet de retrouver le peer (pseudo) associé à une room MP.
// Exemple: mpPeerByRoom["@mp_199974a108b9f46f"] = "test2"
export let mpPeerByRoom = {}; // { [room: string]: pseudo: string }

// Set / get MP peer
export function setMpPeer(room, pseudo) {
  if (!room || !pseudo) return;
  mpPeerByRoom[room] = pseudo;
}

export function getMpPeer(room) {
  return mpPeerByRoom[room] || null;
}

export function clearMpPeer(room) {
  if (!room) return;
  delete mpPeerByRoom[room];
}

// ----------------------------------------
// MP CLEANUP (UI SIDE — DETERMINISTIC)
// ----------------------------------------
export function cleanupMpRoom(room) {
  if (!room) return;

  // Remove from joined rooms
  joinedRooms = joinedRooms.filter(r => r !== room);

  // Remove peer mapping
  clearMpPeer(room);

  // Remove stored messages
  if (roomMessages[room]) {
    delete roomMessages[room];
  }

  // If user was viewing this MP, fallback to a safe room
  if (currentRoom === room) {
    if (joinedRooms.length > 0) {
      currentRoom = joinedRooms[0];
    } else {
      currentRoom = null;
    }
  }
}

// ----------------------------------------
// Setters
// ----------------------------------------
export function setMyPseudo(v) { myPseudo = v; }
export function setMyLang(v) { myLang = v; }

export function setCurrentRoom(r) { currentRoom = r; }

export function setJoinedRooms(arr) { joinedRooms = arr; }
export function addJoinedRoom(r) {
  if (!joinedRooms.includes(r)) joinedRooms.push(r);
}

export function setChannelData(v) { channelData = v; }
export function setRoomCounts(v) { roomCounts = v; }

// ----------------------------------------
// Couleur utilisateur (assignée par le serveur)
// ----------------------------------------
window.myUserColor = null;

// ----------------------------------------
// Helpers
// ----------------------------------------
export function ensureRoomArray(room) {
  if (!roomMessages[room]) {
    roomMessages[room] = [];
  }
  return roomMessages[room];
}
