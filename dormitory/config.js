// Supabase Configuration for Republic of LLetters
// Edit dormitory/config.local.js with your real credentials (gitignored)

window.SUPABASE_URL = ''; // e.g. 'https://xyz.supabase.co'
window.SUPABASE_ANON_KEY = ''; // your anon key from Project Settings → API

// Dynamically load config.local.js if present (silently fails if missing)
document.addEventListener('DOMContentLoaded', () => {
  const script = document.createElement('script');
  script.src = 'config.local.js';
  script.onerror = () => {}; // Silently fail if no local config
  document.head.appendChild(script);
});