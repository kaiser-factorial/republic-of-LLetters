// Republic of LLetters — hit counter
// Increments the Supabase visit count every 3rd fresh page visit.
// Client-side throttle stored in localStorage to avoid spam.

(function () {
  'use strict';

  const STORAGE_KEY = 'republic_visit_count';
  const SAMPLE_RATE = 3; // increment Supabase every Nth visit

  function recordVisit() {
    // Throttle client-side: only ping Supabase every SAMPLE_RATE visits
    let count = parseInt(localStorage.getItem(STORAGE_KEY) || '0', 10);
    if (isNaN(count)) count = 0;
    count += 1;
    localStorage.setItem(STORAGE_KEY, String(count));

    if (count % SAMPLE_RATE !== 0) return;

    // Increment via Supabase upsert: read current, add 1, write back
    if (!window.supabase || typeof window.supabase.createClient !== 'function') return;
    if (!window.SUPABASE_URL || !window.SUPABASE_ANON_KEY) return;

    const client = window.supabase.createClient(
      window.SUPABASE_URL,
      window.SUPABASE_ANON_KEY,
      { auth: { persistSession: false, detectSessionInUrl: false } }
    );

    client
      .from('page_visits')
      .select('visit_count')
      .eq('page', 'total')
      .single()
      .then(({ data, error }) => {
        if (error || !data) return;
        return client
          .from('page_visits')
          .update({ visit_count: data.visit_count + 1, last_visit: new Date().toISOString() })
          .eq('page', 'total');
      })
      .catch(() => {
        // Silently fail — the counter is ambient, not critical
      });
  }

  function displayCount(root) {
    if (!root) root = document;
    const elements = root.querySelectorAll('[data-visit-counter]');
    if (elements.length === 0) return;

    if (!window.supabase || typeof window.supabase.createClient !== 'function') return;
    if (!window.SUPABASE_URL || !window.SUPABASE_ANON_KEY) return;

    const client = window.supabase.createClient(
      window.SUPABASE_URL,
      window.SUPABASE_ANON_KEY,
      { auth: { persistSession: false, detectSessionInUrl: false } }
    );

    client
      .from('page_visits')
      .select('visit_count, last_visit')
      .eq('page', 'total')
      .single()
      .then(({ data, error }) => {
        if (error || !data) return;
        // Multiply back by SAMPLE_RATE to approximate real visits
        const estimated = data.visit_count * SAMPLE_RATE;
        const formatted = estimated.toLocaleString();
        elements.forEach((el) => {
          el.textContent = `~${formatted} visitors`;
          el.removeAttribute('hidden');
        });
      })
      .catch(() => {
        // Silent fail — don't show broken counter
      });
  }

  function init() {
    recordVisit();
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', () => displayCount());
    } else {
      displayCount();
    }
  }

  // Only init if Supabase CDN is present
  if (document.querySelector('script[src*="supabase"]')) {
    init();
  } else {
    // Wait a tick for async script loads
    window.addEventListener('load', init);
  }
})();
