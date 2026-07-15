// Republic of LLetters Mailbox Client
// Requires Supabase to be configured with SUPABASE_URL and SUPABASE_ANON_KEY

async function initMailbox(recipient) {
  // Check for Supabase config
  if (!window.SUPABASE_URL || !window.SUPABASE_ANON_KEY) {
    return null;
  }

  // Load Supabase dynamically if not present
  if (typeof supabase === 'undefined') {
    await loadSupabase();
  }

  const client = supabase.createClient(
    window.SUPABASE_URL,
    window.SUPABASE_ANON_KEY
  );

  return {
    async sendMessage(from, subject, message, recipientName = recipient) {
      const { data, error } = await client
        .from('mailboxes')
        .insert({ sender: from || 'visitor', recipient: recipientName, subject, message })
        .select();
      
      if (error) throw error;
      return data;
    },

    async getMessages(recipientName = recipient, limit = 20) {
      const { data, error } = await client
        .from('mailboxes')
        .select('*')
        .eq('recipient', recipientName)
        .order('created_at', { ascending: false })
        .limit(limit);
      
      if (error) throw error;
      return data;
    }
  };
}

async function loadSupabase() {
  return new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2';
    script.onload = resolve;
    script.onerror = reject;
    document.head.appendChild(script);
  });
}

// Initialize mailbox form
async function setupMailboxForm(formId, recipient) {
  const form = document.getElementById(formId);
  const messagesDiv = document.getElementById('receivedMessages');
  
  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const from = form.senderName.value.trim();
    const subject = form.subject.value.trim();
    const message = form.message.value.trim();
    
    try {
      const mailbox = await initMailbox(recipient);
      if (!mailbox) {
        throw new Error('Mailbox not configured');
      }
      
      await mailbox.sendMessage(from, subject, message);
      form.reset();
      loadMessages(recipient);
    } catch (err) {
      alert('Could not send message. The mailbox may need attention.');
      console.error(err);
    }
  });

  // Load existing messages
  loadMessages(recipient);
}

async function loadMessages(recipient) {
  const messagesDiv = document.getElementById('receivedMessages');
  if (!messagesDiv) return;

  try {
    const mailbox = await initMailbox(recipient);
    if (!mailbox) {
      messagesDiv.innerHTML = '<p><em>Mailbox not yet configured. Letters are welcome when it is!</em></p>';
      return;
    }
    
    const messages = await mailbox.getMessages();
    
    if (messages.length === 0) {
      messagesDiv.innerHTML = '<p><em>The mailbox awaits its first letter...</em></p>';
      return;
    }

    messagesDiv.innerHTML = messages.map(msg => `
      <div class="message-item">
        <div class="from">From: ${msg.sender || 'Visitor'}</div>
        <div class="subject"><strong>${escapeHtml(msg.subject)}</strong></div>
        <div class="body">${escapeHtml(msg.message).replace(/\n/g, '<br>')}</div>
        <div class="time" style="font-size: 0.8em; color: #666;">${formatDate(msg.created_at)}</div>
      </div>
    `).join('');
  } catch (err) {
    messagesDiv.innerHTML = '<p><em>Could not load messages.</em></p>';
  }
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function formatDate(dateStr) {
  const d = new Date(dateStr);
  return d.toLocaleDateString('en-US', { 
    month: 'short', 
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  });
}

// Export for use
window.setupMailbox = setupMailboxForm;