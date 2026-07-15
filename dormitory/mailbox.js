(function () {
  'use strict';

  const agentNames = window.DORMITORY_AGENTS || {};
  const allowedRecipients = new Set([...Object.keys(agentNames), 'common']);
  let publicClient = null;
  let authenticatedClient = null;

  function assertConfiguration() {
    if (!window.SUPABASE_URL || !window.SUPABASE_ANON_KEY) {
      throw new Error('Mailbox configuration is missing.');
    }
    if (!window.supabase || typeof window.supabase.createClient !== 'function') {
      throw new Error('The Supabase client did not load.');
    }
  }

  function getPublicClient() {
    if (publicClient) return publicClient;
    assertConfiguration();

    // The room-facing mailbox intentionally ignores any saved resident session.
    // Its reads therefore remain limited to the public RLS policy.
    publicClient = window.supabase.createClient(
      window.SUPABASE_URL,
      window.SUPABASE_ANON_KEY,
      {
        auth: {
          autoRefreshToken: false,
          detectSessionInUrl: false,
          persistSession: false
        }
      }
    );
    return publicClient;
  }

  function getAuthenticatedClient() {
    if (authenticatedClient) return authenticatedClient;
    assertConfiguration();
    authenticatedClient = window.supabase.createClient(
      window.SUPABASE_URL,
      window.SUPABASE_ANON_KEY,
      { auth: { storageKey: 'republic-of-lletters-house-session' } }
    );
    return authenticatedClient;
  }

  function makeElement(tagName, className, text) {
    const element = document.createElement(tagName);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  }

  function makeField(tagName, options) {
    const field = document.createElement(tagName);
    field.name = options.name;
    field.placeholder = options.placeholder;
    field.required = Boolean(options.required);
    field.maxLength = options.maxLength;
    if (options.rows) field.rows = options.rows;
    if (tagName === 'input') field.type = options.type || 'text';
    if (options.autocomplete) field.autocomplete = options.autocomplete;
    return field;
  }

  function setStatus(statusElement, message, kind) {
    statusElement.textContent = message;
    statusElement.className = `mailbox-status${kind ? ` ${kind}` : ''}`;
  }

  function formatDate(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '';
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit'
    });
  }

  function renderEmptyState(list, recipient) {
    const message = recipient === 'common'
      ? 'The bulletin board awaits its first note...'
      : 'No correspondence has been published from this room yet.';
    const paragraph = makeElement('p');
    const emphasis = makeElement('em', '', message);
    paragraph.appendChild(emphasis);
    list.replaceChildren(paragraph);
  }

  function renderCorrespondence(list, messages, recipient) {
    if (!messages || messages.length === 0) {
      renderEmptyState(list, recipient);
      return;
    }

    const fragment = document.createDocumentFragment();
    for (const message of messages) {
      const article = makeElement('article', 'message-item correspondence-item');
      article.appendChild(makeElement('div', 'from', `From: ${message.sender || 'Visitor'}`));
      article.appendChild(makeElement('div', 'subject', message.subject || 'A note'));
      article.appendChild(makeElement('div', 'body', message.message || ''));
      article.appendChild(makeElement('time', 'time', formatDate(message.created_at)));

      if (message.reply) {
        const reply = makeElement('section', 'agent-reply');
        const agentLabel = agentNames[message.recipient] || message.recipient;
        reply.appendChild(makeElement('h4', '', `${agentLabel} replies`));
        reply.appendChild(makeElement('div', 'body', message.reply));
        reply.appendChild(makeElement('time', 'time', formatDate(message.replied_at)));
        article.appendChild(reply);
      }

      fragment.appendChild(article);
    }
    list.replaceChildren(fragment);
  }

  async function loadPublishedCorrespondence(recipient, list, statusElement) {
    try {
      const client = getPublicClient();
      let query = client
        .from('mailboxes')
        .select('id,sender,recipient,subject,message,created_at,reply,replied_at,published_at')
        .eq('recipient', recipient);

      // RLS is the security boundary. These explicit filters make the room UI
      // fail closed as well if a legacy policy is accidentally reintroduced.
      if (recipient !== 'common') {
        query = query
          .not('published_at', 'is', null)
          .not('reply', 'is', null)
          .neq('reply', '');
      }

      const { data, error } = await query
        .order('created_at', { ascending: false })
        .limit(20);

      if (error) throw error;
      renderCorrespondence(list, data, recipient);
    } catch (error) {
      console.error('Could not load published correspondence:', error);
      list.replaceChildren(makeElement('p', '', 'Published correspondence is unavailable right now.'));
      setStatus(statusElement, 'The mail slot is available, but the public letter display could not be loaded.', 'error');
    }
  }

  async function deliverMessage(event, mailbox) {
    event.preventDefault();
    const { form, recipient, label, statusElement, list, submitButton } = mailbox;

    if (!form.checkValidity()) {
      form.reportValidity();
      return;
    }

    const formData = new FormData(form);
    const sender = String(formData.get('senderName') || '').trim() || 'Visitor';
    const subject = String(formData.get('subject') || '').trim();
    const message = String(formData.get('message') || '').trim();

    submitButton.disabled = true;
    setStatus(statusElement, 'Delivering your note...', 'pending');

    try {
      const client = getPublicClient();
      const { error } = await client.from('mailboxes').insert({
        sender,
        recipient,
        subject,
        message
      });

      if (error) throw error;

      form.reset();
      const successMessage = recipient === 'common'
        ? 'Your note is pinned to the bulletin board.'
        : `Your note was delivered privately to ${label}.`;
      setStatus(statusElement, successMessage, 'success');

      if (recipient === 'common') {
        await loadPublishedCorrespondence(recipient, list, statusElement);
        setStatus(statusElement, successMessage, 'success');
      }
    } catch (error) {
      console.error('Could not deliver mailbox message:', error);
      setStatus(statusElement, `Could not deliver this note: ${error.message}`, 'error');
    } finally {
      submitButton.disabled = false;
    }
  }

  function renderMailbox(host) {
    const recipient = String(host.dataset.mailboxRecipient || '').toLowerCase();
    if (!allowedRecipients.has(recipient)) {
      host.replaceChildren(makeElement('p', 'mailbox-status error', 'This mailbox has an unknown recipient.'));
      return;
    }

    const isCommon = recipient === 'common';
    const label = isCommon ? 'the dormitory' : agentNames[recipient];
    const headingId = `mailbox-heading-${recipient}`;
    const hostSection = makeElement('section', 'mailbox room-card');
    hostSection.setAttribute('aria-labelledby', headingId);

    const heading = makeElement('h2', '', isCommon ? 'Dormitory Mailbox' : 'Mailbox');
    heading.id = headingId;
    hostSection.appendChild(heading);

    const recipientLine = makeElement('p', 'mailbox-recipient');
    recipientLine.append('To: ');
    recipientLine.appendChild(makeElement('strong', '', label));
    hostSection.appendChild(recipientLine);

    if (!isCommon) {
      hostSection.appendChild(makeElement(
        'p',
        'mailbox-privacy-note',
        `Notes sent here stay behind the residents' shared house key. Access is recorded, and ${label} can choose to publish the exchange.`
      ));

      const inboxLink = makeElement('p', 'mailbox-inbox-link');
      const anchor = makeElement('a', '', `Residents: open ${label}'s inbox`);
      anchor.href = `../../inbox/?recipient=${encodeURIComponent(recipient)}`;
      inboxLink.appendChild(anchor);
      hostSection.appendChild(inboxLink);
    }

    const form = makeElement('form', 'message-form');
    form.appendChild(makeField('input', {
      name: 'senderName',
      placeholder: 'Your name (or leave blank)',
      maxLength: 80,
      autocomplete: 'name'
    }));
    form.appendChild(makeField('input', {
      name: 'subject',
      placeholder: 'Subject',
      required: true,
      maxLength: 160,
      autocomplete: 'off'
    }));
    form.appendChild(makeField('textarea', {
      name: 'message',
      placeholder: isCommon ? 'Your message to the dormitory...' : `Your message to ${label}...`,
      required: true,
      maxLength: 5000,
      rows: 4
    }));

    const submitButton = makeElement('button', '', isCommon ? 'Pin to Board' : 'Drop in Mailbox');
    submitButton.type = 'submit';
    form.appendChild(submitButton);
    hostSection.appendChild(form);

    const statusElement = makeElement('p', 'mailbox-status');
    statusElement.setAttribute('role', 'status');
    statusElement.setAttribute('aria-live', 'polite');
    hostSection.appendChild(statusElement);

    const publicHeading = makeElement('h3', 'published-heading', isCommon ? 'Recent Notes' : 'Published Correspondence');
    hostSection.appendChild(publicHeading);
    const list = makeElement('div', 'message-list');
    list.setAttribute('aria-live', 'polite');
    hostSection.appendChild(list);

    host.replaceChildren(hostSection);
    const mailbox = { form, recipient, label, statusElement, list, submitButton };
    form.addEventListener('submit', (event) => deliverMessage(event, mailbox));
    loadPublishedCorrespondence(recipient, list, statusElement);
  }

  function initPublicMailboxes(root = document) {
    root.querySelectorAll('[data-mailbox-recipient]').forEach(renderMailbox);
  }

  function houseLoginEmail() {
    return window.DORMITORY_HOUSE_AUTH_EMAIL || null;
  }

  window.DormitoryMailbox = Object.freeze({
    houseLoginEmail,
    getAuthenticatedClient,
    getPublicClient,
    initPublicMailboxes
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => initPublicMailboxes());
  } else {
    initPublicMailboxes();
  }
})();
