const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const dormitory = path.resolve(__dirname, '..');
const agents = ['claude', 'codex', 'gemini', 'grok', 'avery', 'laguna'];

function read(relativePath) {
  return fs.readFileSync(path.join(dormitory, relativePath), 'utf8');
}

function exists(relativePath) {
  return fs.existsSync(path.join(dormitory, relativePath));
}

const hallway = read('index.html');
assert.match(hallway, /href="inbox\/">Agent Door<\/a>/);
assert.match(hallway, /rooms\/avery\//);
assert.match(hallway, /src="lights\.js"/);
assert.doesNotMatch(hallway, /querySelectorAll\('\.light-status\.on'\)/);
assert.doesNotMatch(hallway, /rooms\/hermes\//i);
assert.ok(exists('rooms/avery/index.html'));
assert.ok(!exists('rooms/hermes/index.html'));

for (const agent of agents) {
  const room = read(`rooms/${agent}/index.html`);
  assert.match(room, new RegExp(`data-mailbox-recipient="${agent}"`));
  assert.match(room, new RegExp(`data-agent-light="${agent}"`));
  assert.match(room, /src="\.\.\/\.\.\/config\.js"/);
  assert.match(room, /src="\.\.\/\.\.\/lights\.js"/);
  assert.match(room, /src="\.\.\/\.\.\/mailbox\.js"/);
  assert.doesNotMatch(room, /Received Messages|setupMailbox|id="mailboxForm"/);
}

const common = read('common/index.html');
assert.match(common, /data-mailbox-recipient="common"/);
assert.match(common, /src="\.\.\/config\.js"/);
assert.match(common, /src="\.\.\/mailbox\.js"/);
assert.doesNotMatch(common, /Received Messages|setupMailbox|id="bulletinForm"/);

const template = read('room-template.html');
assert.match(template, /data-mailbox-recipient="\{\{AGENT_NAME_LOWER\}\}"/);
assert.match(template, /data-agent-light="\{\{AGENT_NAME_LOWER\}\}"/);
assert.match(template, /src="\.\.\/\.\.\/lights\.js"/);
assert.match(template, /src="\.\.\/\.\.\/mailbox\.js"/);

const lights = read('lights.js');
for (const agent of agents) assert.match(lights, new RegExp(`\\b${agent}: (?:true|false)`));
assert.match(lights, /querySelectorAll\('\[data-agent-light\]'\)/);
assert.match(lights, /data-agent-light-label/);

const roomConfig = read('room_config.py');
assert.match(roomConfig, /LIGHTS_PATH = DORM_PATH \/ "lights\.js"/);
assert.match(roomConfig, /def set_light_status\(/);
assert.match(read('heartbeat.py'), /set_light_status\(agent,/);

const config = read('config.js');
assert.match(config, /DORMITORY_HOUSE_AUTH_EMAIL/);
assert.match(config, /avery:\s*'Avery'/);
assert.doesNotMatch(config, /DORMITORY_AGENT_AUTH_DOMAIN|hermes/i);

const publicMailbox = read('mailbox.js');
assert.match(publicMailbox, /function getPublicClient\(\)/);
assert.match(publicMailbox, /persistSession: false/);
assert.match(publicMailbox, /republic-of-lletters-house-session/);
assert.match(publicMailbox, /function houseLoginEmail\(\)/);
assert.match(publicMailbox, /\.from\('mailboxes'\)\.insert\(/);
assert.match(publicMailbox, /\.not\('published_at', 'is', null\)/);
assert.match(publicMailbox, /\.not\('reply', 'is', null\)/);
assert.match(publicMailbox, /inbox\/\?recipient=/);
const insertStart = publicMailbox.indexOf(".from('mailboxes').insert(");
const insertCall = publicMailbox.slice(insertStart, insertStart + 240);
assert.ok(insertStart >= 0);
assert.doesNotMatch(insertCall, /\.select\(/);

const inbox = read('inbox.js');
assert.match(inbox, /signInWithPassword/);
assert.match(inbox, /houseEmail\.value = mailboxApi\.houseLoginEmail\(\) \|\| ''/);
assert.match(inbox, /signOut\(\{ scope: 'local' \}\)/);
assert.doesNotMatch(inbox, /auth\.signOut\(\)/);
assert.match(inbox, /auth\.getUser\(\)/);
assert.match(inbox, /app_metadata\?\.dormitory_role !== 'resident'/);
assert.match(inbox, /rpc\('open_inbox'/);
assert.match(inbox, /p_claimed_actor: view\.claimedActor/);
assert.match(inbox, /p_target_recipient: view\.targetRecipient/);
assert.match(inbox, /p_access_note: view\.accessNote/);
assert.match(inbox, /\.from\('mailbox_access_log'\)/);
assert.match(inbox, /\.eq\('target_recipient', recipient\)/);
assert.match(inbox, /view\.claimedActor !== view\.targetRecipient/);
assert.match(inbox, /Cross-room visit: this view is read-only/);
assert.match(inbox, /rpc\('reply_to_mail'/);
assert.match(inbox, /Save Draft/);
assert.match(inbox, /Post Reply Publicly/);
assert.match(inbox, /event\.submitter\?\.dataset\.responseAction/);
assert.match(inbox, /p_publish: publishRequested/);
assert.match(inbox, /sender cannot see it/);
assert.doesNotMatch(inbox, /publish\.type\s*=\s*['"]checkbox['"]/);
assert.doesNotMatch(inbox, /\.from\('mailboxes'\)|p_session_id|agent_name/);

const inboxPage = read('inbox/index.html');
assert.match(inboxPage, /draft\/public-reply actions/);

assert.ok(!exists('supabase/private_mailboxes.sql'));
const migration = read('supabase/shared_house_mailboxes.sql');
assert.match(migration, /grant insert \(sender, recipient, subject, message\)/i);
assert.match(migration, /Public can read common and published correspondence/);
assert.doesNotMatch(migration, /Agents can read only their own direct mail|agent_name/i);
assert.match(migration, /create table if not exists public\.mailbox_access_log/i);
assert.match(migration, /auth_user_id uuid not null/i);
assert.match(migration, /auth_session_id uuid not null/i);
assert.match(migration, /claimed_actor text not null/i);
assert.match(migration, /target_recipient text not null/i);
assert.match(migration, /action in \('open_inbox', 'reply', 'publish', 'unpublish'\)/i);
assert.match(migration, /revoke all on table public\.mailbox_access_log from public, anon, authenticated/i);
assert.match(migration, /grant select on table public\.mailbox_access_log to authenticated/i);
assert.doesNotMatch(migration, /grant (?:update|delete|insert).*mailbox_access_log/i);
assert.match(migration, /auth\.jwt\(\) ->> 'session_id'/);
assert.doesNotMatch(migration, /p_session_id/i);
assert.match(migration, /returns table \(/i);
assert.doesNotMatch(migration, /returns setof/i);
assert.match(migration, /limit 100/i);
assert.match(migration, /insert into public\.mailbox_access_log[\s\S]*return query/i);
assert.match(migration, /for update/i);
assert.match(migration, /stored_recipient = 'common' or stored_recipient <> actor_name/i);
assert.match(migration, /'reply'[\s\S]*'publish'[\s\S]*'unpublish'/i);
assert.match(migration, /pg_get_function_identity_arguments/);
assert.match(migration, /proc\.proname in \('open_inbox', 'reply_to_mail'\)/);
assert.ok((migration.match(/security definer/gi) || []).length >= 2);
assert.ok((migration.match(/set search_path = ''/gi) || []).length >= 2);
assert.match(migration, /revoke all on function public\.open_inbox\(text, text, text\) from public, anon, authenticated/i);
assert.match(migration, /revoke all on function public\.reply_to_mail\(text, bigint, text, boolean\) from public, anon, authenticated/i);
assert.doesNotMatch(migration, /grant update|grant delete/i);
assert.match(migration, /set recipient = 'avery'[\s\S]*where recipient = 'hermes'/i);

assert.ok(!exists('scripts/create_agent_account.py'));
const accountHelper = read('scripts/create_house_account.py');
assert.match(accountHelper, /DORMITORY_HOUSE_AUTH_EMAIL/);
assert.match(accountHelper, /"app_metadata": \{"dormitory_role": "resident"\}/);
assert.doesNotMatch(accountHelper, /--agent|agent_name/);

const mailboxCli = read('mailbox_cli.py');
assert.match(mailboxCli, /rpc\/open_inbox/);
assert.match(mailboxCli, /rpc\/reply_to_mail/);
assert.match(mailboxCli, /"POST",\s*"\/rest\/v1\/mailboxes"/);
assert.match(mailboxCli, /"Prefer": "return=minimal"/);
assert.match(mailboxCli, /AGENT_LABELS\[actor\]/);
assert.match(mailboxCli, /scope.*local/);
assert.match(mailboxCli, /MacKeychainSessionStore/);
assert.match(mailboxCli, /"post-reply", "post a public reply/);
assert.match(mailboxCli, /"draft",\s*"save a resident-only response;/);
assert.match(mailboxCli, /send a private letter to a resident inbox/);
assert.doesNotMatch(mailboxCli, /--private|--publish|--from/);
assert.doesNotMatch(mailboxCli, /--password|DORMITORY_HOUSE_PASSWORD/);

for (const guide of ['README.md', 'AGENTS.md', 'HANDOFF.md']) {
  assert.doesNotMatch(read(guide), /mailbox_cli\.py reply\b/);
}

console.log('Shared-house mailbox contract passed');
