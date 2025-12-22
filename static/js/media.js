// =====================================================
//   MEDIA.JS — LEXYO CLEAN PRO EDITION (2026)
//   Gestion fiable du scroll avec images / vidéos
//   Compatible avec utils.js (userIsAtBottom)
// =====================================================

import { scrollToBottom, updateScrollState, userIsAtBottom } from "./utils.js";

// =====================================================
//   Force un scroll *SEULEMENT SI* l'utilisateur est en bas
// =====================================================
export function initMediaLoadFix(container) {
  if (!container) return;

  const images = container.querySelectorAll("img");
  const videos = container.querySelectorAll("video");

  // ---------- IMAGES ----------
  images.forEach((img) => {
    // Déjà chargée → scroll uniquement si userIsAtBottom
    if (img.complete) {
      if (userIsAtBottom) scrollToBottom(container);
      return;
    }

    img.addEventListener("load", () => {
      if (userIsAtBottom) scrollToBottom(container);
    });

    img.addEventListener("error", () => {
      if (userIsAtBottom) scrollToBottom(container);
    });
  });

  // ---------- VIDEOS ----------
  videos.forEach((video) => {
    // Prête → scroll uniquement si userIsAtBottom
    if (video.readyState >= 2) {
      if (userIsAtBottom) scrollToBottom(container);
      return;
    }

    video.addEventListener("loadeddata", () => {
      if (userIsAtBottom) scrollToBottom(container);
    });

    video.addEventListener("loadedmetadata", () => {
      if (userIsAtBottom) scrollToBottom(container);
    });
  });
}

// =====================================================
//   MutationObserver : détecte messages / embeds ajoutés
// =====================================================
export function createMediaObserver(messagesEl) {
  const observer = new MutationObserver((mutations) => {
    let needInit = false;

    mutations.forEach((mutation) => {
      mutation.addedNodes.forEach((node) => {
        if (node.nodeType === 1) {
          // On rescan tout le conteneur pour images/vidéos
          needInit = true;
        }
      });
    });

    if (needInit) {
      initMediaLoadFix(messagesEl);

      // Scroll uniquement si userIsAtBottom = true
      if (userIsAtBottom) {
        scrollToBottom(messagesEl);
      }

      // Mise à jour de l'état du scroll après les mutations
      updateScrollState(messagesEl);
    }
  });

  observer.observe(messagesEl, {
    childList: true,
    subtree: true,
  });

  return observer;
}
