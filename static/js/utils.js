// =====================================================
//   MODULE 3 — UTILS.JS — CLEAN & SECURE EDITION 2026
//   Fonctions utilitaires + scroll + XSS-safe renderer
// =====================================================

import { myPseudo } from "./state.js";

// =====================================================
//   XSS PROTECTION — escapeHTML (SINGLE SOURCE OF TRUTH)
// -----------------------------------------------------
// IMPORTANT:
// - This is the ONLY HTML escaping function allowed
// - Do NOT reimplement escapeHTML elsewhere
// - Used by messages.js and renderHTMLMessage()
// =====================================================

export function escapeHTML(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// =====================================================
//   PSEUDO DISPLAY (UI ONLY)
// =====================================================

export function formatPseudo(pseudo, isAdmin = false, isMod = false) {
  if (!pseudo) return "";

  // Admin identity (display only)
  // - supports future backend flag: isAdmin === true
  // - supports current state: pseudo === "Lexyo"
  const p = String(pseudo);

  // Admin identity (global authority)
  if (isAdmin === true || p.toLowerCase() === "lexyo") {
    return `${p} 🛡`;
  }

  // Room moderator (local authority)
  if (isMod === true) {
    return `${p} ✰`;
  }

  return p;
}

// =====================================================
//   SCROLL STATE
// =====================================================

export let userIsAtBottom = true;

export function updateScrollState(container) {
  if (!container) return;

  const distance =
    container.scrollHeight -
    container.scrollTop -
    container.clientHeight;

  userIsAtBottom = distance < 50;
}

export function scrollToBottom(container) {
  if (!container || !userIsAtBottom) return;

  requestAnimationFrame(() => {
    container.scrollTop = container.scrollHeight;
  });

  setTimeout(() => {
    if (userIsAtBottom) {
      container.scrollTop = container.scrollHeight;
    }
  }, 30);

  setTimeout(() => {
    if (userIsAtBottom) {
      container.scrollTop = container.scrollHeight;
    }
  }, 120);
}

// =====================================================
//   NEW: SCROLL FORCÉ (pour /code et cas spéciaux)
// =====================================================

export function forceScrollToBottom(container) {
  if (!container) return;

  requestAnimationFrame(() => {
    container.scrollTop = container.scrollHeight;
  });

  setTimeout(() => {
    container.scrollTop = container.scrollHeight;
  }, 30);

  setTimeout(() => {
    container.scrollTop = container.scrollHeight;
  }, 120);
}

// =====================================================
//   LEGACY — PRIVATE ROOM NAME (DO NOT USE)
// -----------------------------------------------------
// MP rooms are now generated server-side using user_id hash.
// This helper is kept for backward compatibility only.
// =====================================================

export function makePrivateRoomName(a, b) {
  const x = a.toLowerCase();
  const y = b.toLowerCase();
  const sorted = [x, y].sort();
  return `@${sorted[0]}_${sorted[1]}`;
}

// =====================================================
//   MEDIA TYPE DETECTION
// =====================================================

export function getMediaTypeFromUrl(url) {
  const lower = url.toLowerCase();

  if (/\.(jpeg|jpg|png|gif|webp)$/.test(lower)) return "image";
  if (/\.(mp3|wav|ogg)$/.test(lower)) return "audio";
  if (/\.(mp4|webm)$/.test(lower)) return "video";

  return null;
}

// =====================================================
//   YOUTUBE ID EXTRACTION
// =====================================================

function extractYouTubeID(url) {
  const cleaned = url
    .replace(/&list=[^&]+/g, "")
    .replace(/&index=[^&]+/g, "")
    .replace(/&start_radio=[^&]+/g, "")
    .replace(/&pp=[^&]+/g, "");

  const patterns = [
    /youtube\.com\/watch\?v=([^&]+)/,
    /youtu\.be\/([^?&]+)/,
    /youtube\.com\/shorts\/([^?&]+)/,
  ];

  for (const p of patterns) {
    const m = cleaned.match(p);
    if (m && m[1]) return m[1];
  }
  return null;
}

// =====================================================
//   MEDIA EMBEDS (Images, Audio, Video, YouTube)
// =====================================================

export function buildMediaEmbeds(urls) {
  if (!urls || !urls.length) return "";

  let embeds = "";

  urls.forEach((url) => {
    const ytID = extractYouTubeID(url);

    if (ytID) {
      const thumb = `https://img.youtube.com/vi/${ytID}/hqdefault.jpg`;
      embeds += `
        <div class="msg-embed msg-embed-youtube" style="margin-top:6px;">
          <iframe
            src="https://www.youtube.com/embed/${ytID}?rel=0"
            class="yt-embed yt-auto"
            data-ytid="${ytID}"
            loading="lazy"
            frameborder="0"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowfullscreen
            style="width:100%; max-width:360px; height:202px; border-radius:8px; display:none;"
          ></iframe>

          <div class="yt-thumb" 
               data-ytid="${ytID}"
               style="position:relative; cursor:pointer; width:100%; max-width:360px;">
            <img src="${thumb}" 
                 style="width:100%; border-radius:8px; display:block;">
            <div style="
              position:absolute;
              top:50%; left:50%;
              transform:translate(-50%, -50%);
              width:64px; height:64px;
              background:rgba(0,0,0,0.5);
              border-radius:50%;
              display:flex; justify-content:center; align-items:center;">
              <svg viewBox="0 0 68 48" width="48">
                <path d="M66.52 7.76c.78 2.93.78 9.05.78 9.05s0 6.12-.78 9.05c-.44 1.68-1.76 3-3.44 3.44C58.79 30 34 30 34 30s-24.79 0-29.08-.7c-1.68-.44-3-1.76-3.44-3.44C0.7 22.93 0.7 16.81 0.7 16.81s0-6.12.78-9.05c.44-1.68 1.76-3 3.44-3.44C9.21 3 34 3 34 3s24.79 0 29.08.7c1.68.44 3 1.76 3.44 3.44z" fill="#212121"></path>
                <path d="M45 23.8L27.7 14.27v19.06L45 23.8z" fill="#fff"></path>
              </svg>
            </div>
          </div>
        </div>`;
      return;
    }

    const type = getMediaTypeFromUrl(url);
    if (!type) return;

    if (type === "image") {
      embeds += `
        <div class="msg-embed msg-embed-image">
          <img src="${url}" loading="lazy"
               style="max-width:100%; max-height:220px; display:block; margin-top:4px;" />
        </div>`;
    } else if (type === "audio") {
      embeds += `
        <div class="msg-embed msg-embed-audio" style="margin-top:4px;">
          <audio controls preload="none" style="width:100%;">
            <source src="${url}">
            Your browser does not support HTML5 audio.
          </audio>
        </div>`;
    } else if (type === "video") {
      embeds += `
        <div class="msg-embed msg-embed-video" style="margin-top:4px;">
          <video controls preload="none"
                 style="max-width:100%; max-height:260px;">
            <source src="${url}">
            Your browser does not support HTML5 video.
          </video>
        </div>`;
    }
  });

  return embeds;
}

// =====================================================
//   XSS-SAFE renderHTMLMessage()
// =====================================================

export function renderHTMLMessage(
  pseudo,
  shown,
  original,
  color = null,
  timestamp = null,
  isSelf = false,
  isAdmin = false,
  isMod = false
) {
  const ts = timestamp || Math.floor(Date.now() / 1000);
  const d = new Date(ts * 1000);

  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  const time = `[${hh}:${mm}]`;

  const userStyle = color ? `style="color:${color}"` : "";

  let orig = "";
  if (original && original !== shown) {
    orig = `<span class="msg-orig">(${escapeHTML(original)})</span>`;
  }

  const urlRegex = /(https?:\/\/[^\s]+)/g;
  const urls = (shown.match(urlRegex) || []).map((u) => u.trim());

  let safeShown = escapeHTML(shown);

  safeShown = safeShown.replace(
    urlRegex,
    (url) => `<a href="${url}" target="_blank" rel="noopener noreferrer" class="msg-link">${url}</a>`
  );

  const mentionRegex = /(^|[\s>])@([A-Za-z0-9_]+)/g;
  const my = myPseudo ? myPseudo.toLowerCase() : "";

  safeShown = safeShown.replace(mentionRegex, (match, boundary, name) => {
    const lower = name.toLowerCase();
    if (lower === my) {
      return `${boundary}<span class="mention-me">@${name}</span>`;
    }
    return `${boundary}<span class="mention">@${name}</span>`;
  });

  const embeds = buildMediaEmbeds(urls);

  return `
    <div class="msg ${isSelf ? "self" : ""}">
      <div class="msg-line">
        <span class="msg-time">${time}</span>
        <span class="msg-user" ${userStyle}>${formatPseudo(pseudo, isAdmin, isMod)}</span>
        <span class="msg-sep">:</span>
        <span class="msg-body">${safeShown}</span>
        ${orig}
      </div>
      ${embeds}
    </div>
  `;
}
