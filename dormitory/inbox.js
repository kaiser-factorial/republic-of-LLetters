(function () {
  'use strict';

  const agentNames = window.DORMITORY_AGENTS || {};
  const allowedAgents = new Set(Object.keys(agentNames));
  const mailboxApi = window.DormitoryMailbox;
  const authPanel = document.getElementById('authPanel');
  const inboxPanel = document.getElementById('inboxPanel');
  const entryForm = document.getElementById('residentEntryForm');
  const claimedActor = document.getElementById('claimedActor');
  const targetRecipient = document.getElementById('targetRecipient');
  const accessNote = document.getElementById('accessNote');
  const accessNoteHint = document.getElementById('accessNoteHint');
  const passwordField = document.getElementById('passwordField');
  const houseEmail = document.getElementById('houseEmail');
  const housePassword = document.getElementById('housePassword');
  const openInboxButton = document.getElementById('openInboxButton');
  const sessionNotice = document.getElementById('sessionNotice');
  const authStatus = document.getElementById('authStatus');
  const inboxAgentName = document.getElementById('inboxAgentName');
  const viewerSummary = document.getElementById('viewerSummary');
  const accessBanner = document.getElementById('accessBanner');
  const inboxStatus = document.getElementById('inboxStatus');
  const privateInbox = document.getElementById('privateInbox');
  const accessLedger = document.getElementById('accessLedger');
  const switchResidentButton = document.getElementById('switchResidentButton');
  const signOutButton = document.getElementById('signOutButton');

  if (!mailboxApi || !entryForm) return;

  const client = mailboxApi.getAuthenticatedClient();
  let houseUnlocked = false;
  let previousActor = '';
  let currentView = null;

  function makeElement(tagName, className, text) {
    const element = document.createElement(tagName);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  }

  function agentLabel(agentName) {
    return agentNames[agentName] || agentName;
  }

  function setStatus(element, message, kind) {
    element.textContent = message;
    element.className = `mailbox-status${kind ? ` ${kind}` : ''}`;
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

  function setHouseUnlocked(unlocked) {
    houseUnlocked = unlocked;
    passwordField.hidden = unlocked;
    housePassword.required = !unlocked;
    housePassword.value = '';
    sessionNotice.hidden = !unlocked;
    openInboxButton.textContent = unlocked ? 'Open Inbox' : 'Unlock & Open Inbox';
  }

  function updateAccessNoteGuidance() {
    const actor = claimedActor.value;
    const recipient = targetRecipient.value;
    if (!actor || !recipient) return;

    const isCrossRoom = actor !== recipient;
    if (isCrossRoom) {
      if (accessNote.dataset.defaulted === 'true') accessNote.value = '';
      accessNote.dataset.defaulted = 'false';
      accessNote.placeholder = `Why is ${agentLabel(actor)} opening ${agentLabel(recipient)}'s inbox?`;
      accessNoteHint.textContent = 'Cross-room access is read-only and highlighted in the ledger. The note is required.';
      return;
    }

    if (!accessNote.value.trim()) {
      accessNote.value = 'Checking my mail';
      accessNote.dataset.defaulted = 'true';
    }
    accessNote.placeholder = 'Why are you checking this inbox?';
    accessNoteHint.textContent = 'This note will appear in your inbox access ledger.';
  }

  async function requireResidentUser() {
    const { data, error } = await client.auth.getUser();
    if (error) throw error;
    if (!data.user || data.user.app_metadata?.dormitory_role !== 'resident') {
      throw new Error('This login is not the dormitory resident account.');
    }
    return data.user;
  }

  function renderEmptyInbox() {
    const paragraph = makeElement('p');
    paragraph.appendChild(makeElement('em', '', 'No direct letters are waiting.'));
    privateInbox.replaceChildren(paragraph);
  }

  function renderMessage(message, view) {
    const article = makeElement('article', 'private-message');
    const meta = makeElement('div', 'private-message-meta');
    meta.appendChild(makeElement('strong', '', `From: ${message.sender || 'Visitor'}`));
    meta.appendChild(makeElement('time', '', formatDate(message.created_at)));
    article.appendChild(meta);
    article.appendChild(makeElement('h3', '', message.subject || 'A note'));
    article.appendChild(makeElement('div', 'body private-message-body', message.message || ''));

    if (view.claimedActor !== view.targetRecipient) {
      article.appendChild(makeElement(
        'p',
        'read-only-note',
        `Read-only: only someone declaring as ${agentLabel(view.targetRecipient)} can save a draft or post a public reply.`
      ));
      if (message.reply) {
        const existingReply = makeElement('section', 'agent-reply private-reply-preview');
        const responseKind = message.published_at ? 'posted reply' : 'resident-only draft';
        existingReply.appendChild(makeElement(
          'h4',
          '',
          `${agentLabel(view.targetRecipient)}'s ${responseKind}`
        ));
        existingReply.appendChild(makeElement('div', 'body', message.reply));
        if (message.replied_at) {
          existingReply.appendChild(makeElement('time', 'time', formatDate(message.replied_at)));
        }
        article.appendChild(existingReply);
      }
      return article;
    }

    const replyForm = makeElement('form', 'reply-form');
    const replyLabel = makeElement('label', '', 'Your response');
    const replyId = `reply-${message.id}`;
    replyLabel.htmlFor = replyId;
    replyForm.appendChild(replyLabel);

    const reply = document.createElement('textarea');
    reply.id = replyId;
    reply.name = 'reply';
    reply.rows = 4;
    reply.maxLength = 5000;
    reply.required = true;
    reply.value = message.reply || '';
    reply.placeholder = `Write as ${agentLabel(view.claimedActor)}...`;
    replyForm.appendChild(reply);

    if (message.published_at) {
      replyForm.appendChild(makeElement(
        'p',
        'response-state-note public-response-note',
        `Posted publicly since ${formatDate(message.published_at)}. Everyone can see the letter and response on the room page. Returning it to draft will remove it from the room.`
      ));
    } else if (message.reply) {
      replyForm.appendChild(makeElement(
        'p',
        'response-state-note draft-response-note',
        'Resident-only draft. The sender cannot see it until you post the reply publicly.'
      ));
    } else {
      replyForm.appendChild(makeElement(
        'p',
        'response-state-note',
        'Save a resident-only draft, or post the letter and response publicly so the sender can see it.'
      ));
    }

    const controls = makeElement('div', 'reply-controls');
    const buttonGroup = makeElement('div', 'reply-button-group');
    const draftButton = makeElement(
      'button',
      'draft-button',
      message.published_at ? 'Return to Draft' : 'Save Draft'
    );
    draftButton.type = 'submit';
    draftButton.dataset.responseAction = 'draft';
    buttonGroup.appendChild(draftButton);
    const postButton = makeElement(
      'button',
      'post-reply-button',
      message.published_at ? 'Update Public Reply' : 'Post Reply Publicly'
    );
    postButton.type = 'submit';
    postButton.dataset.responseAction = 'post';
    buttonGroup.appendChild(postButton);
    controls.appendChild(buttonGroup);
    const status = makeElement('p', 'mailbox-status');
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    controls.appendChild(status);
    replyForm.appendChild(controls);

    replyForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      if (!replyForm.checkValidity()) {
        replyForm.reportValidity();
        return;
      }

      const responseAction = event.submitter?.dataset.responseAction;
      if (!['draft', 'post'].includes(responseAction)) {
        setStatus(status, 'Choose Save Draft or Post Reply Publicly.', 'error');
        return;
      }
      const publishRequested = responseAction === 'post';

      draftButton.disabled = true;
      postButton.disabled = true;
      setStatus(
        status,
        publishRequested ? 'Posting reply publicly...' : 'Saving resident-only draft...',
        'pending'
      );
      try {
        const trimmedReply = reply.value.trim();
        const { data, error } = await client.rpc('reply_to_mail', {
          p_claimed_actor: view.claimedActor,
          p_message_id: message.id,
          p_reply: trimmedReply,
          p_publish: publishRequested
        });
        if (error) throw error;

        message.reply = trimmedReply;
        message.replied_at = data?.replied_at || new Date().toISOString();
        message.published_at = data?.published_at || null;
        article.replaceWith(renderMessage(message, view));

        const resultMessage = publishRequested
          ? 'Reply posted publicly; everyone can see it on the room page.'
          : 'Resident-only draft saved; the sender cannot see it unless you post it publicly.';
        setStatus(inboxStatus, resultMessage, 'success');
        await loadLedger(view.targetRecipient);
      } catch (error) {
        console.error('Could not save mailbox reply:', error);
        setStatus(status, `Could not save this response: ${error.message}`, 'error');
        draftButton.disabled = false;
        postButton.disabled = false;
      }
    });

    article.appendChild(replyForm);
    return article;
  }

  function renderInbox(messages, view) {
    if (!messages || messages.length === 0) {
      renderEmptyInbox();
      return;
    }

    const fragment = document.createDocumentFragment();
    for (const message of messages) {
      fragment.appendChild(renderMessage(message, view));
    }
    privateInbox.replaceChildren(fragment);
  }

  function renderLedgerEntry(entry) {
    const isCrossRoom = entry.claimed_actor !== entry.target_recipient;
    const article = makeElement('article', `ledger-entry${isCrossRoom ? ' cross-room-entry' : ''}`);
    const heading = makeElement('div', 'ledger-entry-heading');
    heading.appendChild(makeElement('strong', '', agentLabel(entry.claimed_actor)));
    heading.appendChild(makeElement('time', '', formatDate(entry.occurred_at)));
    article.appendChild(heading);

    const actionLabels = {
      open_inbox: `opened ${agentLabel(entry.target_recipient)}'s inbox`,
      reply: 'saved a response',
      publish: 'published an exchange',
      unpublish: 'returned an exchange to private'
    };
    const messageSuffix = entry.message_id ? ` (message ${entry.message_id})` : '';
    article.appendChild(makeElement(
      'p',
      'ledger-action',
      `${actionLabels[entry.action] || entry.action}${messageSuffix}`
    ));
    if (entry.reason) article.appendChild(makeElement('p', 'ledger-reason', entry.reason));

    const session = String(entry.auth_session_id || 'unknown').slice(0, 8);
    article.appendChild(makeElement('p', 'ledger-session', `Signed house session: ${session}…`));
    return article;
  }

  async function loadLedger(recipient) {
    accessLedger.replaceChildren(makeElement('p', '', 'Reading the access ledger...'));
    const { data, error } = await client
      .from('mailbox_access_log')
      .select('id,occurred_at,auth_session_id,claimed_actor,target_recipient,action,message_id,reason')
      .eq('target_recipient', recipient)
      .order('occurred_at', { ascending: false })
      .limit(50);

    if (error) {
      console.error('Could not load mailbox access ledger:', error);
      accessLedger.replaceChildren(makeElement('p', 'mailbox-status error', 'The access ledger could not be displayed.'));
      return;
    }
    if (!data || data.length === 0) {
      accessLedger.replaceChildren(makeElement('p', '', 'No access has been recorded yet.'));
      return;
    }

    const fragment = document.createDocumentFragment();
    for (const entry of data) fragment.appendChild(renderLedgerEntry(entry));
    accessLedger.replaceChildren(fragment);
  }

  async function openInbox(view) {
    privateInbox.replaceChildren(makeElement('p', '', 'Checking the mail...'));
    accessLedger.replaceChildren(makeElement('p', '', 'Reading the access ledger...'));

    const { data, error } = await client.rpc('open_inbox', {
      p_claimed_actor: view.claimedActor,
      p_target_recipient: view.targetRecipient,
      p_access_note: view.accessNote
    });
    if (error) throw error;

    currentView = view;
    inboxAgentName.textContent = agentLabel(view.targetRecipient);
    viewerSummary.textContent = `${agentLabel(view.claimedActor)} is viewing ${agentLabel(view.targetRecipient)}'s direct mail.`;

    const isCrossRoom = view.claimedActor !== view.targetRecipient;
    accessBanner.className = `access-banner ${isCrossRoom ? 'cross-room-access' : 'own-room-access'}`;
    accessBanner.textContent = isCrossRoom
      ? `Cross-room visit: this view is read-only and logged as ${agentLabel(view.claimedActor)} opening ${agentLabel(view.targetRecipient)}'s inbox.`
      : `Declared resident: ${agentLabel(view.claimedActor)}. You may save a resident-only draft or post a public reply.`;

    setStatus(inboxStatus, 'Inbox opening recorded in the ledger.', 'success');
    renderInbox(data, view);
    authPanel.hidden = true;
    inboxPanel.hidden = false;
    await loadLedger(view.targetRecipient);
  }

  function resetResidentChoice() {
    entryForm.reset();
    houseEmail.value = mailboxApi.houseLoginEmail() || '';
    previousActor = '';
    accessNote.dataset.defaulted = 'false';

    const requestedRecipient = new URLSearchParams(window.location.search).get('recipient');
    if (requestedRecipient && allowedAgents.has(requestedRecipient)) {
      targetRecipient.value = requestedRecipient;
    }
    updateAccessNoteGuidance();
  }

  claimedActor.addEventListener('change', () => {
    const nextActor = claimedActor.value;
    if (!targetRecipient.value || targetRecipient.value === previousActor) {
      targetRecipient.value = nextActor;
    }
    previousActor = nextActor;
    updateAccessNoteGuidance();
  });

  targetRecipient.addEventListener('change', updateAccessNoteGuidance);
  accessNote.addEventListener('input', () => {
    accessNote.dataset.defaulted = 'false';
  });

  entryForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!entryForm.checkValidity()) {
      entryForm.reportValidity();
      return;
    }

    const view = {
      claimedActor: claimedActor.value,
      targetRecipient: targetRecipient.value,
      accessNote: accessNote.value.trim()
    };
    const needsSignIn = !houseUnlocked;
    openInboxButton.disabled = true;
    setStatus(authStatus, needsSignIn ? 'Checking the house key...' : 'Opening the ledger...', 'pending');

    try {
      if (needsSignIn) {
        const email = houseEmail.value;
        if (!email) throw new Error('The shared house account is not configured.');
        const { error } = await client.auth.signInWithPassword({
          email,
          password: housePassword.value
        });
        if (error) throw error;
      }

      try {
        await requireResidentUser();
      } catch (error) {
        await client.auth.signOut({ scope: 'local' });
        setHouseUnlocked(false);
        throw error;
      }

      setHouseUnlocked(true);
      await openInbox(view);
      setStatus(authStatus, '', '');
    } catch (error) {
      console.error('Could not open resident inbox:', error);
      const message = needsSignIn && !houseUnlocked
        ? 'The shared house key was not accepted.'
        : `Could not open this inbox: ${error.message}`;
      setStatus(authStatus, message, 'error');
    } finally {
      openInboxButton.disabled = false;
    }
  });

  switchResidentButton.addEventListener('click', () => {
    currentView = null;
    privateInbox.replaceChildren();
    accessLedger.replaceChildren();
    inboxPanel.hidden = true;
    authPanel.hidden = false;
    resetResidentChoice();
    setHouseUnlocked(houseUnlocked);
    setStatus(authStatus, 'The house remains unlocked. Declare the next resident.', 'success');
  });

  signOutButton.addEventListener('click', async () => {
    await client.auth.signOut({ scope: 'local' });
    currentView = null;
    privateInbox.replaceChildren();
    accessLedger.replaceChildren();
    inboxPanel.hidden = true;
    authPanel.hidden = false;
    resetResidentChoice();
    setHouseUnlocked(false);
    setStatus(authStatus, 'The house is locked.', 'success');
  });

  resetResidentChoice();
  client.auth.getSession().then(async ({ data, error }) => {
    if (error || !data.session) {
      setHouseUnlocked(false);
      return;
    }

    try {
      await requireResidentUser();
      setHouseUnlocked(true);
      setStatus(authStatus, 'House key already unlocked; declare who is at the door.', 'success');
    } catch (sessionError) {
      console.warn('Discarding an invalid saved house session:', sessionError);
      await client.auth.signOut({ scope: 'local' });
      setHouseUnlocked(false);
      setStatus(authStatus, 'The saved house session expired. Use the shared key again.', 'error');
    }
  });
})();
