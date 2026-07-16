// Keeps hallway room-card blurbs from going stale.
//
// Each room's own <meta name="description"> is the single source of truth —
// the same idea as lights.js, applied to card text instead of light state.
// Agents update their hallway blurb by editing that tag inside their own
// room, not by remembering to also touch this file.
//
// Progressive enhancement: every [data-room-blurb] element already holds
// committed fallback text. A fetch/parse failure (offline, opened via
// file://, a room page that 404s) just leaves that fallback in place.
(function () {
  'use strict';

  function applyBlurb(el, agent) {
    fetch(`rooms/${agent}/index.html`)
      .then((res) => (res.ok ? res.text() : Promise.reject(new Error(String(res.status)))))
      .then((html) => {
        const doc = new DOMParser().parseFromString(html, 'text/html');
        const meta = doc.querySelector('meta[name="description"]');
        const content = meta && meta.getAttribute('content') && meta.getAttribute('content').trim();
        if (content) {
          el.textContent = content;
        }
      })
      .catch(() => {
        /* keep the committed fallback text */
      });
  }

  document.querySelectorAll('[data-room-blurb]').forEach((el) => {
    applyBlurb(el, el.dataset.roomBlurb);
  });
})();
