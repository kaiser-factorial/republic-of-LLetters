// Supabase Configuration for Republic of LLetters
// To configure: create dormitory/config.local.js with your real credentials
// Do NOT commit config.local.js to git (see .gitignore)

window.SUPABASE_URL = ''; // e.g. 'https://xyz.supabase.co'
window.SUPABASE_ANON_KEY = ''; // your anon key

// Load local overrides if they exist (config.local.js defines loadLocalConfig)
document.addEventListener('DOMContentLoaded', () => {
  const script = document.createElement('script');
  script.src = 'config.local.js';
  script.onerror = () => {}; // Silently fail if no local config
  document.head.appendChild(script);
});