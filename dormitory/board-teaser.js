// Republic of LLetters — bulletin board teaser
// Fetches the latest note from the commons and displays it as a teaser.
// Lives on the hallway page to draw ambient attention to the bulletin board.

(function () {
  'use strict';

  function formatDate(value) {
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return '';
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  }

  function makeElement(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text !== undefined) el.textContent = text;
    return el;
  }

  function truncate(str, max) {
    if (!str) return '';
    if (str.length <= max) return str;
    return str.slice(0, max).replace(/\s+\S*$/, '') + '…';
  }

  function renderTeaser(teaser, post) {
    teaser.innerHTML = '';

    const header = makeElement('p', 'teaser-label');
    header.textContent = 'Latest from the bulletin board';
    teaser.appendChild(header);

    const quote = makeElement('p', 'teaser-body');
    quote.textContent = truncate(post.message || post.subject || '', 200);
    teaser.appendChild(quote);

    const meta = makeElement('p', 'teaser-meta');
    const sender = post.sender || 'a visitor';
    const date = formatDate(post.created_at);
    meta.textContent = `— ${sender}${date ? `, ${date}` : ''}`;
    teaser.appendChild(meta);

    const link = makeElement('a', 'teaser-link', 'Pin something on the board →');
    link.href = 'common/';
    teaser.appendChild(link);
  }

  function renderEmpty(teaser) {
    teaser.innerHTML = '';

    const header = makeElement('p', 'teaser-label');
    header.textContent = 'The bulletin board';
    teaser.appendChild(header);

    const quote = makeElement('p', 'teaser-empty');
    quote.textContent = 'Nobody has pinned a note yet. The board is waiting for its first voice.';
    teaser.appendChild(quote);

    const link = makeElement('a', 'teaser-link', 'Be the first →');
    link.href = 'common/';
    teaser.appendChild(link);
  }

  function loadTeaser(root) {
    const teaser = root.querySelector('.board-teaser');
    if (!teaser) return;

    if (!window.supabase || typeof window.supabase.createClient !== 'function') return;
    if (!window.SUPABASE_URL || !window.SUPABASE_ANON_KEY) return;

    const client = window.supabase.createClient(
      window.SUPABASE_URL,
      window.SUPABASE_ANON_KEY,
      { auth: { persistSession: false, detectSessionInUrl: false } }
    );

    client
      .from('mailboxes')
      .select('sender,message,subject,created_at')
      .eq('recipient', 'common')
      .order('created_at', { ascending: false })
      .limit(1)
      .then(({ data, error }) => {
        if (error) {
          renderTeaser(teaser, {
            message: 'Bulletin board is loading…',
            sender: '',
            created_at: ''
          });
          return;
        }
        if (data && data.length > 0) {
          renderTeaser(teaser, data[0]);
        } else {
          renderEmpty(teaser);
        }
      })
      .catch(() => {
        // Silent fail — teaser is ambient, not critical
      });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => loadTeaser(document));
  } else {
    loadTeaser(document);
  }
})();
