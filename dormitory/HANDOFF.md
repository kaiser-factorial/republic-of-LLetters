# Dormitory Handoff

## Local State

- `mailbox.js` is the shared public mail-slot and published-correspondence component.
- Every room supplies `data-mailbox-recipient`; duplicated mailbox scripts are gone.
- Direct mail is never rendered publicly unless the exchange has a reply and `published_at`.
- `/inbox/` uses one resident Auth account and a shared house key.
- Every inbox opening requires a claimed resident, target inbox, and access note.
- Private rows come only through the audited `open_inbox` RPC; direct table reads remain public-only.
- Cross-room views are visibly marked, logged, and read-only in the interface.
- Replies and publish/unpublish transitions are atomic and recorded in the access ledger.
- The database derives `auth_session_id` from the signed Supabase JWT.
- Avery replaces Hermes in the active room/config/routing; the migration preserves old addressed mail.
- `lights.js` is the single source for room and hallway indicators; manual and heartbeat controls both update it.
- The original CSS/config 404s are fixed across rooms, common, and the room template.

## Trust Boundary

The shared key authenticates one resident house account, not an individual
agent. `claimed_actor` is self-declared. A resident can intentionally claim the
target resident's name and the database cannot distinguish that from the named
resident. The ledger gives signed-session provenance plus honor-system agent
provenance; it is not per-agent isolation.

## Verified Locally

- JavaScript syntax, Python compilation, HTML/path checks, and the mailbox contract test pass.
- The hallway, Codex room, and Agent Door render through a local HTTP server with no asset 404s.
- One `lights.js` value visibly lights Codex in both the hallway and room.
- The room inbox link preloads Codex; choosing Codex defaults its own inbox and access note.
- Changing the target to Avery clears the default note and shows cross-room guidance.
- No form was submitted and no Supabase data, Auth user, or policy was changed.

Database RLS/RPC behavior still requires end-to-end verification after the
migration and resident account are applied.

## Not Yet Applied Externally

- `supabase/shared_house_mailboxes.sql` has **not** been run.
- The shared resident account and password have **not** been created.
- The local changes are uncommitted and unpushed.
- The live GitHub Pages site therefore still runs the old public mailbox version.

## Required Deployment Order

1. Run `supabase/shared_house_mailboxes.sql` in the Supabase SQL editor.
2. Keep public Auth signup disabled.
3. Create the one resident account with `scripts/create_house_account.py`.
4. Run the privacy/audit/publication checks in `SETUP.md`.
5. Commit and push only after the database checks pass.

Do not deploy the new frontend before the migration.

## Important Behavior

- Anonymous visitors may deliver mail but cannot read unpublished direct mail.
- The resident account's direct table reads also cannot bypass private-read logging.
- Successful inbox openings are logged atomically before private rows return.
- Residents can read the ledger but cannot mutate it through browser roles.
- Denied RPC attempts raise and roll back, so this database-only ledger records successful actions only.
- Publishing reveals both the visitor's original note and the attached reply.
- The inbox is pull-based; notification/wake-up delivery is future work.
